"""Tests for the exception-fidelity-lost strict-mode tripwire.

The cattrs unstructure hook for exceptions surfaces a violation when
the wire-format loses traceback frames. Two paths trigger it:

1. The exception was constructed but never raised, so
   ``__traceback__`` is None.
2. ``traceback.format_exception`` itself blew up.

Both leave the orchestrator-side caller with a type and message but
no frames. The rule is ergonomics-class (``correctness=False``):
worker escalates to ERROR, orchestrator stays at WARNING.
"""

from __future__ import annotations

import traceback as _traceback
from typing import TYPE_CHECKING

from griptape_nodes.common.strict_mode import (
    STRICT_MODE,
    StrictModeScopeKind,
    StrictModeSeverity,
)
from griptape_nodes.retained_mode.events.base_events import ForwardedException
from griptape_nodes.retained_mode.events.event_converter import converter

if TYPE_CHECKING:
    import pytest


class TestExceptionFidelityLost:
    """The tripwire fires when the wire-format loses traceback frames."""

    def test_raised_exception_records_no_violation(self) -> None:
        try:
            msg = "expected boom"
            raise RuntimeError(msg)  # noqa: TRY301
        except RuntimeError as exc:
            captured = exc

        with STRICT_MODE.open_scope(
            kind=StrictModeScopeKind.RUNTIME_EXECUTE,
            subject="node-1",
            library_name="libA",
            is_worker=True,
        ) as scope:
            unstructured = converter.unstructure(captured)

        assert scope.violations == []
        assert unstructured["type"] == "builtins.RuntimeError"
        assert unstructured["message"] == "expected boom"
        assert unstructured["traceback"] is not None

    def test_constructed_but_unraised_exception_records_violation(self) -> None:
        # An exception that was instantiated but never raised has no
        # ``__traceback__``. Returning one from worker code (rather than
        # raising it) is the dominant way users hit this rule.
        with STRICT_MODE.open_scope(
            kind=StrictModeScopeKind.RUNTIME_EXECUTE,
            subject="node-1",
            library_name="libA",
            is_worker=True,
        ) as scope:
            unstructured = converter.unstructure(ValueError("constructed-but-not-raised"))

        assert unstructured["traceback"] is None
        assert len(scope.violations) == 1
        violation = scope.violations[0]
        assert violation.rule_id == "exception-fidelity-lost"
        assert violation.severity is StrictModeSeverity.ERROR
        assert violation.subject == "node-1"
        assert "ValueError" in violation.message
        assert "__traceback__" in violation.message

    def test_orchestrator_scope_records_warning_not_error(self) -> None:
        # Ergonomics-class rule: orchestrator stays at WARNING, worker
        # escalates to ERROR. The previous correctness=True misclassification
        # would have promoted both sides to ERROR.
        with STRICT_MODE.open_scope(
            kind=StrictModeScopeKind.RUNTIME_EXECUTE,
            subject="node-1",
            library_name="libA",
            is_worker=False,
        ) as scope:
            converter.unstructure(ValueError("orchestrator-side"))

        assert len(scope.violations) == 1
        assert scope.violations[0].severity is StrictModeSeverity.WARNING

    def test_traceback_capture_failure_records_violation(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def boom(*_args: object, **_kwargs: object) -> str:
            msg = "synthetic traceback failure"
            raise RuntimeError(msg)

        monkeypatch.setattr(_traceback, "format_exception", boom)

        try:
            msg = "real raise so __traceback__ exists"
            raise ValueError(msg)  # noqa: TRY301
        except ValueError as exc:
            captured = exc

        with STRICT_MODE.open_scope(
            kind=StrictModeScopeKind.RUNTIME_EXECUTE,
            subject="node-1",
            library_name="libA",
            is_worker=True,
        ) as scope:
            unstructured = converter.unstructure(captured)

        assert unstructured["traceback"] is None
        assert len(scope.violations) == 1
        violation = scope.violations[0]
        assert violation.rule_id == "exception-fidelity-lost"
        assert violation.severity is StrictModeSeverity.ERROR
        assert "ValueError" in violation.message
        assert "formatted-traceback" in violation.message

    def test_unraised_exception_outside_scope_does_not_crash(self) -> None:
        unstructured = converter.unstructure(ValueError("payload"))

        assert unstructured["traceback"] is None
        assert unstructured["type"] == "builtins.ValueError"


class TestStructuredExceptionRoundTrip:
    """Receiving side rebuilds a ForwardedException carrying original metadata."""

    def test_dict_form_rebuilt_as_forwarded_exception(self) -> None:
        try:
            msg = "boom"
            raise RuntimeError(msg)  # noqa: TRY301
        except RuntimeError as exc:
            captured = exc

        unstructured = converter.unstructure(captured)
        rebuilt = converter.structure(unstructured, Exception)

        assert isinstance(rebuilt, ForwardedException)
        assert str(rebuilt) == "boom"
        assert rebuilt.original_type is not None
        assert "RuntimeError" in rebuilt.original_type
        assert rebuilt.original_traceback is not None
