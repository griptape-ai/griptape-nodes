from __future__ import annotations

import asyncio
import logging
import threading
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from collections.abc import Iterator

from griptape_nodes.common.strict_mode import (
    StrictModeScopeKind,
    StrictModeSeverity,
    any_scope_active_threadsafe,
    current_scope,
    report_violation,
    strict_mode_scope,
)
from griptape_nodes.common.strict_mode_checks import RULES, _rule


@pytest.fixture
def fake_rules() -> Iterator[None]:
    """Register two synthetic rules for the duration of the test.

    The framework PR ships an empty RULES catalog; rule PRs append entries
    later in the stack. Tests at this layer need a registered rule_id to
    exercise severity resolution, so they install one and tear it down.
    """
    ergonomics = _rule(
        "fake-ergonomics",
        severity=StrictModeSeverity.WARNING,
        correctness=False,
        description="synthetic ergonomics rule for tests",
        remediation="ergonomics: {detail}",
        worker_escalation=False,
    )
    correctness = _rule(
        "fake-correctness",
        severity=StrictModeSeverity.ERROR,
        correctness=True,
        description="synthetic correctness rule for tests",
        remediation="correctness: {detail}",
    )
    RULES[ergonomics.rule_id] = ergonomics
    RULES[correctness.rule_id] = correctness
    try:
        yield
    finally:
        RULES.pop(ergonomics.rule_id, None)
        RULES.pop(correctness.rule_id, None)


class TestStrictModeScope:
    def test_current_scope_is_none_outside_any_scope(self) -> None:
        assert current_scope() is None
        assert any_scope_active_threadsafe() is False

    def test_scope_sets_and_resets_contextvar(self) -> None:
        with strict_mode_scope(
            kind=StrictModeScopeKind.RUNTIME_EXECUTE,
            subject="node-1",
            library_name="libA",
            is_worker=False,
        ) as scope:
            assert current_scope() is scope
            assert scope.kind is StrictModeScopeKind.RUNTIME_EXECUTE
            assert scope.subject == "node-1"
            assert scope.library_name == "libA"
            assert scope.is_worker is False
            assert scope.violations == []
        assert current_scope() is None

    def test_nested_scopes_restore_outer_on_exit(self) -> None:
        with strict_mode_scope(
            kind=StrictModeScopeKind.RUNTIME_EXECUTE,
            subject="outer",
            library_name=None,
            is_worker=False,
        ) as outer:
            assert current_scope() is outer
            with strict_mode_scope(
                kind=StrictModeScopeKind.LOAD_PROBE,
                subject="inner",
                library_name="libX",
                is_worker=True,
            ) as inner:
                assert current_scope() is inner
            assert current_scope() is outer
        assert current_scope() is None

    def test_refcount_tracks_entered_scopes(self) -> None:
        assert any_scope_active_threadsafe() is False
        with strict_mode_scope(
            kind=StrictModeScopeKind.RUNTIME_EXECUTE,
            subject="n",
            library_name=None,
            is_worker=False,
        ):
            assert any_scope_active_threadsafe() is True
            with strict_mode_scope(
                kind=StrictModeScopeKind.LOAD_PROBE,
                subject="c",
                library_name=None,
                is_worker=True,
            ):
                assert any_scope_active_threadsafe() is True
            assert any_scope_active_threadsafe() is True
        assert any_scope_active_threadsafe() is False


class TestReportViolation:
    def test_no_op_outside_scope(self, caplog: pytest.LogCaptureFixture) -> None:
        caplog.set_level(logging.DEBUG, logger="griptape_nodes.strict_mode")
        result = report_violation(rule_id="r", message="m")
        assert result is None
        assert caplog.records == []

    def test_orchestrator_logs_warning(self, caplog: pytest.LogCaptureFixture, fake_rules: None) -> None:  # noqa: ARG002
        rule_id = "fake-ergonomics"
        caplog.set_level(logging.DEBUG, logger="griptape_nodes.strict_mode")
        with strict_mode_scope(
            kind=StrictModeScopeKind.RUNTIME_EXECUTE,
            subject="n",
            library_name="libA",
            is_worker=False,
        ) as scope:
            report_violation(rule_id=rule_id, message="something bad")
            assert len(scope.violations) == 1
            v = scope.violations[0]
            assert v.rule_id == rule_id
            assert v.severity is StrictModeSeverity.WARNING
            assert v.scope_kind is StrictModeScopeKind.RUNTIME_EXECUTE
            assert v.subject == "n"
            assert v.library_name == "libA"
            assert v.message == "something bad"

        warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
        errors = [r for r in caplog.records if r.levelno == logging.ERROR]
        assert len(warnings) == 1
        assert len(errors) == 0
        assert "something bad" in warnings[0].getMessage()

    def test_worker_logs_error(self, caplog: pytest.LogCaptureFixture, fake_rules: None) -> None:  # noqa: ARG002
        rule_id = "fake-correctness"
        caplog.set_level(logging.DEBUG, logger="griptape_nodes.strict_mode")
        with strict_mode_scope(
            kind=StrictModeScopeKind.RUNTIME_EXECUTE,
            subject="n",
            library_name="libA",
            is_worker=True,
        ) as scope:
            report_violation(rule_id=rule_id, message="very bad")
            assert scope.violations[0].severity is StrictModeSeverity.ERROR

        errors = [r for r in caplog.records if r.levelno == logging.ERROR]
        warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
        assert len(errors) == 1
        assert len(warnings) == 0


class TestParallelTaskIsolation:
    @pytest.mark.asyncio
    async def test_concurrent_tasks_have_independent_scopes(self) -> None:
        seen: dict[str, tuple[str, int]] = {}

        async def run_one(name: str, *, is_worker: bool) -> None:
            with strict_mode_scope(
                kind=StrictModeScopeKind.RUNTIME_EXECUTE,
                subject=name,
                library_name=None,
                is_worker=is_worker,
            ) as scope:
                report_violation(rule_id="r", message=f"msg-{name}")
                await asyncio.sleep(0)
                report_violation(rule_id="r", message=f"msg-{name}-2")
                seen[name] = (scope.subject, len(scope.violations))

        await asyncio.gather(
            run_one("a", is_worker=False),
            run_one("b", is_worker=True),
            run_one("c", is_worker=False),
        )

        assert seen == {"a": ("a", 2), "b": ("b", 2), "c": ("c", 2)}


class TestThreadSafeActiveFlag:
    def test_active_flag_observable_from_other_thread(self) -> None:
        observed: list[bool] = []
        entered = threading.Event()
        can_exit = threading.Event()

        def observer() -> None:
            entered.wait(timeout=1.0)
            observed.append(any_scope_active_threadsafe())
            can_exit.set()

        t = threading.Thread(target=observer)
        t.start()
        with strict_mode_scope(
            kind=StrictModeScopeKind.RUNTIME_EXECUTE,
            subject="n",
            library_name=None,
            is_worker=False,
        ):
            entered.set()
            can_exit.wait(timeout=1.0)
        t.join(timeout=1.0)

        assert observed == [True]
        assert any_scope_active_threadsafe() is False
