from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any, cast
from urllib.parse import urljoin

from rich.align import Align
from rich.console import Console
from rich.logging import RichHandler
from rich.panel import Panel
from websockets.asyncio.client import connect
from websockets.exceptions import ConnectionClosed, WebSocketException

from griptape_nodes.mcp_server.server import main_async as mcp_server_async
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
    RequestPayload,
    SkipTheLineMixin,
    deserialize_event,
)
from griptape_nodes.retained_mode.events.logger_events import LogHandlerEvent
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

# Global async event queue - created in async context
event_queue: asyncio.Queue | None = None

# Global WebSocket connection for sending events
ws_connection_for_sending = None


# Whether to enable the static server
STATIC_SERVER_ENABLED = os.getenv("STATIC_SERVER_ENABLED", "true").lower() == "true"


def put_event(event: Any) -> None:
    """Put event into async queue from sync context (non-blocking)."""
    if event_queue is None:
        return

    # Use put_nowait and suppress full queue errors
    with contextlib.suppress(asyncio.QueueFull):
        event_queue.put_nowait(event)


async def aput_event(event: Any) -> None:
    """Put event into async queue from async context."""
    if event_queue is None:
        return

    await event_queue.put(event)


class EventLogHandler(logging.Handler):
    """Custom logging handler that emits log messages as AppEvents.

    This is used to forward log messages to the event queue so they can be sent to the GUI.
    """

    def emit(self, record: logging.LogRecord) -> None:
        log_event = AppEvent(
            payload=LogHandlerEvent(message=record.getMessage(), levelname=record.levelname, created=record.created)
        )
        put_event(log_event)


# Logger for this module. Important that this is not the same as the griptape_nodes logger or else we'll have infinite log events.
logger = logging.getLogger("griptape_nodes_app")

griptape_nodes_logger = logging.getLogger("griptape_nodes")
# When running as an app, we want to forward all log messages to the event queue so they can be sent to the GUI
griptape_nodes_logger.addHandler(EventLogHandler())
griptape_nodes_logger.addHandler(RichHandler(show_time=True, show_path=False, markup=True, rich_tracebacks=True))
griptape_nodes_logger.setLevel(logging.INFO)

console = Console()


def start_app() -> None:
    """Legacy sync entry point - runs async app."""
    try:
        asyncio.run(start_async_app())
    except KeyboardInterrupt:
        logger.info("Application stopped by user")
    except Exception as e:
        logger.error("Application error: %s", e)


def _handle_task_exception(task: asyncio.Task) -> None:
    """Handle exceptions from background tasks."""
    try:
        task.result()
    except asyncio.CancelledError:
        # Expected during shutdown, ignore
        pass
    except Exception:
        logger.exception("Uncaught exception in task %s", task.get_name())


async def start_async_app() -> None:
    """New async app entry point."""
    global event_queue  # noqa: PLW0603

    api_key = _ensure_api_key()

    # Create async queue in event loop context
    event_queue = asyncio.Queue()

    # Prepare and start tasks
    tasks = _create_app_tasks(api_key, event_queue)
    task_objects = []

    for i, task in enumerate(tasks):
        task_obj = asyncio.create_task(task, name=f"task-{i}")
        task_obj.add_done_callback(_handle_task_exception)
        task_objects.append(task_obj)

    try:
        # Run all tasks concurrently
        await asyncio.gather(*task_objects)
    except KeyboardInterrupt:
        logger.info("KeyboardInterrupt received, shutting down...")
        # Cancel all running tasks
        for task in task_objects:
            if not task.done():
                task.cancel()

        # Wait for tasks to complete cancellation
        if task_objects:
            await asyncio.gather(*task_objects, return_exceptions=True)

        logger.info("Graceful shutdown complete")
        raise
    except Exception as e:
        logger.error("Application startup failed: %s", e)
        # Cancel all running tasks
        for task in task_objects:
            if not task.done():
                task.cancel()

        # Wait for tasks to complete cancellation
        if task_objects:
            await asyncio.gather(*task_objects, return_exceptions=True)

        raise


def _create_app_tasks(api_key: str, event_queue: asyncio.Queue) -> list:
    """Create all application tasks."""
    tasks = [
        _alisten_for_api_requests(api_key),
        _aprocess_event_queue(event_queue),
        _arun_mcp_server(api_key),
    ]

    # Add static server if enabled
    if STATIC_SERVER_ENABLED:
        static_dir = _build_static_dir()
        tasks.append(_astart_api_server(static_dir, event_queue))

    return tasks


async def _arun_mcp_server(api_key: str) -> None:
    """Run MCP server directly in event loop."""
    try:
        # Run MCP server - it will handle shutdown gracefully when cancelled
        await mcp_server_async(api_key)
    except asyncio.CancelledError:
        # Clean shutdown when task is cancelled
        logger.info("MCP server shutdown complete")
        raise
    except Exception as e:
        logger.error("MCP server error: %s", e)
        raise


async def _astart_api_server(static_dir: Path, event_queue: asyncio.Queue) -> None:
    """Run API server directly in event loop."""
    from .api import start_api_async

    try:
        # Run API server - it will handle shutdown gracefully when cancelled
        await start_api_async(static_dir, event_queue)
    except asyncio.CancelledError:
        # Clean shutdown when task is cancelled
        logger.info("API server shutdown complete")
        raise
    except Exception as e:
        logger.error("API server error: %s", e)
        raise


def _ensure_api_key() -> str:
    secrets_manager = GriptapeNodes.SecretsManager()
    api_key = secrets_manager.get_secret("GT_CLOUD_API_KEY")
    if api_key is None:
        message = Panel(
            Align.center(
                "[bold red]Nodes API key is not set, please run [code]gtn init[/code] with a valid key: [/bold red]"
                "[code]gtn init --api-key <your key>[/code]\n"
                "[bold red]You can generate a new key from [/bold red][bold blue][link=https://nodes.griptape.ai]https://nodes.griptape.ai[/link][/bold blue]",
            ),
            title="[red]X[/red] Missing Nodes API Key",
            border_style="red",
            padding=(1, 4),
        )
        console.print(message)
        sys.exit(1)

    return api_key


def _build_static_dir() -> Path:
    """Build the static directory path based on the workspace configuration."""
    config_manager = GriptapeNodes.ConfigManager()
    return Path(config_manager.workspace_path) / config_manager.merged_config["static_files_directory"]


async def _alisten_for_api_requests(api_key: str) -> None:
    """Listen for events and add to async queue."""
    logger.info("Listening for events from Nodes API via async WebSocket")

    connection_stream = _create_websocket_connection(api_key)
    initialized = False

    try:
        async for ws_connection in connection_stream:
            await _handle_websocket_connection(ws_connection, initialized=initialized)
            initialized = True

    except asyncio.CancelledError:
        # Clean shutdown when task is cancelled
        logger.info("WebSocket listener shutdown complete")
        raise
    except Exception as e:
        logger.error("Fatal error in WebSocket listener: %s", e)
        raise
    finally:
        await _cleanup_websocket_connection()


async def _handle_websocket_connection(ws_connection: Any, *, initialized: bool) -> None:
    """Handle a single WebSocket connection."""
    global ws_connection_for_sending  # noqa: PLW0603

    try:
        ws_connection_for_sending = ws_connection

        if not initialized:
            await aput_event(AppEvent(payload=app_events.AppInitializationComplete()))

        await aput_event(AppEvent(payload=app_events.AppConnectionEstablished()))

        async for message in ws_connection:
            try:
                data = json.loads(message)
                await _aprocess_api_event(data)
            except Exception:
                logger.exception("Error processing event, skipping.")

    except ConnectionClosed:
        logger.info("WebSocket connection closed, will retry")
    except Exception as e:
        logger.error("Error in WebSocket connection. Retrying in 2 seconds... %s", e)
        await asyncio.sleep(2.0)


async def _cleanup_websocket_connection() -> None:
    """Clean up WebSocket connection on shutdown."""
    if ws_connection_for_sending:
        with contextlib.suppress(Exception):
            await ws_connection_for_sending.close()
    logger.info("WebSocket listener shutdown complete")


async def _aprocess_event_queue(event_queue: asyncio.Queue) -> None:
    """Process events concurrently - multiple requests can run simultaneously."""
    # Wait for WebSocket connection (convert to async)
    await _await_websocket_ready()

    try:
        while True:
            event = await event_queue.get()

            if isinstance(event, EventRequest):
                # Create task for concurrent processing
                task = asyncio.create_task(_ahandle_event_request(event))
                # Store reference to prevent garbage collection
                task.add_done_callback(lambda _: None)
            elif isinstance(event, AppEvent):
                # App events processed immediately
                await _aprocess_app_event(event)
            elif isinstance(event, GriptapeNodeEvent):
                # Process GriptapeNodeEvents
                await _aprocess_node_event(event)
            elif isinstance(event, ExecutionGriptapeNodeEvent):
                # Process ExecutionGriptapeNodeEvents
                await _aprocess_execution_node_event(event)
            elif isinstance(event, ProgressEvent):
                # Process ProgressEvents
                await _aprocess_progress_event(event)
            else:
                logger.warning("Unknown event type: %s", type(event))

            event_queue.task_done()
    except asyncio.CancelledError:
        logger.info("Event queue processor shutdown complete")
        raise


async def _ahandle_event_request(event: EventRequest) -> None:
    """Handle individual request asynchronously."""
    try:
        result_payload = await GriptapeNodes.ahandle_request(
            event.request, response_topic=event.response_topic, request_id=event.request_id
        )
        # Emit success/failure events (existing logic)
        await _aemit_request_result(event, result_payload)
    except Exception as e:
        logger.exception(
            "Error handling request of type %s (request_id: %s, response_topic: %s)",
            type(event.request).__name__,
            event.request_id,
            event.response_topic,
        )
        # Emit failure event with preserved exception context
        await _aemit_request_failure(event, e)


async def _await_websocket_ready() -> None:
    """Async version of WebSocket ready check."""
    start_time = asyncio.get_event_loop().time()
    while not ws_connection_for_sending:
        websocket_timeout = 15
        if asyncio.get_event_loop().time() - start_time > websocket_timeout:
            console.print("[red]WebSocket connection timeout[/red]")
            sys.exit(1)
        await asyncio.sleep(0.1)


async def _aemit_request_result(event: EventRequest, result_payload: Any) -> None:
    """Emit request result events."""
    if callable(getattr(result_payload, "succeeded", None)) and result_payload.succeeded():
        dest_socket = "success_result"
        result_event = EventResultSuccess(
            request=event.request,
            result=result_payload,
            response_topic=event.response_topic,
            request_id=event.request_id,
        )
    else:
        dest_socket = "failure_result"
        result_event = EventResultFailure(
            request=event.request,
            result=result_payload,
            response_topic=event.response_topic,
            request_id=event.request_id,
        )

    await __emit_message(dest_socket, result_event.json(), topic=result_event.response_topic)


async def _aemit_request_failure(event: EventRequest, exception: Exception) -> None:
    """Emit request failure events."""
    from griptape_nodes.retained_mode.events.base_events import ResultPayloadFailure

    result_payload = ResultPayloadFailure(exception=exception)
    result_event = EventResultFailure(
        request=event.request, result=result_payload, response_topic=event.response_topic, request_id=event.request_id
    )
    await __emit_message("failure_result", result_event.json(), topic=result_event.response_topic)


async def _aprocess_app_event(event: AppEvent) -> None:
    """Process AppEvents and send them to the API (async version)."""
    # Let Griptape Nodes broadcast it.
    await GriptapeNodes.broadcast_app_event(event.payload)

    await __emit_message("app_event", event.json())


async def _aprocess_node_event(event: GriptapeNodeEvent) -> None:
    """Process GriptapeNodeEvents and send them to the API (async version)."""
    # Emit the result back to the GUI
    result_event = event.wrapped_event
    if isinstance(result_event, EventResultSuccess):
        dest_socket = "success_result"
    elif isinstance(result_event, EventResultFailure):
        dest_socket = "failure_result"
    else:
        msg = f"Unknown/unsupported result event type encountered: '{type(result_event)}'."
        raise TypeError(msg) from None

    await __emit_message(dest_socket, result_event.json(), topic=result_event.response_topic)


async def _aprocess_execution_node_event(event: ExecutionGriptapeNodeEvent) -> None:
    """Process ExecutionGriptapeNodeEvents and send them to the API (async version)."""
    result_event = event.wrapped_event
    if type(result_event.payload).__name__ == "NodeStartProcessEvent":
        GriptapeNodes.EventManager().current_active_node = result_event.payload.node_name

    if type(result_event.payload).__name__ == "ResumeNodeProcessingEvent":
        node_name = result_event.payload.node_name
        logger.info("Resuming Node '%s'", node_name)
        flow_name = GriptapeNodes.NodeManager().get_node_parent_flow_by_name(node_name)
        request = EventRequest(request=execution_events.SingleExecutionStepRequest(flow_name=flow_name))
        await aput_event(request)

    if type(result_event.payload).__name__ == "NodeFinishProcessEvent":
        if result_event.payload.node_name != GriptapeNodes.EventManager().current_active_node:
            msg = "Node start and finish do not match."
            raise KeyError(msg) from None
        GriptapeNodes.EventManager().current_active_node = None
    await __emit_message("execution_event", result_event.json())


async def _aprocess_progress_event(gt_event: ProgressEvent) -> None:
    """Process Griptape framework events and send them to the API (async version)."""
    node_name = gt_event.node_name
    if node_name:
        value = gt_event.value
        payload = execution_events.GriptapeEvent(
            node_name=node_name, parameter_name=gt_event.parameter_name, type=type(gt_event).__name__, value=value
        )
        event_to_emit = ExecutionEvent(payload=payload)
        await __emit_message("execution_event", event_to_emit.json())


def _create_websocket_connection(api_key: str) -> Any:
    """Create an async WebSocket connection to the Nodes API."""
    endpoint = urljoin(
        os.getenv("GRIPTAPE_NODES_API_BASE_URL", "https://api.nodes.griptape.ai").replace("http", "ws"),
        "/ws/engines/events?version=v2",
    )

    return connect(
        endpoint,
        additional_headers={"Authorization": f"Bearer {api_key}"},
    )


async def __emit_message(event_type: str, payload: str, topic: str | None = None) -> None:
    """Send a message via WebSocket asynchronously."""
    if ws_connection_for_sending is None:
        logger.warning("WebSocket connection not available for sending message")
        return

    try:
        # Determine topic based on session_id and engine_id in the payload
        if topic is None:
            topic = _determine_response_topic()

        body = {"type": event_type, "payload": json.loads(payload), "topic": topic}

        await ws_connection_for_sending.send(json.dumps(body))
    except WebSocketException as e:
        logger.error("Error sending event to Nodes API: %s", e)
    except Exception as e:
        logger.error("Unexpected error while sending event to Nodes API: %s", e)


def _determine_response_topic() -> str | None:
    """Determine the response topic based on session_id and engine_id in the payload."""
    engine_id = GriptapeNodes.get_engine_id()
    session_id = GriptapeNodes.get_session_id()

    # Normal topic determination logic
    # Check for session_id first (highest priority)
    if session_id:
        return f"sessions/{session_id}/response"

    # Check for engine_id if no session_id
    if engine_id:
        return f"engines/{engine_id}/response"

    # Default to generic response topic
    return "response"


def determine_request_topic() -> str | None:
    """Determine the request topic based on session_id and engine_id in the payload."""
    engine_id = GriptapeNodes.get_engine_id()
    session_id = GriptapeNodes.get_session_id()

    # Normal topic determination logic
    # Check for session_id first (highest priority)
    if session_id:
        return f"sessions/{session_id}/request"

    # Check for engine_id if no session_id
    if engine_id:
        return f"engines/{engine_id}/request"

    # Default to generic request topic
    return "request"


async def asubscribe_to_topic(topic: str) -> None:
    """Subscribe to a specific topic in the message bus."""
    if ws_connection_for_sending is None:
        logger.warning("WebSocket connection not available for subscribing to topic")
        return

    try:
        body = {"type": "subscribe", "topic": topic, "payload": {}}
        await ws_connection_for_sending.send(json.dumps(body))
        logger.info("Subscribed to topic: %s", topic)
    except WebSocketException as e:
        logger.error("Error subscribing to topic %s: %s", topic, e)
    except Exception as e:
        logger.error("Unexpected error while subscribing to topic %s: %s", topic, e)


async def aunsubscribe_from_topic(topic: str) -> None:
    """Unsubscribe from a specific topic in the message bus."""
    if ws_connection_for_sending is None:
        logger.warning("WebSocket connection not available for unsubscribing from topic")
        return

    try:
        body = {"type": "unsubscribe", "topic": topic, "payload": {}}
        await ws_connection_for_sending.send(json.dumps(body))
        logger.info("Unsubscribed from topic: %s", topic)
    except WebSocketException as e:
        logger.error("Error unsubscribing from topic %s: %s", topic, e)
    except Exception as e:
        logger.error("Unexpected error while unsubscribing from topic %s: %s", topic, e)


async def _aprocess_api_event(event: dict) -> None:
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
        if not isinstance(request_event, EventRequest):
            msg = f"Deserialized event is not an EventRequest: {type(request_event)}"
            raise TypeError(msg)  # noqa: TRY301
    except Exception as e:
        msg = f"Unable to convert request JSON into a valid EventRequest object. Error Message: '{e}'"
        raise RuntimeError(msg) from None

    # Check if the event implements SkipTheLineMixin for priority processing
    if isinstance(request_event.request, SkipTheLineMixin):
        # Handle the event immediately without queuing
        # The request is guaranteed to be a RequestPayload since it passed earlier validation
        result_payload = await GriptapeNodes.ahandle_request(
            cast("RequestPayload", request_event.request),
            response_topic=request_event.response_topic,
            request_id=request_event.request_id,
        )

        # Create the result event and emit response immediately
        if result_payload.succeeded():
            result_event = EventResultSuccess(
                request=cast("RequestPayload", request_event.request),
                request_id=request_event.request_id,
                result=result_payload,
                response_topic=request_event.response_topic,
            )
            dest_socket = "success_result"
        else:
            result_event = EventResultFailure(
                request=cast("RequestPayload", request_event.request),
                request_id=request_event.request_id,
                result=result_payload,
                response_topic=request_event.response_topic,
            )
            dest_socket = "failure_result"

        # Emit the response immediately
        await __emit_message(dest_socket, result_event.json(), topic=result_event.response_topic)
    else:
        # Add the event to the async queue for normal processing
        await aput_event(request_event)
