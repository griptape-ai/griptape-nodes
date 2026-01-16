"""WebSocket listener mixin for subprocess communication.

This module provides a reusable mixin for listening to WebSocket events
from subprocess executions. Used by both SubprocessWorkflowExecutor and
SubprocessWorkflowPublisher.
"""

from __future__ import annotations

import asyncio
import logging
import threading
import uuid
from typing import TYPE_CHECKING

from griptape_nodes.api_client import Client

if TYPE_CHECKING:
    from collections.abc import Callable

logger = logging.getLogger(__name__)


class SubprocessWebSocketListenerMixin:
    """Mixin providing WebSocket listener functionality for subprocess communication.

    This mixin handles:
    - Starting/stopping a WebSocket listener thread
    - Subscribing to session-specific topics
    - Processing incoming events and calling callbacks

    Subclasses should implement _handle_subprocess_event() for custom event handling.
    """

    _listener_session_id: str
    _on_event: Callable[[dict], None] | None
    _websocket_thread: threading.Thread | None
    _websocket_event_loop: asyncio.AbstractEventLoop | None
    _websocket_event_loop_ready: threading.Event
    _shutdown_event: asyncio.Event | None
    _listener_startup_error: Exception | None

    def _init_websocket_listener(
        self,
        session_id: str | None = None,
        on_event: Callable[[dict], None] | None = None,
    ) -> None:
        """Initialize WebSocket listener state.

        Args:
            session_id: Unique session ID for WebSocket topic subscription.
                       If None, a random UUID will be generated.
            on_event: Optional callback invoked for each received event.
        """
        self._listener_session_id = session_id or uuid.uuid4().hex
        self._on_event = on_event
        self._websocket_thread = None
        self._websocket_event_loop = None
        self._websocket_event_loop_ready = threading.Event()
        self._shutdown_event = None
        self._listener_startup_error = None

    def _get_listener_session_id(self) -> str:
        """Get the session ID used for WebSocket communication."""
        return self._listener_session_id

    async def _start_websocket_listener(self) -> None:
        """Start WebSocket connection to listen for events from the subprocess.

        Raises:
            RuntimeError: If the WebSocket listener thread fails to start or times out.
        """
        logger.info("Starting WebSocket listener for session %s", self._listener_session_id)
        self._listener_startup_error = None
        self._websocket_thread = threading.Thread(target=self._start_websocket_thread, daemon=True)
        self._websocket_thread.start()

        if not self._websocket_event_loop_ready.wait(timeout=10):
            # Check if there was an error during startup
            if self._listener_startup_error is not None:
                msg = f"WebSocket listener thread failed to start: {self._listener_startup_error}"
                raise RuntimeError(msg) from self._listener_startup_error
            msg = "Timeout waiting for WebSocket listener thread to start"
            raise RuntimeError(msg)

        # Check if an error occurred after the ready event was set but before we got here
        if self._listener_startup_error is not None:
            msg = f"WebSocket listener thread failed during startup: {self._listener_startup_error}"
            raise RuntimeError(msg) from self._listener_startup_error

        logger.info("WebSocket listener thread ready")

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
            # Store the error so the main thread can raise it
            self._listener_startup_error = e
            # Signal ready event so main thread doesn't hang waiting
            self._websocket_event_loop_ready.set()
        finally:
            self._websocket_event_loop = None
            self._websocket_event_loop_ready.clear()
            self._shutdown_event = None
            logger.info("WebSocket listener thread ended")

    async def _run_websocket_listener(self) -> None:
        """Run WebSocket listener - establish connection and handle incoming messages."""
        logger.info("Creating Client for listening on session %s", self._listener_session_id)

        async with Client() as client:
            logger.info("WebSocket connection established for session %s", self._listener_session_id)

            try:
                await self._listen_for_messages(client)
            except Exception:
                logger.exception("WebSocket listener failed for session %s", self._listener_session_id)
            finally:
                logger.info("WebSocket listener connection loop ended")

    async def _listen_for_messages(self, client: Client) -> None:
        """Listen for incoming WebSocket messages from the subprocess."""
        logger.info("Starting to listen for WebSocket messages")

        topic = f"sessions/{self._listener_session_id}/response"
        await client.subscribe(topic)

        try:
            async for message in client.messages:
                if self._shutdown_event and self._shutdown_event.is_set():
                    logger.info("Shutdown requested, ending message listener")
                    break

                try:
                    logger.debug("Received WebSocket message: %s", message.get("type"))
                    await self._process_listener_event(message)

                except Exception:
                    logger.exception(
                        "Error processing WebSocket message of type '%s' for session %s",
                        message.get("type", "unknown"),
                        self._listener_session_id,
                    )

        except Exception as e:
            logger.error("Error in WebSocket message listener: %s", e)
            raise

    async def _process_listener_event(self, event: dict) -> None:
        """Process events received from the subprocess via WebSocket.

        This method:
        1. Calls the on_event callback if provided (for GUI updates)
        2. Delegates to _handle_subprocess_event for subclass-specific handling

        Args:
            event: The event dictionary received from the subprocess
        """
        # Call the event callback if provided (for GUI updates)
        if self._on_event:
            self._on_event(event)

        # Delegate to subclass for specific event handling
        await self._handle_subprocess_event(event)

    async def _handle_subprocess_event(self, event: dict) -> None:
        """Handle subprocess-specific events.

        Override this method in subclasses to implement custom event handling.
        The default implementation does nothing.

        Args:
            event: The event dictionary received from the subprocess
        """
