"""Tests for the doctor CLI command."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
import typer

from griptape_nodes.cli.commands.doctor import doctor_command
from griptape_nodes.cli.commands.doctor.base import CheckResult

_MODULE = "griptape_nodes.cli.commands.doctor"


class TestDoctorCommand:
    def test_exits_zero_when_all_checks_pass(self) -> None:
        """doctor_command() completes without raising when every check passes."""
        passing_check = MagicMock()
        passing_check.run.return_value = CheckResult(name="Test Check", passed=True, message="ok")

        with (
            patch(f"{_MODULE}.WebSocketConnectionCheck", return_value=passing_check),
            patch(f"{_MODULE}.console"),
        ):
            doctor_command()

    def test_exits_one_when_a_check_fails(self) -> None:
        """doctor_command() raises typer.Exit with code 1 when any check fails."""
        failing_check = MagicMock()
        failing_check.run.return_value = CheckResult(name="Test Check", passed=False, message="failed")

        with (
            patch(f"{_MODULE}.WebSocketConnectionCheck", return_value=failing_check),
            patch(f"{_MODULE}.console"),
            pytest.raises(typer.Exit) as exc_info,
        ):
            doctor_command()

        assert exc_info.value.exit_code == 1

    def test_all_checks_are_run(self) -> None:
        """doctor_command() calls run() on every registered check."""
        mock_check = MagicMock()
        mock_check.run.return_value = CheckResult(name="Test Check", passed=True, message="ok")

        with (
            patch(f"{_MODULE}.WebSocketConnectionCheck", return_value=mock_check),
            patch(f"{_MODULE}.console"),
        ):
            doctor_command()

        mock_check.run.assert_called_once()
