from __future__ import annotations

import asyncio
import json
import logging
import threading
from typing import TYPE_CHECKING, Any, Self

from griptape_nodes.api_client import Client
from griptape_nodes.app.app import WebSocketMessage
from griptape_nodes.bootstrap.workflow_executors.local_workflow_executor import (
    LocalExecutorError,
    LocalWorkflowExecutor,
)
from griptape_nodes.drivers.storage import StorageBackend
from griptape_nodes.retained_mode.events.app_events import AppInitializationComplete
from griptape_nodes.retained_mode.events.base_events import (
    EventRequest,
    EventResultFailure,
    EventResultSuccess,
    ExecutionEvent,
    ExecutionGriptapeNodeEvent,
    ResultPayload,
)
from griptape_nodes.retained_mode.events.execution_events import (
    ControlFlowCancelledEvent,
    StartFlowRequest,
    StartFlowResultFailure,
)
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

if TYPE_CHECKING:
    from collections.abc import Callable
    from types import TracebackType

logger = logging.getLogger(__name__)


class LocalSessionWorkflowExecutor(LocalWorkflowExecutor):
    def __init__(
        self,
        session_id: str,
        storage_backend: StorageBackend = StorageBackend.LOCAL,
        on_start_flow_result: Callable[[ResultPayload], None] | None = None,
    ):
        super().__init__(storage_backend=storage_backend)
        self._session_id = session_id
        self._on_start_flow_result = on_start_flow_result
        self._websocket_thread: threading.Thread | None = None
        self._websocket_event_loop: asyncio.AbstractEventLoop | None = None
        self._websocket_event_loop_ready = threading.Event()
        self._ws_outgoing_queue: asyncio.Queue | None = None
        self._shutdown_event: asyncio.Event | None = None

    async def __aenter__(self) -> Self:
        """Async context manager entry: initialize queue and broadcast app initialization."""
        GriptapeNodes.EventManager().initialize_queue()
        await GriptapeNodes.EventManager().broadcast_app_event(AppInitializationComplete())

        logger.info("Setting up session %s", self._session_id)
        GriptapeNodes.SessionManager().save_session(self._session_id)
        GriptapeNodes.SessionManager().active_session_id = self._session_id
        await self._start_websocket_connection()

        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        """Async context manager exit."""
        self._stop_websocket_thread()

        GriptapeNodes.SessionManager().remove_session(self._session_id)

        # TODO: Broadcast shutdown https://github.com/griptape-ai/griptape-nodes/issues/2149

    def _stop_websocket_thread(self) -> None:
        """Stop the websocket thread."""
        if self._websocket_thread is None or not self._websocket_thread.is_alive():
            logger.debug("No websocket thread to stop")
            return

        logger.debug("Stopping websocket thread")
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
            logger.warning("Websocket thread did not stop gracefully")
        else:
            logger.info("Websocket thread stopped successfully")

    async def _process_execution_event_async(self, event: ExecutionGriptapeNodeEvent) -> None:
        """Process execution events asynchronously for real-time websocket emission."""
        logger.debug("REAL-TIME: Processing execution event for session %s", self._session_id)
        self.send_event("execution_event", event.wrapped_event.json())

    async def arun(
        self,
        flow_input: Any,
        storage_backend: StorageBackend | None = None,
        **kwargs: Any,
    ) -> None:
        """Executes a local workflow.

        Executes a workflow by setting up event listeners, registering libraries,
        loading the user-defined workflow, and running the specified workflow.

        Parameters:
            flow_input: Input data for the flow, typically a dictionary.
            storage_backend: The storage backend to use for the workflow execution.

        Returns:
            None
        """
        try:
            await self._arun(
                flow_input=flow_input,
                storage_backend=storage_backend,
                **kwargs,
            )
        except Exception as e:
            msg = f"Workflow execution failed: {e}"
            logger.exception(msg)
            control_flow_cancelled_event = ControlFlowCancelledEvent(
                result_details="Encountered an error during workflow execution",
                exception=e,
            )
            execution_event = ExecutionEvent(payload=control_flow_cancelled_event)
            self.send_event("execution_event", execution_event.json())
            await self._wait_for_websocket_queue_flush()
            await asyncio.sleep(1)
            raise LocalExecutorError(msg) from e
        finally:
            self._stop_websocket_thread()

    async def _arun(  # noqa: C901, PLR0915
        self,
        flow_input: Any,
        storage_backend: StorageBackend | None = None,
        **kwargs: Any,
    ) -> None:
        """Internal async run method with detailed event handling and websocket integration."""
        flow_name = await self.aprepare_workflow_for_run(
            flow_input=flow_input,
            storage_backend=storage_backend,
            **kwargs,
        )

        # Send the run command to actually execute it (fire and forget)
        pickle_control_flow_result = kwargs.get("pickle_control_flow_result", False)
        start_flow_request = StartFlowRequest(
            flow_name=flow_name, pickle_control_flow_result=pickle_control_flow_result
        )
        start_flow_task = asyncio.create_task(GriptapeNodes.ahandle_request(start_flow_request))

        is_flow_finished = False
        error: Exception | None = None

        def _handle_start_flow_result(task: asyncio.Task[ResultPayload]) -> None:
            nonlocal is_flow_finished, error, start_flow_request
            try:
                start_flow_result = task.result()
                self._on_start_flow_result(start_flow_result) if self._on_start_flow_result is not None else None

                if isinstance(start_flow_result, StartFlowResultFailure):
                    msg = f"Failed to start flow {flow_name}"
                    logger.error(msg)
                    event_result_failure = EventResultFailure(request=start_flow_request, result=start_flow_result)
                    self.send_event("failure_result", event_result_failure.json())
                    raise LocalExecutorError(msg) from start_flow_result.exception  # noqa: TRY301

                event_result_success = EventResultSuccess(request=start_flow_request, result=start_flow_result)
                self.send_event("success_result", event_result_success.json())

            except Exception as e:
                msg = "Error starting workflow"
                logger.exception(msg)
                is_flow_finished = True
                error = e
                # The StartFlowRequest is sent asynchronously to enable real-time event emission via WebSocket.
                # The main while loop below then waits for events from the queue. However, if StartFlowRequest fails
                # immediately, then no events are ever added to the queue, causing the loop to hang indefinitely
                # on event_queue.get(). This fix adds a dummy event to wake up the loop in failure cases.
                event_queue = GriptapeNodes.EventManager().event_queue
                queue_event_task = asyncio.create_task(event_queue.put(None))
                background_tasks.add(queue_event_task)
                queue_event_task.add_done_callback(background_tasks.discard)

        start_flow_task.add_done_callback(_handle_start_flow_result)

        logger.info("Workflow start request sent! Processing events...")

        background_tasks: set[asyncio.Task] = set()

        def _handle_task_done(task: asyncio.Task) -> None:
            background_tasks.discard(task)
            if task.exception() and not task.cancelled():
                logger.exception("Background task failed", exc_info=task.exception())

        event_queue = GriptapeNodes.EventManager().event_queue
        while not is_flow_finished:
            try:
                event = await event_queue.get()

                # Handle the dummy wake up event (None)
                if event is None:
                    event_queue.task_done()
                    continue

                logger.debug("Processing event: %s", type(event).__name__)

                if isinstance(event, EventRequest):
                    self.send_event("event_request", event.json())
                    task = asyncio.create_task(self._handle_event_request(event))
                    background_tasks.add(task)
                    task.add_done_callback(_handle_task_done)
                elif isinstance(event, ExecutionGriptapeNodeEvent):
                    # Emit execution event via WebSocket
                    self.send_event("execution_event", event.wrapped_event.json())
                    task = asyncio.create_task(self._process_execution_event_async(event))
                    background_tasks.add(task)
                    task.add_done_callback(_handle_task_done)
                    is_flow_finished, error = await self._handle_execution_event(event, flow_name)

                event_queue.task_done()

            except Exception as e:
                msg = f"Error handling queue event: {e}"
                logger.exception(msg)
                error = LocalExecutorError(msg)
                break

        if background_tasks:
            logger.info("Waiting for %d background tasks to complete", len(background_tasks))
            await asyncio.gather(*background_tasks, return_exceptions=True)

        await self._wait_for_websocket_queue_flush()

        if error is not None:
            raise error

    async def _start_websocket_connection(self) -> None:
        """Start websocket connection in a background thread for event emission."""
        logger.info("Starting websocket connection for session %s", self._session_id)
        self._websocket_thread = threading.Thread(target=self._start_websocket_thread, daemon=True)
        self._websocket_thread.start()

        if self._websocket_event_loop_ready.wait(timeout=10):
            logger.info("Websocket thread ready")
            await asyncio.sleep(1)  # Brief wait for connection to establish
        else:
            logger.error("Timeout waiting for websocket thread to start")

    def _start_websocket_thread(self) -> None:
        """Run WebSocket tasks in a separate thread with its own async loop."""
        try:
            # Create a new event loop for this thread
            loop = asyncio.new_event_loop()
            self._websocket_event_loop = loop
            asyncio.set_event_loop(loop)

            # Create the outgoing queue and shutdown event
            self._ws_outgoing_queue = asyncio.Queue()
            self._shutdown_event = asyncio.Event()

            # Signal that websocket_event_loop is ready
            self._websocket_event_loop_ready.set()
            logger.info("Websocket thread started and ready")

            # Run the async WebSocket tasks
            loop.run_until_complete(self._run_websocket_tasks())
        except Exception as e:
            logger.error("WebSocket thread error: %s", e)
        finally:
            self._websocket_event_loop = None
            self._websocket_event_loop_ready.clear()
            self._shutdown_event = None
            logger.info("Websocket thread ended")

    async def _run_websocket_tasks(self) -> None:
        """Run websocket tasks - establish connection and handle outgoing messages."""
        logger.info("Creating Client for session %s", self._session_id)

        async with Client() as client:
            logger.info("WebSocket connection established for session %s", self._session_id)

            try:
                await self._send_outgoing_messages(client)
            except Exception:
                logger.exception("WebSocket tasks failed")
            finally:
                logger.info("WebSocket connection loop ended")

    async def _send_outgoing_messages(self, client: Client) -> None:
        """Send outgoing WebSocket messages from queue - matches app.py pattern exactly."""
        if self._ws_outgoing_queue is None:
            logger.error("No outgoing queue available")
            return

        logger.debug("Starting outgoing WebSocket request sender")

        while True:
            # Check if shutdown was requested
            if self._shutdown_event and self._shutdown_event.is_set():
                logger.info("Shutdown requested, ending message sender")
                break

            try:
                # Get message from outgoing queue with timeout to allow shutdown checks
                message = await asyncio.wait_for(self._ws_outgoing_queue.get(), timeout=1.0)
            except TimeoutError:
                # No message in queue, continue to check for shutdown
                continue

            try:
                if isinstance(message, WebSocketMessage):
                    topic = message.topic if message.topic else f"sessions/{self._session_id}/response"
                    payload_dict = json.loads(message.payload)
                    await client.publish(message.event_type, payload_dict, topic)
                    logger.debug("DELIVERED: %s event", message.event_type)
                else:
                    logger.warning("Unknown outgoing message type: %s", type(message))
            except Exception as e:
                logger.error("Error sending outgoing WebSocket request: %s", e)
            finally:
                self._ws_outgoing_queue.task_done()

    def send_event(self, event_type: str, payload: str) -> None:
        """Send an event via websocket if connected - thread-safe version."""
        # Wait for websocket event loop to be ready
        if not self._websocket_event_loop_ready.wait(timeout=1.0):
            logger.debug("Websocket not ready, event not sent: %s", event_type)
            return

        # Use run_coroutine_threadsafe to put message into WebSocket background thread queue
        if self._websocket_event_loop is None:
            logger.debug("WebSocket event loop not available for message: %s", event_type)
            return

        topic = f"sessions/{self._session_id}/response"
        message = WebSocketMessage(event_type, payload, topic)

        if self._ws_outgoing_queue is None:
            logger.debug("No websocket queue available for event: %s", event_type)
            return

        try:
            asyncio.run_coroutine_threadsafe(self._ws_outgoing_queue.put(message), self._websocket_event_loop)
            logger.debug("SENT: %s event via websocket", event_type)
        except Exception as e:
            logger.error("Failed to queue event %s: %s", event_type, e)

    async def _wait_for_websocket_queue_flush(self, timeout_seconds: float = 5.0) -> None:
        """Wait for all websocket messages to be sent."""
        if self._ws_outgoing_queue is None or self._websocket_event_loop is None:
            return

        async def _check_queue_empty() -> bool:
            return self._ws_outgoing_queue.empty() if self._ws_outgoing_queue else True

        start_time = asyncio.get_event_loop().time()
        while asyncio.get_event_loop().time() - start_time < timeout_seconds:
            future = asyncio.run_coroutine_threadsafe(_check_queue_empty(), self._websocket_event_loop)
            try:
                is_empty = future.result(timeout=0.1)
                if is_empty:
                    return
            except Exception as e:
                logger.debug("Error checking queue status: %s", e)
            await asyncio.sleep(0.1)

        logger.warning("Timeout waiting for websocket queue to flush")
