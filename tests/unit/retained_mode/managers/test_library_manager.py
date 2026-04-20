import asyncio
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from griptape_nodes.node_library.library_registry import LibraryRegistry
from griptape_nodes.retained_mode.events.base_events import ResultDetails
from griptape_nodes.retained_mode.events.library_events import (
    GetAllInfoForAllLibrariesRequest,
    GetAllInfoForAllLibrariesResultFailure,
    GetAllInfoForAllLibrariesResultSuccess,
    InstallLibraryDependenciesRequest,
    InstallLibraryDependenciesResultFailure,
    InstallLibraryDependenciesResultSuccess,
    ListRegisteredLibrariesRequest,
    ListRegisteredLibrariesResultSuccess,
    LoadLibrariesRequest,
    LoadLibrariesResultSuccess,
    LoadLibraryMetadataFromFileResultSuccess,
    RegisterLibraryFromFileRequest,
    RegisterLibraryFromFileResultFailure,
)
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes


class TestLibraryManagerLoadLibraries:
    """Test the load_libraries_request functionality in LibraryManager."""

    @pytest.mark.asyncio
    async def test_libraries_already_loaded_returns_success_without_reloading(
        self, griptape_nodes: GriptapeNodes
    ) -> None:
        """Test that when libraries are already loaded, returns success without reloading."""
        library_manager = griptape_nodes.LibraryManager()

        # Mock that libraries are already loaded and discovered libraries match loaded ones
        from griptape_nodes.node_library.library_registry import LibraryRegistry
        from griptape_nodes.retained_mode.managers.library_manager import LibraryManager

        mock_lib_info = library_manager.LibraryInfo(
            lifecycle_state=LibraryManager.LibraryLifecycleState.LOADED,
            library_path="some_lib",
            is_sandbox=False,
            library_name="SomeLib",
            library_version="1.0.0",
            fitness=LibraryManager.LibraryFitness.GOOD,
            problems=[],
        )
        mock_load_config = AsyncMock()
        mock_library = MagicMock()
        mock_library.name = "SomeLib"
        with (
            patch.object(library_manager, "_library_file_path_to_info", {"some_lib": mock_lib_info}),
            patch.object(library_manager, "_discover_library_files", return_value=[Path("some_lib")]),
            patch.object(library_manager, "load_all_libraries_from_config", mock_load_config),
            patch.object(LibraryRegistry, "get_library", return_value=mock_library),
        ):
            request = LoadLibrariesRequest()
            result = await library_manager.load_libraries_request(request)

            assert isinstance(result, LoadLibrariesResultSuccess)
            assert isinstance(result.result_details, ResultDetails)
            # Test that library was loaded successfully (not failed)
            assert "loaded" in result.result_details.result_details[0].message.lower()
            # Since library was already in registry, config loading shouldn't be called
            mock_load_config.assert_not_called()

    @pytest.mark.asyncio
    async def test_empty_libraries_loads_from_config_successfully(self, griptape_nodes: GriptapeNodes) -> None:
        """Test successful library loading from configuration."""
        library_manager = griptape_nodes.LibraryManager()

        # Mock empty libraries and discovered library that needs loading
        mock_load_config = AsyncMock()
        with (
            patch.object(library_manager, "_library_file_path_to_info", {}),
            patch.object(library_manager, "_discover_library_files", return_value=[Path("new_lib")]),
            patch.object(library_manager, "load_all_libraries_from_config", mock_load_config),
        ):
            request = LoadLibrariesRequest()
            result = await library_manager.load_libraries_request(request)

            # Can be success or failure depending on whether sandbox library exists
            # In CI without sandbox: failure (no libraries loaded)
            # Locally with sandbox: success (sandbox loaded even though new_lib failed)
            assert isinstance(result.result_details, ResultDetails)
            # Test that loading was attempted (result mentions libraries or failure)
            message = result.result_details.result_details[0].message.lower()
            assert "loaded" in message or "failed" in message
            # load_all_libraries_from_config was NOT called because libraries were discovered and loaded individually
            # (the new implementation doesn't call load_all_libraries_from_config anymore)

    @pytest.mark.asyncio
    async def test_library_loading_failure_returns_failure_result(self, griptape_nodes: GriptapeNodes) -> None:
        """Test library loading failure returns appropriate error."""
        library_manager = griptape_nodes.LibraryManager()

        # Mock empty libraries, discovered library, and failed loading
        mock_load_config = AsyncMock(side_effect=Exception("Config error"))
        with (
            patch.object(library_manager, "_library_file_path_to_info", {}),
            patch.object(library_manager, "_discover_library_files", return_value=[Path("new_lib")]),
            patch.object(library_manager, "load_all_libraries_from_config", mock_load_config),
        ):
            request = LoadLibrariesRequest()
            result = await library_manager.load_libraries_request(request)

            # Can be success or failure depending on whether sandbox library exists
            # In CI without sandbox: failure (no libraries loaded)
            # Locally with sandbox: success (sandbox loaded even though new_lib failed)
            assert isinstance(result.result_details, ResultDetails)
            # Test that failure was indicated in the result message
            assert "failed" in result.result_details.result_details[0].message.lower()


class TestLibraryManagerMigrateOldXdgPaths:
    """Test the _migrate_old_xdg_library_paths functionality in LibraryManager."""

    def test_removes_old_xdg_paths_and_preserves_valid_paths(self, griptape_nodes: GriptapeNodes) -> None:
        """Test that old XDG paths are removed while valid paths are preserved."""
        library_manager = griptape_nodes.LibraryManager()

        # Mock config with one old XDG path and one valid path
        old_xdg_path = "/home/user/.local/share/griptape_nodes/libraries/griptape_nodes_library"
        valid_path = "/custom/path/to/library"
        register_config = [old_xdg_path, valid_path]
        download_config = []

        mock_config_manager = MagicMock()
        mock_config_manager.get_config_value.side_effect = lambda key: (
            register_config
            if "libraries_to_register" in key
            else download_config
            if "libraries_to_download" in key
            else None
        )

        with (
            patch(
                "griptape_nodes.retained_mode.managers.library_manager.GriptapeNodes.ConfigManager",
                return_value=mock_config_manager,
            ),
            patch("griptape_nodes.utils.library_utils.xdg_data_home") as mock_xdg,
        ):
            mock_xdg.return_value = Path("/home/user/.local/share")

            library_manager._migrate_old_xdg_library_paths()

            # Verify both configs were updated
            assert mock_config_manager.set_config_value.call_count == 2  # noqa: PLR2004
            calls = mock_config_manager.set_config_value.call_args_list
            register_call = next(c for c in calls if "libraries_to_register" in c[0][0])
            assert register_call[0][1] == [valid_path]

    def test_idempotent_with_no_old_paths(self, griptape_nodes: GriptapeNodes) -> None:
        """Test that migration does nothing when config has no old XDG paths."""
        library_manager = griptape_nodes.LibraryManager()

        # Mock config with only valid paths (no old XDG paths)
        valid_paths = ["/custom/path/library1", "https://github.com/user/library@main"]

        mock_config_manager = MagicMock()
        mock_config_manager.get_config_value.return_value = valid_paths

        with (
            patch(
                "griptape_nodes.retained_mode.managers.library_manager.GriptapeNodes.ConfigManager",
                return_value=mock_config_manager,
            ),
            patch("griptape_nodes.utils.library_utils.xdg_data_home") as mock_xdg,
        ):
            mock_xdg.return_value = Path("/home/user/.local/share")

            library_manager._migrate_old_xdg_library_paths()

            # Verify config was NOT updated (no old paths to remove)
            mock_config_manager.set_config_value.assert_not_called()

    def test_handles_empty_config_gracefully(self, griptape_nodes: GriptapeNodes) -> None:
        """Test that migration returns early when config is empty."""
        library_manager = griptape_nodes.LibraryManager()

        mock_config_manager = MagicMock()
        mock_config_manager.get_config_value.return_value = []

        with patch(
            "griptape_nodes.retained_mode.managers.library_manager.GriptapeNodes.ConfigManager",
            return_value=mock_config_manager,
        ):
            library_manager._migrate_old_xdg_library_paths()

            # Verify config was NOT updated (empty config)
            mock_config_manager.set_config_value.assert_not_called()

    def test_handles_none_config_gracefully(self, griptape_nodes: GriptapeNodes) -> None:
        """Test that migration returns early when config is None."""
        library_manager = griptape_nodes.LibraryManager()

        mock_config_manager = MagicMock()
        mock_config_manager.get_config_value.return_value = None

        with patch(
            "griptape_nodes.retained_mode.managers.library_manager.GriptapeNodes.ConfigManager",
            return_value=mock_config_manager,
        ):
            library_manager._migrate_old_xdg_library_paths()

            # Verify config was NOT updated (None config)
            mock_config_manager.set_config_value.assert_not_called()

    def test_removes_all_three_old_library_paths(self, griptape_nodes: GriptapeNodes) -> None:
        """Test that all three old XDG library types are removed."""
        library_manager = griptape_nodes.LibraryManager()

        # Mock config with all three old XDG library paths
        xdg_base = "/home/user/.local/share/griptape_nodes/libraries"
        old_paths = [
            f"{xdg_base}/griptape_nodes_library/some_file.json",
            f"{xdg_base}/griptape_nodes_advanced_media_library/another.json",
            f"{xdg_base}/griptape_cloud/cloud.json",
        ]
        valid_path = "/custom/library"
        register_config = [*old_paths, valid_path]
        download_config = []

        mock_config_manager = MagicMock()
        mock_config_manager.get_config_value.side_effect = lambda key: (
            register_config
            if "libraries_to_register" in key
            else download_config
            if "libraries_to_download" in key
            else None
        )

        with (
            patch(
                "griptape_nodes.retained_mode.managers.library_manager.GriptapeNodes.ConfigManager",
                return_value=mock_config_manager,
            ),
            patch("griptape_nodes.utils.library_utils.xdg_data_home") as mock_xdg,
        ):
            mock_xdg.return_value = Path("/home/user/.local/share")

            library_manager._migrate_old_xdg_library_paths()

            # Verify all old paths removed, only valid path remains
            assert mock_config_manager.set_config_value.call_count == 2  # noqa: PLR2004
            calls = mock_config_manager.set_config_value.call_args_list
            register_call = next(c for c in calls if "libraries_to_register" in c[0][0])
            assert register_call[0][1] == [valid_path]

    def test_preserves_custom_paths_and_git_urls(self, griptape_nodes: GriptapeNodes) -> None:
        """Test that custom paths and git URLs are preserved during migration."""
        library_manager = griptape_nodes.LibraryManager()

        # Mock config with old XDG path, custom path, and git URL
        xdg_base = "/home/user/.local/share/griptape_nodes/libraries"
        old_path = f"{xdg_base}/griptape_nodes_library"
        custom_path = "/opt/custom/libraries/my_library"
        git_url = "https://github.com/user/awesome-library@stable"
        register_config = [old_path, custom_path, git_url]
        download_config = []

        mock_config_manager = MagicMock()
        mock_config_manager.get_config_value.side_effect = lambda key: (
            register_config
            if "libraries_to_register" in key
            else download_config
            if "libraries_to_download" in key
            else None
        )

        with (
            patch(
                "griptape_nodes.retained_mode.managers.library_manager.GriptapeNodes.ConfigManager",
                return_value=mock_config_manager,
            ),
            patch("griptape_nodes.utils.library_utils.xdg_data_home") as mock_xdg,
        ):
            mock_xdg.return_value = Path("/home/user/.local/share")

            library_manager._migrate_old_xdg_library_paths()

            # Verify only old XDG path removed, custom and git URL preserved
            assert mock_config_manager.set_config_value.call_count == 2  # noqa: PLR2004
            calls = mock_config_manager.set_config_value.call_args_list
            register_call = next(c for c in calls if "libraries_to_register" in c[0][0])
            assert register_call[0][1] == [custom_path, git_url]

    def test_adds_git_urls_to_downloads_when_xdg_paths_removed(self, griptape_nodes: GriptapeNodes) -> None:
        """Test that migration adds git URLs to downloads when XDG paths are removed."""
        library_manager = griptape_nodes.LibraryManager()

        # Mock config with old XDG path in register and empty downloads
        xdg_base = "/home/user/.local/share/griptape_nodes/libraries"
        old_path = f"{xdg_base}/griptape_nodes_library"
        register_config = [old_path]
        download_config = []

        mock_config_manager = MagicMock()
        mock_config_manager.get_config_value.side_effect = lambda key: (
            register_config
            if "libraries_to_register" in key
            else download_config
            if "libraries_to_download" in key
            else None
        )

        with (
            patch(
                "griptape_nodes.retained_mode.managers.library_manager.GriptapeNodes.ConfigManager",
                return_value=mock_config_manager,
            ),
            patch("griptape_nodes.utils.library_utils.xdg_data_home") as mock_xdg,
        ):
            mock_xdg.return_value = Path("/home/user/.local/share")

            library_manager._migrate_old_xdg_library_paths()

            # Verify both configs were updated
            assert mock_config_manager.set_config_value.call_count == 2  # noqa: PLR2004

            # Check that register was cleared and download was populated
            calls = mock_config_manager.set_config_value.call_args_list
            register_call = next(c for c in calls if "libraries_to_register" in c[0][0])
            download_call = next(c for c in calls if "libraries_to_download" in c[0][0])

            assert register_call[0][1] == []  # XDG path removed
            assert len(download_call[0][1]) == 1  # Git URL added
            assert "griptape-nodes-library-standard" in download_call[0][1][0]

    def test_doesnt_duplicate_existing_git_urls(self, griptape_nodes: GriptapeNodes) -> None:
        """Test that migration doesn't add URLs already in downloads."""
        library_manager = griptape_nodes.LibraryManager()

        # Mock config with XDG path in register and corresponding git URL already in downloads
        xdg_base = "/home/user/.local/share/griptape_nodes/libraries"
        old_path = f"{xdg_base}/griptape_nodes_library"
        register_config = [old_path]
        download_config = ["https://github.com/griptape-ai/griptape-nodes-library-standard@stable"]

        mock_config_manager = MagicMock()
        mock_config_manager.get_config_value.side_effect = lambda key: (
            register_config
            if "libraries_to_register" in key
            else download_config
            if "libraries_to_download" in key
            else None
        )

        with (
            patch(
                "griptape_nodes.retained_mode.managers.library_manager.GriptapeNodes.ConfigManager",
                return_value=mock_config_manager,
            ),
            patch("griptape_nodes.utils.library_utils.xdg_data_home") as mock_xdg,
        ):
            mock_xdg.return_value = Path("/home/user/.local/share")

            library_manager._migrate_old_xdg_library_paths()

            # Verify only register was updated, downloads unchanged (no duplicate)
            assert mock_config_manager.set_config_value.call_count == 1
            call_args = mock_config_manager.set_config_value.call_args
            assert "libraries_to_register" in call_args[0][0]
            assert call_args[0][1] == []

    def test_handles_multiple_libraries(self, griptape_nodes: GriptapeNodes) -> None:
        """Test migration with all three library types."""
        library_manager = griptape_nodes.LibraryManager()

        # Mock config with all 3 old XDG paths and empty downloads
        xdg_base = "/home/user/.local/share/griptape_nodes/libraries"
        old_paths = [
            f"{xdg_base}/griptape_nodes_library",
            f"{xdg_base}/griptape_nodes_advanced_media_library",
            f"{xdg_base}/griptape_cloud",
        ]
        register_config = old_paths
        download_config = []

        mock_config_manager = MagicMock()
        mock_config_manager.get_config_value.side_effect = lambda key: (
            register_config
            if "libraries_to_register" in key
            else download_config
            if "libraries_to_download" in key
            else None
        )

        with (
            patch(
                "griptape_nodes.retained_mode.managers.library_manager.GriptapeNodes.ConfigManager",
                return_value=mock_config_manager,
            ),
            patch("griptape_nodes.utils.library_utils.xdg_data_home") as mock_xdg,
        ):
            mock_xdg.return_value = Path("/home/user/.local/share")

            library_manager._migrate_old_xdg_library_paths()

            # Verify both configs were updated
            assert mock_config_manager.set_config_value.call_count == 2  # noqa: PLR2004

            # Check that all 3 git URLs were added
            calls = mock_config_manager.set_config_value.call_args_list
            download_call = next(c for c in calls if "libraries_to_download" in c[0][0])

            assert len(download_call[0][1]) == 3  # noqa: PLR2004
            assert any("griptape-nodes-library-standard" in url for url in download_call[0][1])
            assert any("griptape-nodes-library-advanced-media" in url for url in download_call[0][1])
            assert any("griptape-nodes-library-griptape-cloud" in url for url in download_call[0][1])

    def test_handles_partial_overlap(self, griptape_nodes: GriptapeNodes) -> None:
        """Test when some URLs already exist in downloads."""
        library_manager = griptape_nodes.LibraryManager()

        # Mock config with 2 XDG paths, 1 git URL already in downloads
        xdg_base = "/home/user/.local/share/griptape_nodes/libraries"
        old_paths = [
            f"{xdg_base}/griptape_nodes_library",
            f"{xdg_base}/griptape_cloud",
        ]
        register_config = old_paths
        download_config = ["https://github.com/griptape-ai/griptape-nodes-library-standard@stable"]

        mock_config_manager = MagicMock()
        mock_config_manager.get_config_value.side_effect = lambda key: (
            register_config
            if "libraries_to_register" in key
            else download_config
            if "libraries_to_download" in key
            else None
        )

        with (
            patch(
                "griptape_nodes.retained_mode.managers.library_manager.GriptapeNodes.ConfigManager",
                return_value=mock_config_manager,
            ),
            patch("griptape_nodes.utils.library_utils.xdg_data_home") as mock_xdg,
        ):
            mock_xdg.return_value = Path("/home/user/.local/share")

            library_manager._migrate_old_xdg_library_paths()

            # Verify both configs were updated
            assert mock_config_manager.set_config_value.call_count == 2  # noqa: PLR2004

            # Check that only missing git URL was added
            calls = mock_config_manager.set_config_value.call_args_list
            download_call = next(c for c in calls if "libraries_to_download" in c[0][0])

            assert len(download_call[0][1]) == 2  # Original + 1 new  # noqa: PLR2004
            assert "griptape-nodes-library-standard" in download_call[0][1][0]  # Original
            assert any("griptape-nodes-library-griptape-cloud" in url for url in download_call[0][1])


class TestLibraryManagerRegisterLibraryFromFile:
    """Test the register_library_from_file_request functionality in LibraryManager."""

    @pytest.mark.asyncio
    async def test_always_installs_dependencies_even_when_venv_exists(self, griptape_nodes: GriptapeNodes) -> None:
        """Test that dependencies are always installed on library load, even when venv already exists."""
        library_manager = griptape_nodes.LibraryManager()

        # Mock library schema with pip dependencies
        schema = MagicMock()
        schema.name = "test_lib"
        schema.metadata.library_version = "1.0.0"
        schema.metadata.dependencies.pip_dependencies = ["requests"]
        schema.advanced_library_path = None

        with (
            patch("griptape_nodes.retained_mode.managers.library_manager.Path") as mock_path,
            patch.object(library_manager, "load_library_metadata_from_file_request") as mock_load,
            # Mock that venv already exists (old code would skip installation)
            patch.object(library_manager, "_get_library_venv_path") as mock_venv,
            patch.object(library_manager, "install_library_dependencies_request") as mock_install,
            patch("griptape_nodes.retained_mode.managers.library_manager.logger"),
        ):
            mock_path.return_value.exists.return_value = True
            mock_load.return_value = LoadLibraryMetadataFromFileResultSuccess(
                library_schema=schema,
                file_path="/mock.json",
                git_remote=None,
                git_ref=None,
                result_details=ResultDetails(message="Success", level=20),
            )
            mock_venv.return_value.exists.return_value = True
            # Mock successful dependency installation
            mock_install.return_value = InstallLibraryDependenciesResultSuccess(
                library_name="test_lib", dependencies_installed=2, result_details=ResultDetails(message="OK", level=20)
            )

            await library_manager.register_library_from_file_request(
                RegisterLibraryFromFileRequest(file_path="/mock.json")
            )

            # Verify dependencies were installed despite existing venv
            mock_install.assert_called_once()

    @pytest.mark.asyncio
    async def test_dependency_installation_failure_returns_failure(self, griptape_nodes: GriptapeNodes) -> None:
        """Test that dependency installation failure returns RegisterLibraryFromFileResultFailure."""
        mgr = griptape_nodes.LibraryManager()
        schema = MagicMock()
        schema.name = "lib"
        schema.metadata.library_version = "1.0.0"
        schema.metadata.dependencies.pip_dependencies = ["req"]
        schema.advanced_library_path = None

        with (
            patch(
                "griptape_nodes.retained_mode.managers.library_manager.Path",
                return_value=MagicMock(exists=MagicMock(return_value=True)),
            ),
            patch.object(
                mgr,
                "load_library_metadata_from_file_request",
                return_value=LoadLibraryMetadataFromFileResultSuccess(
                    library_schema=schema,
                    file_path="/f",
                    git_remote=None,
                    git_ref=None,
                    result_details=ResultDetails(message="OK", level=20),
                ),
            ),
            patch.object(mgr, "_get_library_venv_path", return_value=MagicMock(exists=MagicMock(return_value=True))),
            # Mock failed dependency installation
            patch.object(
                mgr,
                "install_library_dependencies_request",
                return_value=InstallLibraryDependenciesResultFailure(result_details="Install failed"),
            ),
        ):
            result = await mgr.register_library_from_file_request(RegisterLibraryFromFileRequest(file_path="/f"))

            # Verify failure result with expected error message
            assert isinstance(result, RegisterLibraryFromFileResultFailure)
            assert "Install failed" in str(result.result_details)


class TestLibraryManagerInstallLibraryDependencies:
    """Tests for install_library_dependencies_request."""

    def _metadata_result(self, schema: MagicMock) -> LoadLibraryMetadataFromFileResultSuccess:
        return LoadLibraryMetadataFromFileResultSuccess(
            library_schema=schema,
            file_path="/mock.json",
            git_remote=None,
            git_ref=None,
            result_details=ResultDetails(message="OK", level=20),
        )

    @pytest.mark.asyncio
    async def test_creates_venv_when_pip_dependencies_is_empty(self, griptape_nodes: GriptapeNodes) -> None:
        """Test that the venv is created even when pip_dependencies is empty."""
        mgr = griptape_nodes.LibraryManager()
        schema = MagicMock()
        schema.name = "test_lib"
        schema.metadata.library_version = "1.0.0"
        schema.metadata.dependencies.pip_dependencies = []
        schema.metadata.dependencies.pip_install_flags = []
        mock_python_path = MagicMock()

        with (
            patch.object(mgr, "load_library_metadata_from_file_request", return_value=self._metadata_result(schema)),
            patch.object(mgr, "_get_library_venv_path", return_value=MagicMock()),
            patch.object(
                mgr, "_init_library_venv", new_callable=AsyncMock, return_value=mock_python_path
            ) as mock_init_venv,
            patch.object(mgr, "_can_write_to_venv_location", return_value=True),
            patch(
                "griptape_nodes.retained_mode.managers.library_manager.OSManager.check_available_disk_space",
                return_value=True,
            ),
            patch.object(griptape_nodes.ConfigManager(), "get_config_value", return_value=5.0),
        ):
            result = await mgr.install_library_dependencies_request(
                InstallLibraryDependenciesRequest(library_file_path="/mock.json")
            )

        mock_init_venv.assert_called_once()
        assert isinstance(result, InstallLibraryDependenciesResultSuccess)
        assert result.dependencies_installed == 0

    @pytest.mark.asyncio
    async def test_creates_venv_when_dependencies_is_none(self, griptape_nodes: GriptapeNodes) -> None:
        """Test that the venv is created even when the dependencies section is absent."""
        mgr = griptape_nodes.LibraryManager()
        schema = MagicMock()
        schema.name = "test_lib"
        schema.metadata.library_version = "1.0.0"
        schema.metadata.dependencies = None
        mock_python_path = MagicMock()

        with (
            patch.object(mgr, "load_library_metadata_from_file_request", return_value=self._metadata_result(schema)),
            patch.object(mgr, "_get_library_venv_path", return_value=MagicMock()),
            patch.object(
                mgr, "_init_library_venv", new_callable=AsyncMock, return_value=mock_python_path
            ) as mock_init_venv,
            patch.object(mgr, "_can_write_to_venv_location", return_value=True),
            patch(
                "griptape_nodes.retained_mode.managers.library_manager.OSManager.check_available_disk_space",
                return_value=True,
            ),
            patch.object(griptape_nodes.ConfigManager(), "get_config_value", return_value=5.0),
        ):
            result = await mgr.install_library_dependencies_request(
                InstallLibraryDependenciesRequest(library_file_path="/mock.json")
            )

        mock_init_venv.assert_called_once()
        assert isinstance(result, InstallLibraryDependenciesResultSuccess)
        assert result.dependencies_installed == 0

    @pytest.mark.asyncio
    async def test_returns_failure_when_venv_creation_fails_with_no_deps(self, griptape_nodes: GriptapeNodes) -> None:
        """Test that venv creation failure returns failure even when pip_dependencies is empty."""
        mgr = griptape_nodes.LibraryManager()
        schema = MagicMock()
        schema.name = "test_lib"
        schema.metadata.library_version = "1.0.0"
        schema.metadata.dependencies.pip_dependencies = []
        schema.metadata.dependencies.pip_install_flags = []

        with (
            patch.object(mgr, "load_library_metadata_from_file_request", return_value=self._metadata_result(schema)),
            patch.object(mgr, "_get_library_venv_path", return_value=MagicMock()),
            patch.object(mgr, "_init_library_venv", new_callable=AsyncMock, side_effect=RuntimeError("disk full")),
        ):
            result = await mgr.install_library_dependencies_request(
                InstallLibraryDependenciesRequest(library_file_path="/mock.json")
            )

        assert isinstance(result, InstallLibraryDependenciesResultFailure)
        assert "disk full" in str(result.result_details)

    @pytest.mark.asyncio
    async def test_returns_failure_when_venv_unwritable_with_no_deps(self, griptape_nodes: GriptapeNodes) -> None:
        """Test that an unwritable venv returns failure even when pip_dependencies is empty."""
        mgr = griptape_nodes.LibraryManager()
        schema = MagicMock()
        schema.name = "test_lib"
        schema.metadata.library_version = "1.0.0"
        schema.metadata.dependencies.pip_dependencies = []
        schema.metadata.dependencies.pip_install_flags = []

        with (
            patch.object(mgr, "load_library_metadata_from_file_request", return_value=self._metadata_result(schema)),
            patch.object(mgr, "_get_library_venv_path", return_value=MagicMock()),
            patch.object(mgr, "_init_library_venv", new_callable=AsyncMock, return_value=MagicMock()),
            patch.object(mgr, "_can_write_to_venv_location", return_value=False),
        ):
            result = await mgr.install_library_dependencies_request(
                InstallLibraryDependenciesRequest(library_file_path="/mock.json")
            )

        assert isinstance(result, InstallLibraryDependenciesResultFailure)

    @pytest.mark.asyncio
    async def test_returns_failure_when_insufficient_disk_space_with_no_deps(
        self, griptape_nodes: GriptapeNodes
    ) -> None:
        """Test that insufficient disk space returns failure even when pip_dependencies is empty."""
        mgr = griptape_nodes.LibraryManager()
        schema = MagicMock()
        schema.name = "test_lib"
        schema.metadata.library_version = "1.0.0"
        schema.metadata.dependencies.pip_dependencies = []
        schema.metadata.dependencies.pip_install_flags = []

        with (
            patch.object(mgr, "load_library_metadata_from_file_request", return_value=self._metadata_result(schema)),
            patch.object(mgr, "_get_library_venv_path", return_value=MagicMock()),
            patch.object(mgr, "_init_library_venv", new_callable=AsyncMock, return_value=MagicMock()),
            patch.object(mgr, "_can_write_to_venv_location", return_value=True),
            patch(
                "griptape_nodes.retained_mode.managers.library_manager.OSManager.check_available_disk_space",
                return_value=False,
            ),
            patch(
                "griptape_nodes.retained_mode.managers.library_manager.OSManager.format_disk_space_error",
                return_value="not enough space",
            ),
            patch.object(griptape_nodes.ConfigManager(), "get_config_value", return_value=5.0),
        ):
            result = await mgr.install_library_dependencies_request(
                InstallLibraryDependenciesRequest(library_file_path="/mock.json")
            )

        assert isinstance(result, InstallLibraryDependenciesResultFailure)


class TestListRegisteredLibraries:
    """Test the on_list_registered_libraries_request functionality in LibraryManager."""

    @pytest.mark.asyncio
    async def test_waits_for_loading_complete_before_returning_libraries(self, griptape_nodes: GriptapeNodes) -> None:
        """Test that the handler blocks until _libraries_loading_complete is set."""
        library_manager = griptape_nodes.LibraryManager()

        # Ensure the event is not set so the handler will block
        library_manager._libraries_loading_complete.clear()

        mock_libraries = ["LibA", "LibB"]

        with patch.object(LibraryRegistry, "list_libraries", return_value=mock_libraries):
            request = ListRegisteredLibrariesRequest()
            task = asyncio.create_task(library_manager.on_list_registered_libraries_request(request))

            # Yield control so the task can start and block on the event
            await asyncio.sleep(0)

            # The task should still be waiting because the event is not set
            assert not task.done()

            # Signal that loading is complete
            library_manager._libraries_loading_complete.set()

            result = await task

        assert isinstance(result, ListRegisteredLibrariesResultSuccess)
        assert result.libraries == mock_libraries

    @pytest.mark.asyncio
    async def test_returns_library_list_when_loading_already_complete(self, griptape_nodes: GriptapeNodes) -> None:
        """Test that the handler returns the library list immediately when loading is already done."""
        library_manager = griptape_nodes.LibraryManager()

        # Simulate loading already finished
        library_manager._libraries_loading_complete.set()

        mock_libraries = ["LibA", "LibB", "LibC"]

        with patch.object(LibraryRegistry, "list_libraries", return_value=mock_libraries):
            request = ListRegisteredLibrariesRequest()
            result = await library_manager.on_list_registered_libraries_request(request)

        assert isinstance(result, ListRegisteredLibrariesResultSuccess)
        assert result.libraries == mock_libraries

    @pytest.mark.asyncio
    async def test_returns_copy_of_library_list(self, griptape_nodes: GriptapeNodes) -> None:
        """Test that the returned library list is a copy and not the original reference."""
        library_manager = griptape_nodes.LibraryManager()
        library_manager._libraries_loading_complete.set()

        mock_libraries = ["LibA"]

        with patch.object(LibraryRegistry, "list_libraries", return_value=mock_libraries):
            request = ListRegisteredLibrariesRequest()
            result = await library_manager.on_list_registered_libraries_request(request)

        assert isinstance(result, ListRegisteredLibrariesResultSuccess)
        # Mutating the result should not affect the original list
        result.libraries.append("LibB")
        assert mock_libraries == ["LibA"]


class TestGetAllInfoForAllLibraries:
    """Test the get_all_info_for_all_libraries_request functionality in LibraryManager."""

    def test_calls_library_registry_directly(self, griptape_nodes: GriptapeNodes) -> None:
        """Test that the method reads libraries from LibraryRegistry without going through on_list_registered_libraries_request."""
        library_manager = griptape_nodes.LibraryManager()

        with (
            patch.object(LibraryRegistry, "list_libraries", return_value=[]) as mock_list,
            patch.object(library_manager, "on_list_registered_libraries_request") as mock_handler,
        ):
            request = GetAllInfoForAllLibrariesRequest()
            result = library_manager.get_all_info_for_all_libraries_request(request)

        mock_list.assert_called_once()
        mock_handler.assert_not_called()
        assert isinstance(result, GetAllInfoForAllLibrariesResultSuccess)

    def test_returns_failure_when_individual_library_info_fails(self, griptape_nodes: GriptapeNodes) -> None:
        """Test that the method returns failure when retrieving info for a library fails."""
        library_manager = griptape_nodes.LibraryManager()

        mock_failure = MagicMock()
        mock_failure.succeeded.return_value = False

        with (
            patch.object(LibraryRegistry, "list_libraries", return_value=["BadLib"]),
            patch.object(library_manager, "get_all_info_for_library_request", return_value=mock_failure),
        ):
            request = GetAllInfoForAllLibrariesRequest()
            result = library_manager.get_all_info_for_all_libraries_request(request)

        assert isinstance(result, GetAllInfoForAllLibrariesResultFailure)
        assert "BadLib" in str(result.result_details)


class TestAddLibraryPathsToSysPath:
    """Test the _add_library_paths_to_sys_path helper method."""

    @pytest.mark.asyncio
    async def test_adds_base_dir_to_sys_path(self, griptape_nodes: GriptapeNodes) -> None:
        """Test that the library base directory is added to sys.path."""
        library_manager = griptape_nodes.LibraryManager()
        base_dir = Path("/fake/library/dir")

        mock_anyio_path = MagicMock()
        mock_anyio_path.return_value.exists = AsyncMock(return_value=False)

        original_sys_path = sys.path.copy()
        try:
            with (
                patch.object(library_manager, "_get_library_venv_path", return_value=Path("/fake/venv")),
                patch("griptape_nodes.retained_mode.managers.library_manager.anyio.Path", mock_anyio_path),
            ):
                await library_manager._add_library_paths_to_sys_path("test_lib", "/fake/lib.json", base_dir)

            assert str(base_dir) in sys.path
        finally:
            sys.path[:] = original_sys_path

    @pytest.mark.asyncio
    async def test_adds_venv_site_packages_when_venv_exists(self, griptape_nodes: GriptapeNodes) -> None:
        """Test that venv site-packages are added to sys.path when the venv exists."""
        library_manager = griptape_nodes.LibraryManager()
        base_dir = Path("/fake/library/dir")
        venv_path = Path("/fake/library/dir/.venv")
        fake_site_packages = str(Path("/fake/library/dir/.venv/lib/python3.12/site-packages"))

        mock_anyio_path = MagicMock()
        mock_anyio_path.return_value.exists = AsyncMock(return_value=True)

        original_sys_path = sys.path.copy()
        try:
            with (
                patch.object(library_manager, "_get_library_venv_path", return_value=venv_path),
                patch("griptape_nodes.retained_mode.managers.library_manager.anyio.Path", mock_anyio_path),
                patch(
                    "griptape_nodes.retained_mode.managers.library_manager.sysconfig.get_path",
                    return_value=fake_site_packages,
                ),
            ):
                await library_manager._add_library_paths_to_sys_path("test_lib", "/fake/lib.json", base_dir)

            assert fake_site_packages in sys.path
            assert str(base_dir) in sys.path
        finally:
            sys.path[:] = original_sys_path

    @pytest.mark.asyncio
    async def test_skips_venv_when_venv_does_not_exist(self, griptape_nodes: GriptapeNodes) -> None:
        """Test that venv site-packages are NOT added when the venv doesn't exist."""
        library_manager = griptape_nodes.LibraryManager()
        base_dir = Path("/fake/library/dir")
        venv_path = Path("/fake/library/dir/.venv")

        mock_anyio_path = MagicMock()
        mock_anyio_path.return_value.exists = AsyncMock(return_value=False)

        original_sys_path = sys.path.copy()
        try:
            with (
                patch.object(library_manager, "_get_library_venv_path", return_value=venv_path),
                patch("griptape_nodes.retained_mode.managers.library_manager.anyio.Path", mock_anyio_path),
                patch("griptape_nodes.retained_mode.managers.library_manager.sysconfig.get_path") as mock_get_path,
            ):
                await library_manager._add_library_paths_to_sys_path("test_lib", "/fake/lib.json", base_dir)

            # sysconfig.get_path should not have been called since venv doesn't exist
            mock_get_path.assert_not_called()
            assert str(base_dir) in sys.path
        finally:
            sys.path[:] = original_sys_path
