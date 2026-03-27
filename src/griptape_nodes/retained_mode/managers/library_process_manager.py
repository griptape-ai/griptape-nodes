"""Parent-side manager for library worker subprocesses.

Spawns one worker subprocess per out-of-process library, communicates via
WebSocket using the existing event system, and provides request-response
correlation using request_id matching.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from griptape_nodes.bootstrap.utils.subprocess_websocket_listener import SubprocessWebSocketListenerMixin
from griptape_nodes.retained_mode.events.base_events import (
    EventRequest,
    EventResultFailure,
    EventResultSuccess,
    ResultPayload,
)
from griptape_nodes.retained_mode.events.execution_events import (
    ExecuteRemoteNodeRequest,
    ExecuteRemoteNodeResultSuccess,
)
from griptape_nodes.retained_mode.events.node_events import (
    CreateNodeRequest,
    CreateNodeResultSuccess,
)
from griptape_nodes.retained_mode.events.payload_registry import PayloadRegistry

logger = logging.getLogger(__name__)

_WORKER_SCRIPT = str(Path(__file__).resolve().parents[2] / "bootstrap" / "library_worker.py")

_WORKER_READY_TIMEOUT_SECONDS = 120


@dataclass
class LibraryProcessHandle:
    """Tracks a single library worker subprocess."""

    library_name: str
    process: asyncio.subprocess.Process
    session_id: str
    pending: dict[str, asyncio.Future[ResultPayload]] = field(default_factory=dict)
    stderr_task: asyncio.Task | None = None
    ready_future: asyncio.Future[None] | None = None


class LibraryProcessManager(SubprocessWebSocketListenerMixin):
    """Manages library worker subprocesses for process-isolated node execution."""

    def __init__(self) -> None:
        self._handles: dict[str, LibraryProcessHandle] = {}
        self._main_loop: asyncio.AbstractEventLoop | None = None

    def has_worker(self, library_name: str) -> bool:
        """Check if a worker subprocess exists for the given library."""
        return library_name in self._handles

    async def start_worker(
        self,
        library_name: str,
        python_path: Path,
        library_base_dir: Path,
        library_file_path: str,
    ) -> None:
        """Spawn a worker subprocess for a library.

        Args:
            library_name: Identifier for the library.
            python_path: Path to the Python executable in the library's venv.
            library_base_dir: Directory containing the library's code.
            library_file_path: Path to the library JSON file.
        """
        if library_name in self._handles:
            msg = f"Worker for library '{library_name}' already exists."
            raise ValueError(msg)

        if self._main_loop is None:
            self._main_loop = asyncio.get_running_loop()

        session_id = uuid.uuid4().hex

        # Initialize WebSocket listener for this worker
        self._init_websocket_listener(session_id=session_id)
        await self._start_websocket_listener()

        logger.info(
            "Starting worker for library '%s' (python=%s, library_dir=%s)",
            library_name,
            python_path,
            library_base_dir,
        )

        process = await asyncio.create_subprocess_exec(
            str(python_path),
            _WORKER_SCRIPT,
            "--library-name",
            library_name,
            "--library-file-path",
            library_file_path,
            "--session-id",
            session_id,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env={**os.environ, "GRIPTAPE_WORKER_PROCESS": "1"},
        )

        loop = asyncio.get_running_loop()
        ready_future: asyncio.Future[None] = loop.create_future()

        handle = LibraryProcessHandle(
            library_name=library_name,
            process=process,
            session_id=session_id,
            ready_future=ready_future,
        )
        handle.stderr_task = asyncio.create_task(self._read_stderr(library_name, process))
        self._handles[library_name] = handle

        logger.info("Worker for library '%s' started (pid=%s), waiting for ready signal...", library_name, process.pid)

        await asyncio.wait_for(ready_future, timeout=_WORKER_READY_TIMEOUT_SECONDS)

        logger.info("Worker for library '%s' is ready", library_name)

    async def create_node(
        self,
        library_name: str,
        node_type: str,
        node_name: str,
        metadata: dict[str, Any] | None = None,
    ) -> CreateNodeResultSuccess:
        """Create a node in a library worker and return the result.

        Args:
            library_name: Library whose worker should create the node.
            node_type: Class name of the node to create.
            node_name: Unique name for the node instance.
            metadata: Optional metadata to pass to the node.

        Returns:
            CreateNodeResultSuccess with the node's details.
        """
        request = CreateNodeRequest(
            node_type=node_type,
            node_name=node_name,
            specific_library_name=library_name,
            metadata=metadata,
        )
        result = await self._send_request(library_name, request)

        if isinstance(result, CreateNodeResultSuccess):
            return result

        error = result.result_details if hasattr(result, "result_details") else "Unknown error"
        msg = f"Failed to create node '{node_name}' in worker '{library_name}': {error}"
        raise RuntimeError(msg)

    async def execute_node(
        self,
        library_name: str,
        node_name: str,
        parameter_values: dict[str, Any],
        entry_control_parameter_name: str | None = None,
    ) -> ExecuteRemoteNodeResultSuccess:
        """Execute a node in a library worker.

        Args:
            library_name: Library whose worker owns the node.
            node_name: Name of the node to execute.
            parameter_values: Input parameter values.
            entry_control_parameter_name: Name of the entry control parameter, if any.

        Returns:
            ExecuteRemoteNodeResultSuccess with output values and selected control output.
        """
        request = ExecuteRemoteNodeRequest(
            node_name=node_name,
            parameter_values=parameter_values,
            entry_control_parameter_name=entry_control_parameter_name,
        )
        result = await self._send_request(library_name, request)

        if isinstance(result, ExecuteRemoteNodeResultSuccess):
            return result

        details = result.result_details if hasattr(result, "result_details") else "Unknown error"
        msg = f"Node '{node_name}' execution failed in worker '{library_name}': {details}"
        raise RuntimeError(msg)

    async def shutdown(self) -> None:
        """Terminate all worker subprocesses."""
        logger.info("Shutting down library process manager (%d worker(s))", len(self._handles))

        for library_name, handle in self._handles.items():
            logger.info("Shutting down worker for library '%s' (pid=%s)", library_name, handle.process.pid)

            if handle.stderr_task is not None:
                handle.stderr_task.cancel()

            try:
                handle.process.terminate()
                await asyncio.wait_for(handle.process.wait(), timeout=5.0)
                logger.info("Worker for library '%s' terminated gracefully", library_name)
            except (TimeoutError, ProcessLookupError):
                handle.process.kill()
                logger.warning("Worker for library '%s' killed after timeout", library_name)

            for future in handle.pending.values():
                if not future.done():
                    future.set_exception(RuntimeError(f"Worker '{library_name}' shut down."))

        await self._stop_websocket_listener()
        self._handles.clear()
        logger.info("Library process manager shutdown complete")

    async def _send_request(
        self,
        library_name: str,
        request: Any,
    ) -> ResultPayload:
        """Send a request to a library worker and await the result.

        When called from a thread that is not the main event loop (e.g. during
        workflow script execution), the request is transparently routed to the
        main loop where the WebSocket client lives.
        """
        current_loop = asyncio.get_running_loop()

        if self._main_loop is not None and current_loop is not self._main_loop:
            cf_future = asyncio.run_coroutine_threadsafe(
                self._send_request_on_main_loop(library_name, request),
                self._main_loop,
            )
            return await asyncio.wrap_future(cf_future, loop=current_loop)

        return await self._send_request_on_main_loop(library_name, request)

    async def _send_request_on_main_loop(
        self,
        library_name: str,
        request: Any,
    ) -> ResultPayload:
        """Send a request on the main event loop and await the result."""
        if library_name not in self._handles:
            msg = f"No worker for library '{library_name}'. Call start_worker first."
            raise ValueError(msg)

        handle = self._handles[library_name]

        if handle.process.returncode is not None:
            msg = f"Worker for '{library_name}' has exited with code {handle.process.returncode}."
            raise RuntimeError(msg)

        # Wrap the request in an EventRequest for serialization
        request_id = uuid.uuid4().hex
        event_request = EventRequest(request=request, request_id=request_id)

        loop = asyncio.get_running_loop()
        future: asyncio.Future[ResultPayload] = loop.create_future()
        handle.pending[request_id] = future

        # Send via WebSocket
        await self._publish_event(handle, event_request)

        return await future

    async def _publish_event(self, handle: LibraryProcessHandle, event_request: EventRequest) -> None:
        """Publish an EventRequest to a worker via WebSocket."""
        if self._ws_client is None:
            msg = "WebSocket client not available."
            raise RuntimeError(msg)

        topic = f"sessions/{handle.session_id}/commands"
        payload_dict = json.loads(event_request.json())

        await self._ws_client.publish("event_request", payload_dict, topic)

    async def _handle_subprocess_event(self, event: dict) -> None:
        """Handle events from worker subprocesses.

        Routes result events to pending futures and forwards execution events
        to the parent's EventManager for UI display.
        """
        event_type = event.get("type", "")

        if event_type in ("success_result", "failure_result"):
            self._handle_result_event(event)
        elif event_type == "queue_event":
            self._handle_queue_event(event)
        elif event_type == "worker_ready":
            self._handle_worker_ready()

    def _handle_result_event(self, event: dict) -> None:
        """Route a result event to the matching pending future."""
        payload = event.get("payload", {})

        # Parse JSON string payload if needed
        if isinstance(payload, str):
            payload = json.loads(payload)

        request_id = payload.get("request_id")
        if not request_id:
            logger.warning("Received result event without request_id")
            return

        # Find the handle that owns this pending request
        for handle in self._handles.values():
            if request_id in handle.pending:
                future = handle.pending.pop(request_id)
                if future.done():
                    logger.warning("Future for request_id %s already done, ignoring", request_id)
                    return

                # Deserialize the result payload
                result_type_name = payload.get("result_type", "")
                result_type = PayloadRegistry.get_type(result_type_name)
                if result_type is None:
                    logger.warning("Unknown result type: %s", result_type_name)
                    future.set_exception(RuntimeError(f"Unknown result type: {result_type_name}"))
                    return

                request_type_name = payload.get("request_type", "")
                request_type = PayloadRegistry.get_type(request_type_name)
                if request_type is None:
                    logger.warning("Unknown request type: %s", request_type_name)
                    future.set_exception(RuntimeError(f"Unknown request type: {request_type_name}"))
                    return

                event_type = event.get("type", "")
                if event_type == "success_result":
                    result_event = EventResultSuccess.from_dict(payload, request_type, result_type)
                else:
                    result_event = EventResultFailure.from_dict(payload, request_type, result_type)

                future.set_result(result_event.result)
                return

        logger.warning("Received result event for unknown request_id: %s", request_id)

    def _handle_queue_event(self, event: dict) -> None:
        """Deserialize a forwarded queue event and put it on the parent's EventManager queue.

        The worker serializes every queued event's inner payload via .json() and
        sends it as a generic "queue_event". Here we deserialize it back into the
        correct BaseEvent subclass and re-queue it on the parent so the UI receives it.
        """
        from griptape_nodes.retained_mode.events.base_events import (
            EventResult,
            ExecutionEvent,
            ExecutionGriptapeNodeEvent,
            GriptapeNodeEvent,
            deserialize_event,
        )
        from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

        payload = event.get("payload", {})
        if isinstance(payload, str):
            payload = json.loads(payload)

        try:
            deserialized = deserialize_event(payload)
        except (TypeError, ValueError):
            logger.exception("Failed to deserialize queue event from worker")
            return

        if isinstance(deserialized, ExecutionEvent):
            GriptapeNodes.EventManager().put_event(ExecutionGriptapeNodeEvent(wrapped_event=deserialized))
        elif isinstance(deserialized, EventResult):
            GriptapeNodes.EventManager().put_event(GriptapeNodeEvent(wrapped_event=deserialized))

    def _handle_worker_ready(self) -> None:
        """Resolve the ready future for the worker that sent the signal."""
        for handle in self._handles.values():
            if handle.ready_future is not None and not handle.ready_future.done():
                handle.ready_future.set_result(None)
                return

        logger.warning("Received worker_ready but no handle is waiting")

    async def _read_stderr(self, library_name: str, process: asyncio.subprocess.Process) -> None:
        """Background task that reads and logs worker stderr output."""
        if process.stderr is None:
            return

        try:
            while True:
                line = await process.stderr.readline()
                if not line:
                    break
                text = line.decode(errors="replace").rstrip()
                logger.info("[worker:%s] %s", library_name, text)
        except asyncio.CancelledError:
            return
