"""WebSocket sender mixin for subprocess communication.

This module provides a reusable mixin for sending WebSocket events
from subprocess executions back to the parent process.
"""

from __future__ import annotations

import asyncio
import json
import logging
import threading

from griptape_nodes.api_client import Client
from griptape_nodes.app.app import WebSocketMessage

logger = logging.getLogger(__name__)


class SubprocessWebSocketSenderMixin:
    """Mixin providing WebSocket sender functionality for subprocess communication.

    This mixin handles:
    - Starting/stopping a WebSocket sender thread
    - Queuing and sending events to the parent process
    - Thread-safe event emission
    """

    _sender_session_id: str
    _websocket_thread: threading.Thread | None
    _websocket_event_loop: asyncio.AbstractEventLoop | None
    _websocket_event_loop_ready: threading.Event
    _ws_outgoing_queue: asyncio.Queue | None
    _shutdown_event: asyncio.Event | None

    def _init_websocket_sender(self, session_id: str) -> None:
        """Initialize WebSocket sender state.

        Args:
            session_id: Unique session ID for WebSocket topic.
        """
        self._sender_session_id = session_id
        self._websocket_thread = None
        self._websocket_event_loop = None
        self._websocket_event_loop_ready = threading.Event()
        self._ws_outgoing_queue = None
        self._shutdown_event = None

    def _get_sender_session_id(self) -> str:
        """Get the session ID used for WebSocket communication."""
        return self._sender_session_id

    async def _start_websocket_connection(self) -> None:
        """Start websocket connection in a background thread for event emission."""
        logger.info("Starting websocket connection for session %s", self._sender_session_id)
        self._websocket_thread = threading.Thread(target=self._start_websocket_thread, daemon=True)
        self._websocket_thread.start()

        if self._websocket_event_loop_ready.wait(timeout=10):
            logger.info("Websocket thread ready")
            await asyncio.sleep(1)  # Brief wait for connection to establish
        else:
            logger.error("Timeout waiting for websocket thread to start")

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
        logger.info("Creating Client for session %s", self._sender_session_id)

        async with Client() as client:
            logger.info("WebSocket connection established for session %s", self._sender_session_id)

            try:
                await self._send_outgoing_messages(client)
            except Exception:
                logger.exception("WebSocket tasks failed")
            finally:
                logger.info("WebSocket connection loop ended")

    async def _send_outgoing_messages(self, client: Client) -> None:
        """Send outgoing WebSocket messages from queue."""
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
                    topic = message.topic if message.topic else f"sessions/{self._sender_session_id}/response"
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
        """Send an event via websocket if connected - thread-safe version.

        Args:
            event_type: Type of event (e.g., "execution_event", "success_result")
            payload: JSON string payload to send
        """
        # Wait for websocket event loop to be ready
        if not self._websocket_event_loop_ready.wait(timeout=1.0):
            logger.debug("Websocket not ready, event not sent: %s", event_type)
            return

        # Use run_coroutine_threadsafe to put message into WebSocket background thread queue
        if self._websocket_event_loop is None:
            logger.debug("WebSocket event loop not available for message: %s", event_type)
            return

        topic = f"sessions/{self._sender_session_id}/response"
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
        """Wait for all websocket messages to be sent.

        Args:
            timeout_seconds: Maximum time to wait for queue to flush
        """
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
