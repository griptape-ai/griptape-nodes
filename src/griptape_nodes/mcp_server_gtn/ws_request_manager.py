import asyncio
import contextlib
import json
import logging
import os
import uuid
from collections.abc import Callable
from typing import Any, Generic, TypeVar
from urllib.parse import urljoin

import websockets

logger = logging.getLogger("griptape_nodes_mcp_server")

T = TypeVar("T")


class WebSocketConnectionManager:
    """Python equivalent of WebSocketConnectionManager in TypeScript."""

    def __init__(
        self,
        websocket_url: str = urljoin(
            os.getenv("GRIPTAPE_NODES_API_BASE_URL", "https://api.nodes.griptape.ai").replace("http", "ws"),
            "/ws/engines/events?version=v2",
        ),
    ):
        self.websocket_url = websocket_url
        self.websocket: Any = None
        self.connected = False
        self.event_handlers: dict[str, list[Callable]] = {}
        self.request_handlers: dict[str, tuple[Callable, Callable]] = {}
        self._process_task: asyncio.Task | None = None

    async def send(self, data: dict[str, Any]) -> None:
        """Send a message to the WebSocket server."""
        if not self.connected or not self.websocket:
            msg = "Not connected to WebSocket server"
            raise ConnectionError(msg)

        try:
            message = json.dumps(data)
            await self.websocket.send(message)
            logger.debug("📤 Sent message: %s", message)
        except Exception as e:
            logger.error("Failed to send message: %s", e)
            raise

    async def _process_messages(self) -> None:
        """Process incoming WebSocket messages."""
        if not self.websocket:
            logger.warning("WebSocket is not connected, cannot process messages")
            return

        try:
            async for message in self.websocket:
                try:
                    data = json.loads(message)
                    logger.debug("📥 Received message: %s", message)
                    await self._handle_message(data)
                except json.JSONDecodeError:
                    logger.error("Failed to parse message: %s", message)
                except Exception as e:
                    logger.error("Error processing message: %s", e)
        except websockets.exceptions.ConnectionClosed:
            logger.warning("WebSocket connection closed")
            self.connected = False
        except asyncio.CancelledError:
            # Task was cancelled, just exit
            pass
        except Exception as e:
            logger.error("Error in message processing loop: %s", e)
            self.connected = False

    async def _handle_message(self, data: dict[str, Any]) -> None:
        request = data.get("payload", {}).get("request", {})
        request_id = request.get("request_id")

        if request_id and request_id in self.request_handlers:
            success_handler, failure_handler = self.request_handlers[request_id]
            try:
                if data.get("type") == "success_result":
                    success_handler(data, request)
                else:
                    failure_handler(data, request)
            except Exception as e:
                logger.error("Error in request handler: %s", e)

    def subscribe_to_request_event(
        self, success_handler: Callable[[Any, Any], None], failure_handler: Callable[[Any, Any], None]
    ) -> str:
        """Subscribe to a request-response event."""
        request_id = str(uuid.uuid4())
        self.request_handlers[request_id] = (success_handler, failure_handler)
        return request_id

    def unsubscribe_from_request_event(self, request_id: str) -> None:
        """Unsubscribe from a request-response event."""
        if request_id in self.request_handlers:
            del self.request_handlers[request_id]


class AsyncRequestManager(Generic[T]):
    def __init__(self, connection_manager: WebSocketConnectionManager):
        self.connection_manager = connection_manager
        self.engine_id = None
        self.session_id = None

    async def _subscribe_to_topic(self, ws_connection: Any, topic: str) -> None:
        """Subscribe to a specific topic in the message bus."""
        if ws_connection is None:
            logger.warning("WebSocket connection not available for subscribing to topic")
            return

        try:
            body = {"type": "subscribe", "topic": topic, "payload": {}}
            await ws_connection.send(json.dumps(body))
            logger.info("Subscribed to topic: %s", topic)
        except websockets.exceptions.WebSocketException as e:
            logger.error("Error subscribing to topic %s: %s", topic, e)
        except Exception as e:
            logger.error("Unexpected error while subscribing to topic %s: %s", topic, e)

    async def _subscribe_to_engine_and_session(self, ws_connection: Any) -> None:
        """Subscribe to engine ID, session ID, and request topics on WebSocket connection."""
        # Subscribe to response topic (engine discovery)
        await self._subscribe_to_topic(ws_connection, "response")

        if self.engine_id:
            await self._subscribe_to_topic(ws_connection, f"engines/{self.engine_id}/response")
        else:
            logger.warning("Engine ID not available for subscription")

        if self.session_id:
            topic = f"sessions/{self.session_id}/response"
            await self._subscribe_to_topic(ws_connection, topic)
        else:
            logger.info("No session ID available for subscription")

    async def connect(self, token: str | None = None) -> None:
        """Connect to the WebSocket server."""
        from griptape_nodes.retained_mode.utils.engine_identity import EngineIdentity
        from griptape_nodes.retained_mode.managers.session_manager import SessionManager

        headers = {}
        if token:
            headers["Authorization"] = f"Bearer {token}"

        try:
            self.connection_manager.websocket = await websockets.connect(
                self.connection_manager.websocket_url, additional_headers=headers
            )
            self.connection_manager.connected = True
            logger.debug("🟢 WebSocket connection established: %s", self.connection_manager.websocket)

            self.engine_id = EngineIdentity.get_engine_id()
            self.session_id = SessionManager.get_saved_session_id()
            await self._subscribe_to_engine_and_session(self.connection_manager.websocket)

            # Start processing messages
            self.connection_manager._process_task = asyncio.create_task(self.connection_manager._process_messages())

        except Exception as e:
            self.connection_manager.connected = False
            logger.error("🔴 WebSocket connection failed: %s", str(e))
            msg = f"Failed to connect to WebSocket: {e!s}"
            raise ConnectionError(msg) from e

    async def disconnect(self) -> None:
        """Disconnect from the WebSocket server."""
        if self.connection_manager.websocket:
            await self.connection_manager.websocket.close()
            self.connection_manager.websocket = None
        self.connection_manager.connected = False

        # Cancel processing task if it's running
        if self.connection_manager._process_task:
            self.connection_manager._process_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self.connection_manager._process_task
            self.connection_manager._process_task = None

        logger.debug("WebSocket disconnected")

    async def send_api_message(self, data: dict[str, Any]) -> None:
        """Send a message to the API via WebSocket."""
        try:
            await self.connection_manager.send(data)
        except ConnectionError as e:
            logger.error("Failed to send API message: %s", e)
            raise
        except Exception as e:
            logger.error("Unexpected error sending API message: %s", e)
            raise

    def _determine_request_topic(self) -> str | None:
        """Determine the request topic based on session_id and engine_id in the payload."""
        # Normal topic determination logic
        # Check for session_id first (highest priority)
        if self.session_id:
            return f"sessions/{self.session_id}/request"

        # Check for engine_id if no session_id
        if self.engine_id:
            return f"engines/{self.engine_id}/request"

        # Default to generic request topic
        return "request"

    async def create_event(self, request_type: str, payload: dict[str, Any]) -> None:
        """Send an event to the API without waiting for a response."""
        logger.debug("📝 Creating Event: %s - %s", request_type, json.dumps(payload))

        data = {"event_type": "EventRequest", "request_type": request_type, "request": payload}
        topic = self._determine_request_topic()

        request_data = {"payload": data, "type": data["event_type"], "topic": topic}

        if not request_data["payload"]["request"].get("request_id"):
            request_data["payload"]["request"]["request_id"] = ""

        await self.send_api_message(request_data)

    async def create_request_event(
        self, request_type: str, payload: dict[str, Any], timeout_ms: int | None = None
    ) -> T:
        """Send a request and wait for its response.

        Args:
            request_type: Type of request to send
            payload: Data to send with the request
            timeout_ms: Optional timeout in milliseconds

        Returns:
            The response data

        Raises:
            asyncio.TimeoutError: If the request times out
            Exception: If the request fails
        """
        # Create a future that will be resolved when the response arrives
        response_future = asyncio.Future()

        # Convert timeout from milliseconds to seconds for asyncio
        timeout_sec = timeout_ms / 1000 if timeout_ms else None

        # Define handlers that will resolve/reject the future
        def success_handler(response: Any, _: Any) -> None:
            if not response_future.done():
                result = response.get("payload", {}).get("result", "Success")
                logger.debug("✅ Request succeeded: %s", result)
                response_future.set_result(result)

        def failure_handler(response: Any, _: Any) -> None:
            if not response_future.done():
                error = (
                    response.get("payload", {}).get("result", {}).get("exception", "Unknown error") or "Unknown error"
                )
                logger.error("❌ Request failed: %s", error)
                response_future.set_exception(Exception(error))

        # Generate request ID and subscribe
        request_id = self.connection_manager.subscribe_to_request_event(success_handler, failure_handler)
        payload["request_id"] = request_id

        logger.debug("🚀 Request (%s): %s %s", request_id, request_type, json.dumps(payload))

        try:
            # Send the event
            await self.create_event(request_type, payload)

            # Wait for the response with optional timeout
            if timeout_sec:
                return await asyncio.wait_for(response_future, timeout=timeout_sec)
            return await response_future

        except TimeoutError:
            logger.error("Request timed out after %s ms: %s", timeout_ms, request_id)
            self.connection_manager.unsubscribe_from_request_event(request_id)
            raise

        except Exception as e:
            logger.error("Request failed: %s - %s", request_id, e)
            self.connection_manager.unsubscribe_from_request_event(request_id)
            raise
