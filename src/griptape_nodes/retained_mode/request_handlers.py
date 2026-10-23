from __future__ import annotations

import inspect
from enum import StrEnum
from typing import TYPE_CHECKING, TypeVar

if TYPE_CHECKING:
    from collections.abc import Callable
    from typing import Any

    from griptape_nodes.retained_mode.events.base_events import RequestPayload

F = TypeVar("F", bound="Callable[..., Any]")

_HANDLED_REQUEST_TYPES_ATTR = "__handled_request_types__"
_REQUIRED_SENDERS_ATTR = "__required_senders__"


class RequiredSender(StrEnum):
    """Who must have sent a request for its handler to run. `EventManager` refuses any other."""

    # Another engine, named on the request's envelope.
    ENGINE = "engine"
    # Another engine, and the session it sent the request from.
    SESSION = "session"


def handles(*request_types: type[RequestPayload], sender: RequiredSender | None = None) -> Callable[[F], F]:
    """Mark a method as the handler for `request_types`. `EventManager.register_request_handlers` wires it up.

    With `sender`, the handler runs only for requests another engine sent, as `sender` requires.
    """
    # A bare `@handles` passes the method itself here and would otherwise mark nothing.
    if not request_types or not all(inspect.isclass(request_type) for request_type in request_types):
        msg = f"@handles takes one or more request types, e.g. @handles(SomeRequest). Got {request_types!r}."
        raise TypeError(msg)

    def mark(method: F) -> F:
        # Marks set on the wrapper would be skipped, since the registration walk reads `__func__`.
        if isinstance(method, (staticmethod, classmethod)):
            msg = f"@handles must sit directly above `def`, below any @staticmethod or @classmethod. Got {method!r}."
            raise TypeError(msg)
        setattr(method, _HANDLED_REQUEST_TYPES_ATTR, (*handled_request_types(method), *request_types))
        if sender is not None:
            required = {**required_senders(method), **dict.fromkeys(request_types, sender)}
            setattr(method, _REQUIRED_SENDERS_ATTR, required)
        return method

    return mark


def handled_request_types(attr: object) -> tuple[type[RequestPayload], ...]:
    """Empty for anything not marked with `@handles`. Looks through @staticmethod and @classmethod."""
    return getattr(getattr(attr, "__func__", attr), _HANDLED_REQUEST_TYPES_ATTR, ())


def required_senders(attr: object) -> dict[type[RequestPayload], RequiredSender]:
    """The sender each request type `attr` handles requires, for those marked with one."""
    return getattr(getattr(attr, "__func__", attr), _REQUIRED_SENDERS_ATTR, {})
