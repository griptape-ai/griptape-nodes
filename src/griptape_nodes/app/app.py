from __future__ import annotations

import asyncio
import json
import logging
import threading
from dataclasses import dataclass

from rich.console import Console
from rich.logging import RichHandler

from griptape_nodes.api_client import Client
from griptape_nodes.retained_mode.events import app_events, execution_events

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
    deserialize_event,
)
from griptape_nodes.retained_mode.events.logger_events import LogHandlerEvent
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes


# WebSocket thread communication message types
@dataclass
class WebSocketMessage:
    """Message to send via WebSocket."""

    event_type: str
    payload: str
    topic: str | None = None


@dataclass
class SubscribeCommand:
    """Command to subscribe to a topic."""

    topic: str


@dataclass
class UnsubscribeCommand:
    """Command to unsubscribe from a topic."""

    topic: str


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


class EventLogHandler(logging.Handler):
    """Custom logging handler that emits log messages as AppEvents.

    This is used to forward log messages to the event queue so they can be sent to the GUI.
    """

    def emit(self, record: logging.LogRecord) -> None:
        log_event = AppEvent(
            payload=LogHandlerEvent(message=record.getMessage(), levelname=record.levelname, created=record.created)
        )
        griptape_nodes.EventManager().put_event(log_event)


# Logger for this module. Important that this is not the same as the griptape_nodes logger or else we'll have infinite log events.
logger = logging.getLogger("griptape_nodes_app")

griptape_nodes_logger = logging.getLogger("griptape_nodes")
griptape_nodes_logger.addHandler(EventLogHandler())
griptape_nodes_logger.setLevel(logging.INFO)

# Root logger only gets RichHandler for console output
logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
    datefmt="[%X]",
    handlers=[RichHandler(show_time=True, show_path=False, markup=True, rich_tracebacks=True)],
)

console = Console()


def start_app() -> None:
    """Legacy sync entry point - runs async app."""
    try:
        asyncio.run(astart_app())
    except KeyboardInterrupt:
        logger.info("Application stopped by user")
    except Exception as e:
        logger.error("Application error: %s", e)


async def astart_app() -> None:
    """New async app entry point."""
    # Initialize event queue in main thread
    griptape_nodes.EventManager().initialize_queue()

    try:
        # Start WebSocket tasks in daemon thread
        threading.Thread(target=_start_websocket_connection, daemon=True, name="websocket-tasks").start()

        # Run event processing on main thread
        await _process_event_queue()

    except Exception as e:
        logger.error("Application startup failed: %s", e)
        raise


def _start_websocket_connection() -> None:
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
        loop.run_until_complete(_run_websocket_tasks())
    except Exception as e:
        logger.error("WebSocket thread error: %s", e)
        raise
    finally:
        websocket_event_loop = None
        websocket_event_loop_ready.clear()


async def _run_websocket_tasks() -> None:
    """Run WebSocket tasks - async version."""
    async with Client() as client:
        logger.debug("WebSocket connection established")

        griptape_nodes.EventManager().put_event(AppEvent(payload=app_events.AppInitializationComplete()))
        griptape_nodes.EventManager().put_event(AppEvent(payload=app_events.AppConnectionEstablished()))

        async with asyncio.TaskGroup() as tg:
            tg.create_task(_process_incoming_messages(client))
            tg.create_task(_send_outgoing_messages(client))


async def _process_incoming_messages(client: Client) -> None:
    """Process incoming WebSocket requests from Nodes API."""
    logger.debug("Processing incoming WebSocket requests from WebSocket connection")

    topics = ["request"]
    engine_id = griptape_nodes.get_engine_id()
    if engine_id:
        topics.append(f"engines/{engine_id}/request")

    session_id = griptape_nodes.get_session_id()
    if session_id:
        topics.append(f"sessions/{session_id}/request")

    for topic in topics:
        await client.subscribe(topic)

    async for message in client.messages:
        try:
            await _process_api_event(message)
        except Exception:
            logger.exception("Error processing event, skipping.")


async def _process_api_event(event: dict) -> None:
    """Process API events and add to async queue."""
    payload = event.get("payload", {})

    try:
        payload["request"]
    except KeyError:
        msg = "Error: 'request' was expected but not found."
        raise RuntimeError(msg) from None

    try:
        event_type = payload["event_type"]
        if event_type != "EventRequest":
            msg = "Error: 'event_type' was found on request, but did not match 'EventRequest' as expected."
            raise RuntimeError(msg) from None
    except KeyError:
        msg = "Error: 'event_type' not found in request."
        raise RuntimeError(msg) from None

    # Now attempt to convert it into an EventRequest.
    try:
        request_event = deserialize_event(json_data=payload)
    except Exception as e:
        msg = f"Unable to convert request JSON into a valid EventRequest object. Error Message: '{e}'"
        raise RuntimeError(msg) from None

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
                topic = message.topic if message.topic else _determine_response_topic()
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
    """Handle request and emit success/failure events based on result."""
    result_event = await griptape_nodes.EventManager().ahandle_request(
        event.request,
        result_context={"response_topic": event.response_topic, "request_id": event.request_id},
    )
    await _process_node_event(GriptapeNodeEvent(wrapped_event=result_event))


async def _process_app_event(event: AppEvent) -> None:
    """Process AppEvents and send them to the API (async version)."""
    # Let Griptape Nodes broadcast it.
    await griptape_nodes.broadcast_app_event(event.payload)

    await _send_message("app_event", event.json())


async def _process_node_event(event: GriptapeNodeEvent) -> None:
    """Process GriptapeNodeEvents and send them to the API (async version)."""
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
        elif isinstance(result_event.result, app_events.AppEndSessionResultSuccess):
            session_id = result_event.result.session_id
            if session_id is not None:
                topic = f"sessions/{session_id}/request"
                await _unsubscribe_from_topic(topic)
                logger.info("Unsubscribed from session topic: %s", topic)
    elif isinstance(result_event, EventResultFailure):
        dest_socket = "failure_result"
    else:
        msg = f"Unknown/unsupported result event type encountered: '{type(result_event)}'."
        raise TypeError(msg) from None

    await _send_message(dest_socket, result_event.json(), topic=result_event.response_topic)


async def _process_execution_node_event(event: ExecutionGriptapeNodeEvent) -> None:
    """Process ExecutionGriptapeNodeEvents and send them to the API (async version)."""
    await _send_message("execution_event", event.wrapped_event.json())


async def _process_progress_event(gt_event: ProgressEvent) -> None:
    """Process Griptape framework events and send them to the API (async version)."""
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
