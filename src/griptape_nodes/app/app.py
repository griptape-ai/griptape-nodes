from __future__ import annotations

import asyncio
import json
import logging
import os
import signal
import sys
import threading
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable

    from griptape_nodes.retained_mode.managers.worker_manager import WorkerManager

import truststore
from cattrs import BaseValidationError, transform_error
from rich.align import Align
from rich.console import Console
from rich.panel import Panel

from griptape_nodes.api_client import Client, RequestClient
from griptape_nodes.app.engine_log import _engine_role_filter, _rich_handler
from griptape_nodes.bootstrap.utils.subprocess_websocket_base import WebSocketMessage
from griptape_nodes.common.node_executor import current_executing_node_name
from griptape_nodes.retained_mode.events import app_events, execution_events, worker_events

# This import is necessary to register all events, even if not technically used
from griptape_nodes.retained_mode.events.base_events import (
    AppEvent,
    EventRequest,
    EventResultFailure,
    EventResultSuccess,
    ExecutionEvent,
    ExecutionGriptapeNodeEvent,
    GriptapeNodeEvent,
    ProgressEvent,
    SkipTheLineMixin,
)
from griptape_nodes.retained_mode.events.logger_events import LogHandlerEvent
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
from griptape_nodes.utils import install_file_url_support
from griptape_nodes.utils.version_utils import engine_version


# WebSocket thread communication message types
@dataclass
class SubscribeCommand:
    """Command to subscribe to a topic."""

    topic: str


@dataclass
class UnsubscribeCommand:
    """Command to unsubscribe from a topic."""

    topic: str


@dataclass(frozen=True)
class Orchestrator:
    """Engine role: owns the session, routes requests to workers."""


@dataclass(frozen=True)
class Worker:
    """Engine role: attached to an existing orchestrator session.

    library_name is None for general-purpose workers and set for
    library-dedicated workers that serve exactly one library.
    """

    session_id: str
    library_name: str | None = None


EngineRole = Orchestrator | Worker


# Important to bootstrap singleton here so that we don't
# get any weird circular import issues from the EventLogHandler
# initializing it from a log during it's own initialization.
griptape_nodes: GriptapeNodes = GriptapeNodes()

# WebSocket outgoing queue for messages and commands.
# Appears to be fine to create outside event loop
# https://discuss.python.org/t/can-asyncio-queue-be-safely-created-outside-of-the-event-loop-thread/49215/8
ws_outgoing_queue: asyncio.Queue = asyncio.Queue()

# Background WebSocket event loop reference for cross-thread communication
websocket_event_loop: asyncio.AbstractEventLoop | None = None

# Threading event to signal when websocket_event_loop is ready
websocket_event_loop_ready = threading.Event()


# Semaphore to limit concurrent requests
REQUEST_SEMAPHORE = asyncio.Semaphore(100)

config_manager = GriptapeNodes.ConfigManager()

# Install file:// URL support for httpx/requests
install_file_url_support()


# Maximum length for log messages forwarded to the GUI.
LOG_MESSAGE_MAX_LENGTH = 500

# Timeout for worker-originated requests forwarded to the orchestrator.
# Orchestrator handlers for graph-introspection requests complete in milliseconds;
# a 30s ceiling bounds the wait if the orchestrator is overloaded or unreachable.
ORCHESTRATOR_REQUEST_TIMEOUT_MS = 30_000


class EventLogHandler(logging.Handler):
    """Custom logging handler that emits log messages as AppEvents.

    This is used to forward log messages to the event queue so they can be sent to the GUI.
    """

    def emit(self, record: logging.LogRecord) -> None:
        log_level_no = logging.getLevelNamesMapping()[config_manager.get_config_value("log_level").upper()]
        if record.levelno >= log_level_no:
            message = record.getMessage()
            if len(message) > LOG_MESSAGE_MAX_LENGTH:
                message = message[:LOG_MESSAGE_MAX_LENGTH] + "... (truncated; full output available in engine logs)"
            node_name = current_executing_node_name.get(None)
            log_event = AppEvent(
                payload=LogHandlerEvent(
                    message=message, levelname=record.levelname, created=record.created, node_name=node_name
                )
            )
            griptape_nodes.EventManager().put_event(log_event)


# Logger for this module. Important that this is not the same as the griptape_nodes logger or else we'll have infinite log events.
logger = logging.getLogger("griptape_nodes_app")

# Get configured log level from config
log_level_str = config_manager.get_config_value("log_level").upper()
log_level = logging.getLevelNamesMapping()[log_level_str]

griptape_nodes_logger = logging.getLogger("griptape_nodes")
griptape_nodes_logger.addHandler(EventLogHandler())
griptape_nodes_logger.setLevel(log_level)

# Root logger only gets RichHandler for console output
logging.basicConfig(
    level=log_level,
    format="%(message)s",
    datefmt="[%X]",
    handlers=[_rich_handler],
)

# Suppress noisy third-party library logging
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("mcp").setLevel(logging.WARNING)

console = Console()


def _ensure_api_key() -> str:
    """Verify that GT_CLOUD_API_KEY is set, exit with clear error message if not.

    Returns:
        The API key value

    Raises:
        SystemExit: If API key is missing or empty
    """
    secrets_manager = griptape_nodes.SecretsManager()
    api_key = secrets_manager.get_secret("GT_CLOUD_API_KEY", should_error_on_not_found=False)

    if not api_key:
        message = Panel(
            Align.center(
                "[bold red]Nodes API key is not set, please run [code]gtn init[/code] with a valid key:[/bold red]\n"
                "[code]gtn init --api-key <your key>[/code]\n\n"
                "[bold red]You can generate a new key from [/bold red][bold blue][link=https://nodes.griptape.ai]https://nodes.griptape.ai[/link][/bold blue]",
            ),
            title="[red]X[/red] Missing Nodes API Key",
            border_style="red",
            padding=(1, 4),
        )
        console.print(message)
        sys.exit(1)

    return api_key


def start_app(role: EngineRole) -> None:
    """Legacy sync entry point - runs async app."""
    # Use the system certificate store for SSL verification.
    # Called here (not at module level) so it only applies in server mode,
    # not when app.py is imported by headless/subprocess contexts.
    truststore.inject_into_ssl()
    try:
        asyncio.run(astart_app(role))
    except KeyboardInterrupt:
        logger.info("Application stopped by user")
    except Exception as e:
        logger.error("Application error: %s", e)


async def astart_app(role: EngineRole) -> None:
    """New async app entry point."""
    # Verify API key is set before starting
    _ensure_api_key()

    # Initialize event queue in main thread
    griptape_nodes.EventManager().initialize_queue()

    try:
        # Start WebSocket tasks in daemon thread
        threading.Thread(
            target=_start_websocket_connection,
            kwargs={"role": role},
            daemon=True,
            name="websocket-tasks",
        ).start()

        # Run event processing on main thread
        await _process_event_queue()

    except Exception as e:
        logger.error("Application startup failed: %s", e)
        raise


def _start_websocket_connection(role: EngineRole) -> None:
    """Run WebSocket tasks in a separate thread with its own async loop."""
    global websocket_event_loop  # noqa: PLW0603
    try:
        # Create a new event loop for this thread
        loop = asyncio.new_event_loop()
        websocket_event_loop = loop
        asyncio.set_event_loop(loop)

        # Signal that websocket_event_loop is ready
        websocket_event_loop_ready.set()

        # Run the async WebSocket tasks
        loop.run_until_complete(_run_websocket_tasks(role))
    except ConnectionError:
        # Connection failed - likely due to invalid/missing API key
        message = Panel(
            Align.center(
                "[bold red]Failed to connect to Nodes API.[/bold red]\n\n"
                "This usually indicates an invalid or missing [code]GT_CLOUD_API_KEY[/code].\n\n"
                "[bold red]Please verify your API key:[/bold red]\n"
                "[code]gtn init --api-key <your key>[/code]\n\n"
                "[bold red]You can generate a new key from [/bold red][bold blue][link=https://nodes.griptape.ai]https://nodes.griptape.ai[/link][/bold blue]",
            ),
            title="[red]X[/red] Connection Failed",
            border_style="red",
            padding=(1, 4),
        )
        console.print(message)
        sys.exit(1)
    except Exception as e:
        logger.error("WebSocket thread error: %s", e)
        raise
    finally:
        websocket_event_loop = None
        websocket_event_loop_ready.clear()


async def _run_websocket_tasks(role: EngineRole) -> None:
    """Run WebSocket tasks - async version."""
    async with Client() as client:
        logger.debug("WebSocket connection established")
        is_worker = isinstance(role, Worker)
        libraries_to_register = [role.library_name] if isinstance(role, Worker) and role.library_name else []
        griptape_nodes.EventManager().put_event(
            AppEvent(
                payload=app_events.AppInitializationComplete(
                    is_worker=is_worker,
                    libraries_to_register=libraries_to_register,
                )
            )
        )
        griptape_nodes.EventManager().put_event(AppEvent(payload=app_events.AppConnectionEstablished()))

        if isinstance(role, Worker):
            await _run_worker(client, role)
        else:
            await _run_orchestrator(client)


async def _run_worker(client: Client, role: Worker) -> None:
    """Run the WebSocket task group for a worker engine."""
    # Announce this worker to the orchestrator's session request topic.
    # The orchestrator will store our engine_id and subscribe to our response topic.
    worker_engine_id = griptape_nodes.get_engine_id()
    if not worker_engine_id:
        msg = "Engine ID is not set; cannot register as a worker."
        raise RuntimeError(msg)
    _engine_role_filter.prefix = f"Worker-{worker_engine_id[:8]}"
    reg_event = EventRequest(
        request=worker_events.RegisterWorkerRequest(
            worker_engine_id=worker_engine_id,
            engine_version=engine_version,
            library_name=role.library_name,
        ),
        response_topic=None,
    )
    await client.publish(
        "EventRequest",
        json.loads(reg_event.json()),
        f"sessions/{role.session_id}/request",
    )
    logger.info("Worker %s registered with orchestrator", worker_engine_id)

    # Set session_id so _determine_response_topic() returns the session topic,
    # routing intermediate events (AppEvents, ProgressEvents) directly to the GUI.
    griptape_nodes.SessionManager().active_session_id = role.session_id

    # Relay LibraryLoadedNotification events to the orchestrator over the transport layer.
    # LibraryManager broadcasts these when a library finishes loading on this worker;
    # publishing them to the session request topic lets the orchestrator update its state.
    #
    # IMPORTANT: abroadcast_app_event is called from the main event loop (loop A), but
    # client and its WebSocket are bound to the WebSocket event loop (loop B). Calling
    # client.publish() directly from loop A would silently fail or hang. Use _send_message()
    # instead -- it enqueues via run_coroutine_threadsafe and is safe to call from loop A.
    async def _relay_library_loaded(notification: app_events.LibraryLoadedNotification) -> None:
        relay = AppEvent(payload=notification)
        await _send_message("AppEvent", relay.json(), f"sessions/{role.session_id}/request")

    griptape_nodes.EventManager().add_listener_to_app_event(app_events.LibraryLoadedNotification, _relay_library_loaded)

    async def _consume_messages() -> None:
        async for message in client.messages:
            try:
                await _process_api_event(message)
            except Exception as e:
                logger.error("Error handling message: %s", e)

    try:
        async with RequestClient(client) as request_client:
            worker_manager = griptape_nodes.WorkerManager()
            worker_manager.attach_transport(
                ws_outgoing_queue=ws_outgoing_queue,
                send_message=_send_message,
                subscribe_to_topic=_subscribe_to_topic,
                unsubscribe_from_topic=_unsubscribe_from_topic,
                request_client=request_client,
            )
            for topic in worker_manager.get_topics_to_subscribe(is_worker=True):
                await client.subscribe(topic)

            # Enable worker -> orchestrator forwarding for requests originated
            # from node execution (gated by EventManager.worker_node_execution_scope,
            # opened around ExecuteNodeRequest dispatch in _process_event_request).
            # Must be configured before the event queue processor can dispatch any
            # AppInitializationComplete handlers -- those run outside the scope and
            # will stay local, but the forwarding plumbing needs to be live in case
            # one ever opens a scope itself.
            worker_response_topic = f"engines/{worker_engine_id}/response"
            await client.subscribe(worker_response_topic)
            griptape_nodes.EventManager().configure_worker_forwarding(
                request_client=request_client,
                orchestrator_request_topic=f"sessions/{role.session_id}/request",
                worker_response_topic=worker_response_topic,
                websocket_event_loop=asyncio.get_running_loop(),
                timeout_ms=ORCHESTRATOR_REQUEST_TIMEOUT_MS,
            )

            async with asyncio.TaskGroup() as tg:
                tg.create_task(_send_outgoing_messages(client))
                tg.create_task(worker_manager.worker_heartbeat_monitor())
                tg.create_task(_consume_messages())
    except BaseException:
        # Best-effort unregister so the orchestrator can clean up immediately.
        unregister_event = EventRequest(
            request=worker_events.UnregisterWorkerRequest(worker_engine_id=worker_engine_id),
            response_topic=None,
        )
        try:
            await client.publish(
                "EventRequest",
                json.loads(unregister_event.json()),
                f"sessions/{role.session_id}/request",
            )
            logger.info("Worker %s sent unregister to session %s", worker_engine_id, role.session_id)
        except Exception as e:
            logger.debug("Could not send unregister on shutdown: %s", e)
        os.kill(os.getpid(), signal.SIGINT)


async def _handle_orchestrator_unmatched(message: dict, worker_manager: WorkerManager) -> None:
    """Handle messages not resolved by RequestClient as pending requests.

    Called for every message not claimed by RequestClient's response filter.
    Routes worker result messages (heartbeats and any unmatched results) to
    WorkerManager, and all other messages to _process_api_event.
    """
    try:
        payload = message.get("payload", {})
        event_type = payload.get("event_type", "")
        if event_type in ("EventResultSuccess", "EventResultFailure"):
            # Heartbeat or unmatched result from a worker — relay via the orchestrator.
            await worker_manager.relay_worker_result(payload)
        else:
            await _process_api_event(message)
    except Exception as e:
        logger.warning(
            "Skipping unrecognized event. Your editor may be newer than this engine version. (%s)",
            e,
        )


async def _run_orchestrator(client: Client) -> None:
    """Run the WebSocket task group for an orchestrator engine."""
    async with RequestClient(client) as request_client:
        worker_manager = griptape_nodes.WorkerManager()
        worker_manager.attach_transport(
            ws_outgoing_queue=ws_outgoing_queue,
            send_message=_send_message,
            subscribe_to_topic=_subscribe_to_topic,
            unsubscribe_from_topic=_unsubscribe_from_topic,
            request_client=request_client,
        )
        for topic in worker_manager.get_topics_to_subscribe(is_worker=False):
            await client.subscribe(topic)

        async def _handle_unmatched(message: dict) -> None:
            await _handle_orchestrator_unmatched(message, worker_manager)

        async def _consume_messages() -> None:
            async for message in client.messages:
                await _handle_unmatched(message)

        try:
            async with asyncio.TaskGroup() as tg:
                tg.create_task(_send_outgoing_messages(client))
                tg.create_task(worker_manager.orchestrator_heartbeat_loop())
                tg.create_task(_consume_messages())
        finally:
            await worker_manager.reset_workers()


def _deserialize_event[T](from_dict: Callable[[dict], T], payload: dict, label: str) -> T:
    """Deserialize an event from a raw payload dict, wrapping errors with context."""
    try:
        return from_dict(payload)
    except Exception as e:
        details = str(e)
        if isinstance(e, BaseValidationError):
            details = "; ".join(transform_error(e))
        msg = f"Unable to convert request JSON into a valid {label} object. Error Message: '{details}'"
        raise RuntimeError(msg) from None


async def _process_api_event(event: dict) -> None:
    """Process API events and add to async queue."""
    payload = event.get("payload", {})

    try:
        event_type = payload["event_type"]
    except KeyError:
        msg = "Error: 'event_type' not found in request."
        raise RuntimeError(msg) from None

    if event_type == "AppEvent":
        griptape_nodes.EventManager().put_event(_deserialize_event(AppEvent.from_dict, payload, "AppEvent"))
        return

    try:
        payload["request"]
    except KeyError:
        msg = "Error: 'request' was expected but not found."
        raise RuntimeError(msg) from None

    if event_type != "EventRequest":
        msg = "Error: 'event_type' was found on request, but did not match 'EventRequest' as expected."
        raise RuntimeError(msg) from None

    # Now attempt to convert it into an EventRequest.
    request_event = _deserialize_event(EventRequest.from_dict, payload, "EventRequest")

    if not isinstance(request_event, EventRequest):
        msg = f"Deserialized event is not an EventRequest: {type(request_event)}"
        raise TypeError(msg)

    # Check if the event implements SkipTheLineMixin for priority processing
    if isinstance(request_event.request, SkipTheLineMixin):
        # Handle the event immediately without queuing
        await _process_event_request(request_event)
    else:
        # Add the event to the main thread event queue for processing
        griptape_nodes.EventManager().put_event(request_event)


async def _send_outgoing_messages(client: Client) -> None:
    """Send outgoing WebSocket requests from queue on background thread."""
    logger.debug("Starting outgoing WebSocket request sender")

    while True:
        # Get message from outgoing queue
        message = await ws_outgoing_queue.get()

        try:
            if isinstance(message, WebSocketMessage):
                # Use client to publish message
                topic = message.topic or _determine_response_topic()
                payload_dict = json.loads(message.payload)
                await client.publish(message.event_type, payload_dict, topic)
            elif isinstance(message, SubscribeCommand):
                await client.subscribe(message.topic)
            elif isinstance(message, UnsubscribeCommand):
                await client.unsubscribe(message.topic)
            else:
                logger.warning("Unknown outgoing message type: %s", type(message))
        except Exception as e:
            logger.error("Error sending outgoing WebSocket request: %s", e)
        finally:
            ws_outgoing_queue.task_done()


async def _process_event_queue() -> None:
    """Process events concurrently - runs on main thread."""
    logger.debug("Starting event queue processor on main thread")
    background_tasks = set()

    def _handle_task_result(task: asyncio.Task) -> None:
        background_tasks.discard(task)
        if task.exception() and not task.cancelled():
            logger.exception("Background task failed", exc_info=task.exception())

    try:
        event_queue = griptape_nodes.EventManager().event_queue
        while True:
            event = await event_queue.get()

            async with REQUEST_SEMAPHORE:
                if isinstance(event, EventRequest):
                    task = asyncio.create_task(_process_event_request(event))
                elif isinstance(event, AppEvent):
                    task = asyncio.create_task(_process_app_event(event))
                elif isinstance(event, GriptapeNodeEvent):
                    task = asyncio.create_task(_process_node_event(event))
                elif isinstance(event, ExecutionGriptapeNodeEvent):
                    task = asyncio.create_task(_process_execution_node_event(event))
                elif isinstance(event, ProgressEvent):
                    task = asyncio.create_task(_process_progress_event(event))
                else:
                    logger.warning("Unknown event type: %s", type(event))
                    event_queue.task_done()
                    continue

            background_tasks.add(task)
            task.add_done_callback(_handle_task_result)
            event_queue.task_done()
    except asyncio.CancelledError:
        logger.debug("Event queue processor shutdown complete")
        raise


async def _process_event_request(event: EventRequest) -> None:
    """Handle request and emit success/failure events based on result.

    Two independent reasons to emit the result:
    - broadcast_result=True: the request wants its result fanned out (typically
      to the GUI or default session topic).
    - response_topic is set: the caller is waiting for a reply on that topic
      (e.g. a worker that forwarded this request to us). The reply is required
      regardless of broadcast_result, otherwise the caller's future hangs until
      timeout. This covers request types like WriteFileRequest that default to
      broadcast_result=False but must still reply when they arrive over the wire.
    """
    result_event = await griptape_nodes.EventManager().ahandle_request(
        event.request,
        result_context={"response_topic": event.response_topic, "request_id": event.request_id},
    )
    if event.request.broadcast_result or event.response_topic is not None:
        await _process_node_event(GriptapeNodeEvent(wrapped_event=result_event))


async def _process_app_event(event: AppEvent) -> None:
    """Process AppEvents and send them to the API (async version)."""
    # Let Griptape Nodes broadcast it.
    await griptape_nodes.abroadcast_app_event(event.payload)

    # Strip node_schemas before forwarding LibraryLoadedNotification to the GUI.
    # The orchestrator has already consumed the schemas to register stub classes;
    # the GUI has no use for them and the payload can exceed 100 KB for large libraries.
    payload = event.payload
    if isinstance(payload, app_events.LibraryLoadedNotification) and payload.node_schemas:
        event = AppEvent(payload=replace(payload, node_schemas=None))

    await _send_message("app_event", event.json())


async def _process_node_event(event: GriptapeNodeEvent) -> None:
    """Process GriptapeNodeEvents and send them to the API (async version)."""
    # Check if events are suppressed
    if griptape_nodes.EventManager().should_suppress_event(event):
        return

    # Emit the result back to the GUI
    result_event = event.wrapped_event

    if isinstance(result_event, EventResultSuccess):
        dest_socket = "success_result"
        # Handle session-specific topic subscriptions
        if isinstance(result_event.result, app_events.AppStartSessionResultSuccess):
            session_id = result_event.result.session_id
            topic = f"sessions/{session_id}/request"
            await _subscribe_to_topic(topic)
            logger.info("Subscribed to session topic: %s", topic)
            # Unblock any worker spawns that were waiting for a session to become available,
            # then broadcast so interested managers (e.g. LibraryManager) can react.
            worker_manager = GriptapeNodes.WorkerManager()
            if worker_manager is not None:
                worker_manager.set_session_ready()
            await GriptapeNodes.abroadcast_app_event(app_events.AppSessionStartedEvent(session_id=session_id))
        elif isinstance(result_event.result, app_events.AppEndSessionResultSuccess):
            session_id = result_event.result.session_id
            if session_id is not None:
                topic = f"sessions/{session_id}/request"
                await _unsubscribe_from_topic(topic)
                logger.info("Unsubscribed from session topic: %s", topic)
            # Terminate workers so they are recreated when the next session starts.
            worker_manager = GriptapeNodes.WorkerManager()
            if worker_manager is not None:
                await worker_manager.reset_workers()
                worker_manager.clear_session_ready()
    elif isinstance(result_event, EventResultFailure):
        dest_socket = "failure_result"
    else:
        msg = f"Unknown/unsupported result event type encountered: '{type(result_event)}'."
        raise TypeError(msg) from None

    await _send_message(dest_socket, result_event.json(), topic=result_event.response_topic)


async def _process_execution_node_event(event: ExecutionGriptapeNodeEvent) -> None:
    """Process ExecutionGriptapeNodeEvents and send them to the API (async version)."""
    # Check if events are suppressed
    if griptape_nodes.EventManager().should_suppress_event(event):
        return

    await _send_message("execution_event", event.wrapped_event.json())


async def _process_progress_event(gt_event: ProgressEvent) -> None:
    """Process Griptape framework events and send them to the API (async version)."""
    # Check if events are suppressed
    if griptape_nodes.EventManager().should_suppress_event(gt_event):
        return

    node_name = gt_event.node_name
    if node_name:
        value = gt_event.value
        payload = execution_events.GriptapeEvent(
            node_name=node_name, parameter_name=gt_event.parameter_name, type=type(gt_event).__name__, value=value
        )
        event_to_emit = ExecutionEvent(payload=payload)
        await _send_message("execution_event", event_to_emit.json())


async def _send_message(event_type: str, payload: str, topic: str | None = None) -> None:
    """Queue a message to be sent via WebSocket using run_coroutine_threadsafe."""
    # Wait for websocket event loop to be ready
    websocket_event_loop_ready.wait()

    # Use run_coroutine_threadsafe to put message into WebSocket background thread queue
    if websocket_event_loop is None:
        logger.error("WebSocket event loop not available for message")
        return

    # Determine topic based on session_id and engine_id in the payload
    if topic is None:
        topic = _determine_response_topic()

    message = WebSocketMessage(event_type, payload, topic)

    asyncio.run_coroutine_threadsafe(ws_outgoing_queue.put(message), websocket_event_loop)


async def _subscribe_to_topic(topic: str) -> None:
    """Queue a subscribe command for WebSocket using run_coroutine_threadsafe."""
    # Wait for websocket event loop to be ready
    websocket_event_loop_ready.wait()

    if websocket_event_loop is None:
        logger.error("WebSocket event loop not available for subscribe")
        return

    asyncio.run_coroutine_threadsafe(ws_outgoing_queue.put(SubscribeCommand(topic)), websocket_event_loop)


async def _unsubscribe_from_topic(topic: str) -> None:
    """Queue an unsubscribe command for WebSocket using run_coroutine_threadsafe."""
    if websocket_event_loop is None:
        logger.error("WebSocket event loop not available for unsubscribe")
        return

    asyncio.run_coroutine_threadsafe(ws_outgoing_queue.put(UnsubscribeCommand(topic)), websocket_event_loop)


def _determine_response_topic() -> str:
    """Determine the response topic based on session_id and engine_id in the payload."""
    engine_id = griptape_nodes.get_engine_id()
    session_id = griptape_nodes.get_session_id()

    # Normal topic determination logic
    # Check for session_id first (highest priority)
    if session_id:
        return f"sessions/{session_id}/response"

    # Check for engine_id if no session_id
    if engine_id:
        return f"engines/{engine_id}/response"

    # Default to generic response topic
    return "response"
