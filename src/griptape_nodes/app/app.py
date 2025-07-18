from __future__ import annotations

import asyncio
import binascii
import json
import logging
import os
import signal
import sys
import threading
from pathlib import Path
from queue import Queue
from typing import Any, cast
from urllib.parse import urljoin

import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from griptape.events import (
    EventBus,
    EventListener,
)
from rich.align import Align
from rich.console import Console
from rich.logging import RichHandler
from rich.panel import Panel
from websockets.asyncio.client import connect
from websockets.exceptions import ConnectionClosed, WebSocketException

# This import is necessary to register all events, even if not technically used
from griptape_nodes.retained_mode.events import app_events, execution_events
from griptape_nodes.retained_mode.events.base_events import (
    AppEvent,
    EventRequest,
    EventResultFailure,
    EventResultSuccess,
    ExecutionEvent,
    ExecutionGriptapeNodeEvent,
    GriptapeNodeEvent,
    ProgressEvent,
    deserialize_event,
)
from griptape_nodes.retained_mode.events.logger_events import LogHandlerEvent
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

# This is a global event queue that will be used to pass events between threads
event_queue = Queue()

# Global WebSocket connection for sending events
ws_connection_for_sending = None
event_loop = None

# Event to signal when WebSocket connection is ready
ws_ready_event = threading.Event()


# Whether to enable the static server
STATIC_SERVER_ENABLED = os.getenv("STATIC_SERVER_ENABLED", "true").lower() == "true"
# Host of the static server
STATIC_SERVER_HOST = os.getenv("STATIC_SERVER_HOST", "localhost")
# Port of the static server
STATIC_SERVER_PORT = int(os.getenv("STATIC_SERVER_PORT", "8124"))
# URL path for the static server
STATIC_SERVER_URL = os.getenv("STATIC_SERVER_URL", "/static")
# Log level for the static server
STATIC_SERVER_LOG_LEVEL = os.getenv("STATIC_SERVER_LOG_LEVEL", "info").lower()


class EventLogHandler(logging.Handler):
    """Custom logging handler that emits log messages as AppEvents.

    This is used to forward log messages to the event queue so they can be sent to the GUI.
    """

    def emit(self, record: logging.LogRecord) -> None:
        event_queue.put(
            AppEvent(
                payload=LogHandlerEvent(message=record.getMessage(), levelname=record.levelname, created=record.created)
            )
        )


# Logger for this module. Important that this is not the same as the griptape_nodes logger or else we'll have infinite log events.
logger = logging.getLogger("griptape_nodes_app")

griptape_nodes_logger = logging.getLogger("griptape_nodes")
# When running as an app, we want to forward all log messages to the event queue so they can be sent to the GUI
griptape_nodes_logger.addHandler(EventLogHandler())
griptape_nodes_logger.addHandler(RichHandler(show_time=True, show_path=False, markup=True, rich_tracebacks=True))
griptape_nodes_logger.setLevel(logging.INFO)

console = Console()


def start_app() -> None:
    """Main entry point for the Griptape Nodes app.

    Starts the event loop and listens for events from the Nodes API.
    """
    _init_event_listeners()

    # Listen for any signals to exit the app
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_: sys.exit(0))

    api_key = _ensure_api_key()
    threading.Thread(target=_listen_for_api_events, args=(api_key,), daemon=True).start()

    if STATIC_SERVER_ENABLED:
        static_dir = _build_static_dir()
        threading.Thread(target=_serve_static_server, args=(static_dir,), daemon=True).start()

    _process_event_queue()


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
            title="🔑 ❌ Missing Nodes API Key",
            border_style="red",
            padding=(1, 4),
        )
        console.print(message)
        sys.exit(1)

    return api_key


def _build_static_dir() -> Path:
    """Build the static directory path based on the workspace configuration."""
    config_manager = GriptapeNodes.ConfigManager()
    return config_manager.workspace_path / config_manager.merged_config["static_files_directory"]


def _serve_static_server(static_dir: Path) -> None:
    """Run FastAPI with Uvicorn in order to serve static files produced by nodes."""
    app = FastAPI()

    if not static_dir.exists():
        static_dir.mkdir(parents=True, exist_ok=True)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            os.getenv("GRIPTAPE_NODES_UI_BASE_URL", "https://app.nodes.griptape.ai"),
            "https://app.nodes-staging.griptape.ai",
            "http://localhost:5173",
        ],
        allow_credentials=True,
        allow_methods=["OPTIONS", "GET", "POST", "PUT"],
        allow_headers=["*"],
    )

    app.mount(
        STATIC_SERVER_URL,
        StaticFiles(directory=static_dir),
        name="static",
    )

    @app.post("/static-upload-urls")
    async def create_static_file_upload_url(request: Request) -> dict:
        """Create a URL for uploading a static file.

        Similar to a presigned URL, but for uploading files to the static server.
        """
        base_url = request.base_url
        body = await request.json()
        file_name = body["file_name"]
        url = urljoin(str(base_url), f"/static-uploads/{file_name}")

        return {"url": url}

    @app.put("/static-uploads/{file_path:path}")
    async def create_static_file(request: Request, file_path: str) -> dict:
        """Upload a static file to the static server."""
        if not STATIC_SERVER_ENABLED:
            msg = "Static server is not enabled. Please set STATIC_SERVER_ENABLED to True."
            raise ValueError(msg)

        file_full_path = Path(static_dir / file_path)

        # Create parent directories if they don't exist
        file_full_path.parent.mkdir(parents=True, exist_ok=True)

        data = await request.body()
        try:
            file_full_path.write_bytes(data)
        except binascii.Error as e:
            msg = f"Invalid base64 encoding for file {file_path}."
            logger.error(msg)
            raise HTTPException(status_code=400, detail=msg) from e
        except (OSError, PermissionError) as e:
            msg = f"Failed to write file {file_path} to {static_dir}: {e}"
            logger.error(msg)
            raise HTTPException(status_code=500, detail=msg) from e

        static_url = f"http://{STATIC_SERVER_HOST}:{STATIC_SERVER_PORT}{STATIC_SERVER_URL}/{file_path}"
        return {"url": static_url}

    @app.post("/engines/request")
    async def create_event(request: Request) -> None:
        body = await request.json()
        __process_api_event(body)

    logging.getLogger("uvicorn").addHandler(
        RichHandler(show_time=True, show_path=False, markup=True, rich_tracebacks=True)
    )

    uvicorn.run(
        app, host=STATIC_SERVER_HOST, port=STATIC_SERVER_PORT, log_level=STATIC_SERVER_LOG_LEVEL, log_config=None
    )


def _init_event_listeners() -> None:
    """Set up the Griptape EventBus EventListeners."""
    EventBus.add_event_listener(
        event_listener=EventListener(on_event=__process_node_event, event_types=[GriptapeNodeEvent])
    )

    EventBus.add_event_listener(
        event_listener=EventListener(
            on_event=__process_execution_node_event,
            event_types=[ExecutionGriptapeNodeEvent],
        )
    )

    EventBus.add_event_listener(
        event_listener=EventListener(
            on_event=__process_progress_event,
            event_types=[ProgressEvent],
        )
    )

    EventBus.add_event_listener(
        event_listener=EventListener(
            on_event=__process_app_event,  # pyright: ignore[reportArgumentType] TODO: https://github.com/griptape-ai/griptape-nodes/issues/868
            event_types=[AppEvent],  # pyright: ignore[reportArgumentType] TODO: https://github.com/griptape-ai/griptape-nodes/issues/868
        )
    )


async def _alisten_for_api_requests(api_key: str) -> None:
    """Listen for events from the Nodes API and process them asynchronously."""
    global ws_connection_for_sending, event_loop  # noqa: PLW0603
    event_loop = asyncio.get_running_loop()  # Store the event loop reference
    logger.info("Listening for events from Nodes API via async WebSocket")

    # Auto reconnect https://websockets.readthedocs.io/en/stable/reference/asyncio/client.html#opening-a-connection
    connection_stream = __create_websocket_connection(api_key)
    initialized = False
    async for ws_connection in connection_stream:
        try:
            ws_connection_for_sending = ws_connection  # Store for sending events
            ws_ready_event.set()  # Signal that WebSocket is ready for sending

            if not initialized:
                event_queue.put(AppEvent(payload=app_events.AppInitializationComplete()))
                initialized = True

            event_queue.put(AppEvent(payload=app_events.AppConnectionEstablished()))

            async for message in ws_connection:
                try:
                    data = json.loads(message)

                    __process_api_event(data)
                except Exception:
                    logger.exception("Error processing event, skipping.")
        except ConnectionClosed:
            continue
        except Exception as e:
            logger.error("Error while listening for events. Retrying in 2 seconds... %s", e)
            await asyncio.sleep(2)


def _listen_for_api_events(api_key: str) -> None:
    """Run the async WebSocket listener in an event loop."""
    asyncio.run(_alisten_for_api_requests(api_key))


def __process_node_event(event: GriptapeNodeEvent) -> None:
    """Process GriptapeNodeEvents and send them to the API."""
    # Emit the result back to the GUI
    result_event = event.wrapped_event
    if isinstance(result_event, EventResultSuccess):
        dest_socket = "success_result"
    elif isinstance(result_event, EventResultFailure):
        dest_socket = "failure_result"
    else:
        msg = f"Unknown/unsupported result event type encountered: '{type(result_event)}'."
        raise TypeError(msg) from None

    __schedule_async_task(__emit_message(dest_socket, result_event.json(), topic=result_event.response_topic))


def __process_execution_node_event(event: ExecutionGriptapeNodeEvent) -> None:
    """Process ExecutionGriptapeNodeEvents and send them to the API."""
    result_event = event.wrapped_event
    if type(result_event.payload).__name__ == "NodeStartProcessEvent":
        GriptapeNodes.EventManager().current_active_node = result_event.payload.node_name

    if type(result_event.payload).__name__ == "ResumeNodeProcessingEvent":
        node_name = result_event.payload.node_name
        logger.info("Resuming Node '%s'", node_name)
        flow_name = GriptapeNodes.NodeManager().get_node_parent_flow_by_name(node_name)
        request = EventRequest(request=execution_events.SingleExecutionStepRequest(flow_name=flow_name))
        event_queue.put(request)

    if type(result_event.payload).__name__ == "NodeFinishProcessEvent":
        if result_event.payload.node_name != GriptapeNodes.EventManager().current_active_node:
            msg = "Node start and finish do not match."
            raise KeyError(msg) from None
        GriptapeNodes.EventManager().current_active_node = None
    __schedule_async_task(__emit_message("execution_event", result_event.json()))


def __process_progress_event(gt_event: ProgressEvent) -> None:
    """Process Griptape framework events and send them to the API."""
    node_name = gt_event.node_name
    if node_name:
        value = gt_event.value
        payload = execution_events.GriptapeEvent(
            node_name=node_name, parameter_name=gt_event.parameter_name, type=type(gt_event).__name__, value=value
        )
        event_to_emit = ExecutionEvent(payload=payload)
        __schedule_async_task(__emit_message("execution_event", event_to_emit.json()))


def __process_app_event(event: AppEvent) -> None:
    """Process AppEvents and send them to the API."""
    # Let Griptape Nodes broadcast it.
    GriptapeNodes.broadcast_app_event(event.payload)

    __schedule_async_task(__emit_message("app_event", event.json()))


def _process_event_queue() -> None:
    """Listen for events in the event queue and process them.

    Event queue will be populated by background threads listening for events from the Nodes API.
    """
    # Wait for WebSocket connection to be established before processing events
    ws_ready_event.wait()

    while True:
        event = event_queue.get(block=True)
        if isinstance(event, EventRequest):
            request_payload = event.request
            GriptapeNodes.handle_request(
                request_payload, response_topic=event.response_topic, request_id=event.request_id
            )
        elif isinstance(event, AppEvent):
            __process_app_event(event)
        else:
            logger.warning("Unknown event type encountered: '%s'.", type(event))

        event_queue.task_done()


def __create_websocket_connection(api_key: str) -> Any:
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
    global ws_connection_for_sending  # noqa: PLW0602
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


def subscribe_to_topic(topic: str) -> None:
    """Subscribe to a specific topic in the message bus."""
    __schedule_async_task(_asubscribe_to_topic(topic))


def unsubscribe_from_topic(topic: str) -> None:
    """Unsubscribe from a specific topic in the message bus."""
    __schedule_async_task(_aunsubscribe_from_topic(topic))


async def _asubscribe_to_topic(topic: str) -> None:
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


async def _aunsubscribe_from_topic(topic: str) -> None:
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


def __schedule_async_task(coro: Any) -> None:
    """Schedule an async coroutine to run in the event loop from a sync context."""
    if event_loop and event_loop.is_running():
        asyncio.run_coroutine_threadsafe(coro, event_loop)
    else:
        logger.warning("Event loop not available for scheduling async task")


def __process_api_event(event: dict) -> None:
    """Process API events and send them to the event queue."""
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
        request_event: EventRequest = cast("EventRequest", deserialize_event(json_data=payload))
    except Exception as e:
        msg = f"Unable to convert request JSON into a valid EventRequest object. Error Message: '{e}'"
        raise RuntimeError(msg) from None

    # Add the event to the queue
    event_queue.put(request_event)
