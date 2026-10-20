from __future__ import annotations

import ast
import inspect
from enum import StrEnum
from typing import TYPE_CHECKING, TypeVar, get_args

if TYPE_CHECKING:
    from collections.abc import Callable
    from typing import Any

    from griptape_nodes.retained_mode.events.base_events import RequestPayload

F = TypeVar("F", bound="Callable[..., Any]")

_HANDLED_REQUEST_TYPES_ATTR = "__handled_request_types__"
_HANDLER_SCOPE_ATTR = "__handler_scope__"
# Subscripted names whose arguments are alternatives: `Optional[X]` admits None, `Union[...]` may.
_OPTIONAL_NAMES = frozenset({"Optional"})
_UNION_NAMES = frozenset({"Union"})


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

    A handler declares its scope by its signature. One that takes no `workflow` parameter is HOST. One
    that takes `workflow: WorkflowRuntime` is WORKFLOW, and `workflow: WorkflowRuntime | None = None` is
    OPTIONAL_WORKFLOW; dispatch passes it the workflow it resolved. A handler that depends on a workflow
    only through code that reads the binding itself, such as the library File API or user code it runs,
    passes `scope=` to @handles instead (see `resolve_handler_scope`).
    """

    HOST = "host"
    WORKFLOW = "workflow"
    OPTIONAL_WORKFLOW = "optional_workflow"


def handles(*request_types: type[RequestPayload], scope: RequestScope | None = None) -> Callable[[F], F]:
    """Mark a method as the handler for `request_types`. `EventManager.register_request_handlers` wires it up.

    `scope` is for a handler that depends on a workflow without taking one. See `resolve_handler_scope`.
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
    """The scope a `@handles` method passed as `scope=`, or None when it passed none."""
    return getattr(getattr(attr, "__func__", attr), _HANDLER_SCOPE_ATTR, None)


def resolve_handler_scope(handler: Callable[..., Any], declared: RequestScope | None) -> RequestScope:
    """The scope `handler` acts on: from its `workflow` parameter, else `declared`, else HOST.

    `declared` is the `scope=` its registration passed. It exists only for a handler that depends on a
    workflow without taking one, so it may only be WORKFLOW or OPTIONAL_WORKFLOW, and only on a handler
    whose signature declares nothing.

    Raises:
        TypeError: `declared` is HOST, or contradicts or repeats the signature, or the signature is
            ambiguous (see `scope_from_signature`).
    """
    name = getattr(handler, "__qualname__", repr(handler))
    if declared is RequestScope.HOST:
        msg = (
            f"Attempted to register the request handler '{name}' with scope=host. Failed because a handler "
            "that takes no `workflow` parameter is already a host handler. Drop `scope=`."
        )
        raise TypeError(msg)
    signature_scope = scope_from_signature(handler)
    if signature_scope is not None and declared is not None:
        msg = (
            f"Attempted to register the request handler '{name}' with scope={declared.value}. Failed because "
            f"its `workflow` parameter already makes it {signature_scope.value}. Drop `scope=`."
        )
        raise TypeError(msg)
    if signature_scope is not None:
        return signature_scope
    if declared is not None:
        return declared
    return RequestScope.HOST


def scope_from_signature(handler: Callable[..., Any]) -> RequestScope | None:
    """The scope a handler's `workflow` parameter declares, or None when it takes no workflow.

    A callable object that wraps a handler, like the worker's RemoteHandler, declares nothing here: it
    says whether it takes a workflow through a `takes_workflow` attribute, and keeps the scope of the
    handler it replaced.

    Raises:
        TypeError: The signature can't say. The handler accepts `**kwargs` without naming `workflow`, as a
            decorator that hides its wrapped function's signature does, or its `workflow` parameter is
            annotated optional without defaulting to None, or defaults to something else.
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
    if _annotation_admits_none(parameter.annotation):
        msg = (
            f"Attempted to register the request handler '{name}'. Failed because its `workflow` parameter "
            "may be None but has no default. Default it to None to accept no workflow."
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


def _annotation_admits_none(annotation: object) -> bool:
    """Whether a parameter annotation admits None, as `X | None`, `Optional[X]`, or `Union[X, None]` do.

    Under `from __future__ import annotations` the annotation is a string, and the names in it are often
    imported only for type checking, so it is parsed rather than evaluated.
    """
    if annotation is inspect.Parameter.empty:
        return False
    if annotation is None or annotation is type(None):
        return True
    if not isinstance(annotation, str):
        return type(None) in get_args(annotation)
    try:
        expression = ast.parse(annotation, mode="eval").body
    except SyntaxError:
        return False
    return _expression_admits_none(expression)


def _expression_admits_none(expression: ast.expr) -> bool:
    if isinstance(expression, ast.Constant):
        return _constant_admits_none(expression)
    if isinstance(expression, ast.BinOp) and isinstance(expression.op, ast.BitOr):
        return _expression_admits_none(expression.left) or _expression_admits_none(expression.right)
    if isinstance(expression, ast.Subscript):
        return _subscript_admits_none(expression)
    return False


def _constant_admits_none(constant: ast.Constant) -> bool:
    if constant.value is None:
        return True
    # A quoted forward reference inside the annotation, such as `"WorkflowRuntime | None"`.
    if isinstance(constant.value, str):
        return _annotation_admits_none(constant.value)
    return False


def _subscript_admits_none(subscript: ast.Subscript) -> bool:
    name = _subscripted_name(subscript.value)
    if name in _OPTIONAL_NAMES:
        return True
    if name not in _UNION_NAMES:
        return False
    alternatives = [subscript.slice]
    if isinstance(subscript.slice, ast.Tuple):
        alternatives = subscript.slice.elts
    return any(_expression_admits_none(alternative) for alternative in alternatives)


def _subscripted_name(expression: ast.expr) -> str | None:
    """The bare name being subscripted: `Optional` for both `Optional[X]` and `typing.Optional[X]`."""
    if isinstance(expression, ast.Name):
        return expression.id
    if isinstance(expression, ast.Attribute):
        return expression.attr
    return None
