"""Library worker subprocess for process-isolated node execution.

This script runs in a library's venv Python process. It bootstraps a full
GriptapeNodes engine, loads only the target library, connects to the parent
via WebSocket, and enters a command dispatch loop.

Usage:
    python library_worker.py --library-name NAME --library-file-path PATH --session-id ID
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import sys
from argparse import ArgumentParser
from typing import Any

from griptape_nodes.bootstrap.utils.subprocess_websocket_sender import SubprocessWebSocketSenderMixin
from griptape_nodes.exe_types.core_types import Parameter
from griptape_nodes.ipc.protocol import (
    CREATE_NODE,
    CREATE_NODE_RESULT,
    DESTROY_NODE,
    EXECUTE_NODE,
    EXECUTE_NODE_ERROR,
    EXECUTE_NODE_RESULT,
    CreateNodeCommand,
    CreateNodeResult,
    DestroyNodeCommand,
    ExecuteNodeCommand,
    ExecuteNodeResult,
    IPCMessage,
    ParameterSchema,
)
from griptape_nodes.retained_mode.events.app_events import AppInitializationComplete
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

logger = logging.getLogger(__name__)


class LibraryWorker(SubprocessWebSocketSenderMixin):
    """Worker process that hosts a single library's nodes.

    Bootstraps a full GriptapeNodes engine, loads only the target library,
    and processes IPC commands from the parent engine.
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
        """Subscribe to commands and enter the dispatch loop."""
        if self._ws_client is None:
            msg = "WebSocket client not available."
            raise RuntimeError(msg)

        # Signal to the parent that this worker is ready to accept commands
        self.send_event("worker_ready", json.dumps({"session_id": self._session_id}))

        topic = f"sessions/{self._session_id}/commands"
        await self._ws_client.subscribe(topic)

        logger.info("Worker for library '%s' listening for commands on topic '%s'", self._library_name, topic)

        async for message in self._ws_client.messages:
            try:
                await self._dispatch_message(message)
            except Exception:
                logger.exception("Error dispatching message in worker '%s'", self._library_name)

    async def shutdown(self) -> None:
        """Clean up resources."""
        await self._stop_websocket_connection()

    async def _dispatch_message(self, message: dict[str, Any]) -> None:
        """Parse an IPC message and dispatch to the appropriate handler."""
        payload = message.get("payload", message)
        ipc_message = IPCMessage.from_dict(payload)

        logger.debug(
            "Worker '%s' received command: type=%s, id=%s",
            self._library_name,
            ipc_message.message_type,
            ipc_message.message_id,
        )

        response: dict[str, Any]
        if ipc_message.message_type == CREATE_NODE:
            response = await self._handle_create_node(ipc_message)
        elif ipc_message.message_type == EXECUTE_NODE:
            response = await self._handle_execute_node(ipc_message)
        elif ipc_message.message_type == DESTROY_NODE:
            response = await self._handle_destroy_node(ipc_message)
        else:
            response = {
                "message_id": ipc_message.message_id,
                "message_type": "error",
                "payload": {"error": f"Unknown message type: {ipc_message.message_type}"},
            }

        self._send_response(response)

    async def _handle_create_node(self, ipc_message: IPCMessage) -> dict[str, Any]:
        """Create a node instance and return its parameter schema."""
        cmd = CreateNodeCommand.from_payload(ipc_message.payload)
        logger.info("Creating node '%s' (type=%s) in worker '%s'", cmd.node_name, cmd.node_type, self._library_name)

        from griptape_nodes.node_library.library_registry import LibraryRegistry

        node = await LibraryRegistry.acreate_node(
            node_type=cmd.node_type,
            name=cmd.node_name,
            metadata=cmd.metadata,
            specific_library_name=self._library_name,
        )
        self._nodes[cmd.node_name] = node

        # Serialize parameter schema
        parameter_schemas = []
        for param in node.parameters:
            if isinstance(param, Parameter):
                schema = ParameterSchema(
                    name=param.name,
                    type=param.type,
                    input_types=param.input_types,
                    output_type=param.output_type,
                    allowed_modes=[m.name for m in param.allowed_modes] if param.allowed_modes else None,
                    default_value=param.default_value,
                    tooltip=param.tooltip if isinstance(param.tooltip, str) else "",
                    ui_options=param.ui_options or None,
                )
                parameter_schemas.append(schema)

        result = CreateNodeResult(
            node_name=cmd.node_name,
            parameter_schemas=parameter_schemas,
        )

        logger.info(
            "Node '%s' created in worker '%s' with %d parameter(s)",
            cmd.node_name,
            self._library_name,
            len(parameter_schemas),
        )

        return {
            "message_id": ipc_message.message_id,
            "message_type": CREATE_NODE_RESULT,
            "payload": result.to_payload(),
        }

    async def _handle_execute_node(self, ipc_message: IPCMessage) -> dict[str, Any]:
        """Execute a node and return serialized outputs."""
        cmd = ExecuteNodeCommand.from_payload(ipc_message.payload)

        if cmd.node_name not in self._nodes:
            logger.warning("Attempted to execute unknown node '%s' in worker '%s'", cmd.node_name, self._library_name)
            return {
                "message_id": ipc_message.message_id,
                "message_type": EXECUTE_NODE_ERROR,
                "payload": {"node_name": cmd.node_name, "error": f"Node '{cmd.node_name}' not found."},
            }

        node = self._nodes[cmd.node_name]

        logger.info("Executing node '%s' in worker '%s'", cmd.node_name, self._library_name)

        # Hydrate parameter values
        for param_name, value in cmd.parameter_values.items():
            node.parameter_values[param_name] = value

        # Set entry control parameter if provided
        if cmd.entry_control_parameter_name:
            param = node.get_parameter_by_name(cmd.entry_control_parameter_name)
            if param is not None:
                node.set_entry_control_parameter(param)

        node.parameter_output_values.silent_clear()

        # Start draining execution events from the worker's EventManager queue
        # so they can be forwarded to the parent for UI display
        drain_task = asyncio.create_task(self._drain_event_queue())

        try:
            await node.aprocess()
        except Exception as e:
            logger.exception("Node '%s' execution failed in worker '%s'", cmd.node_name, self._library_name)
            return {
                "message_id": ipc_message.message_id,
                "message_type": EXECUTE_NODE_ERROR,
                "payload": {"node_name": cmd.node_name, "error": str(e)},
            }
        finally:
            drain_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await drain_task

        # Get next control output
        next_control = node.get_next_control_output()
        next_control_name = next_control.name if next_control else None

        result = ExecuteNodeResult(
            node_name=cmd.node_name,
            parameter_output_values=dict(node.parameter_output_values),
            next_control_output_name=next_control_name,
        )

        logger.info(
            "Node '%s' execution complete in worker '%s' with %d output(s)",
            cmd.node_name,
            self._library_name,
            len(result.parameter_output_values),
        )

        return {
            "message_id": ipc_message.message_id,
            "message_type": EXECUTE_NODE_RESULT,
            "payload": result.to_payload(),
        }

    async def _handle_destroy_node(self, ipc_message: IPCMessage) -> dict[str, Any]:
        """Destroy a node instance."""
        cmd = DestroyNodeCommand.from_payload(ipc_message.payload)

        if cmd.node_name not in self._nodes:
            return {
                "message_id": ipc_message.message_id,
                "message_type": "error",
                "payload": {"error": f"Node '{cmd.node_name}' not found."},
            }

        del self._nodes[cmd.node_name]
        logger.info("Node '%s' destroyed in worker '%s'", cmd.node_name, self._library_name)

        return {
            "message_id": ipc_message.message_id,
            "message_type": DESTROY_NODE + "_result",
            "payload": {"node_name": cmd.node_name},
        }

    async def _drain_event_queue(self) -> None:
        """Read events from the worker's EventManager queue and forward to parent.

        Runs as a background task during node execution. Handles the same event
        types as local_session_workflow_executor.py (ExecutionGriptapeNodeEvent,
        ProgressEvent).
        """
        from griptape_nodes.retained_mode.events.base_events import (
            ExecutionEvent,
            ExecutionGriptapeNodeEvent,
            ProgressEvent,
        )
        from griptape_nodes.retained_mode.events.execution_events import GriptapeEvent

        event_queue = GriptapeNodes.EventManager().event_queue
        while True:
            event = await event_queue.get()
            if event is None:
                event_queue.task_done()
                continue

            try:
                if isinstance(event, ExecutionGriptapeNodeEvent):
                    self.send_event("event_broadcast", event.wrapped_event.json())
                elif isinstance(event, ProgressEvent):
                    payload = GriptapeEvent(
                        node_name=event.node_name,
                        parameter_name=event.parameter_name,
                        type=type(event).__name__,
                        value=event.value,
                    )
                    execution_event = ExecutionEvent(payload=payload)
                    self.send_event("event_broadcast", execution_event.json())
            except Exception:
                logger.exception("Failed to forward event from worker '%s'", self._library_name)

            event_queue.task_done()

    def _send_response(self, response: dict[str, Any]) -> None:
        """Send a response back to the parent via WebSocket."""
        self.send_event("ipc_response", json.dumps(response))


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
