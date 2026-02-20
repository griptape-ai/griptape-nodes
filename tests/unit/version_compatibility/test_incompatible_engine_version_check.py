"""Tests for IncompatibleEngineVersionCheck and LibraryEngineVersionTooNewProblem."""

from unittest.mock import MagicMock, patch

import pytest

from griptape_nodes.retained_mode.managers.fitness_problems.libraries.library_engine_version_too_new_problem import (
    LibraryEngineVersionTooNewProblem,
)
from griptape_nodes.retained_mode.managers.library_manager import LibraryManager
from griptape_nodes.version_compatibility.versions.general.incompatible_engine_version_check import (
    IncompatibleEngineVersionCheck,
)

_MODULE = "griptape_nodes.version_compatibility.versions.general.incompatible_engine_version_check"


class TestLibraryEngineVersionTooNewProblem:
    """Tests for LibraryEngineVersionTooNewProblem fitness problem."""

    def test_collate_single_problem(self) -> None:
        """Test display message for a single engine version problem."""
        problem = LibraryEngineVersionTooNewProblem(
            library_engine_version="1.0.0",
            current_engine_version="0.70.0",
        )

        result = LibraryEngineVersionTooNewProblem.collate_problems_for_display([problem])

        assert "1.0.0" in result
        assert "0.70.0" in result
        assert "Please update your engine" in result

    def test_collate_multiple_problems(self) -> None:
        """Test display message for multiple engine version problems."""
        problems = [
            LibraryEngineVersionTooNewProblem(
                library_engine_version="1.0.0",
                current_engine_version="0.70.0",
            ),
            LibraryEngineVersionTooNewProblem(
                library_engine_version="0.80.0",
                current_engine_version="0.70.0",
            ),
        ]

        result = LibraryEngineVersionTooNewProblem.collate_problems_for_display(problems)

        assert "Encountered 2 libraries" in result
        # Should be sorted by version
        assert result.index("0.80.0") < result.index("1.0.0")

    def test_collate_problems_sorted_by_version(self) -> None:
        """Test that multiple problems are sorted by library_engine_version."""
        problems = [
            LibraryEngineVersionTooNewProblem(library_engine_version="2.0.0", current_engine_version="0.70.0"),
            LibraryEngineVersionTooNewProblem(library_engine_version="0.90.0", current_engine_version="0.70.0"),
            LibraryEngineVersionTooNewProblem(library_engine_version="1.5.0", current_engine_version="0.70.0"),
        ]

        result = LibraryEngineVersionTooNewProblem.collate_problems_for_display(problems)

        # Verify the order by finding each version's position in the output
        pos_090 = result.index("0.90.0")
        pos_150 = result.index("1.5.0")
        pos_200 = result.index("2.0.0")
        assert pos_090 < pos_150 < pos_200


class TestIncompatibleEngineVersionCheck:
    """Tests for IncompatibleEngineVersionCheck version compatibility check."""

    @pytest.fixture
    def check(self) -> IncompatibleEngineVersionCheck:
        """Provide an IncompatibleEngineVersionCheck instance."""
        return IncompatibleEngineVersionCheck()

    @pytest.fixture
    def mock_library_data(self) -> MagicMock:
        """Provide a mock LibrarySchema with configurable engine_version."""
        library_data = MagicMock()
        library_data.metadata.engine_version = "0.70.0"
        return library_data

    def test_applies_when_library_version_greater_than_engine(
        self, check: IncompatibleEngineVersionCheck, mock_library_data: MagicMock
    ) -> None:
        """Test that check applies when library requires newer engine version."""
        mock_library_data.metadata.engine_version = "1.0.0"

        with patch(f"{_MODULE}.engine_version", "0.70.0"):
            result = check.applies_to_library(mock_library_data)

        assert result is True

    def test_does_not_apply_when_library_version_equal_to_engine(
        self, check: IncompatibleEngineVersionCheck, mock_library_data: MagicMock
    ) -> None:
        """Test that check does not apply when library version equals engine version."""
        mock_library_data.metadata.engine_version = "0.70.0"

        with patch(f"{_MODULE}.engine_version", "0.70.0"):
            result = check.applies_to_library(mock_library_data)

        assert result is False

    def test_does_not_apply_when_library_version_less_than_engine(
        self, check: IncompatibleEngineVersionCheck, mock_library_data: MagicMock
    ) -> None:
        """Test that check does not apply when library version is older than engine."""
        mock_library_data.metadata.engine_version = "0.60.0"

        with patch(f"{_MODULE}.engine_version", "0.70.0"):
            result = check.applies_to_library(mock_library_data)

        assert result is False

    def test_does_not_apply_when_engine_version_invalid(
        self, check: IncompatibleEngineVersionCheck, mock_library_data: MagicMock
    ) -> None:
        """Test that check does not apply when engine version string cannot be parsed."""
        mock_library_data.metadata.engine_version = "1.0.0"

        with patch(f"{_MODULE}.engine_version", "invalid-version"):
            result = check.applies_to_library(mock_library_data)

        assert result is False

    def test_does_not_apply_when_library_version_invalid(
        self, check: IncompatibleEngineVersionCheck, mock_library_data: MagicMock
    ) -> None:
        """Test that check does not apply when library version is invalid."""
        mock_library_data.metadata.engine_version = "invalid-version"

        with patch(f"{_MODULE}.engine_version", "0.70.0"):
            result = check.applies_to_library(mock_library_data)

        assert result is False

    def test_check_library_returns_unusable_for_pypi_install(
        self, check: IncompatibleEngineVersionCheck, mock_library_data: MagicMock
    ) -> None:
        """Test that check_library returns UNUSABLE severity for PyPI installs."""
        mock_library_data.metadata.engine_version = "1.0.0"

        with (
            patch(f"{_MODULE}.engine_version", "0.70.0"),
            patch(f"{_MODULE}.get_install_source", return_value=("pypi", None)),
        ):
            issues = check.check_library(mock_library_data)

        assert len(issues) == 1
        assert issues[0].severity == LibraryManager.LibraryFitness.UNUSABLE
        assert isinstance(issues[0].problem, LibraryEngineVersionTooNewProblem)
        assert issues[0].problem.library_engine_version == "1.0.0"
        assert issues[0].problem.current_engine_version == "0.70.0"

    def test_check_library_returns_flawed_for_git_install(
        self, check: IncompatibleEngineVersionCheck, mock_library_data: MagicMock
    ) -> None:
        """Test that check_library returns FLAWED severity for git installs."""
        mock_library_data.metadata.engine_version = "1.0.0"

        with (
            patch(f"{_MODULE}.engine_version", "0.70.0"),
            patch(f"{_MODULE}.get_install_source", return_value=("git", "abc1234")),
        ):
            issues = check.check_library(mock_library_data)

        assert len(issues) == 1
        assert issues[0].severity == LibraryManager.LibraryFitness.FLAWED

    def test_check_library_returns_flawed_for_file_install(
        self, check: IncompatibleEngineVersionCheck, mock_library_data: MagicMock
    ) -> None:
        """Test that check_library returns FLAWED severity for local file installs."""
        mock_library_data.metadata.engine_version = "1.0.0"

        with (
            patch(f"{_MODULE}.engine_version", "0.70.0"),
            patch(f"{_MODULE}.get_install_source", return_value=("file", None)),
        ):
            issues = check.check_library(mock_library_data)

        assert len(issues) == 1
        assert issues[0].severity == LibraryManager.LibraryFitness.FLAWED

    def test_applies_with_patch_version_difference(
        self, check: IncompatibleEngineVersionCheck, mock_library_data: MagicMock
    ) -> None:
        """Test that check applies correctly when only patch version differs."""
        mock_library_data.metadata.engine_version = "0.70.1"

        with patch(f"{_MODULE}.engine_version", "0.70.0"):
            result = check.applies_to_library(mock_library_data)

        assert result is True

    def test_does_not_apply_with_lower_patch_version(
        self, check: IncompatibleEngineVersionCheck, mock_library_data: MagicMock
    ) -> None:
        """Test that check does not apply when library has lower patch version."""
        mock_library_data.metadata.engine_version = "0.70.0"

        with patch(f"{_MODULE}.engine_version", "0.70.5"):
            result = check.applies_to_library(mock_library_data)

        assert result is False
