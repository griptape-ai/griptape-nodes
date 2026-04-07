"""Request/response tracking with futures and timeouts."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import uuid
from typing import TYPE_CHECKING, Any, Self

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable
    from types import TracebackType

    from griptape_nodes.api_client.client import Client

logger = logging.getLogger(__name__)


class RequestClient:
    """Request/response client built on top of Client.

    Wraps a Client to provide request/response semantics on top of
    pub/sub messaging. Tracks pending requests by request_id and resolves/rejects
    futures when responses arrive. Supports timeouts for requests that don't
    receive responses.

    When used as the sole consumer of client.messages (i.e. no separate
    _process_incoming_messages loop), pass an unhandled_handler to receive
    messages that do not match a pending request.
    """

    def __init__(
        self,
        client: Client,
        request_topic_fn: Callable[[], str] | None = None,
        response_topic_fn: Callable[[], str] | None = None,
        unhandled_handler: Callable[[dict], Awaitable[None]] | None = None,
    ) -> None:
        """Initialize request/response client.

        Args:
            client: Client instance to use for communication
            request_topic_fn: Function to determine request topic (defaults to "request")
            response_topic_fn: Function to determine response topic (defaults to "response")
            unhandled_handler: Async callback for messages not matched to a pending request
        """
        self.client = client
        self.request_topic_fn = request_topic_fn or (lambda: "request")
        self.response_topic_fn = response_topic_fn or (lambda: "response")
        self._unhandled_handler = unhandled_handler

        # Map of request_id -> (Future, tag) where tag identifies the originating worker/caller
        self._pending_requests: dict[str, tuple[asyncio.Future, str]] = {}
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
        self,
        request_type: str,
        payload: dict[str, Any],
        topic: str | None = None,
        timeout_ms: int | None = None,
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
            topic: Optional per-call request topic override (defaults to request_topic_fn())
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
        request_topic = topic or self.request_topic_fn()
        response_topic = self.response_topic_fn()

        # Subscribe to response topic if not already subscribed
        if response_topic not in self._subscribed_response_topics:
            await self.client.subscribe(response_topic)
            self._subscribed_response_topics.add(response_topic)

        # Send the request as an EventRequest
        event_payload = {
            "event_type": "EventRequest",
            "request_type": request_type,
            "request_id": request_id,
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

    async def track_request(self, request_id: str, tag: str = "") -> asyncio.Future:
        """Register a future for an outgoing request and return it.

        Use this when the send path is handled externally (e.g. WorkerManager
        sends via forward_event_to_worker) and only the future tracking is needed.
        The future is resolved when _handle_response matches the request_id.

        Args:
            request_id: Unique identifier for this request
            tag: Optional tag for grouping related requests (e.g. worker_engine_id)

        Returns:
            Future that will be resolved when the matching response arrives
        """
        return await self._track_request(request_id, tag=tag)

    async def cancel_requests_by_tag(self, tag: str) -> None:
        """Cancel all pending futures that were registered with the given tag.

        Args:
            tag: The tag value used when track_request was called (e.g. worker_engine_id)
        """
        async with self._lock:
            to_cancel = [rid for rid, (_, t) in self._pending_requests.items() if t == tag]
            for rid in to_cancel:
                future, _ = self._pending_requests.pop(rid)
                if not future.done():
                    future.cancel()
                    logger.debug("Cancelled request %s (tag=%s)", rid, tag)

    async def _track_request(self, request_id: str, tag: str = "") -> asyncio.Future:
        """Start tracking a request and return a future that will be resolved on response.

        Args:
            request_id: Unique identifier for this request
            tag: Optional tag for grouping (e.g. worker_engine_id)

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
            self._pending_requests[request_id] = (future, tag)
            logger.debug("Tracking request: %s (tag=%s)", request_id, tag)
            return future

    async def _resolve_request(self, request_id: str, result: Any) -> None:
        """Mark a request as successful and resolve its future with a result.

        Args:
            request_id: Request identifier
            result: Result data to return to the requester
        """
        async with self._lock:
            entry = self._pending_requests.pop(request_id, None)

            if entry is None:
                logger.warning("Received response for unknown request: %s", request_id)
                return

            future, _ = entry
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
            entry = self._pending_requests.pop(request_id, None)

            if entry is None:
                logger.warning("Received error for unknown request: %s", request_id)
                return

            future, _ = entry
            if not future.done():
                future.set_exception(error)
                logger.debug("Rejected request: %s with error: %s", request_id, error)

    async def _cancel_request(self, request_id: str) -> None:
        """Cancel a pending request and clean up its tracking.

        Args:
            request_id: Request identifier
        """
        async with self._lock:
            entry = self._pending_requests.pop(request_id, None)

            if entry is None:
                logger.debug("Request already completed or unknown: %s", request_id)
                return

            future, _ = entry
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
                    handled = await self._handle_response(message)
                    if not handled and self._unhandled_handler:
                        await self._unhandled_handler(message)
                except Exception as e:
                    logger.error("Error handling response message: %s", e)
        except asyncio.CancelledError:
            logger.debug("Response listener cancelled")
            raise

    async def _handle_response(self, message: dict[str, Any]) -> bool:
        """Handle response messages by resolving tracked requests.

        Expects worker/event-bus response format:
          payload["event_type"] in ("EventResultSuccess", "EventResultFailure")
          payload["request_id"] = UUID (outer event request_id)
          Resolves with the full payload dict.

        Args:
            message: WebSocket message containing response

        Returns:
            True if the message was matched to a pending request and resolved/rejected,
            False otherwise (caller may pass to unhandled_handler).
        """
        payload = message.get("payload", {})

        request_id = payload.get("request_id") or ""
        if not request_id or request_id not in self._pending_requests:
            return False

        event_type = payload.get("event_type", "")
        if event_type == "EventResultSuccess":
            await self._resolve_request(request_id, payload)
            return True
        if event_type == "EventResultFailure":
            result = payload.get("result", {})
            error_msg = str(result.get("result_details") or result.get("exception") or "Unknown error")
            await self._reject_request(request_id, Exception(error_msg))
            return True

        return False
