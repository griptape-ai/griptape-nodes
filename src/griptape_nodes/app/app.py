from __future__ import annotations

import json
import logging
import os
import signal
import sys
import threading
from queue import Queue
from time import sleep
from typing import Any, cast
from urllib.parse import urljoin

import httpx
import uvicorn
from dotenv import get_key
from fastapi import FastAPI, Request
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
from xdg_base_dirs import xdg_config_home

from griptape_nodes.app.nodes_api_socket_manager import NodesApiSocketManager

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


griptape_nodes_logger = logging.getLogger("griptape_nodes")
# When running as an app, we want to forward all log messages to the event queue so they can be sent to the GUI
griptape_nodes_logger.addHandler(EventLogHandler())
griptape_nodes_logger.addHandler(RichHandler(show_time=True, show_path=False, markup=True, rich_tracebacks=True))
griptape_nodes_logger.setLevel(logging.INFO)

# Logger for this module. Important that this is not the same as the griptape_nodes logger or else we'll have infinite log events.
logger = logging.getLogger(__name__)
console = Console()


def start_app() -> None:
    """Main entry point for the Griptape Nodes app.

    Starts the event loop and listens for events from the Nodes API.
    """
    global socket_manager  # noqa: PLW0603 # Need to initialize the socket lazily here to avoid auth-ing too early

    # Listen for SSE events from the Nodes API in a separate thread
    socket_manager = NodesApiSocketManager()

    _init_event_listeners()

    # Listen for any signals to exit the app
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_: sys.exit(0))

    # SSE subscription pushes events into event_queue
    threading.Thread(target=_listen_for_api_events, daemon=True).start()

    if STATIC_SERVER_ENABLED:
        threading.Thread(target=_serve_static_server, daemon=True).start()

    _process_event_queue()


def _serve_static_server() -> None:
    """Run FastAPI with Uvicorn in order to serve static files produced by nodes."""
    config_manager = GriptapeNodes.ConfigManager()
    app = FastAPI()

    static_dir = config_manager.workspace_path / config_manager.merged_config["static_files_directory"]

    if not static_dir.exists():
        static_dir.mkdir(parents=True, exist_ok=True)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[os.getenv("GRIPTAPE_NODES_UI_BASE_URL", "https://nodes.griptape.ai"), "http://localhost:5173"],
        allow_credentials=True,
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )

    app.mount(
        STATIC_SERVER_URL,
        StaticFiles(directory=static_dir),
        name="static",
    )

    @app.post("/engines/request")
    async def create_event(request: Request) -> None:
        body = await request.json()
        if "payload" in body:
            __process_api_event(body["payload"])

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


def _listen_for_api_events() -> None:
    """Listen for events from the Nodes API and process them."""
    init = False
    while True:
        try:
            endpoint = urljoin(
                os.getenv("GRIPTAPE_NODES_API_BASE_URL", "https://api.nodes.griptape.ai"), "/api/engines/stream"
            )
            nodes_app_url = os.getenv("GRIPTAPE_NODES_UI_BASE_URL", "https://nodes.griptape.ai")

            with httpx.stream("get", endpoint, auth=__build_authorized_request, timeout=None) as response:  # noqa: S113 We intentionally want to never timeout
                __check_api_key_validity(response)

                response.raise_for_status()

                for line in response.iter_lines():
                    if line.startswith("data:"):
                        data = line.removeprefix("data:").strip()
                        if data == "START":
                            if not init:
                                __broadcast_app_initialization_complete(nodes_app_url)
                                init = True
                        else:
                            try:
                                event = json.loads(data)
                                # With heartbeat events, we skip the regular processing and just send the heartbeat
                                # Technically no longer needed since https://github.com/griptape-ai/griptape-nodes/pull/369
                                # but we don't have a proper EventRequest for it yet.
                                if event.get("request_type") == "Heartbeat":
                                    session_id = GriptapeNodes.get_session_id()
                                    socket_manager.heartbeat(session_id=session_id, request=event["request"])
                                else:
                                    __process_api_event(event)
                            except Exception:
                                logger.exception("Error processing event, skipping.")

        except Exception as e:
            details = f"Error while listening for events. Retrying in 2 seconds.: {e}"
            logger.error(details)
            sleep(2)
            init = False


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

    # Don't send events over the wire that don't have a request_id set (e.g. engine-internal events)
    event_json = result_event.json()
    socket_manager.emit(dest_socket, event_json)


def __process_execution_node_event(event: ExecutionGriptapeNodeEvent) -> None:
    """Process ExecutionGriptapeNodeEvents and send them to the API."""
    result_event = event.wrapped_event
    if type(result_event.payload).__name__ == "NodeStartProcessEvent":
        GriptapeNodes.EventManager().current_active_node = result_event.payload.node_name
    event_json = result_event.json()

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
    # Set the node name here so I am not double importing
    socket_manager.emit("execution_event", event_json)


def __process_progress_event(gt_event: ProgressEvent) -> None:
    """Process Griptape framework events and send them to the API."""
    node_name = gt_event.node_name
    if node_name:
        value = gt_event.value
        payload = execution_events.GriptapeEvent(
            node_name=node_name, parameter_name=gt_event.parameter_name, type=type(gt_event).__name__, value=value
        )
        event_to_emit = ExecutionEvent(payload=payload)
        socket_manager.emit("execution_event", event_to_emit.json())


def __process_app_event(event: AppEvent) -> None:
    """Process AppEvents and send them to the API."""
    # Let Griptape Nodes broadcast it.
    GriptapeNodes.broadcast_app_event(event.payload)

    socket_manager.emit("app_event", event.json())


def _process_event_queue() -> None:
    """Listen for events in the event queue and process them.

    Event queue will be populated by background threads listening for events from the Nodes API.
    """
    while True:
        event = event_queue.get(block=True)
        if isinstance(event, EventRequest):
            request_payload = event.request
            GriptapeNodes.handle_request(request_payload)
        elif isinstance(event, AppEvent):
            __process_app_event(event)
        else:
            logger.warning("Unknown event type encountered: '%s'.", type(event))

        event_queue.task_done()


def __build_authorized_request(request: httpx.Request) -> httpx.Request:
    api_key = get_key(xdg_config_home() / "griptape_nodes" / ".env", "GT_CLOUD_API_KEY")
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
    request.headers.update(
        {
            "Accept": "text/event-stream",
            "Authorization": f"Bearer {api_key}",
        }
    )
    return request


def __check_api_key_validity(response: httpx.Response) -> None:
    """Check if the API key is valid by checking the response status code.

    If the API key is invalid, print an error message and exit the program.
    """
    if response.status_code in {401, 403}:
        message = Panel(
            Align.center(
                "[bold red]Nodes API key is invalid, please run [code]gtn init[/code] with a valid key: [/bold red]"
                "[code]gtn init --api-key <your key>[/code]\n"
                "[bold red]You can generate a new key from [/bold red][bold blue][link=https://nodes.griptape.ai]https://nodes.griptape.ai[/link][/bold blue]",
            ),
            title="🔑 ❌ Invalid Nodes API Key",
            border_style="red",
            padding=(1, 4),
        )
        console.print(message)
        sys.exit(1)


def __broadcast_app_initialization_complete(nodes_app_url: str) -> None:
    """Broadcast the AppInitializationComplete event to all listeners.

    This is used to notify the GUI that the app is ready to receive events.
    """
    # Broadcast this to anybody who wants a callback on "hey, the app's ready to roll"
    payload = app_events.AppInitializationComplete()
    app_event = AppEvent(payload=payload)
    __process_app_event(app_event)

    engine_version_request = app_events.GetEngineVersionRequest()
    engine_version_result = GriptapeNodes.get_instance().handle_engine_version_request(engine_version_request)
    if isinstance(engine_version_result, app_events.GetEngineVersionResultSuccess):
        engine_version = f"v{engine_version_result.major}.{engine_version_result.minor}.{engine_version_result.patch}"
    else:
        engine_version = "<UNKNOWN ENGINE VERSION>"

    message = Panel(
        Align.center(
            f"[bold green]Engine is ready to receive events[/bold green]\n"
            f"[bold blue]Return to: [link={nodes_app_url}]{nodes_app_url}[/link] to access the Workflow Editor[/bold blue]",
            vertical="middle",
        ),
        title="🚀 Griptape Nodes Engine Started",
        subtitle=f"[green]{engine_version}[/green]",
        border_style="green",
        padding=(1, 4),
    )
    console.print(message)


def __process_api_event(data: Any) -> None:
    """Process API events and send them to the event queue."""
    try:
        data["request"]
    except KeyError:
        msg = "Error: 'request' was expected but not found."
        raise RuntimeError(msg) from None

    try:
        event_type = data["event_type"]
        if event_type != "EventRequest":
            msg = "Error: 'event_type' was found on request, but did not match 'EventRequest' as expected."
            raise RuntimeError(msg) from None
    except KeyError:
        msg = "Error: 'event_type' not found in request."
        raise RuntimeError(msg) from None

    # Now attempt to convert it into an EventRequest.
    try:
        request_event: EventRequest = cast("EventRequest", deserialize_event(json_data=data))
    except Exception as e:
        msg = f"Unable to convert request JSON into a valid EventRequest object. Error Message: '{e}'"
        raise RuntimeError(msg) from None

    # Add a request_id to the payload
    request_id = request_event.request.request_id
    request_event.request.request_id = request_id

    # Add the event to the queue
    event_queue.put(request_event)

    return request_id
