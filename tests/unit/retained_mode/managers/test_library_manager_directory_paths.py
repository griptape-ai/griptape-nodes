"""Tests for absolute and relative directory path resolution in LibraryManager."""

import asyncio
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from griptape_nodes.retained_mode.events.library_events import DownloadLibraryResultFailure
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
from griptape_nodes.utils.git_utils import GitCloneError


class TestGetSandboxDirectory:
    """Test _get_sandbox_directory resolves absolute and relative paths."""

    def test_relative_path(self, griptape_nodes: GriptapeNodes) -> None:
        """A relative sandbox_library_directory is resolved against the workspace."""
        library_manager = griptape_nodes.LibraryManager()
        config_mgr = MagicMock()
        config_mgr.get_config_value.return_value = "sandbox_library"
        config_mgr.workspace_path = Path("/workspace")

        with (
            patch.object(GriptapeNodes, "ConfigManager", return_value=config_mgr),
            patch(
                "griptape_nodes.retained_mode.managers.library_manager.resolve_workspace_path",
                return_value=Path("/workspace/sandbox_library"),
            ) as mock_resolve,
            patch.object(Path, "exists", return_value=True),
        ):
            result = library_manager._get_sandbox_directory()

        mock_resolve.assert_called_once_with(Path("sandbox_library"), Path("/workspace"))
        assert result == Path("/workspace/sandbox_library")

    def test_absolute_path(self, griptape_nodes: GriptapeNodes) -> None:
        """An absolute sandbox_library_directory is used as-is."""
        library_manager = griptape_nodes.LibraryManager()
        config_mgr = MagicMock()
        config_mgr.get_config_value.return_value = "/opt/sandbox"
        config_mgr.workspace_path = Path("/workspace")

        with (
            patch.object(GriptapeNodes, "ConfigManager", return_value=config_mgr),
            patch(
                "griptape_nodes.retained_mode.managers.library_manager.resolve_workspace_path",
                return_value=Path("/opt/sandbox"),
            ) as mock_resolve,
            patch.object(Path, "exists", return_value=True),
        ):
            result = library_manager._get_sandbox_directory()

        mock_resolve.assert_called_once_with(Path("/opt/sandbox"), Path("/workspace"))
        assert result == Path("/opt/sandbox")

    def test_not_configured_returns_none(self, griptape_nodes: GriptapeNodes) -> None:
        """When sandbox_library_directory is empty, returns None without resolving."""
        library_manager = griptape_nodes.LibraryManager()
        config_mgr = MagicMock()
        config_mgr.get_config_value.return_value = ""
        config_mgr.workspace_path = Path("/workspace")

        with patch.object(GriptapeNodes, "ConfigManager", return_value=config_mgr):
            result = library_manager._get_sandbox_directory()

        assert result is None

    def test_nonexistent_directory_returns_none(self, griptape_nodes: GriptapeNodes) -> None:
        """When the resolved directory does not exist, returns None."""
        library_manager = griptape_nodes.LibraryManager()
        config_mgr = MagicMock()
        config_mgr.get_config_value.return_value = "sandbox_library"
        config_mgr.workspace_path = Path("/workspace")

        with (
            patch.object(GriptapeNodes, "ConfigManager", return_value=config_mgr),
            patch(
                "griptape_nodes.retained_mode.managers.library_manager.resolve_workspace_path",
                return_value=Path("/workspace/sandbox_library"),
            ),
            patch.object(Path, "exists", return_value=False),
        ):
            result = library_manager._get_sandbox_directory()

        assert result is None


class TestDownloadLibrariesFromGitUrlsPath:
    """Test _download_libraries_from_git_urls resolves absolute and relative paths."""

    @pytest.mark.asyncio
    async def test_relative_path(self, griptape_nodes: GriptapeNodes) -> None:
        """A relative libraries_directory is resolved against the workspace."""
        library_manager = griptape_nodes.LibraryManager()
        config_mgr = MagicMock()
        config_mgr.get_config_value.return_value = "libraries"
        config_mgr.workspace_path = Path("/workspace")

        with (
            patch.object(GriptapeNodes, "ConfigManager", return_value=config_mgr),
            patch(
                "griptape_nodes.retained_mode.managers.library_manager.resolve_workspace_path",
                return_value=Path("/workspace/libraries"),
            ) as mock_resolve,
        ):
            result = await library_manager._download_libraries_from_git_urls([])

        mock_resolve.assert_called_once_with(Path("libraries"), Path("/workspace"))
        assert result == {}

    @pytest.mark.asyncio
    async def test_absolute_path(self, griptape_nodes: GriptapeNodes) -> None:
        """An absolute libraries_directory is used as-is."""
        library_manager = griptape_nodes.LibraryManager()
        config_mgr = MagicMock()
        config_mgr.get_config_value.return_value = "/opt/libraries"
        config_mgr.workspace_path = Path("/workspace")

        with (
            patch.object(GriptapeNodes, "ConfigManager", return_value=config_mgr),
            patch(
                "griptape_nodes.retained_mode.managers.library_manager.resolve_workspace_path",
                return_value=Path("/opt/libraries"),
            ) as mock_resolve,
        ):
            result = await library_manager._download_libraries_from_git_urls([])

        mock_resolve.assert_called_once_with(Path("/opt/libraries"), Path("/workspace"))
        assert result == {}

    @pytest.mark.asyncio
    async def test_not_configured_returns_empty(self, griptape_nodes: GriptapeNodes) -> None:
        """When libraries_directory is empty, returns empty dict without resolving."""
        library_manager = griptape_nodes.LibraryManager()
        config_mgr = MagicMock()
        config_mgr.get_config_value.return_value = ""
        config_mgr.workspace_path = Path("/workspace")

        with patch.object(GriptapeNodes, "ConfigManager", return_value=config_mgr):
            result = await library_manager._download_libraries_from_git_urls([])

        assert result == {}


class TestDownloadLibraryRequestPath:
    """Test download_library_request resolves absolute and relative paths."""

    @pytest.mark.asyncio
    async def test_relative_path(self, griptape_nodes: GriptapeNodes) -> None:
        """A relative libraries_directory is resolved against the workspace."""
        library_manager = griptape_nodes.LibraryManager()
        config_mgr = MagicMock()
        config_mgr.get_config_value.return_value = "libraries"
        config_mgr.workspace_path = Path("/workspace")

        request = MagicMock()
        request.git_url = "https://github.com/user/repo.git"
        request.branch_tag_commit = None
        request.target_directory_name = None
        request.download_directory = None

        with (
            patch.object(GriptapeNodes, "ConfigManager", return_value=config_mgr),
            patch(
                "griptape_nodes.retained_mode.managers.library_manager.resolve_workspace_path",
                return_value=Path("/workspace/libraries"),
            ) as mock_resolve,
            patch(
                "griptape_nodes.retained_mode.managers.library_manager.normalize_github_url",
                return_value="https://github.com/user/repo.git",
            ),
            patch("anyio.Path.mkdir"),
            patch("anyio.Path.exists", return_value=False),
            patch.object(asyncio, "to_thread", side_effect=GitCloneError("stop test here")),
        ):
            result = await library_manager.download_library_request(request)

        mock_resolve.assert_called_once_with(Path("libraries"), Path("/workspace"))
        assert isinstance(result, DownloadLibraryResultFailure)

    @pytest.mark.asyncio
    async def test_absolute_path(self, griptape_nodes: GriptapeNodes) -> None:
        """An absolute libraries_directory is used as-is."""
        library_manager = griptape_nodes.LibraryManager()
        config_mgr = MagicMock()
        config_mgr.get_config_value.return_value = "/opt/libraries"
        config_mgr.workspace_path = Path("/workspace")

        request = MagicMock()
        request.git_url = "https://github.com/user/repo.git"
        request.branch_tag_commit = None
        request.target_directory_name = None
        request.download_directory = None

        with (
            patch.object(GriptapeNodes, "ConfigManager", return_value=config_mgr),
            patch(
                "griptape_nodes.retained_mode.managers.library_manager.resolve_workspace_path",
                return_value=Path("/opt/libraries"),
            ) as mock_resolve,
            patch(
                "griptape_nodes.retained_mode.managers.library_manager.normalize_github_url",
                return_value="https://github.com/user/repo.git",
            ),
            patch("anyio.Path.mkdir"),
            patch("anyio.Path.exists", return_value=False),
            patch.object(asyncio, "to_thread", side_effect=GitCloneError("stop test here")),
        ):
            result = await library_manager.download_library_request(request)

        mock_resolve.assert_called_once_with(Path("/opt/libraries"), Path("/workspace"))
        assert isinstance(result, DownloadLibraryResultFailure)

    @pytest.mark.asyncio
    async def test_custom_download_directory_skips_config(self, griptape_nodes: GriptapeNodes) -> None:
        """When download_directory is provided, it is used directly without resolving config."""
        library_manager = griptape_nodes.LibraryManager()
        config_mgr = MagicMock()
        config_mgr.workspace_path = Path("/workspace")

        request = MagicMock()
        request.git_url = "https://github.com/user/repo.git"
        request.branch_tag_commit = None
        request.target_directory_name = None
        request.download_directory = "/custom/dir"

        with (
            patch.object(GriptapeNodes, "ConfigManager", return_value=config_mgr),
            patch(
                "griptape_nodes.retained_mode.managers.library_manager.resolve_workspace_path",
            ) as mock_resolve,
            patch(
                "griptape_nodes.retained_mode.managers.library_manager.normalize_github_url",
                return_value="https://github.com/user/repo.git",
            ),
            patch("anyio.Path.mkdir"),
            patch("anyio.Path.exists", return_value=False),
            patch.object(asyncio, "to_thread", side_effect=GitCloneError("stop test here")),
        ):
            await library_manager.download_library_request(request)

        mock_resolve.assert_not_called()

    @pytest.mark.asyncio
    async def test_not_configured_returns_failure(self, griptape_nodes: GriptapeNodes) -> None:
        """When libraries_directory is empty and no download_directory, returns failure."""
        library_manager = griptape_nodes.LibraryManager()
        config_mgr = MagicMock()
        config_mgr.get_config_value.return_value = ""
        config_mgr.workspace_path = Path("/workspace")

        request = MagicMock()
        request.git_url = "https://github.com/user/repo.git"
        request.branch_tag_commit = None
        request.target_directory_name = None
        request.download_directory = None

        with (
            patch.object(GriptapeNodes, "ConfigManager", return_value=config_mgr),
            patch(
                "griptape_nodes.retained_mode.managers.library_manager.normalize_github_url",
                return_value="https://github.com/user/repo.git",
            ),
        ):
            result = await library_manager.download_library_request(request)

        assert isinstance(result, DownloadLibraryResultFailure)
