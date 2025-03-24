from typing import Any, cast

from flask import Blueprint, Response, jsonify, make_response, request

from griptape_nodes.api.queue_manager import event_queue
from griptape_nodes.retained_mode.events.base_events import (
    EventRequest,
    deserialize_event,
)

# This will be to create objects (nodes, connections)
api_blueprint = Blueprint("api", __name__, url_prefix="/api")

request_counter = 0


def process_event(data: Any) -> int:
    global request_counter  # noqa: PLW0603

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
    request_id = request_counter
    request_event.request.request_id = request_id

    # increment the request counter
    request_counter += 1
    # Add the event to the queue
    event_queue.put(request_event)

    return request_id


@api_blueprint.route("/request", methods=["POST", "OPTIONS"])
def post_request() -> Response:
    if request.method == "OPTIONS":
        response = make_response()
        response.headers.add("Access-Control-Allow-Origin", "*")
        response.headers.add("Access-Control-Allow-Headers", "Content-Type")
        response.headers.add("Access-Control-Allow-Methods", "POST")
        return response

    data = request.get_json()

    try:
        request_id = process_event(data)
    except Exception as e:
        response = jsonify(
            {
                "message": f"{e}",
            },
            400,
        )
        response.headers.add("Access-Control-Allow-Origin", "*")
        return response

    # Create response with CORS headers
    response = jsonify(
        {
            "message": f"Request for event type '{data['event_type']}' successfully received",
            "request_id": request_id,
        },
        200,
    )
    response.headers.add("Access-Control-Allow-Origin", "*")
    return response
