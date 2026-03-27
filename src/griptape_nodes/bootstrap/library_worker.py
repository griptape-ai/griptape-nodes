"""Library worker subprocess for process-isolated node execution.

This script runs in a library's venv Python process. It bootstraps a full
GriptapeNodes engine, loads only the target library, connects to the parent
via WebSocket, and enters an event dispatch loop.

Usage:
    python library_worker.py --library-name NAME --library-file-path PATH --session-id ID
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import sys
from argparse import ArgumentParser
from typing import Any

from griptape_nodes.bootstrap.utils.subprocess_websocket_sender import SubprocessWebSocketSenderMixin
from griptape_nodes.retained_mode.events.app_events import AppInitializationComplete
from griptape_nodes.retained_mode.events.base_events import (
    EventRequest,
    EventResultFailure,
    EventResultSuccess,
    ExecutionEvent,
    ProgressEvent,
    ResultPayload,
    deserialize_event,
)
from griptape_nodes.retained_mode.events.execution_events import (
    ExecuteRemoteNodeRequest,
    ExecuteRemoteNodeResultFailure,
    ExecuteRemoteNodeResultSuccess,
    GriptapeEvent,
)
from griptape_nodes.retained_mode.events.node_events import (
    CreateNodeRequest,
    CreateNodeResultFailure,
    CreateNodeResultSuccess,
)
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

logger = logging.getLogger(__name__)


class LibraryWorker(SubprocessWebSocketSenderMixin):
    """Worker process that hosts a single library's nodes.

    Bootstraps a full GriptapeNodes engine, loads only the target library,
    and processes events from the parent engine.
    """

    def __init__(self, library_name: str, library_file_path: str, session_id: str) -> None:
        self._library_name = library_name
        self._library_file_path = library_file_path
        self._init_websocket_sender(session_id)
        self._nodes: dict[str, Any] = {}

    async def initialize(self) -> None:
        """Bootstrap GriptapeNodes and load the target library."""
        logger.info("Initializing GriptapeNodes engine in worker for library '%s'", self._library_name)

        GriptapeNodes()
        GriptapeNodes.EventManager().initialize_queue()

        await GriptapeNodes.EventManager().abroadcast_app_event(
            AppInitializationComplete(
                libraries_to_register=[self._library_file_path],
            )
        )

        await self._start_websocket_connection()
        logger.info("Worker for library '%s' initialized and connected", self._library_name)

    async def run(self) -> None:
        """Subscribe to events and enter the dispatch loop."""
        if self._ws_client is None:
            msg = "WebSocket client not available."
            raise RuntimeError(msg)

        # Signal to the parent that this worker is ready to accept events
        self.send_event("worker_ready", "{}")

        topic = f"sessions/{self._session_id}/commands"
        await self._ws_client.subscribe(topic)

        logger.info("Worker for library '%s' listening on topic '%s'", self._library_name, topic)

        async for message in self._ws_client.messages:
            try:
                await self._dispatch_event(message)
            except Exception:
                logger.exception("Error dispatching event in worker '%s'", self._library_name)

    async def shutdown(self) -> None:
        """Clean up resources."""
        await self._stop_websocket_connection()

    async def _dispatch_event(self, message: dict[str, Any]) -> None:
        """Deserialize an incoming event and dispatch to the appropriate handler."""
        payload = message.get("payload", message)
        event = deserialize_event(payload)

        if not isinstance(event, EventRequest):
            logger.warning("Worker '%s' received non-request event: %s", self._library_name, type(event).__name__)
            return

        request = event.request
        request_id = event.request_id

        if isinstance(request, CreateNodeRequest):
            self._handle_create_node(request, request_id=request_id)
        elif isinstance(request, ExecuteRemoteNodeRequest):
            await self._handle_execute_remote_node(request, request_id=request_id)
        else:
            # Forward all other requests through the standard event system
            result = await GriptapeNodes.ahandle_request(request)
            self._send_result_event(request, result, request_id=request_id)

    def _handle_create_node(self, request: CreateNodeRequest, *, request_id: str | None = None) -> None:
        """Create a node directly via LibraryRegistry and register it locally."""
        from griptape_nodes.node_library.library_registry import LibraryRegistry

        node_type = request.node_type
        node_name = request.node_name or node_type
        logger.info("Creating node '%s' (type=%s) in worker '%s'", node_name, node_type, self._library_name)

        try:
            node = LibraryRegistry.create_node(
                node_type=node_type,
                name=node_name,
                metadata=request.metadata,
                specific_library_name=self._library_name,
            )
        except Exception as e:
            logger.exception("Failed to create node '%s' in worker '%s'", node_name, self._library_name)
            result = CreateNodeResultFailure(
                result_details=f"Failed to create node '{node_name}': {e}",
            )
            self._send_result_event(request, result, request_id=request_id)
            return

        self._nodes[node_name] = node

        result = CreateNodeResultSuccess(
            node_name=node_name,
            node_type=node_type,
            specific_library_name=self._library_name,
            root_element_tree=node.root_ui_element.to_dict(),
            result_details=f"Node '{node_name}' created successfully.",
        )
        self._send_result_event(request, result, request_id=request_id)

    async def _handle_execute_remote_node(
        self, request: ExecuteRemoteNodeRequest, *, request_id: str | None = None
    ) -> None:
        """Execute a node's aprocess() and return outputs."""
        node_name = request.node_name

        if node_name not in self._nodes:
            logger.warning("Unknown node '%s' in worker '%s'", node_name, self._library_name)
            result = ExecuteRemoteNodeResultFailure(
                node_name=node_name,
                result_details=f"Node '{node_name}' not found in worker '{self._library_name}'.",
            )
            self._send_result_event(request, result, request_id=request_id)
            return

        node = self._nodes[node_name]
        logger.info("Executing node '%s' in worker '%s'", node_name, self._library_name)

        # Hydrate parameter values
        for param_name, value in request.parameter_values.items():
            node.parameter_values[param_name] = value

        # Set entry control parameter if provided
        if request.entry_control_parameter_name:
            param = node.get_parameter_by_name(request.entry_control_parameter_name)
            if param is not None:
                node.set_entry_control_parameter(param)

        node.parameter_output_values.silent_clear()

        # Drain execution events from the worker's EventManager queue
        # and forward them to the parent for UI display
        drain_task = asyncio.create_task(self._drain_event_queue())

        try:
            await node.aprocess()
        except Exception as e:
            logger.exception("Node '%s' execution failed in worker '%s'", node_name, self._library_name)
            result = ExecuteRemoteNodeResultFailure(
                node_name=node_name,
                result_details=f"Node '{node_name}' execution failed: {e}",
                exception=e,
            )
            self._send_result_event(request, result, request_id=request_id)
            return
        finally:
            drain_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await drain_task

        # Get next control output
        next_control = node.get_next_control_output()
        next_control_name = next_control.name if next_control else None

        result = ExecuteRemoteNodeResultSuccess(
            node_name=node_name,
            parameter_output_values=dict(node.parameter_output_values),
            next_control_output_name=next_control_name,
            result_details=f"Node '{node_name}' executed successfully.",
        )
        self._send_result_event(request, result, request_id=request_id)

    def register_node(self, node_name: str, node: Any) -> None:
        """Register a node instance created by the standard event system."""
        self._nodes[node_name] = node

    async def _drain_event_queue(self) -> None:
        """Read events from the worker's EventManager queue and forward to parent.

        Runs as a background task during node execution.
        """
        event_queue = GriptapeNodes.EventManager().event_queue
        while True:
            event = await event_queue.get()
            if event is None:
                event_queue.task_done()
                continue

            try:
                if isinstance(event, ProgressEvent):
                    # ProgressEvent is a plain dataclass, convert to an
                    # ExecutionEvent so it can be serialized and forwarded.
                    payload = GriptapeEvent(
                        node_name=event.node_name,
                        parameter_name=event.parameter_name,
                        type=type(event).__name__,
                        value=event.value,
                    )
                    execution_event = ExecutionEvent(payload=payload)
                    self.send_event("queue_event", execution_event.json())
                elif hasattr(event, "wrapped_event"):
                    self.send_event("queue_event", event.wrapped_event.json())
            except Exception:
                logger.exception("Failed to forward event from worker '%s'", self._library_name)

            event_queue.task_done()

    def _send_result_event(self, request: Any, result: ResultPayload, *, request_id: str | None = None) -> None:
        """Send a result event back to the parent via WebSocket."""
        if result.succeeded():
            event = EventResultSuccess(request=request, result=result, request_id=request_id)
            self.send_event("success_result", event.json())
        else:
            event = EventResultFailure(request=request, result=result, request_id=request_id)
            self.send_event("failure_result", event.json())


async def _async_main(library_name: str, library_file_path: str, session_id: str) -> None:
    """Async entry point for the library worker."""
    worker = LibraryWorker(library_name, library_file_path, session_id)
    try:
        await worker.initialize()
        await worker.run()
    finally:
        await worker.shutdown()


def main() -> None:
    """Parse CLI args and run the library worker."""
    logging.basicConfig(
        level=logging.DEBUG,
        format="[worker %(process)d] %(levelname)s %(name)s: %(message)s",
        stream=sys.stderr,
    )

    parser = ArgumentParser(description="Library worker subprocess")
    parser.add_argument("--library-name", required=True, help="Name of the library to load")
    parser.add_argument("--library-file-path", required=True, help="Path to the library JSON file")
    parser.add_argument("--session-id", required=True, help="WebSocket session ID for IPC")
    args = parser.parse_args()

    logger.info("Starting library worker for '%s' (session=%s)", args.library_name, args.session_id)

    asyncio.run(_async_main(args.library_name, args.library_file_path, args.session_id))


if __name__ == "__main__":
    main()
