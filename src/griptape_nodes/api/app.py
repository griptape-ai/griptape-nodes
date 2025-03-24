from __future__ import annotations

import contextvars
import json
import logging
import os
import threading
from time import sleep
from typing import TYPE_CHECKING, Any

import httpx
from flask import Flask
from flask_cors import CORS
from flask_socketio import SocketIO
from griptape.events import (
    BaseEvent,
    EventBus,
    EventListener,
    FinishStructureRunEvent,
    TextChunkEvent,
)

from griptape_nodes.api.queue_manager import event_queue
from griptape_nodes.api.routes.api import api_blueprint, process_event
from griptape_nodes.api.routes.nodes_api_fake_socket import NodesApiFakeSocket

# This import is necessary to register all events, even if not technically used
from griptape_nodes.retained_mode.events import (
    app_events,
    execution_events,
)
from griptape_nodes.retained_mode.events.base_events import (
    AppEvent,
    EventRequest,
    EventResult_Failure,
    EventResult_Success,
    ExecutionEvent,
    ExecutionGriptapeNodeEvent,
    GriptapeNodeEvent,
)
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

if TYPE_CHECKING:
    from collections.abc import Callable


logger = logging.getLogger(__name__)

# This is a hack to allow the app to run in a non-websocket mode
# without updating the event handling code.
socket = NodesApiFakeSocket()


def run_with_context(func: Callable) -> Callable:
    ctx = contextvars.copy_context()

    def wrapper(*args, **kwargs) -> Any:
        return ctx.run(func, *args, **kwargs)

    return wrapper


# Define methods for events etc
def process_request(event: EventRequest) -> None:
    # make the request with this event
    from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

    # my start flow requests don't go through here well.
    request_payload = event.request
    GriptapeNodes().handle_request(request_payload)
    # All event sending is taking place


def send_event(event: GriptapeNodeEvent) -> None:
    # Emit the result back to the GUI
    result_event = event.wrapped_event
    if isinstance(result_event, EventResult_Success):
        dest_socket = "success_result"
    elif isinstance(result_event, EventResult_Failure):
        dest_socket = "failure_result"
    else:
        msg = f"Unknown/unsupported result event type encountered: '{type(result_event)}'."
        raise TypeError(msg) from None

    event_json = result_event.json()

    socket.emit(dest_socket, event_json)


def process_gt_event(gt_event: BaseEvent) -> None:
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


def send_execution_event(event: ExecutionGriptapeNodeEvent) -> None:
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


def process_app_event(event: AppEvent) -> None:
    # Get the payload
    payload = event.payload

    # Let Griptape Nodes broadcast it.
    GriptapeNodes().broadcast_app_event(payload)

    # TODO(griptape): send to GUI?


def check_event_queue() -> None:
    while True:
        if not event_queue.empty():
            event = event_queue.get()
            process_request(event)
            event_queue.task_done()


def setup_event_listeners() -> None:
    EventBus.add_event_listener(event_listener=EventListener(on_event=send_event, event_types=[GriptapeNodeEvent]))

    EventBus.add_event_listener(
        event_listener=EventListener(
            on_event=process_gt_event,
            event_types=[FinishStructureRunEvent, TextChunkEvent],
        )
    )

    EventBus.add_event_listener(
        event_listener=EventListener(
            on_event=send_execution_event,
            event_types=[ExecutionGriptapeNodeEvent],
        )
    )

    EventBus.add_event_listener(event_listener=EventListener(on_event=process_app_event, event_types=[AppEvent]))  # pyright: ignore[reportArgumentType] TODO(collin): need to restructure Event class hierarchy


def sse_listener() -> None:
    while True:
        try:
            # TODO(griptape): make environment driven
            endpoint = "https://api.nodes.griptape.ai/api/engines/stream"

            def auth(request: httpx.Request) -> httpx.Request:
                service = "Nodes"
                value = "NODES_API_TOKEN"
                api_token = GriptapeNodes.get_instance().ConfigManager().get_config_value(f"env.{service}.{value}")
                request.headers.update({"Accept": "text/event-stream", "Authorization": f"Bearer {api_token}"})
                return request

            with httpx.stream("get", endpoint, auth=auth, timeout=None) as response:  # noqa: S113 We intentionally want to never timeout
                response.raise_for_status()
                for line in response.iter_lines():
                    if not line.strip():
                        continue
                    if line.startswith("data:"):
                        data = line.removeprefix("data:").strip()
                        if data == "START":
                            logger.info("Engine is ready to receive events")
                        else:
                            process_event(json.loads(data))
        except httpx.HTTPStatusError:
            logger.exception("Error while listening to SSE")
            sleep(5)


def run_sse_mode() -> None:
    sse_thread = threading.Thread(target=sse_listener)
    sse_thread.start()

    setup_event_listeners()

    check_event_queue()


def run_websocket_mode() -> None:
    global socket  # noqa: PLW0603 Need to override the global socketio instance

    # Allows CORS
    app = Flask(__name__)
    socket = SocketIO(app, cors_allowed_origins="*")
    CORS(app, resources={r"/*": {"origins": "*"}})

    # Pass in the app and allow CORS from all origins
    # TODO(griptape): what about manage_session=False, async_handlers=False
    setup_event_listeners()
    app.register_blueprint(api_blueprint)

    # Broadcast this to anybody who wants a callback on "hey, the app's ready to roll"
    payload = app_events.AppInitializationComplete()
    app_event = AppEvent(payload=payload)
    EventBus.publish_event(app_event)  # pyright: ignore[reportArgumentType] TODO(collin): need to restructure Event class hierarchy

    socket.start_background_task(run_with_context(check_event_queue))
    socket.run(app, debug=False)


def main() -> None:
    if os.getenv("DEBUG", "true").lower() == "true":
        run_websocket_mode()
    else:
        run_sse_mode()
