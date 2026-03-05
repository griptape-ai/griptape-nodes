"""Tests for doctor health check base types."""

from __future__ import annotations

import pytest

from griptape_nodes.cli.commands.doctor.base import CheckResult, HealthCheck


class TestCheckResult:
    def test_passed_result(self) -> None:
        result = CheckResult(name="My Check", passed=True, message="All good.")
        assert result.name == "My Check"
        assert result.passed is True
        assert result.message == "All good."

    def test_failed_result(self) -> None:
        result = CheckResult(name="My Check", passed=False, message="Something went wrong.")
        assert result.passed is False
        assert result.message == "Something went wrong."


class TestHealthCheck:
    def test_cannot_instantiate_without_run(self) -> None:
        """Subclasses that do not implement run() cannot be instantiated."""

        class IncompleteCheck(HealthCheck):
            pass

        with pytest.raises(TypeError):
            IncompleteCheck()  # type: ignore[abstract]

    def test_concrete_subclass_is_instantiable(self) -> None:
        """A subclass that implements run() can be instantiated and called."""

        class ConcreteCheck(HealthCheck):
            def run(self) -> CheckResult:
                return CheckResult(name="Concrete", passed=True, message="ok")

        check = ConcreteCheck()
        result = check.run()
        assert result.passed is True
