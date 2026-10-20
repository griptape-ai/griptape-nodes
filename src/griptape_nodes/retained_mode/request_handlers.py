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

    A handler declares its scope by its `workflow` parameter. One that takes none is HOST. One that takes
    `workflow: WorkflowRuntime` is WORKFLOW, and `workflow: WorkflowRuntime | None = None` is
    OPTIONAL_WORKFLOW; dispatch passes it the workflow it resolved. The default decides, not the
    annotation. A handler that depends on a workflow through code that reads the binding itself, such as
    the library File API or user code it runs, takes the parameter too and binds it around that code with
    `Engine.bind_workflow`, passing `NO_WORKFLOW` when an optional one got None.
    """

    HOST = "host"
    WORKFLOW = "workflow"
    OPTIONAL_WORKFLOW = "optional_workflow"


def handles(*request_types: type[RequestPayload]) -> Callable[[F], F]:
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
        setattr(method, _HANDLED_REQUEST_TYPES_ATTR, (*handled_request_types(method), *request_types))
        return method

    return mark


def handled_request_types(attr: object) -> tuple[type[RequestPayload], ...]:
    """Empty for anything not marked with `@handles`. Looks through @staticmethod and @classmethod."""
    return getattr(getattr(attr, "__func__", attr), _HANDLED_REQUEST_TYPES_ATTR, ())


def scope_from_signature(handler: Callable[..., Any]) -> RequestScope | None:
    """The scope a handler's `workflow` parameter declares, or None when it takes no workflow.

    A callable object that wraps a handler, like the worker's RemoteHandler, declares nothing here: it
    says whether it takes a workflow through a `takes_workflow` attribute, and keeps the scope of the
    handler it replaced.

    Raises:
        TypeError: The signature can't say. The handler accepts `**kwargs` without naming `workflow`, as a
            decorator that hides its wrapped function's signature does, or its `workflow` parameter
            defaults to something other than None.
    """
    name = getattr(handler, "__qualname__", repr(handler))
    parameters = inspect.signature(handler).parameters
    parameter = parameters.get("workflow")
    if parameter is None:
        if any(other.kind is inspect.Parameter.VAR_KEYWORD for other in parameters.values()):
            msg = (
                f"Attempted to register the request handler '{name}'. Failed because it accepts **kwargs, so "
                "whether it takes a workflow can't be read from its signature. Name the parameters it takes, "
                "or wrap it with functools.wraps."
            )
            raise TypeError(msg)
        return None
    if parameter.default is None:
        return RequestScope.OPTIONAL_WORKFLOW
    if parameter.default is not inspect.Parameter.empty:
        msg = (
            f"Attempted to register the request handler '{name}'. Failed because its `workflow` parameter "
            f"defaults to {parameter.default!r}. Give it no default, or default it to None."
        )
        raise TypeError(msg)
    return RequestScope.WORKFLOW


def handler_takes_workflow(handler: Callable[..., Any]) -> bool:
    """Whether dispatch passes `handler` the workflow it resolved, as its `workflow` argument.

    A callable object that wraps a handler, like the worker's RemoteHandler, answers for the handler it
    wraps through a `takes_workflow` attribute.
    """
    declared = getattr(handler, "takes_workflow", None)
    if isinstance(declared, bool):
        return declared
    return scope_from_signature(handler) is not None
