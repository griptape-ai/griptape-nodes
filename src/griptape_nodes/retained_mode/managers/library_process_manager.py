"""Parent-side manager for library worker subprocesses.

Spawns one worker subprocess per out-of-process library, communicates via
WebSocket using the existing SubprocessWebSocketListenerMixin, and provides
request-response correlation for IPC commands.
"""

from __future__ import annotations

import asyncio
import logging
import os
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from griptape_nodes.bootstrap.utils.subprocess_websocket_listener import SubprocessWebSocketListenerMixin
from griptape_nodes.ipc.protocol import (
    CREATE_NODE,
    CREATE_NODE_RESULT,
    DESTROY_NODE,
    EVENT_BROADCAST,
    EXECUTE_NODE,
    EXECUTE_NODE_ERROR,
    EXECUTE_NODE_RESULT,
    CreateNodeCommand,
    CreateNodeResult,
    DestroyNodeCommand,
    ExecuteNodeCommand,
    ExecuteNodeError,
    ExecuteNodeResult,
    IPCMessage,
)

logger = logging.getLogger(__name__)

_WORKER_SCRIPT = str(Path(__file__).resolve().parents[2] / "bootstrap" / "library_worker.py")


_WORKER_READY_TIMEOUT_SECONDS = 120


@dataclass
class LibraryProcessHandle:
    """Tracks a single library worker subprocess."""

    library_name: str
    process: asyncio.subprocess.Process
    session_id: str
    pending: dict[str, asyncio.Future[dict[str, Any]]] = field(default_factory=dict)
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
    ) -> CreateNodeResult:
        """Create a node in a library worker and return its parameter schema.

        Args:
            library_name: Library whose worker should create the node.
            node_type: Class name of the node to create.
            node_name: Unique name for the node instance.
            metadata: Optional metadata to pass to the node.

        Returns:
            CreateNodeResult with the node's parameter schema.
        """
        cmd = CreateNodeCommand(node_type=node_type, node_name=node_name, metadata=metadata)
        response = await self._send_command(library_name, CREATE_NODE, cmd.to_payload())

        response_type = response.get("message_type", "")
        if response_type == CREATE_NODE_RESULT:
            return CreateNodeResult.from_payload(response.get("payload", {}))

        error = response.get("payload", {}).get("error", "Unknown error")
        msg = f"Failed to create node '{node_name}' in worker '{library_name}': {error}"
        raise RuntimeError(msg)

    async def execute_node(
        self,
        library_name: str,
        node_name: str,
        parameter_values: dict[str, Any],
        entry_control_parameter_name: str | None = None,
    ) -> ExecuteNodeResult:
        """Execute a node in a library worker.

        Args:
            library_name: Library whose worker owns the node.
            node_name: Name of the node to execute.
            parameter_values: Input parameter values.
            entry_control_parameter_name: Name of the entry control parameter, if any.

        Returns:
            ExecuteNodeResult with output values and selected control output.
        """
        cmd = ExecuteNodeCommand(
            node_name=node_name,
            parameter_values=parameter_values,
            entry_control_parameter_name=entry_control_parameter_name,
        )
        response = await self._send_command(library_name, EXECUTE_NODE, cmd.to_payload())

        response_type = response.get("message_type", "")
        if response_type == EXECUTE_NODE_RESULT:
            return ExecuteNodeResult.from_payload(response.get("payload", {}))
        if response_type == EXECUTE_NODE_ERROR:
            error_result = ExecuteNodeError.from_payload(response.get("payload", {}))
            msg = f"Node '{node_name}' execution failed in worker '{library_name}': {error_result.error}"
            raise RuntimeError(msg)

        error = response.get("payload", {}).get("error", "Unknown error")
        msg = f"Unexpected response executing node '{node_name}': {error}"
        raise RuntimeError(msg)

    async def destroy_node(self, library_name: str, node_name: str) -> None:
        """Destroy a node instance in a library worker.

        Args:
            library_name: Library whose worker owns the node.
            node_name: Name of the node to destroy.
        """
        cmd = DestroyNodeCommand(node_name=node_name)
        response = await self._send_command(library_name, DESTROY_NODE, cmd.to_payload())

        response_type = response.get("message_type", "")
        if response_type != DESTROY_NODE + "_result":
            error = response.get("payload", {}).get("error", "Unknown error")
            msg = f"Failed to destroy node '{node_name}' in worker '{library_name}': {error}"
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

    async def _send_command(
        self,
        library_name: str,
        message_type: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        """Send a command to a library worker and await the response.

        When called from a thread that is not the main event loop (e.g. during
        workflow script execution via ``exec()`` in a thread), the command is
        transparently routed to the main loop where the WebSocket client lives.
        """
        current_loop = asyncio.get_running_loop()

        if self._main_loop is not None and current_loop is not self._main_loop:
            cf_future = asyncio.run_coroutine_threadsafe(
                self._send_command_on_main_loop(library_name, message_type, payload),
                self._main_loop,
            )
            return await asyncio.wrap_future(cf_future, loop=current_loop)

        return await self._send_command_on_main_loop(library_name, message_type, payload)

    async def _send_command_on_main_loop(
        self,
        library_name: str,
        message_type: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        """Send a command on the main event loop and await the response."""
        if library_name not in self._handles:
            msg = f"No worker for library '{library_name}'. Call start_worker first."
            raise ValueError(msg)

        handle = self._handles[library_name]

        if handle.process.returncode is not None:
            msg = f"Worker for '{library_name}' has exited with code {handle.process.returncode}."
            raise RuntimeError(msg)

        message = IPCMessage(message_type=message_type, payload=payload)

        loop = asyncio.get_running_loop()
        future: asyncio.Future[dict[str, Any]] = loop.create_future()
        handle.pending[message.message_id] = future

        # Send via WebSocket
        await self._send_ipc_message(handle, message)

        return await future

    async def _send_ipc_message(self, handle: LibraryProcessHandle, message: IPCMessage) -> None:
        """Send an IPC message to a worker via WebSocket."""
        if self._ws_client is None:
            msg = "WebSocket client not available."
            raise RuntimeError(msg)

        topic = f"sessions/{handle.session_id}/commands"
        payload_dict = message.to_dict()

        await self._ws_client.publish("ipc_command", payload_dict, topic)

    async def _handle_subprocess_event(self, event: dict) -> None:
        """Handle events from worker subprocesses.

        Routes responses to pending futures and forwards execution events.
        """
        event_type = event.get("type", "")

        if event_type == "ipc_response":
            await self._handle_ipc_response(event.get("payload", {}))
        elif event_type == EVENT_BROADCAST:
            await self._handle_event_broadcast(event.get("payload", {}))
        elif event_type == "worker_ready":
            self._handle_worker_ready(event.get("payload", {}))

    async def _handle_ipc_response(self, payload: dict[str, Any]) -> None:
        """Route an IPC response to the matching pending future."""
        message_id = payload.get("message_id")
        if not message_id:
            logger.warning("Received IPC response without message_id")
            return

        # Find the handle that owns this pending request
        for handle in self._handles.values():
            if message_id in handle.pending:
                future = handle.pending.pop(message_id)
                if not future.done():
                    future.set_result(payload)
                else:
                    logger.warning("Future for message_id %s already done, ignoring response", message_id)
                return

        logger.warning("Received IPC response for unknown message_id: %s", message_id)

    def _handle_worker_ready(self, payload: dict[str, Any]) -> None:
        """Resolve the ready future for the worker that sent the signal."""
        import json

        if isinstance(payload, str):
            payload = json.loads(payload)
        session_id = payload.get("session_id")
        if not session_id:
            logger.warning("Received worker_ready without session_id")
            return

        for handle in self._handles.values():
            if handle.session_id == session_id and handle.ready_future is not None and not handle.ready_future.done():
                handle.ready_future.set_result(None)
                return

        logger.warning("Received worker_ready for unknown session_id: %s", session_id)

    async def _handle_event_broadcast(self, payload: dict[str, Any]) -> None:
        """Forward execution events from workers to the parent EventManager.

        The worker sends serialized ExecutionEvent JSON. We reconstruct the event
        as an ExecutionGriptapeNodeEvent and inject it into the parent's event queue
        so app.py can forward it to the UI.
        """
        import json

        from griptape_nodes.retained_mode.events.base_events import ExecutionEvent, ExecutionGriptapeNodeEvent
        from griptape_nodes.retained_mode.events.execution_events import GriptapeEvent
        from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

        # payload may be a JSON string from the WebSocket transport
        if isinstance(payload, str):
            payload = json.loads(payload)

        # Reconstruct the ExecutionEvent with a GriptapeEvent payload
        event_payload = payload.get("payload", {})
        griptape_event = GriptapeEvent(
            node_name=event_payload.get("node_name", ""),
            parameter_name=event_payload.get("parameter_name", ""),
            type=event_payload.get("type", ""),
            value=event_payload.get("value"),
        )
        execution_event = ExecutionEvent(payload=griptape_event)
        wrapped = ExecutionGriptapeNodeEvent(wrapped_event=execution_event)

        GriptapeNodes.EventManager().put_event(wrapped)

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
