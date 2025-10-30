from __future__ import annotations

import asyncio
import inspect
import threading
from collections import defaultdict
from dataclasses import fields
from typing import TYPE_CHECKING, Any, cast

from asyncio_thread_runner import ThreadRunner
from typing_extensions import TypedDict, TypeVar

from griptape_nodes.retained_mode.events.base_events import (
    AppPayload,
    EventRequest,
    EventResultFailure,
    EventResultSuccess,
    FlushParameterChangesRequest,
    FlushParameterChangesResultSuccess,
    RequestPayload,
    ResultPayload,
)
from griptape_nodes.utils.async_utils import call_function

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable


RP = TypeVar("RP", bound=RequestPayload, default=RequestPayload)
AP = TypeVar("AP", bound=AppPayload, default=AppPayload)

# Result types that should NOT trigger a flush request.
#
# After most requests complete, we queue a FlushParameterChangesRequest to flush any tracked
# parameter changes to the UI. However, when the FlushParameterChangesRequest itself completes,
# it returns a FlushParameterChangesResultSuccess. If we don't exclude this result type, it would
# trigger another FlushParameterChangesRequest, which would return another FlushParameterChangesResultSuccess,
# creating an infinite loop of flush requests.
#
# Add result types to this set if they should never trigger a flush (typically because they ARE
# the flush operation itself, or other internal operations that don't modify workflow state).
RESULT_TYPES_THAT_SKIP_FLUSH = {FlushParameterChangesResultSuccess}


class ResultContext(TypedDict, total=False):
    response_topic: str | None
    request_id: str | None


class EventManager:
    def __init__(self) -> None:
        # Dictionary to store the SPECIFIC manager for each request type
        self._request_type_to_manager: dict[type[RequestPayload], Callable] = defaultdict(list)  # pyright: ignore[reportAttributeAccessIssue]
        # Dictionary to store ALL SUBSCRIBERS to app events.
        self._app_event_listeners: dict[type[AppPayload], set[Callable]] = {}
        # Boolean that lets us know if there is currently a FlushParameterChangesRequest in the event queue.
        self._flush_in_queue: bool = False
        # Event queue for publishing events
        self._event_queue: asyncio.Queue | None = None
        # Keep track of which thread the event loop runs on
        self._loop_thread_id: int | None = None
        # Keep a reference to the event loop for thread-safe operations
        self._event_loop: asyncio.AbstractEventLoop | None = None

    @property
    def event_queue(self) -> asyncio.Queue:
        if self._event_queue is None:
            msg = "Event queue has not been initialized. Please call 'initialize_queue' with an asyncio.Queue instance before accessing the event queue."
            raise ValueError(msg)
        return self._event_queue

    def clear_flush_in_queue(self) -> None:
        self._flush_in_queue = False

    def initialize_queue(self, queue: asyncio.Queue | None = None) -> None:
        """Set the event queue for this manager.

        Args:
            queue: The asyncio.Queue to use for events, or None to clear
        """
        if queue is not None:
            self._event_queue = queue
            # Track which thread the event loop is running on and store loop reference
            try:
                self._event_loop = asyncio.get_running_loop()
                self._loop_thread_id = threading.get_ident()
            except RuntimeError:
                self._event_loop = None
                self._loop_thread_id = None
        else:
            try:
                self._event_queue = asyncio.Queue()
                self._event_loop = asyncio.get_running_loop()
                self._loop_thread_id = threading.get_ident()
            except RuntimeError:
                # Defer queue creation until we're in an event loop
                self._event_queue = None
                self._event_loop = None
                self._loop_thread_id = None

    def _is_cross_thread_call(self) -> bool:
        """Check if the current call is from a different thread than the event loop.

        Returns:
            True if we're on a different thread and need thread-safe operations
        """
        current_thread_id = threading.get_ident()
        return (
            self._loop_thread_id is not None
            and current_thread_id != self._loop_thread_id
            and self._event_loop is not None
        )

    def put_event(self, event: Any) -> None:
        """Put event into async queue from sync context (non-blocking).

        Automatically detects if we're in a different thread and uses thread-safe operations.

        Args:
            event: The event to publish to the queue
        """
        if self._event_queue is None:
            return

        if self._is_cross_thread_call() and self._event_loop is not None:
            # We're in a different thread from the event loop, use thread-safe method
            # _is_cross_thread_call() guarantees _event_loop is not None
            self._event_loop.call_soon_threadsafe(self._event_queue.put_nowait, event)
        else:
            # We're on the same thread as the event loop or no loop thread tracked, use direct method
            self._event_queue.put_nowait(event)

    async def aput_event(self, event: Any) -> None:
        """Put event into async queue from async context.

        Automatically detects if we're in a different thread and uses thread-safe operations.

        Args:
            event: The event to publish to the queue
        """
        if self._event_queue is None:
            return

        if self._is_cross_thread_call() and self._event_loop is not None:
            # We're in a different thread from the event loop, use thread-safe method
            # _is_cross_thread_call() guarantees _event_loop is not None
            self._event_loop.call_soon_threadsafe(self._event_queue.put_nowait, event)
        else:
            # We're on the same thread as the event loop or no loop thread tracked, use async method
            await self._event_queue.put(event)

    def assign_manager_to_request_type(
        self,
        request_type: type[RP],
        callback: Callable[[RP], ResultPayload] | Callable[[RP], Awaitable[ResultPayload]],
    ) -> None:
        """Assign a manager to handle a request.

        Args:
            request_type: The type of request to assign the manager to
            callback: Function to be called when event occurs
        """
        existing_manager = self._request_type_to_manager.get(request_type)
        if existing_manager is not None:
            msg = f"Attempted to assign an event of type {request_type} to manager {callback.__name__}, but that request is already assigned to manager {existing_manager.__name__}."
            raise ValueError(msg)
        self._request_type_to_manager[request_type] = callback

    def remove_manager_from_request_type(self, request_type: type[RP]) -> None:
        """Unsubscribe the manager from the request of a specific type.

        Args:
            request_type: The type of request to unsubscribe from
        """
        if request_type in self._request_type_to_manager:
            del self._request_type_to_manager[request_type]

    def _handle_request_core(
        self,
        request: RP,
        callback_result: ResultPayload,
        *,
        context: ResultContext,
    ) -> EventResultSuccess | EventResultFailure:
        """Core logic for handling requests, shared between sync and async methods."""
        from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

        operation_depth_mgr = GriptapeNodes.OperationDepthManager()
        workflow_mgr = GriptapeNodes.WorkflowManager()

        with operation_depth_mgr as depth_manager:
            # Now see if the WorkflowManager was asking us to squelch altered_workflow_state commands
            # This prevents situations like loading a workflow (which naturally alters the workflow state)
            # from coming in and immediately being flagged as being dirty.
            if workflow_mgr.should_squelch_workflow_altered():
                callback_result.altered_workflow_state = False

            retained_mode_str = None
            # If request_id exists, that means it's a direct request from the GUI (not internal), and should be echoed by retained mode.
            if depth_manager.is_top_level() and context.get("request_id") is not None:
                retained_mode_str = depth_manager.request_retained_mode_translation(request)

            # Some requests have fields marked as "omit_from_result" which should be removed from the request
            for field in fields(request):
                if field.metadata.get("omit_from_result", False):
                    setattr(request, field.name, None)
            if callback_result.succeeded():
                result_event = EventResultSuccess(
                    request=request,
                    request_id=context.get("request_id"),
                    result=callback_result,
                    retained_mode=retained_mode_str,
                    response_topic=context.get("response_topic"),
                )
            else:
                result_event = EventResultFailure(
                    request=request,
                    request_id=context.get("request_id"),
                    result=callback_result,
                    retained_mode=retained_mode_str,
                    response_topic=context.get("response_topic"),
                )

        return result_event

    async def ahandle_request(
        self,
        request: RP,
        *,
        result_context: ResultContext | None = None,
    ) -> EventResultSuccess | EventResultFailure:
        """Publish an event to the manager assigned to its type.

        Args:
            request: The request to handle
            result_context: The result context containing response_topic and request_id
        """
        from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

        operation_depth_mgr = GriptapeNodes.OperationDepthManager()
        if result_context is None:
            result_context = ResultContext()

        # Notify the manager of the event type
        request_type = type(request)
        callback = self._request_type_to_manager.get(request_type)
        if not callback:
            msg = f"No manager found to handle request of type '{request_type.__name__}'."
            raise TypeError(msg)

        # Actually make the handler callback (support both sync and async):
        result_payload: ResultPayload = await call_function(callback, request)

        # Queue flush request for async context (unless result type should skip flush)
        with operation_depth_mgr:
            if not self._flush_in_queue and type(result_payload) not in RESULT_TYPES_THAT_SKIP_FLUSH:
                await self.aput_event(EventRequest(request=FlushParameterChangesRequest()))
                self._flush_in_queue = True

        return self._handle_request_core(
            request,
            cast("ResultPayload", result_payload),
            context=result_context,
        )

    def handle_request(
        self,
        request: RP,
        *,
        result_context: ResultContext | None = None,
    ) -> EventResultSuccess | EventResultFailure:
        """Publish an event to the manager assigned to its type (sync version).

        Args:
            request: The request to handle
            result_context: The result context containing response_topic and request_id
        """
        from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

        operation_depth_mgr = GriptapeNodes.OperationDepthManager()
        if result_context is None:
            result_context = ResultContext()

        # Notify the manager of the event type
        request_type = type(request)
        callback = self._request_type_to_manager.get(request_type)
        if not callback:
            msg = f"No manager found to handle request of type '{request_type.__name__}'."
            raise TypeError(msg)

        # Support async callbacks for sync method ONLY if there is no running event loop
        if inspect.iscoroutinefunction(callback):
            try:
                asyncio.get_running_loop()
                with ThreadRunner() as runner:
                    result_payload: ResultPayload = runner.run(callback(request))
            except RuntimeError:
                # No event loop running, safe to use asyncio.run
                result_payload: ResultPayload = asyncio.run(callback(request))
        else:
            result_payload: ResultPayload = callback(request)

        # Queue flush request for sync context (unless result type should skip flush)
        with operation_depth_mgr:
            if not self._flush_in_queue and type(result_payload) not in RESULT_TYPES_THAT_SKIP_FLUSH:
                self.put_event(EventRequest(request=FlushParameterChangesRequest()))
                self._flush_in_queue = True

        return self._handle_request_core(
            request,
            cast("ResultPayload", result_payload),
            context=result_context,
        )

    def add_listener_to_app_event(
        self, app_event_type: type[AP], callback: Callable[[AP], None] | Callable[[AP], Awaitable[None]]
    ) -> None:
        listener_set = self._app_event_listeners.get(app_event_type)
        if listener_set is None:
            listener_set = set()
            self._app_event_listeners[app_event_type] = listener_set

        listener_set.add(callback)

    def remove_listener_for_app_event(
        self, app_event_type: type[AP], callback: Callable[[AP], None] | Callable[[AP], Awaitable[None]]
    ) -> None:
        listener_set = self._app_event_listeners[app_event_type]
        listener_set.remove(callback)

    async def broadcast_app_event(self, app_event: AP) -> None:
        app_event_type = type(app_event)
        if app_event_type in self._app_event_listeners:
            listener_set = self._app_event_listeners[app_event_type]

            async with asyncio.TaskGroup() as tg:
                for listener_callback in listener_set:
                    tg.create_task(call_function(listener_callback, app_event))
