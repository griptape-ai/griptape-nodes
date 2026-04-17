from __future__ import annotations

import asyncio
import inspect
import logging
import threading
from collections import defaultdict
from contextlib import contextmanager
from dataclasses import fields
from typing import TYPE_CHECKING, Any, cast

from asyncio_thread_runner import ThreadRunner
from typing_extensions import TypedDict, TypeVar

from griptape_nodes.exe_types.node_types import BaseNode
from griptape_nodes.retained_mode.events.base_events import (
    AppPayload,
    BaseEvent,
    EventRequest,
    EventResultFailure,
    EventResultSuccess,
    ForwardFromWorkerMixin,
    ProgressEvent,
    RequestPayload,
    ResultDetails,
    ResultPayload,
)
from griptape_nodes.retained_mode.events.event_converter import converter
from griptape_nodes.retained_mode.events.payload_registry import PayloadRegistry
from griptape_nodes.utils.async_utils import call_function

if TYPE_CHECKING:
    import types
    from collections.abc import Awaitable, Callable, Iterator

    from griptape_nodes.api_client.request_client import RequestClient


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
        # Worker-to-orchestrator forwarding state. Inert until
        # configure_worker_forwarding() is called at worker startup.
        self._worker_forwarding_enabled: bool = False
        self._worker_request_client: RequestClient | None = None
        self._orchestrator_request_topic: str | None = None
        self._worker_response_topic: str | None = None
        self._websocket_event_loop: asyncio.AbstractEventLoop | None = None
        self._forward_timeout_ms: int | None = None
        # Node-execution refcount. Incremented on worker_node_execution_scope entry,
        # decremented on exit. Plain instance state guarded by a lock so any thread
        # -- including threads spawned inside third-party libraries (diffusers,
        # transformers, etc.) during node execution -- can observe it via
        # _should_forward. ContextVar was tried first and lost the flag when
        # library-internal ThreadPoolExecutors ran node-emitted requests.
        self._node_execution_depth: int = 0
        self._node_execution_lock = threading.Lock()

    @property
    def event_queue(self) -> asyncio.Queue:
        if self._event_queue is None:
            msg = "Event queue has not been initialized. Please call 'initialize_queue' with an asyncio.Queue instance before accessing the event queue."
            raise ValueError(msg)
        return self._event_queue

    def should_suppress_event(self, event: BaseEvent | ProgressEvent) -> bool:
        """Check if events should be suppressed from being sent to websockets.

        This method checks both the wrapper event type and the payload type for wrapped events.
        For example, if InvolvedNodesEvent is in the suppression set, an ExecutionGriptapeNodeEvent
        that wraps an InvolvedNodesEvent will be suppressed.
        """
        event_type = type(event)

        # Check wrapper type first
        if self._event_suppression_counts.get(event_type, 0) > 0:
            return True

        # For wrapped events (like ExecutionGriptapeNodeEvent), also check the payload type
        wrapped_event = getattr(event, "wrapped_event", None)
        if wrapped_event is not None:
            payload = getattr(wrapped_event, "payload", None)
            if payload is not None:
                payload_type = type(payload)
                if self._event_suppression_counts.get(payload_type, 0) > 0:
                    return True

        return False

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

    def configure_worker_forwarding(
        self,
        *,
        request_client: RequestClient,
        orchestrator_request_topic: str,
        worker_response_topic: str,
        websocket_event_loop: asyncio.AbstractEventLoop,
        timeout_ms: int | None = None,
    ) -> None:
        """Enable worker -> orchestrator forwarding for requests originated from node execution.

        Called once at worker startup after the RequestClient is constructed and topics
        are subscribed. Inert on the orchestrator (never called there).

        websocket_event_loop is the loop that owns the Client/RequestClient (the daemon
        thread's loop). All RequestClient primitives -- its asyncio.Lock, the pending-
        request Future, and the _try_match filter that claims responses -- are bound to
        that loop. Forwarding calls must be dispatched there via run_coroutine_threadsafe;
        awaiting RequestClient methods directly from the main loop or a ThreadRunner loop
        causes cross-loop contention that stalls for seconds per request.
        """
        self._worker_request_client = request_client
        self._orchestrator_request_topic = orchestrator_request_topic
        self._worker_response_topic = worker_response_topic
        self._websocket_event_loop = websocket_event_loop
        self._forward_timeout_ms = timeout_ms
        self._worker_forwarding_enabled = True

    @contextmanager
    def worker_node_execution_scope(self) -> Iterator[None]:
        """Mark this worker as actively executing a node.

        Increments a thread-safe refcount on entry and decrements on exit.
        While the refcount is > 0, requests marked ForwardFromWorkerMixin
        dispatched on this worker are forwarded to the orchestrator.

        The refcount is plain instance state guarded by a lock, so any
        thread -- including threads spawned internally by third-party
        libraries (diffusers, transformers) during node execution --
        observes the same value. A ContextVar was tried first and lost
        the flag when library-internal ThreadPoolExecutors emitted
        requests.

        Opened by NodeManager._hydrate_and_run_node around node.aprocess()
        inside the ExecuteNodeRequest handler. Bootstrap paths and
        AppInitializationComplete fan-out are not wrapped and therefore
        never forward.
        """
        with self._node_execution_lock:
            self._node_execution_depth += 1
        try:
            yield
        finally:
            with self._node_execution_lock:
                self._node_execution_depth -= 1

    def _in_node_execution(self) -> bool:
        """Return True when this worker is currently inside a node-execution scope."""
        with self._node_execution_lock:
            return self._node_execution_depth > 0

    def _should_forward(self, request: RequestPayload) -> bool:
        """Return True when this request should be forwarded to the orchestrator.

        Forwarding is active only when:
          (1) configure_worker_forwarding has been called (we're on a worker),
          (2) the request type is marked ForwardFromWorkerMixin (opt-in),
          (3) the worker is currently inside a worker_node_execution_scope
              (i.e. the request originated from node execution, not bootstrap).

        ExecuteNodeRequest is excluded structurally: the scope is opened by
        NodeManager._hydrate_and_run_node around node.aprocess(), *inside* the
        ExecuteNodeRequest handler. The request that enters the handler runs
        outside the scope, so forwarding naturally skips it.
        """
        if not self._worker_forwarding_enabled:
            return False
        if not isinstance(request, ForwardFromWorkerMixin):
            return False
        return self._in_node_execution()

    async def _forward_to_orchestrator(
        self,
        request: RP,
        result_context: ResultContext,
    ) -> EventResultSuccess | EventResultFailure:
        """Forward a worker-originated request to the orchestrator and structure its reply.

        Wraps the request in an EventRequest, awaits the orchestrator's EventResult
        payload, and reconstructs it as an EventResultSuccess/EventResultFailure whose
        shape matches the locally-dispatched path.

        The RequestClient send/track/await happens on the websocket event loop
        (configured via configure_worker_forwarding) so that its asyncio.Lock and
        the pending-request Future live on the same loop as the _try_match filter
        that resolves them. Awaiting those primitives from any other loop causes
        cross-loop contention that stalls for seconds.
        """
        if (
            self._worker_request_client is None
            or self._orchestrator_request_topic is None
            or self._worker_response_topic is None
            or self._websocket_event_loop is None
        ):
            msg = "Worker forwarding is enabled but not fully configured."
            raise RuntimeError(msg)

        event_request: EventRequest = EventRequest(request=request)

        response_future = asyncio.run_coroutine_threadsafe(
            self._worker_request_client.request_to_orchestrator(
                event_request=event_request,
                orchestrator_request_topic=self._orchestrator_request_topic,
                worker_response_topic=self._worker_response_topic,
                timeout_ms=self._forward_timeout_ms,
            ),
            self._websocket_event_loop,
        )
        response_payload = await asyncio.wrap_future(response_future)

        event_type = response_payload.get("event_type", "")
        result_type_name = response_payload.get("result_type")
        result_data = response_payload.get("result", {})

        if not result_type_name:
            msg = f"Forwarded response for {type(request).__name__} missing 'result_type'."
            raise RuntimeError(msg)

        resolved_result_type = PayloadRegistry.get_type(result_type_name)
        if resolved_result_type is None:
            msg = f"Forwarded response 'result_type' is not registered: {result_type_name}"
            raise RuntimeError(msg)

        result_payload = cast("ResultPayload", converter.structure(result_data, resolved_result_type))

        event_cls: type[EventResultSuccess | EventResultFailure]
        event_cls = EventResultSuccess if event_type == "EventResultSuccess" else EventResultFailure

        return event_cls(
            request=request,
            request_id=result_context.get("request_id"),
            result=result_payload,
            response_topic=result_context.get("response_topic"),
        )

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

        if self._should_forward(request):
            return await self._forward_to_orchestrator(request, result_context)

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

        if self._should_forward(request):
            try:
                asyncio.get_running_loop()
                with ThreadRunner() as runner:
                    return runner.run(self._forward_to_orchestrator(request, result_context))
            except RuntimeError:
                return asyncio.run(self._forward_to_orchestrator(request, result_context))

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

    def broadcast_app_event(self, app_event: AP) -> None:
        """Broadcast an app event to all registered listeners (sync version).

        Args:
            app_event: The app event to broadcast
        """
        app_event_type = type(app_event)
        if app_event_type in self._app_event_listeners:
            listener_set = self._app_event_listeners[app_event_type]

            # Support async callbacks for sync method
            async def _broadcast_async() -> None:
                async with asyncio.TaskGroup() as tg:
                    for listener_callback in listener_set:
                        tg.create_task(call_function(listener_callback, app_event))

            try:
                asyncio.get_running_loop()
                with ThreadRunner() as runner:
                    runner.run(_broadcast_async())
            except RuntimeError:
                # No event loop running, safe to use asyncio.run
                asyncio.run(_broadcast_async())

    async def abroadcast_app_event(self, app_event: AP) -> None:
        """Broadcast an app event to all registered listeners (async version).

        Args:
            app_event: The app event to broadcast
        """
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
        self.original_aput_event: Any = None

    def __enter__(self) -> None:
        """Enter the context and start translating events."""
        self.original_put_event = self.manager.put_event
        self.original_aput_event = self.manager.aput_event
        self.manager.put_event = self._translate_and_put  # type: ignore[method-assign]
        self.manager.aput_event = self._translate_and_aput  # type: ignore[method-assign]

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        exc_traceback: types.TracebackType | None,
    ) -> None:
        """Exit the context and restore original event sending."""
        self.manager.put_event = self.original_put_event  # type: ignore[method-assign]
        self.manager.aput_event = self.original_aput_event  # type: ignore[method-assign]

    def _translate_event(self, event: Any) -> Any:
        """Translate node names in an event.

        Args:
            event: The event to potentially translate

        Returns:
            The translated event, or the original if no translation needed
        """
        # Handle wrapped events (like ExecutionGriptapeNodeEvent)
        wrapped_event = getattr(event, "wrapped_event", None)
        if wrapped_event is not None:
            payload = getattr(wrapped_event, "payload", None)
            if payload is not None:
                translated_payload = self._translate_payload(payload)
                if translated_payload is not payload:
                    # Create a new wrapped event with the translated payload
                    translated_event = self._create_translated_wrapped_event(event, translated_payload)
                    if translated_event is not None:
                        return translated_event

        # Check if event has node_name attribute and needs translation
        if hasattr(event, "node_name"):
            node_name = event.node_name
            if node_name in self.node_name_mapping:
                # Create a copy of the event with the translated node name
                return self._copy_event_with_translated_name(event)

        return event

    def _translate_and_put(self, event: Any) -> None:
        """Translate node names in events and put them in the queue (sync version).

        Args:
            event: The event to potentially translate and send
        """
        translated_event = self._translate_event(event)
        self.original_put_event(translated_event)

    async def _translate_and_aput(self, event: Any) -> None:
        """Translate node names in events and put them in the queue (async version).

        Args:
            event: The event to potentially translate and send
        """
        translated_event = self._translate_event(event)
        await self.original_aput_event(translated_event)

    def _translate_payload(self, payload: Any) -> Any:
        """Translate node names in a payload.

        Handles both single node_name and involved_nodes list.

        Args:
            payload: The payload to translate

        Returns:
            A new payload with translated names, or the original if no translation needed
        """
        # Handle involved_nodes list (e.g., InvolvedNodesEvent)
        involved_nodes = getattr(payload, "involved_nodes", None)
        if involved_nodes is not None and isinstance(involved_nodes, list):
            translated_nodes: list[str] = []
            any_translated = False
            for node_name in involved_nodes:
                if node_name in self.node_name_mapping:
                    translated_nodes.append(self.node_name_mapping[node_name])
                    any_translated = True
                else:
                    translated_nodes.append(node_name)
            # Only create new payload if something was translated
            if any_translated:
                return self._copy_payload_with_translated_involved_nodes(payload, translated_nodes)

        # Handle single node_name
        node_name = getattr(payload, "node_name", None)
        if node_name is not None and node_name in self.node_name_mapping:
            return self._copy_payload_with_translated_node_name(payload, self.node_name_mapping[node_name])

        return payload

    def _copy_payload_with_translated_involved_nodes(self, payload: Any, translated_nodes: list[str]) -> Any:
        """Create a copy of a payload with translated involved_nodes.

        Args:
            payload: The payload to copy
            translated_nodes: The translated list of node names

        Returns:
            A new payload instance with translated involved_nodes
        """
        payload_class = type(payload)

        if hasattr(payload, "model_dump"):
            payload_dict = payload.model_dump()
        elif hasattr(payload, "__dict__"):
            payload_dict = payload.__dict__.copy()
        else:
            return payload

        payload_dict["involved_nodes"] = translated_nodes

        try:
            return payload_class(**payload_dict)
        except Exception:
            return payload

    def _copy_payload_with_translated_node_name(self, payload: Any, translated_name: str) -> Any:
        """Create a copy of a payload with a translated node_name.

        Args:
            payload: The payload to copy
            translated_name: The translated node name

        Returns:
            A new payload instance with translated node_name
        """
        payload_class = type(payload)

        if hasattr(payload, "model_dump"):
            payload_dict = payload.model_dump()
        elif hasattr(payload, "__dict__"):
            payload_dict = payload.__dict__.copy()
        else:
            return payload

        payload_dict["node_name"] = translated_name

        try:
            return payload_class(**payload_dict)
        except Exception:
            return payload

    def _create_translated_wrapped_event(self, event: Any, translated_payload: Any) -> Any | None:
        """Create a new wrapped event with a translated payload.

        Args:
            event: The original wrapped event (e.g., ExecutionGriptapeNodeEvent)
            translated_payload: The translated payload

        Returns:
            A new wrapped event with the translated payload, or None if creation fails
        """
        wrapped_event = getattr(event, "wrapped_event", None)
        if wrapped_event is None:
            return None

        # Create new wrapped_event with translated payload
        wrapped_class = type(wrapped_event)
        try:
            new_wrapped = wrapped_class(payload=translated_payload)
        except Exception:
            return None

        # Create new outer event with new wrapped_event
        event_class = type(event)
        try:
            return event_class(wrapped_event=new_wrapped)
        except Exception:
            return None

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
