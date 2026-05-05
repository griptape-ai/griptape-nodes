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


_current_scope: ContextVar[StrictModeScope | None] = ContextVar("_strict_mode_current_scope", default=None)

_scope_lock = threading.Lock()
_scope_refcount = 0


@contextmanager
def strict_mode_scope(
    *,
    kind: StrictModeScopeKind,
    subject: str,
    library_name: str | None,
    is_worker: bool,
) -> Iterator[StrictModeScope]:
    """Enter a strict-mode scope.

    Sets a per-task ContextVar for attribution and bumps a process-wide
    refcount so ``any_scope_active_threadsafe`` is observable from threads
    that escape the ContextVar copy (e.g. threads spawned inside a node's
    aprocess).
    """
    global _scope_refcount  # noqa: PLW0603
    scope = StrictModeScope(kind=kind, subject=subject, library_name=library_name, is_worker=is_worker)
    token = _current_scope.set(scope)
    with _scope_lock:
        _scope_refcount += 1
    try:
        yield scope
    finally:
        with _scope_lock:
            _scope_refcount -= 1
        _current_scope.reset(token)


def current_scope() -> StrictModeScope | None:
    """Return the strict-mode scope active on the current task, if any."""
    return _current_scope.get()


def any_scope_active_threadsafe() -> bool:
    """Return True if any strict-mode scope is active anywhere in this process.

    Readable from threads that do not have a ContextVar copy of the
    enclosing scope.
    """
    with _scope_lock:
        return _scope_refcount > 0


_node_init_depth = threading.local()


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
        return StrictModeSeverity.ERROR if is_worker else StrictModeSeverity.WARNING
    if rule.correctness:
        return StrictModeSeverity.ERROR
    return StrictModeSeverity.ERROR if is_worker else StrictModeSeverity.WARNING


def report_violation(*, rule_id: str, message: str) -> StrictModeScope | None:
    """Record a strict-mode violation against the currently active scope.

    No-op when no scope is active. Severity is resolved via the rule
    registry (see :func:`_resolve_severity`). Returns the active scope
    (with the new violation appended to ``violations``) so callers can
    inspect or pass it along.
    """
    scope = _current_scope.get()
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


def attach_violations_to_result(result: ResultPayload, scope: StrictModeScope) -> ResultPayload:
    """Merge ``scope.violations`` into ``result.result_details``.

    Coerces ``str`` result_details into a ``ResultDetails`` first (matching
    the ``__post_init__`` behavior of ``ResultPayloadSuccess`` and
    ``ResultPayloadFailure``). Each violation becomes a
    ``StrictModeViolationDetail`` appended to the existing list so the
    editor can render both the original message and the violations.

    Returns the same ``result`` object (mutated in place); returned for
    call-site chaining.
    """
    # Lazy import to avoid circular dependency: base_events imports nothing from this module,
    # but the caller chain (node_manager -> strict_mode) would circle back through base_events.
    import logging as _logging

    from griptape_nodes.retained_mode.events.base_events import (
        ResultDetails,
        StrictModeViolationDetail,
    )

    if not scope.violations:
        return result

    existing = result.result_details
    if isinstance(existing, str):
        existing = ResultDetails(message=existing, level=_logging.DEBUG)
        result.result_details = existing

    for violation in scope.violations:
        level = _logging.ERROR if violation.severity is StrictModeSeverity.ERROR else _logging.WARNING
        existing.result_details.append(
            StrictModeViolationDetail(
                level=level,
                message=violation.message,
                rule_id=violation.rule_id,
                severity=violation.severity.value,
                subject=violation.subject,
                library_name=violation.library_name,
            )
        )
    return result
