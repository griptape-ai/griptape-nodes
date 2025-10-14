from __future__ import annotations

import asyncio
import json
import logging
import tempfile
import threading
import uuid
from pathlib import Path
from typing import TYPE_CHECKING, Any, Self

import anyio

from griptape_nodes.api_client import Client
from griptape_nodes.bootstrap.utils.python_subprocess_executor import PythonSubprocessExecutor
from griptape_nodes.bootstrap.workflow_executors.local_session_workflow_executor import LocalSessionWorkflowExecutor
from griptape_nodes.drivers.storage import StorageBackend
from griptape_nodes.retained_mode.events.base_events import (
    EventResultFailure,
    EventResultSuccess,
    ExecutionEvent,
    ResultPayload,
)
from griptape_nodes.retained_mode.events.execution_events import (
    ControlFlowCancelledEvent,
    ControlFlowResolvedEvent,
    StartFlowRequest,
)
from griptape_nodes.retained_mode.events.payload_registry import PayloadRegistry

if TYPE_CHECKING:
    from collections.abc import Callable
    from types import TracebackType

logger = logging.getLogger(__name__)


class SubprocessWorkflowExecutorError(Exception):
    """Exception raised during subprocess workflow execution."""


class SubprocessWorkflowExecutor(LocalSessionWorkflowExecutor, PythonSubprocessExecutor):
    def __init__(
        self,
        workflow_path: str,
        on_start_flow_result: Callable[[ResultPayload], None] | None = None,
        session_id: str | None = None,
    ) -> None:
        PythonSubprocessExecutor.__init__(self)
        self._workflow_path = workflow_path
        self._on_start_flow_result = on_start_flow_result
        # Generate a unique session ID for this execution
        self._session_id = session_id or uuid.uuid4().hex
        self._websocket_thread: threading.Thread | None = None
        self._websocket_event_loop: asyncio.AbstractEventLoop | None = None
        self._websocket_event_loop_ready = threading.Event()
        self._event_handlers: dict[str, list] = {}
        self._shutdown_event: asyncio.Event | None = None
        self._stored_exception: SubprocessWorkflowExecutorError | None = None

    async def __aenter__(self) -> Self:
        """Async context manager entry: start WebSocket connection."""
        logger.info("Starting WebSocket listener for session %s", self._session_id)
        await self._start_websocket_listener()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        """Async context manager exit: stop WebSocket connection."""
        logger.info("Stopping WebSocket listener for session %s", self._session_id)
        self._stop_websocket_listener()

    async def arun(
        self,
        flow_input: Any,
        storage_backend: StorageBackend = StorageBackend.LOCAL,
        *,
        pickle_control_flow_result: bool = False,
        **kwargs: Any,  # noqa: ARG002
    ) -> None:
        """Execute a workflow in a subprocess and wait for completion."""
        script_path = Path(__file__).parent / "utils" / "subprocess_script.py"

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_workflow_path = Path(tmpdir) / "workflow.py"
            tmp_script_path = Path(tmpdir) / "subprocess_script.py"

            try:
                async with (
                    await anyio.open_file(self._workflow_path, "rb") as src,
                    await anyio.open_file(tmp_workflow_path, "wb") as dst,
                ):
                    await dst.write(await src.read())

                async with (
                    await anyio.open_file(script_path, "rb") as src,
                    await anyio.open_file(tmp_script_path, "wb") as dst,
                ):
                    await dst.write(await src.read())
            except Exception as e:
                msg = f"Failed to copy workflow or script to temp directory: {e}"
                logger.exception(msg)
                raise SubprocessWorkflowExecutorError(msg) from e

            args = [
                "--json-input",
                json.dumps(flow_input),
                "--session-id",
                self._session_id,
                "--storage-backend",
                storage_backend.value,
                "--workflow-path",
                str(tmp_workflow_path),
            ]

            if pickle_control_flow_result:
                args.append("--pickle-control-flow-result")

            try:
                await self.execute_python_script(
                    script_path=tmp_script_path,
                    args=args,
                    cwd=Path(tmpdir),
                )
            except Exception as e:
                msg = f"Failed to execute subprocess script: {e}"
                logger.exception(msg)
                raise SubprocessWorkflowExecutorError(msg) from e
            finally:
                # Check if an exception was stored coming from the WebSocket
                if self._stored_exception:
                    raise self._stored_exception

    async def _start_websocket_listener(self) -> None:
        """Start WebSocket connection to listen for events from the subprocess."""
        logger.info("Starting WebSocket listener for session %s", self._session_id)
        self._websocket_thread = threading.Thread(target=self._start_websocket_thread, daemon=True)
        self._websocket_thread.start()

        if self._websocket_event_loop_ready.wait(timeout=10):
            logger.info("WebSocket listener thread ready")
        else:
            logger.error("Timeout waiting for WebSocket listener thread to start")

    def _stop_websocket_listener(self) -> None:
        """Stop the WebSocket listener thread."""
        if self._websocket_thread is None or not self._websocket_thread.is_alive():
            return

        logger.info("Stopping WebSocket listener thread")
        self._websocket_event_loop_ready.clear()

        # Signal shutdown to the websocket tasks
        if self._websocket_event_loop and self._websocket_event_loop.is_running() and self._shutdown_event:

            def signal_shutdown() -> None:
                if self._shutdown_event:
                    self._shutdown_event.set()

            self._websocket_event_loop.call_soon_threadsafe(signal_shutdown)

        # Wait for thread to finish
        self._websocket_thread.join(timeout=5.0)
        if self._websocket_thread.is_alive():
            logger.warning("WebSocket listener thread did not stop gracefully")
        else:
            logger.info("WebSocket listener thread stopped successfully")

    def _start_websocket_thread(self) -> None:
        """Run WebSocket tasks in a separate thread with its own async loop."""
        try:
            # Create a new event loop for this thread
            loop = asyncio.new_event_loop()
            self._websocket_event_loop = loop
            asyncio.set_event_loop(loop)

            # Create shutdown event
            self._shutdown_event = asyncio.Event()

            # Signal that websocket_event_loop is ready
            self._websocket_event_loop_ready.set()
            logger.info("WebSocket listener thread started and ready")

            # Run the async WebSocket listener
            loop.run_until_complete(self._run_websocket_listener())
        except Exception as e:
            logger.error("WebSocket listener thread error: %s", e)
        finally:
            self._websocket_event_loop = None
            self._websocket_event_loop_ready.clear()
            self._shutdown_event = None
            logger.info("WebSocket listener thread ended")

    async def _run_websocket_listener(self) -> None:
        """Run WebSocket listener - establish connection and handle incoming messages."""
        logger.info("Creating Client for listening on session %s", self._session_id)

        async with Client() as client:
            logger.info("WebSocket connection established for session %s", self._session_id)

            try:
                await self._listen_for_messages(client)
            except Exception:
                logger.exception("WebSocket listener failed")
            finally:
                logger.info("WebSocket listener connection loop ended")

    async def _listen_for_messages(self, client: Client) -> None:
        """Listen for incoming WebSocket messages from the subprocess."""
        logger.info("Starting to listen for WebSocket messages")

        topic = f"sessions/{self._session_id}/response"
        await client.subscribe(topic)

        try:
            async for message in client.messages:
                if self._shutdown_event and self._shutdown_event.is_set():
                    logger.info("Shutdown requested, ending message listener")
                    break

                try:
                    logger.debug("Received WebSocket message: %s", message.get("type"))
                    await self._process_event(message)

                except Exception:
                    logger.exception("Error processing WebSocket message")

        except Exception as e:
            logger.error("Error in WebSocket message listener: %s", e)
            raise

    async def _process_event(self, event: dict) -> None:
        """Process events received from the subprocess via WebSocket."""
        event_type = event.get("type", "unknown")
        if event_type == "execution_event":
            await self._process_execution_event(event)
        elif event_type in ["success_result", "failure_result"]:
            await self._process_result_event(event)

    async def _process_execution_event(self, event: dict) -> None:
        payload = event.get("payload", {})
        event_type = payload.get("event_type", "")
        payload_type_name = payload.get("payload_type", "")
        payload_type = PayloadRegistry.get_type(payload_type_name)

        # Focusing on ExecutionEvent types for the workflow executor
        if event_type not in ["ExecutionEvent", "EventResultSuccess", "EventResultFailure"]:
            logger.debug("Ignoring event type: %s", event_type)
            return

        if payload_type is None:
            logger.warning("Unknown payload type: %s", payload_type_name)
            return

        ex_event = ExecutionEvent.from_dict(data=payload, payload_type=payload_type)

        if isinstance(ex_event.payload, ControlFlowResolvedEvent):
            logger.info("Workflow execution completed successfully")
            # Store both parameter output values and unique UUID values for deserialization
            result = {
                "parameter_output_values": ex_event.payload.parameter_output_values,
                "unique_parameter_uuid_to_values": ex_event.payload.unique_parameter_uuid_to_values,
            }
            self.output = {ex_event.payload.end_node_name: result}

        if isinstance(ex_event.payload, ControlFlowCancelledEvent):
            logger.error("Workflow execution cancelled")

            details = ex_event.payload.result_details or "No details provided"
            msg = f"Workflow execution cancelled: {details}"

            if ex_event.payload.exception:
                msg = f"Exception running workflow: {ex_event.payload.exception}"
                self._stored_exception = SubprocessWorkflowExecutorError(ex_event.payload.exception)
            else:
                self._stored_exception = SubprocessWorkflowExecutorError(msg)

    async def _process_result_event(self, event: dict) -> None:
        payload = event.get("payload", {})
        request_type_name = payload.get("request_type", "")
        response_type_name = payload.get("result_type", "")
        request_payload_type = PayloadRegistry.get_type(request_type_name)
        response_payload_type = PayloadRegistry.get_type(response_type_name)

        if request_payload_type is None or response_payload_type is None:
            logger.warning("Unknown payload types: %s, %s", request_type_name, response_type_name)
            return
        if payload.get("type", "unknown") == "success_result":
            result_event = EventResultSuccess.from_dict(
                data=payload, req_payload_type=request_payload_type, res_payload_type=response_payload_type
            )
        else:
            result_event = EventResultFailure.from_dict(
                data=payload, req_payload_type=request_payload_type, res_payload_type=response_payload_type
            )

        if isinstance(result_event.request, StartFlowRequest):
            logger.info("Received StartFlowRequest result event")
            if self._on_start_flow_result:
                self._on_start_flow_result(result_event.result)
        else:
            logger.warning("Ignoring result event for request type: %s", request_type_name)
