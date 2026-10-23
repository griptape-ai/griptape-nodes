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
_HANDLED_REQUEST_SCOPE_ATTR = "__handled_request_scope__"


class RequestScope(StrEnum):
    """What a request acts on, declared by its handler with `@handles(..., scope=...)`.

    HOST: the engine rather than one workflow. Dispatch ignores a workflow id on the request envelope
        and never rejects one. The handler has no `workflow` parameter.
    WORKFLOW: one open workflow, the one the request envelope names. The handler takes `workflow`
        with no default.
    OPTIONAL_WORKFLOW: works without a workflow, and uses the one the envelope names when there is
        one. The handler takes `workflow=None`.

    A handler that declares no scope is called with the request alone and has no `workflow` parameter.
    """

    HOST = "host"
    WORKFLOW = "workflow"
    OPTIONAL_WORKFLOW = "optional_workflow"


def handles(*request_types: type[RequestPayload], scope: RequestScope | None = None) -> Callable[[F], F]:
    """Mark a method as the handler for `request_types`. `EventManager.register_request_handlers` wires it up."""
    # A bare `@handles` passes the method itself here and would otherwise mark nothing.
    if not request_types or not all(inspect.isclass(request_type) for request_type in request_types):
        msg = f"@handles takes one or more request types, e.g. @handles(SomeRequest). Got {request_types!r}."
        raise TypeError(msg)

    def mark(method: F) -> F:
        # Marks set on the wrapper would be skipped, since the registration walk reads `__func__`.
        if isinstance(method, (staticmethod, classmethod)):
            msg = f"@handles must sit directly above `def`, below any @staticmethod or @classmethod. Got {method!r}."
            raise TypeError(msg)
        # One handler has one signature, so stacked marks must agree on what it is passed.
        if handled_request_types(method) and handled_request_scope(method) != scope:
            msg = f"Every @handles on {method.__qualname__} must declare the same scope."
            raise TypeError(msg)
        setattr(method, _HANDLED_REQUEST_TYPES_ATTR, (*handled_request_types(method), *request_types))
        setattr(method, _HANDLED_REQUEST_SCOPE_ATTR, scope)
        return method

    return mark


def handled_request_types(attr: object) -> tuple[type[RequestPayload], ...]:
    """Empty for anything not marked with `@handles`. Looks through @staticmethod and @classmethod."""
    return getattr(getattr(attr, "__func__", attr), _HANDLED_REQUEST_TYPES_ATTR, ())


def handled_request_scope(attr: object) -> RequestScope | None:
    """The scope `@handles` declared, or None when it declared none. Looks through @staticmethod and @classmethod."""
    return getattr(getattr(attr, "__func__", attr), _HANDLED_REQUEST_SCOPE_ATTR, None)


def check_handler_signature(
    handler: Callable[..., Any], scope: RequestScope | None, request_type: type[RequestPayload]
) -> None:
    """Check that `handler` takes the `workflow` argument dispatch passes for `scope`, by parameter name.

    Raises:
        TypeError: The handler's `workflow` parameter does not match its scope.
    """
    parameter = inspect.signature(handler).parameters.get("workflow")
    name = getattr(handler, "__qualname__", repr(handler))
    declared = "no scope" if scope is None else f"scope {scope.name}"
    attempt = f"Attempted to register '{name}' as the handler for {request_type.__name__} with {declared}."

    if scope is RequestScope.WORKFLOW:
        if parameter is None:
            msg = f"{attempt} Failed because it has no `workflow` parameter. Add `workflow` with no default."
            raise TypeError(msg)
        if parameter.default is not inspect.Parameter.empty:
            msg = f"{attempt} Failed because its `workflow` parameter has a default. Remove the default: dispatch always passes a workflow."
            raise TypeError(msg)
        return

    if scope is RequestScope.OPTIONAL_WORKFLOW:
        if parameter is None or parameter.default is not None:
            msg = f"{attempt} Failed because it has no `workflow` parameter defaulting to None. Add `workflow=None`."
            raise TypeError(msg)
        return

    if parameter is not None:
        msg = (
            f"{attempt} Failed because it has a `workflow` parameter, which dispatch passes only to "
            "WORKFLOW and OPTIONAL_WORKFLOW handlers. Remove it, or declare one of those scopes."
        )
        raise TypeError(msg)
