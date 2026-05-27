"""Strict-mode enforcement framework.

Strict mode is a runtime contract for what node code is allowed to do
across the orchestrator/worker split. This module owns the scope
machinery, the violation record, and the reporter. Detectors live at
their own call sites (e.g. ``BaseNode.aprocess``, ``EventManager.handle_request``)
and import ``report_violation`` to route violations here.

Two scope kinds exist:

* ``RUNTIME_EXECUTE`` opens around ``NodeManager.on_execute_node_request``
  for a single node's execution.
* ``LOAD_PROBE`` opens around each class's schema probe in
  ``LibraryManager._serialize_library_node_schemas``.

Severity is picked per-rule by :func:`_resolve_severity`: correctness
rules fail on both sides, ergonomics rules warn on orchestrator and
escalate to ERROR on the worker. Callers that need to escalate a worker
violation (e.g. convert ``ExecuteNodeResultSuccess`` to a failure, or
skip a class's schema) inspect the scope's ``violations`` list after
exit.
"""

from __future__ import annotations

import logging
import threading
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterator

    from griptape_nodes.retained_mode.events.base_events import ResultPayload

logger = logging.getLogger("griptape_nodes.strict_mode")


_current_scope_stack: ContextVar[tuple[StrictModeScope, ...]] = ContextVar(
    "_strict_mode_current_scope_stack", default=()
)

_node_init_depth = threading.local()
_sanctioned_param_mutation_depth = threading.local()


class StrictModeScopeKind(StrEnum):
    RUNTIME_EXECUTE = "runtime_execute"
    LOAD_PROBE = "load_probe"


class StrictModeSeverity(StrEnum):
    WARNING = "warning"
    ERROR = "error"


@dataclass(frozen=True)
class StrictModeViolation:
    rule_id: str
    severity: StrictModeSeverity
    scope_kind: StrictModeScopeKind
    subject: str
    library_name: str | None
    message: str


@dataclass
class StrictModeScope:
    kind: StrictModeScopeKind
    subject: str
    library_name: str | None
    is_worker: bool
    violations: list[StrictModeViolation] = field(default_factory=list)


@contextmanager
def strict_mode_scope(
    *,
    kind: StrictModeScopeKind,
    subject: str,
    library_name: str | None,
    is_worker: bool,
) -> Iterator[StrictModeScope]:
    """Enter a strict-mode scope.

    Pushes onto a per-task ContextVar stack so nested scopes (e.g. a
    LOAD_PROBE inside a RUNTIME_EXECUTE) restore the outer scope on
    exit. ``current_scope()`` always returns the innermost.
    """
    scope = StrictModeScope(kind=kind, subject=subject, library_name=library_name, is_worker=is_worker)
    previous = _current_scope_stack.get()
    token = _current_scope_stack.set((*previous, scope))
    try:
        yield scope
    finally:
        _current_scope_stack.reset(token)


def current_scope() -> StrictModeScope | None:
    """Return the innermost strict-mode scope active on the current task, if any."""
    stack = _current_scope_stack.get()
    if not stack:
        return None
    return stack[-1]


@contextmanager
def node_init_scope() -> Iterator[None]:
    """Mark the calling thread as executing ``BaseNode.__init__``.

    ``EventManager.handle_request`` checks the flag to detect the
    ``reentrant-bus-in-init`` rule: a node class that issues an
    event-bus request from its constructor deadlocks the worker's
    schema probe, which calls ``__init__`` on the worker thread.

    Nested constructors (subclass __init__ calls super().__init__) are
    supported via a depth counter -- the flag is cleared only when the
    outermost __init__ returns.
    """
    depth = getattr(_node_init_depth, "depth", 0)
    _node_init_depth.depth = depth + 1
    try:
        yield
    finally:
        _node_init_depth.depth -= 1


def in_node_init() -> bool:
    """Return True when the calling thread is inside ``BaseNode.__init__``."""
    return getattr(_node_init_depth, "depth", 0) > 0


@contextmanager
def sanctioned_parameter_mutation() -> Iterator[None]:
    """Mark an add_parameter / remove_parameter_element call as handler-driven.

    The ``parameter-mutation-during-aprocess`` detector fires whenever a
    node mutates its own parameter list while a strict-mode execution
    scope is active. The AddParameterToNodeRequest and
    RemoveParameterFromNodeRequest handlers reach ``BaseNode.add_parameter``
    /``remove_parameter_element`` by design -- they are the sanctioned
    path. Handlers wrap their call with this context so the detector
    only fires on direct calls from ``aprocess`` code.
    """
    depth = getattr(_sanctioned_param_mutation_depth, "depth", 0)
    _sanctioned_param_mutation_depth.depth = depth + 1
    try:
        yield
    finally:
        _sanctioned_param_mutation_depth.depth -= 1


def in_sanctioned_parameter_mutation() -> bool:
    """Return True when the current thread is inside a handler-sanctioned param mutation."""
    return getattr(_sanctioned_param_mutation_depth, "depth", 0) > 0


def _resolve_severity(*, rule_id: str, is_worker: bool) -> StrictModeSeverity:
    """Pick the severity for a reported rule.

    Correctness rules ({@code correctness=True} in the registry) fail on
    both sides. Non-correctness rules warn on the orchestrator and
    escalate to ERROR on the worker -- the worker's stateless model
    makes ergonomics issues load-bearing. If the rule is not in the
    registry, fall back to the historical worker=ERROR /
    orchestrator=WARNING split so migration can be incremental.
    """
    # Lazy import to avoid a circular dependency: strict_mode_checks imports StrictModeSeverity from here.
    from griptape_nodes.common.strict_mode_checks import RULES

    rule = RULES.get(rule_id)
    if rule is None:
        # A typo'd or unregistered rule_id should not silently produce a
        # violation. Log loudly so it surfaces in dev; production callers
        # still get the historical worker=ERROR / orchestrator=WARNING
        # fallback so existing detectors are not broken by the change.
        logger.warning(
            "strict-mode rule '%s' is not registered in RULES. Falling back to worker=%s default severity.",
            rule_id,
            "ERROR" if is_worker else "WARNING",
        )
        return StrictModeSeverity.ERROR if is_worker else StrictModeSeverity.WARNING
    if rule.correctness:
        return StrictModeSeverity.ERROR
    if is_worker and rule.worker_escalation:
        return StrictModeSeverity.ERROR
    return StrictModeSeverity.WARNING


def report_violation(*, rule_id: str, message: str) -> StrictModeScope | None:
    """Record a strict-mode violation against the currently active scope.

    No-op when no scope is active. Severity is resolved via the rule
    registry (see :func:`_resolve_severity`). Returns the active scope
    (with the new violation appended to ``violations``) so callers can
    inspect or pass it along.
    """
    scope = current_scope()
    if scope is None:
        return None
    severity = _resolve_severity(rule_id=rule_id, is_worker=scope.is_worker)
    violation = StrictModeViolation(
        rule_id=rule_id,
        severity=severity,
        scope_kind=scope.kind,
        subject=scope.subject,
        library_name=scope.library_name,
        message=message,
    )
    scope.violations.append(violation)
    subject_label = "node" if scope.kind is StrictModeScopeKind.RUNTIME_EXECUTE else "class"
    if severity is StrictModeSeverity.ERROR:
        logger.error(
            "strict-mode [%s/%s] %s=%s library=%s: %s",
            scope.kind.value,
            severity.value,
            subject_label,
            scope.subject,
            scope.library_name,
            message,
        )
    else:
        logger.warning(
            "strict-mode [%s/%s] %s=%s library=%s: %s",
            scope.kind.value,
            severity.value,
            subject_label,
            scope.subject,
            scope.library_name,
            message,
        )
    return scope


def attach_violations_to_result(result: ResultPayload, scope: StrictModeScope) -> None:
    """Append ``scope.violations`` onto ``result.result_details`` in place.

    ``ResultPayload.__post_init__`` has already coerced any string
    ``result_details`` into a ``ResultDetails``, so this function can
    rely on the list-of-details shape. Each violation becomes a
    ``StrictModeViolationDetail`` appended to the existing list.

    Mutates ``result`` and returns ``None``. Callers that want to
    return ``result`` after attaching should do so explicitly on the
    next line.
    """
    # Lazy import to avoid circular dependency: base_events imports nothing from this module,
    # but the caller chain (node_manager -> strict_mode) would circle back through base_events.
    from griptape_nodes.retained_mode.events.base_events import ResultDetails, StrictModeViolationDetail

    if not scope.violations:
        return

    # The Success/Failure base classes' __post_init__ coerce a string
    # ``result_details`` into a ``ResultDetails`` instance, so by the time
    # we see the payload the union has been narrowed -- but the type
    # system can't see that. The runtime check documents the invariant
    # and satisfies the checker.
    details = result.result_details
    if not isinstance(details, ResultDetails):
        msg = (
            f"attach_violations_to_result expected result_details to be ResultDetails "
            f"after __post_init__ coercion, got {type(details).__name__}."
        )
        raise TypeError(msg)
    for violation in scope.violations:
        level = logging.ERROR if violation.severity is StrictModeSeverity.ERROR else logging.WARNING
        details.result_details.append(
            StrictModeViolationDetail(
                level=level,
                message=violation.message,
                rule_id=violation.rule_id,
                severity=violation.severity.value,
                subject=violation.subject,
                library_name=violation.library_name,
            )
        )
