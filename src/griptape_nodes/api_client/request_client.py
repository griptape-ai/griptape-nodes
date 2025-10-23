"""Request/response tracking with futures and timeouts."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import uuid
from typing import TYPE_CHECKING, Any, Self, TypeVar

if TYPE_CHECKING:
    from collections.abc import Callable
    from types import TracebackType

    from griptape_nodes.api_client.client import Client

logger = logging.getLogger(__name__)

T = TypeVar("T")


class RequestClient:
    """Request/response client built on top of Client.

    Wraps a Client to provide request/response semantics on top of
    pub/sub messaging. Tracks pending requests by request_id and resolves/rejects
    futures when responses arrive. Supports timeouts for requests that don't
    receive responses.
    """

    def __init__(
        self,
        client: Client,
        request_topic_fn: Callable[[], str] | None = None,
        response_topic_fn: Callable[[], str] | None = None,
    ) -> None:
        """Initialize request/response client.

        Args:
            client: Client instance to use for communication
            request_topic_fn: Function to determine request topic (defaults to "request")
            response_topic_fn: Function to determine response topic (defaults to "response")
        """
        self.client = client
        self.request_topic_fn = request_topic_fn or (lambda: "request")
        self.response_topic_fn = response_topic_fn or (lambda: "response")

        # Map of request_id -> Future that will be resolved when response arrives
        self._pending_requests: dict[str, asyncio.Future] = {}
        self._lock = asyncio.Lock()

        # Track subscribed response topics
        self._subscribed_response_topics: set[str] = set()

        # Background task for listening to responses
        self._response_listener_task: asyncio.Task | None = None

    async def __aenter__(self) -> Self:
        """Async context manager entry: start response listener."""
        self._response_listener_task = asyncio.create_task(self._listen_for_responses())
        logger.debug("RequestClient started")
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        """Async context manager exit: stop response listener."""
        if self._response_listener_task:
            self._response_listener_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._response_listener_task
        logger.debug("RequestClient stopped")

    async def request(
        self, request_type: str, payload: dict[str, Any], timeout_ms: int | None = None
    ) -> dict[str, Any]:
        """Send a request and wait for its response.

        This method automatically:
        - Generates a request_id
        - Determines request and response topics
        - Subscribes to response topic if needed
        - Sends the request
        - Waits for and returns the response

        Args:
            request_type: Type of request to send
            payload: Request payload data
            timeout_ms: Optional timeout in milliseconds

        Returns:
            Response data from the server

        Raises:
            TimeoutError: If request times out
            Exception: If request fails
        """
        # Generate request ID and track it
        request_id = str(uuid.uuid4())
        payload["request_id"] = request_id

        response_future = await self._track_request(request_id)

        # Determine topics
        request_topic = self.request_topic_fn()
        response_topic = self.response_topic_fn()

        # Subscribe to response topic if not already subscribed
        if response_topic not in self._subscribed_response_topics:
            await self.client.subscribe(response_topic)
            self._subscribed_response_topics.add(response_topic)

        # Send the request as an EventRequest
        event_payload = {
            "event_type": "EventRequest",
            "request_type": request_type,
            "request": payload,
            "response_topic": response_topic,
        }

        logger.debug("Sending request %s: %s", request_id, request_type)

        try:
            await self.client.publish("EventRequest", event_payload, request_topic)

            # Wait for response with optional timeout
            if timeout_ms:
                timeout_sec = timeout_ms / 1000
                result = await asyncio.wait_for(response_future, timeout=timeout_sec)
            else:
                result = await response_future

        except TimeoutError:
            logger.error("Request %s timed out", request_id)
            await self._cancel_request(request_id)
            raise

        except Exception as e:
            logger.error("Request %s failed: %s", request_id, e)
            await self._cancel_request(request_id)
            raise
        else:
            logger.debug("Request %s completed successfully", request_id)
            return result

    async def _track_request(self, request_id: str) -> asyncio.Future:
        """Start tracking a request and return a future that will be resolved on response.

        Args:
            request_id: Unique identifier for this request

        Returns:
            Future that will be resolved when response arrives

        Raises:
            ValueError: If request_id is already being tracked
        """
        async with self._lock:
            if request_id in self._pending_requests:
                msg = f"Request ID already exists: {request_id}"
                raise ValueError(msg)

            future: asyncio.Future = asyncio.Future()
            self._pending_requests[request_id] = future
            logger.debug("Tracking request: %s", request_id)
            return future

    async def _resolve_request(self, request_id: str, result: Any) -> None:
        """Mark a request as successful and resolve its future with a result.

        Args:
            request_id: Request identifier
            result: Result data to return to the requester
        """
        async with self._lock:
            future = self._pending_requests.pop(request_id, None)

            if future is None:
                logger.warning("Received response for unknown request: %s", request_id)
                return

            if not future.done():
                future.set_result(result)
                logger.debug("Resolved request: %s", request_id)

    async def _reject_request(self, request_id: str, error: Exception) -> None:
        """Mark a request as failed and reject its future with an exception.

        Args:
            request_id: Request identifier
            error: Exception to raise for the requester
        """
        async with self._lock:
            future = self._pending_requests.pop(request_id, None)

            if future is None:
                logger.warning("Received error for unknown request: %s", request_id)
                return

            if not future.done():
                future.set_exception(error)
                logger.debug("Rejected request: %s with error: %s", request_id, error)

    async def _cancel_request(self, request_id: str) -> None:
        """Cancel a pending request and clean up its tracking.

        Args:
            request_id: Request identifier
        """
        async with self._lock:
            future = self._pending_requests.pop(request_id, None)

            if future is None:
                logger.debug("Request already completed or unknown: %s", request_id)
                return

            if not future.done():
                future.cancel()
                logger.debug("Cancelled request: %s", request_id)

    @property
    def pending_count(self) -> int:
        """Get number of currently pending requests.

        Returns:
            Count of pending requests
        """
        return len(self._pending_requests)

    @property
    def pending_request_ids(self) -> list[str]:
        """Get list of all pending request IDs.

        Returns:
            List of request_id strings
        """
        return list(self._pending_requests.keys())

    async def _listen_for_responses(self) -> None:
        """Listen for response messages from subscribed topics."""
        try:
            async for message in self.client.messages:
                try:
                    await self._handle_response(message)
                except Exception as e:
                    logger.error("Error handling response message: %s", e)
        except asyncio.CancelledError:
            logger.debug("Response listener cancelled")
            raise

    async def _handle_response(self, message: dict[str, Any]) -> None:
        """Handle response messages by resolving tracked requests.

        Args:
            message: WebSocket message containing response
        """
        message_type = message.get("type")

        # Only handle success/failure result messages
        if message_type not in ("success_result", "failure_result"):
            return

        payload = message.get("payload", {})
        request_id = payload.get("request", {}).get("request_id")

        if not request_id:
            logger.debug("Response message has no request_id")
            return

        if message_type == "success_result":
            result = payload.get("result", "Success")
            await self._resolve_request(request_id, result)
        else:
            error_msg = payload.get("result", {}).get("exception", "Unknown error") or "Unknown error"
            await self._reject_request(request_id, Exception(error_msg))
