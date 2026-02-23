"""Unit tests for version_utils module."""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

from griptape_nodes.utils.version_utils import (
    _detect_source_from_package_location,
    _get_git_commit_id,
    get_install_source,
)

_MODULE = "griptape_nodes.utils.version_utils"


class TestGetGitCommitId:
    """Tests for _get_git_commit_id helper."""

    def test_returns_short_sha_on_success(self) -> None:
        """Test that a 7-character SHA is returned when git rev-parse succeeds."""
        mock_result = MagicMock()
        mock_result.stdout = "abcdef1234567890\n"

        with patch(f"{_MODULE}.subprocess.run", return_value=mock_result) as mock_run:
            result = _get_git_commit_id(Path("/some/repo"))

        assert result == "abcdef1"
        mock_run.assert_called_once_with(
            ["git", "rev-parse", "HEAD"],
            cwd=Path("/some/repo"),
            capture_output=True,
            text=True,
            check=True,
        )

    def test_returns_none_when_git_fails(self) -> None:
        """Test that None is returned when subprocess raises an error."""
        with patch(f"{_MODULE}.subprocess.run", side_effect=subprocess.CalledProcessError(1, "git")):
            result = _get_git_commit_id(Path("/some/repo"))

        assert result is None

    def test_returns_none_when_git_not_installed(self) -> None:
        """Test that None is returned when git binary is not found."""
        with patch(f"{_MODULE}.subprocess.run", side_effect=FileNotFoundError):
            result = _get_git_commit_id(Path("/some/repo"))

        assert result is None


class TestDetectSourceFromPackageLocation:
    """Tests for _detect_source_from_package_location fallback detector."""

    def test_returns_git_when_git_dir_found(self) -> None:
        """Test that ('git', commit_id) is returned when .git directory exists above __file__."""
        with tempfile.TemporaryDirectory() as tmpdir:
            git_dir = Path(tmpdir) / ".git"
            git_dir.mkdir()
            fake_file = Path(tmpdir) / "src" / "griptape_nodes" / "utils" / "version_utils.py"
            fake_file.parent.mkdir(parents=True)
            fake_file.touch()

            with (
                patch(f"{_MODULE}.__file__", str(fake_file)),
                patch(f"{_MODULE}._get_git_commit_id", return_value="abc1234"),
            ):
                result = _detect_source_from_package_location()

            assert result == ("git", "abc1234")

    def test_returns_none_when_no_git_dir(self) -> None:
        """Test that None is returned when no .git directory is found."""
        with tempfile.TemporaryDirectory() as tmpdir:
            fake_file = Path(tmpdir) / "src" / "griptape_nodes" / "utils" / "version_utils.py"
            fake_file.parent.mkdir(parents=True)
            fake_file.touch()

            with patch(f"{_MODULE}.__file__", str(fake_file)):
                result = _detect_source_from_package_location()

            assert result is None

    def test_returns_git_with_none_commit_when_git_fails(self) -> None:
        """Test that ('git', None) is returned when .git exists but commit lookup fails."""
        with tempfile.TemporaryDirectory() as tmpdir:
            git_dir = Path(tmpdir) / ".git"
            git_dir.mkdir()
            fake_file = Path(tmpdir) / "pkg" / "module.py"
            fake_file.parent.mkdir(parents=True)
            fake_file.touch()

            with (
                patch(f"{_MODULE}.__file__", str(fake_file)),
                patch(f"{_MODULE}._get_git_commit_id", return_value=None),
            ):
                result = _detect_source_from_package_location()

            assert result == ("git", None)

    def test_returns_none_on_exception(self) -> None:
        """Test that None is returned when __file__ resolution raises an exception."""
        with patch(f"{_MODULE}.__file__", "/nonexistent/path/that/causes/issues"):
            result = _detect_source_from_package_location()

        assert result is None


class TestGetInstallSource:
    """Tests for get_install_source with the fallback to package location detection."""

    def _mock_distribution(self, direct_url_text: str | None) -> MagicMock:
        """Create a mock distribution with the given direct_url.json text."""
        dist = MagicMock()
        dist.read_text.return_value = direct_url_text
        return dist

    def test_returns_pypi_when_no_direct_url_and_no_git_dir(self) -> None:
        """Test that ('pypi', None) is returned for a genuine PyPI install."""
        dist = self._mock_distribution(None)

        with (
            patch(f"{_MODULE}.importlib.metadata.distribution", return_value=dist),
            patch(f"{_MODULE}._detect_source_from_package_location", return_value=None),
        ):
            result = get_install_source()

        assert result == ("pypi", None)

    def test_returns_git_fallback_when_no_direct_url_but_in_git_repo(self) -> None:
        """Test that the fallback overrides PyPI to git when source is in a git repo."""
        dist = self._mock_distribution(None)

        with (
            patch(f"{_MODULE}.importlib.metadata.distribution", return_value=dist),
            patch(f"{_MODULE}._detect_source_from_package_location", return_value=("git", "abc1234")),
        ):
            result = get_install_source()

        assert result == ("git", "abc1234")

    def test_returns_file_when_direct_url_has_file_scheme(self) -> None:
        """Test that ('file', None) is returned for local file installs."""
        direct_url = '{"url": "file:///home/user/griptape-nodes"}'
        dist = self._mock_distribution(direct_url)

        with patch(f"{_MODULE}.importlib.metadata.distribution", return_value=dist):
            result = get_install_source()

        assert result == ("file", None)

    def test_returns_git_when_direct_url_has_vcs_info(self) -> None:
        """Test that ('git', short_sha) is returned for git installs via direct_url.json."""
        direct_url = '{"url": "https://github.com/user/repo", "vcs_info": {"commit_id": "abcdef1234567890"}}'
        dist = self._mock_distribution(direct_url)

        with patch(f"{_MODULE}.importlib.metadata.distribution", return_value=dist):
            result = get_install_source()

        assert result == ("git", "abcdef1")

    def test_returns_pypi_when_direct_url_has_unknown_scheme(self) -> None:
        """Test fallback to pypi when direct_url.json has an unrecognized format."""
        direct_url = '{"url": "https://some-mirror.com/package"}'
        dist = self._mock_distribution(direct_url)

        with patch(f"{_MODULE}.importlib.metadata.distribution", return_value=dist):
            result = get_install_source()

        assert result == ("pypi", None)
