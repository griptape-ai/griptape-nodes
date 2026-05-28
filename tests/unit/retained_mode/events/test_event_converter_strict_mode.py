"""Tests for the exception-fidelity-lost strict-mode tripwire.

The cattrs unstructure hook for exceptions captures the traceback by
calling ``traceback.format_exception``. If that capture fails, the
hook reports an ``exception-fidelity-lost`` violation against the
active scope before falling back to ``traceback=None`` so the wire
shape stays serializable.

The detector is correctness-class: callers downstream rely on the
worker-side traceback for actionable failure logs, so severity is
ERROR on both orchestrator and worker.
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
    """The tripwire fires only when traceback capture itself fails."""

    def test_normal_exception_records_no_violation(self) -> None:
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
        assert unstructured["type"] == "RuntimeError"
        assert unstructured["message"] == "expected boom"
        assert unstructured["traceback"] is not None

    def test_traceback_capture_failure_records_violation(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def boom(*_args: object, **_kwargs: object) -> str:
            msg = "synthetic traceback failure"
            raise RuntimeError(msg)

        monkeypatch.setattr(_traceback, "format_exception", boom)

        with STRICT_MODE.open_scope(
            kind=StrictModeScopeKind.RUNTIME_EXECUTE,
            subject="node-1",
            library_name="libA",
            is_worker=True,
        ) as scope:
            unstructured = converter.unstructure(ValueError("payload"))

        assert unstructured["traceback"] is None
        assert len(scope.violations) == 1
        violation = scope.violations[0]
        assert violation.rule_id == "exception-fidelity-lost"
        assert violation.severity is StrictModeSeverity.ERROR
        assert violation.subject == "node-1"
        assert violation.library_name == "libA"
        assert "ValueError" in violation.message
        assert "traceback" in violation.message

    def test_traceback_capture_failure_outside_scope_does_not_crash(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def boom(*_args: object, **_kwargs: object) -> str:
            msg = "synthetic traceback failure"
            raise RuntimeError(msg)

        monkeypatch.setattr(_traceback, "format_exception", boom)
        unstructured = converter.unstructure(ValueError("payload"))

        assert unstructured["traceback"] is None
        assert unstructured["type"] == "ValueError"


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

    def test_string_form_falls_back_to_forwarded_exception(self) -> None:
        rebuilt = converter.structure("legacy stringified exception", Exception)
        assert isinstance(rebuilt, ForwardedException)
        assert str(rebuilt) == "legacy stringified exception"
        assert rebuilt.original_type is None
        assert rebuilt.original_traceback is None
