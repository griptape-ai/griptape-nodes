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
_HANDLER_SCOPE_ATTR = "__handler_scope__"


class RequestScope(StrEnum):
    """What a request acts on, declared by its handler. Dispatch binds the workflow from it.

    HOST: the host rather than any one workflow (config, libraries, projects, secrets). It ignores any
        workflow the caller names, and its result is a host event.
    WORKFLOW: one open workflow. The caller names it, else the request acts on the workflow of the work that
        issued it, else on the engine's only open workflow. A request naming a workflow that isn't open
        fails, and so does one that names none while several are open.
    OPTIONAL_WORKFLOW: works on its own but resolves paths and macros against a workflow it is given.
        `{workflow_dir}` and the project situations built on it depend on which workflow is asking. Naming
        none while several are open runs it with no workflow rather than failing.
    """

    HOST = "host"
    WORKFLOW = "workflow"
    OPTIONAL_WORKFLOW = "optional_workflow"


def handles(*request_types: type[RequestPayload], scope: RequestScope | None = None) -> Callable[[F], F]:
    """Mark a method as the handler for `request_types`. `EventManager.register_request_handlers` wires it up.

    `scope` overrides the owner's `request_scope` for these request types.
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
        existing_scope = handler_scope(method)
        if scope is not None and existing_scope is not None and existing_scope != scope:
            msg = f"@handles gave {method!r} two different scopes: {existing_scope.value} and {scope.value}."
            raise TypeError(msg)
        setattr(method, _HANDLED_REQUEST_TYPES_ATTR, (*handled_request_types(method), *request_types))
        if scope is not None:
            setattr(method, _HANDLER_SCOPE_ATTR, scope)
        return method

    return mark


def handled_request_types(attr: object) -> tuple[type[RequestPayload], ...]:
    """Empty for anything not marked with `@handles`. Looks through @staticmethod and @classmethod."""
    return getattr(getattr(attr, "__func__", attr), _HANDLED_REQUEST_TYPES_ATTR, ())


def handler_scope(attr: object) -> RequestScope | None:
    """The scope a `@handles` method declared for itself, or None to take its owner's `request_scope`."""
    return getattr(getattr(attr, "__func__", attr), _HANDLER_SCOPE_ATTR, None)
