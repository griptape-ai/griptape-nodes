from typing import Any, cast

from griptape_nodes.api.queue_manager import event_queue
from griptape_nodes.retained_mode.events.base_events import (
    EventRequest,
    deserialize_event,
)


def process_event(data: Any) -> int:
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

    # increment the request counter
    # Add the event to the queue
    event_queue.put(request_event)

    return request_id
