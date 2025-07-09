import asyncio
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
    """Python equivalent of WebSocketConnectionManager in TypeScript"""

    def __init__(
        self,
        websocket_url: str = urljoin(
            os.getenv("GRIPTAPE_NODES_API_BASE_URL", "https://api.nodes.griptape.ai").replace("http", "ws"),
            "/ws/engines/events?publish_channel=requests&subscribe_channel=responses",
        ),
    ):
        self.websocket_url = websocket_url
        self.websocket = None
        self.connected = False
        self.event_handlers: dict[str, list[Callable]] = {}
        self.request_handlers: dict[str, tuple[Callable, Callable]] = {}
        self._connect_task = None
        self._process_task = None

    async def send(self, data: dict[str, Any]) -> None:
        """Send a message to the WebSocket server"""
        if not self.connected or not self.websocket:
            raise ConnectionError("Not connected to WebSocket server")

        try:
            message = json.dumps(data)
            await self.websocket.send(message)
            logger.debug(f"📤 Sent message: {message}")
        except Exception as e:
            logger.error(f"Failed to send message: {e!s}")
            raise

    async def _process_messages(self) -> None:
        """Process incoming WebSocket messages"""
        if not self.websocket:
            logger.warning("WebSocket is not connected, cannot process messages")
            return

        try:
            async for message in self.websocket:
                try:
                    data = json.loads(message)
                    # logger.debug(f"📥 Received message: {message}")
                    await self._handle_message(data)
                except json.JSONDecodeError:
                    logger.error(f"Failed to parse message: {message}")
                except Exception as e:
                    logger.error(f"Error processing message: {e!s}")
        except websockets.exceptions.ConnectionClosed:
            logger.warning("WebSocket connection closed")
            self.connected = False
        except asyncio.CancelledError:
            # Task was cancelled, just exit
            pass
        except Exception as e:
            logger.error(f"Error in message processing loop: {e!s}")
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
                logger.error(f"Error in request handler: {e!s}")

    def subscribe_to_request_event(
        self, success_handler: Callable[[Any, Any], None], failure_handler: Callable[[Any, Any], None]
    ) -> str:
        """Subscribe to a request-response event"""
        request_id = str(uuid.uuid4())
        self.request_handlers[request_id] = (success_handler, failure_handler)
        return request_id

    def unsubscribe_from_request_event(self, request_id: str) -> None:
        """Unsubscribe from a request-response event"""
        if request_id in self.request_handlers:
            del self.request_handlers[request_id]


class AsyncRequestManager(Generic[T]):
    def __init__(self, connection_manager: WebSocketConnectionManager):
        self.connection_manager = connection_manager

    async def connect(self, token: str | None = None) -> None:
        """Connect to the WebSocket server"""
        headers = {}
        if token:
            headers["Authorization"] = f"Bearer {token}"

        try:
            self.connection_manager.websocket = await websockets.connect(
                self.connection_manager.websocket_url, additional_headers=headers
            )
            self.connection_manager.connected = True
            logger.debug(f"🟢 WebSocket connection established: {self.connection_manager.websocket}")

            # Start processing messages
            self.connection_manager._process_task = asyncio.create_task(self.connection_manager._process_messages())

        except Exception as e:
            self.connection_manager.connected = False
            logger.error(f"🔴 WebSocket connection failed: {e!s}")
            raise ConnectionError(f"Failed to connect to WebSocket: {e!s}")

    async def disconnect(self) -> None:
        """Disconnect from the WebSocket server"""
        if self.connection_manager.websocket:
            await self.connection_manager.websocket.close()
            self.connection_manager.websocket = None
        self.connection_manager.connected = False

        # Cancel processing task if it's running
        if self.connection_manager._process_task:
            self.connection_manager._process_task.cancel()
            try:
                await self.connection_manager._process_task
            except asyncio.CancelledError:
                pass
            self.connection_manager._process_task = None

        logger.debug("WebSocket disconnected")

    async def send_api_message(self, data: dict[str, Any]) -> None:
        """Send a message to the API via WebSocket"""
        try:
            await self.connection_manager.send(data)
        except ConnectionError as e:
            logger.error(f"Failed to send API message: {e!s}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error sending API message: {e!s}")
            raise

    async def create_event(self, request_type: str, payload: dict[str, Any]) -> None:
        """Send an event to the API without waiting for a response."""
        logger.debug(f"📝 Creating Event: {request_type} - {json.dumps(payload)}")

        data = {"event_type": "EventRequest", "request_type": request_type, "request": payload}

        request_data = {"payload": data, "type": data["event_type"]}

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
        def success_handler(response, request):
            if not response_future.done():
                result = response.get("payload", {}).get("result", "Success")
                logger.debug(f"✅ Request succeeded: {result}")
                response_future.set_result(result)

        def failure_handler(response, request):
            if not response_future.done():
                error = (
                    response.get("payload", {}).get("result", {}).get("exception", "Unknown error") or "Unknown error"
                )
                logger.error(f"❌ Request failed: {error}")
                response_future.set_exception(Exception(error))

        # Generate request ID and subscribe
        request_id = self.connection_manager.subscribe_to_request_event(success_handler, failure_handler)
        payload["request_id"] = request_id

        logger.debug(f"🚀 Request ({request_id}): {request_type} {json.dumps(payload)}")

        try:
            # Send the event
            await self.create_event(request_type, payload)

            # Wait for the response with optional timeout
            if timeout_sec:
                return await asyncio.wait_for(response_future, timeout=timeout_sec)
            return await response_future

        except TimeoutError:
            logger.error(f"Request timed out after {timeout_ms}ms: {request_id}")
            self.connection_manager.unsubscribe_from_request_event(request_id)
            raise

        except Exception as e:
            logger.error(f"Request failed: {request_id} - {e!s}")
            self.connection_manager.unsubscribe_from_request_event(request_id)
            raise
