from __future__ import annotations

import json
import logging
import os
import sys
import threading
from queue import Queue
from time import sleep
from typing import Any, cast
from urllib.parse import urljoin

import httpx
from dotenv import get_key
from griptape.events import (
    BaseEvent,
    EventBus,
    EventListener,
    FinishStructureRunEvent,
    TextChunkEvent,
)
from rich.align import Align
from rich.console import Console
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
    deserialize_event,
)
from griptape_nodes.retained_mode.events.logger_events import LogHandlerEvent
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

# This is a global event queue that will be used to pass events between threads
event_queue = Queue()


class EventLogHandler(logging.Handler):
    """Custom logging handler that emits log messages as AppEvents.

    This is used to forward log messages to the event queue so they can be sent to the GUI.
    """

    def emit(self, record) -> None:
        event_queue.put(
            AppEvent(
                payload=LogHandlerEvent(message=record.getMessage(), levelname=record.levelname, created=record.created)
            )
        )


# When running as an app, we want to forward all log messages to the event queue so they can be sent to the GUI
logging.getLogger("griptape_nodes").addHandler(EventLogHandler())
# Logger for this module. Important that this is not the same as the griptape_nodes logger or else we'll have infinite log events.
logger = logging.getLogger(__name__)
console = Console()


def start_app() -> None:
    """Main entry point for the Griptape Nodes app.

    Starts the event loop and listens for events from the Nodes API.
    """
    global socket  # noqa: PLW0603 # Need to initialize the socket lazily here to avoid auth-ing too early

    # Listen for SSE events from the Nodes API in a separate thread
    socket = NodesApiSocketManager()
    sse_thread = threading.Thread(target=_listen_for_api_events, daemon=True)
    sse_thread.start()

    _init_event_listeners()

    try:
        _process_event_queue()
    except KeyboardInterrupt:
        sys.exit(0)


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
            on_event=__process_griptape_event,
            event_types=[FinishStructureRunEvent, TextChunkEvent],
        )
    )

    EventBus.add_event_listener(
        event_listener=EventListener(
            on_event=__process_app_event,  # pyright: ignore[reportArgumentType] TODO(collin): need to restructure Event class hierarchy
            event_types=[AppEvent],  # pyright: ignore[reportArgumentType] TODO(collin): need to restructure Event class hierarchy
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
            nodes_app_url = os.getenv("GRIPTAPE_NODES_APP_URL", "https://nodes.griptape.ai")

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
                                if event.get("request_type") == "Heartbeat":
                                    session_id = GriptapeNodes.get_session_id()
                                    socket.heartbeat(session_id=session_id, request=event)
                                else:
                                    __process_api_event(event)
                            except Exception:
                                logger.exception("Error processing event, skipping.")

        except Exception:
            logger.error("Error while listening for events. Retrying in 2 seconds.")
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

    event_json = result_event.json()
    socket.emit(dest_socket, event_json)


def __process_execution_node_event(event: ExecutionGriptapeNodeEvent) -> None:
    """Process ExecutionGriptapeNodeEvents and send them to the API."""
    result_event = event.wrapped_event
    if type(result_event.payload).__name__ == "NodeStartProcessEvent":
        GriptapeNodes.get_instance().EventManager().current_active_node = result_event.payload.node_name
    event_json = result_event.json()
    if type(result_event.payload).__name__ == "NodeFinishProcessEvent":
        if result_event.payload.node_name != GriptapeNodes.get_instance().EventManager().current_active_node:
            msg = "Node start and finish do not match."
            raise KeyError(msg) from None
        GriptapeNodes.get_instance().EventManager().current_active_node = None
    # Set the node name here so I am not double importing
    socket.emit("execution_event", event_json)


def __process_griptape_event(gt_event: BaseEvent) -> None:
    """Process Griptape framework events and send them to the API."""
    node_name = GriptapeNodes.get_instance().EventManager().current_active_node
    if node_name:
        if isinstance(gt_event, FinishStructureRunEvent):
            value = gt_event.to_dict()["output_task_output"]["value"]
        elif isinstance(gt_event, TextChunkEvent):
            value = gt_event.to_dict()["token"]
        else:
            value = gt_event.to_dict()
        payload = execution_events.GriptapeEvent(node_name=node_name, type=type(gt_event).__name__, value=value)
        event_to_emit = ExecutionEvent(payload=payload)
        socket.emit("execution_event", event_to_emit.json())


def __process_app_event(event: AppEvent) -> None:
    """Process AppEvents and send them to the API."""
    # Let Griptape Nodes broadcast it.
    GriptapeNodes.broadcast_app_event(event.payload)

    socket.emit("app_event", event.json())


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
            f"[bold blue]Return to: [link={nodes_app_url}]{nodes_app_url}[/link][/bold blue] to access the IDE",
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
        raise Exception(msg) from None

    try:
        event_type = data["event_type"]
        if event_type != "EventRequest":
            msg = "Error: 'event_type' was found on request, but did not match 'EventRequest' as expected."
            raise Exception(msg) from None
    except KeyError:
        msg = "Error: 'event_type' not found in request."
        raise Exception(msg) from None

    # Now attempt to convert it into an EventRequest.
    try:
        request_event: EventRequest = cast("EventRequest", deserialize_event(json_data=data))
    except Exception as e:
        msg = f"Unable to convert request JSON into a valid EventRequest object. Error Message: '{e}'"
        raise Exception(msg) from None

    # Add a request_id to the payload
    request_id = request_event.request.request_id
    request_event.request.request_id = request_id

    # Add the event to the queue
    event_queue.put(request_event)

    return request_id
