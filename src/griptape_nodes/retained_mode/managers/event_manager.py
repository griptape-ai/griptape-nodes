from __future__ import annotations

import asyncio
import inspect
import logging
import threading
from collections import defaultdict
from dataclasses import fields
from typing import TYPE_CHECKING, Any, cast

from asyncio_thread_runner import ThreadRunner
from typing_extensions import TypedDict, TypeVar

from griptape_nodes.exe_types.node_types import BaseNode
from griptape_nodes.retained_mode.events.base_events import (
    AppPayload,
    BaseEvent,
    EventResultFailure,
    EventResultSuccess,
    ProgressEvent,
    RequestPayload,
    ResultDetails,
    ResultPayload,
)
from griptape_nodes.utils.async_utils import call_function

if TYPE_CHECKING:
    import types
    from collections.abc import Awaitable, Callable


RP = TypeVar("RP", bound=RequestPayload, default=RequestPayload)
AP = TypeVar("AP", bound=AppPayload, default=AppPayload)

# Result types that should NOT trigger a flush request.
#
# Add result types to this set if they should never trigger a flush (typically because they ARE
# the flush operation itself, or other internal operations that don't modify workflow state).
RESULT_TYPES_THAT_SKIP_FLUSH = {}


class ResultContext(TypedDict, total=False):
    response_topic: str | None
    request_id: str | None


class EventManager:
    def __init__(self) -> None:
        # Dictionary to store the SPECIFIC manager for each request type
        self._request_type_to_manager: dict[type[RequestPayload], Callable] = defaultdict(list)  # pyright: ignore[reportAttributeAccessIssue]
        # Dictionary to store ALL SUBSCRIBERS to app events.
        self._app_event_listeners: dict[type[AppPayload], set[Callable]] = {}
        # Event queue for publishing events
        self._event_queue: asyncio.Queue | None = None
        # Keep track of which thread the event loop runs on
        self._loop_thread_id: int | None = None
        # Keep a reference to the event loop for thread-safe operations
        self._event_loop: asyncio.AbstractEventLoop | None = None
        # Per-event reference counting for event suppression
        self._event_suppression_counts: dict[type, int] = {}

    @property
    def event_queue(self) -> asyncio.Queue:
        if self._event_queue is None:
            msg = "Event queue has not been initialized. Please call 'initialize_queue' with an asyncio.Queue instance before accessing the event queue."
            raise ValueError(msg)
        return self._event_queue

    def should_suppress_event(self, event: BaseEvent | ProgressEvent) -> bool:
        """Check if events should be suppressed from being sent to websockets."""
        event_type = type(event)
        return self._event_suppression_counts.get(event_type, 0) > 0

    def clear_event_suppression(self) -> None:
        """Clear all event suppression counts."""
        self._event_suppression_counts.clear()

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

    def _override_result_log_level(self, result: ResultPayload, level: int) -> None:
        """Override the log level on all result details.

        Args:
            result: The result payload to modify
            level: The new log level to set
        """
        if isinstance(result.result_details, ResultDetails):
            for detail in result.result_details.result_details:
                detail.level = level

    def _log_result_details(self, result: ResultPayload) -> None:
        """Log the result details at their specified levels.

        Args:
            result: The result payload containing details to log
        """
        if isinstance(result.result_details, ResultDetails):
            logger = logging.getLogger("griptape_nodes")
            for detail in result.result_details.result_details:
                logger.log(detail.level, detail.message)

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

            # Override failure log level if requested
            if callback_result.failed() and request.failure_log_level is not None:
                self._override_result_log_level(callback_result, request.failure_log_level)

            # Log result details (after potential level override)
            self._log_result_details(callback_result)

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
            if type(result_payload) not in RESULT_TYPES_THAT_SKIP_FLUSH:
                self._flush_tracked_parameter_changes()

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
            if type(result_payload) not in RESULT_TYPES_THAT_SKIP_FLUSH:
                self._flush_tracked_parameter_changes()

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

    def _flush_tracked_parameter_changes(self) -> None:
        from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

        obj_manager = GriptapeNodes.ObjectManager()
        # Get all flows and their nodes
        nodes = obj_manager.get_filtered_subset(type=BaseNode)
        for node in nodes.values():
            # Only flush if there are actually tracked parameters
            if node._tracked_parameters:
                node.emit_parameter_changes()


class EventSuppressionContext:
    """Context manager to suppress events from being sent to websockets.

    Use this to prevent internal operations (like deserialization/deletion of iteration flows)
    from sending events to the GUI while still allowing the operations to complete normally.

    Uses per-event reference counting to track nested suppression contexts.
    Each event type maintains its own reference count, and is only unsuppressed
    when its count reaches zero.
    """

    events_to_suppress: set[type]

    def __init__(self, manager: EventManager, events_to_suppress: set[type]):
        self.manager = manager
        self.events_to_suppress = events_to_suppress

    def __enter__(self) -> None:
        for event_type in self.events_to_suppress:
            current_count = self.manager._event_suppression_counts.get(event_type, 0)
            self.manager._event_suppression_counts[event_type] = current_count + 1

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        exc_traceback: types.TracebackType | None,
    ) -> None:
        for event_type in self.events_to_suppress:
            current_count = self.manager._event_suppression_counts.get(event_type, 0)
            if current_count <= 1:
                self.manager._event_suppression_counts.pop(event_type, None)
            else:
                self.manager._event_suppression_counts[event_type] = current_count - 1


class EventTranslationContext:
    """Context manager to translate node names in events from packaged to original names.

    Use this to make loop execution events reference the original nodes that the user placed,
    rather than the packaged node copies. This allows the UI to highlight the correct nodes
    during loop execution.
    """

    def __init__(self, manager: EventManager, node_name_mapping: dict[str, str]):
        """Initialize the event translation context.

        Args:
            manager: The EventManager to intercept events from
            node_name_mapping: Dict mapping packaged node names to original node names
        """
        self.manager = manager
        self.node_name_mapping = node_name_mapping
        self.original_put_event: Any = None

    def __enter__(self) -> None:
        """Enter the context and start translating events."""
        self.original_put_event = self.manager.put_event
        self.manager.put_event = self._translate_and_put  # type: ignore[method-assign]

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        exc_traceback: types.TracebackType | None,
    ) -> None:
        """Exit the context and restore original event sending."""
        self.manager.put_event = self.original_put_event  # type: ignore[method-assign]

    def _translate_and_put(self, event: Any) -> None:
        """Translate node names in events and put them in the queue.

        Args:
            event: The event to potentially translate and send
        """
        # Check if event has node_name attribute and needs translation
        if hasattr(event, "node_name"):
            node_name = event.node_name
            if node_name in self.node_name_mapping:
                # Create a copy of the event with the translated node name
                translated_event = self._copy_event_with_translated_name(event)
                self.original_put_event(translated_event)
                return

        # No translation needed, send as-is
        self.original_put_event(event)

    def _copy_event_with_translated_name(self, event: Any) -> Any:
        """Create a copy of an event with the node name translated to the original name.

        Args:
            event: The event to copy and translate

        Returns:
            A new event instance with the translated node name
        """
        # Get the original node name from the mapping
        node_name = event.node_name
        original_node_name = self.node_name_mapping[node_name]

        # Get the event class
        event_class = type(event)

        # Create a dict of all event attributes
        if hasattr(event, "model_dump"):
            event_dict = event.model_dump()
        elif hasattr(event, "__dict__"):
            event_dict = event.__dict__.copy()
        else:
            # Can't copy this event, return as-is
            return event

        # Replace the node name with the original name
        event_dict["node_name"] = original_node_name

        # Create a new event instance with the translated name
        try:
            return event_class(**event_dict)
        except Exception:
            # If we can't create a new instance, return the original
            return event
