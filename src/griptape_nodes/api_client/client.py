"""Unified WebSocket client for Nodes API communication."""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
from typing import TYPE_CHECKING, Any, Self
from urllib.parse import urljoin

from websockets.asyncio.client import connect
from websockets.exceptions import ConnectionClosed

from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

if TYPE_CHECKING:
    from collections.abc import AsyncIterator
    from types import TracebackType

logger = logging.getLogger("griptape_nodes_client")


def get_default_websocket_url() -> str:
    """Get the default WebSocket endpoint URL for connecting to Nodes API.

    Returns:
        WebSocket URL for Nodes API events endpoint
    """
    return urljoin(
        os.getenv("GRIPTAPE_NODES_API_BASE_URL", "https://api.nodes.griptape.ai").replace("http", "ws"),
        "/ws/engines/events?version=v2",
    )


class Client:
    """WebSocket client for Nodes API pub/sub communication.

    Provides connection management, topic-based pub/sub, and message routing.
    Handles WebSocket reconnection and async event streaming.
    """

    def __init__(
        self,
        api_key: str | None = None,
        url: str | None = None,
    ):
        """Initialize Nodes API client.

        Args:
            api_key: API key for authentication (defaults to GT_CLOUD_API_KEY from SecretsManager)
            url: WebSocket URL to connect to (defaults to Nodes API endpoint)
        """
        self.url = url if url is not None else get_default_websocket_url()

        # Get API key from SecretsManager if not provided
        if api_key is None:
            api_key = GriptapeNodes.SecretsManager().get_secret("GT_CLOUD_API_KEY")

        self.api_key = api_key

        self.headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}

        # Event streaming management
        self._message_queue: asyncio.Queue = asyncio.Queue()
        self._subscribed_topics: set[str] = set()
        self._receiving_task: asyncio.Task | None = None
        self._sending_task: asyncio.Task | None = None
        self._websocket: Any = None
        self._connection_ready = asyncio.Event()
        self._reconnect_delay = 2.0

    async def __aenter__(self) -> Self:
        """Async context manager entry: connect to WebSocket server."""
        await self._connect()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        """Async context manager exit: disconnect from WebSocket server."""
        await self._disconnect()

    def __aiter__(self) -> AsyncIterator[dict[str, Any]]:
        """Return self as async iterator."""
        return self

    async def __anext__(self) -> dict[str, Any]:
        """Get next message from the message queue.

        Returns:
            Next message dictionary from subscribed topics

        Raises:
            StopAsyncIteration: When iteration is cancelled
        """
        try:
            return await self._message_queue.get()
        except asyncio.CancelledError:
            raise StopAsyncIteration from None

    @property
    def messages(self) -> AsyncIterator[dict[str, Any]]:
        """Async iterator for receiving messages from subscribed topics.

        Returns:
            Async iterator yielding message dictionaries

        Example:
            async with Client(...) as client:
                await client.subscribe("topic")
                async for message in client.messages:
                    print(message)
        """
        return self

    async def subscribe(self, topic: str) -> None:
        """Subscribe to a topic by sending subscribe command to server.

        Args:
            topic: Topic name to subscribe to

        Example:
            await client.subscribe("sessions/123/response")
        """
        self._subscribed_topics.add(topic)
        await self._send_subscribe_command(topic)

    async def unsubscribe(self, topic: str) -> None:
        """Unsubscribe from a topic.

        Args:
            topic: Topic name to unsubscribe from
        """
        self._subscribed_topics.discard(topic)
        await self._send_unsubscribe_command(topic)

    async def publish(self, event_type: str, payload: dict[str, Any], topic: str) -> None:
        """Publish an event to the server.

        Args:
            event_type: Type of event to publish
            payload: Event payload data
            topic: Topic to publish to
        """
        message = {"type": event_type, "payload": payload, "topic": topic}
        await self._send_message(message)

    async def _connect(self) -> None:
        """Connect to the WebSocket server and start receiving messages.

        This method starts the connection manager task.
        It returns once the initial connection is established.

        Raises:
            ConnectionError: If connection fails
        """
        # Start connection manager task
        self._receiving_task = asyncio.create_task(self._manage_connection())

        # Wait for initial connection to be established
        try:
            await asyncio.wait_for(self._connection_ready.wait(), timeout=10.0)
            logger.debug("WebSocket client connected")
        except TimeoutError as e:
            logger.error("Failed to connect WebSocket client: timeout")
            msg = "Connection timeout"
            raise ConnectionError(msg) from e

    async def _disconnect(self) -> None:
        """Disconnect from the WebSocket server and clean up tasks."""
        # Cancel tasks
        if self._receiving_task:
            self._receiving_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._receiving_task

        if self._sending_task:
            self._sending_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._sending_task

        # Close websocket connection
        if self._websocket:
            await self._websocket.close()
        logger.info("WebSocket client disconnected")

    async def _manage_connection(self) -> None:
        """Manage WebSocket connection lifecycle with automatic reconnection.

        This method establishes and maintains the WebSocket connection,
        automatically reconnecting on failures.
        """
        try:
            async for websocket in connect(self.url, additional_headers=self.headers):
                self._websocket = websocket
                self._connection_ready.set()
                logger.debug("WebSocket connection established: %s", self.url)

                # Resubscribe to all topics after reconnection
                if self._subscribed_topics:
                    logger.debug("Resubscribing to %d topics after reconnection", len(self._subscribed_topics))
                    for topic in self._subscribed_topics:
                        await self._send_subscribe_command(topic)

                try:
                    await self._receive_messages(websocket)
                except ConnectionClosed:
                    logger.info("WebSocket connection closed, reconnecting...")
                    self._connection_ready.clear()
                    continue

        except asyncio.CancelledError:
            logger.debug("Connection manager task cancelled")

    async def _receive_messages(self, websocket: Any) -> None:
        """Receive messages from WebSocket and put them in message queue.

        Args:
            websocket: WebSocket connection to receive messages from

        Raises:
            ConnectionClosed: When the WebSocket connection is closed
        """
        try:
            async for message in websocket:
                try:
                    data = json.loads(message)
                    await self._message_queue.put(data)
                except json.JSONDecodeError:
                    logger.error("Failed to parse message: %s", message)
                except Exception as e:
                    logger.error("Error receiving message: %s", e)
        except asyncio.CancelledError:
            logger.debug("Receive messages task cancelled")
            raise

    async def _send_message(self, message: dict[str, Any]) -> None:
        """Send a message through the WebSocket connection.

        Args:
            message: Message dictionary to send

        Raises:
            ConnectionError: If not connected
        """
        if not self._websocket:
            msg = "Not connected to WebSocket"
            raise ConnectionError(msg)

        try:
            await self._websocket.send(json.dumps(message))
            logger.debug("Sent message type: %s", message.get("type"))
        except Exception as e:
            logger.error("Failed to send message: %s", e)

    async def _send_subscribe_command(self, topic: str) -> None:
        """Send subscribe command to server.

        Args:
            topic: Topic to subscribe to
        """
        message = {"type": "subscribe", "topic": topic, "payload": {}}
        await self._send_message(message)
        logger.debug("Sent subscribe command for topic: %s", topic)

    async def _send_unsubscribe_command(self, topic: str) -> None:
        """Send unsubscribe command to server.

        Args:
            topic: Topic to unsubscribe from
        """
        message = {"type": "unsubscribe", "topic": topic, "payload": {}}
        await self._send_message(message)
        logger.debug("Sent unsubscribe command for topic: %s", topic)
