from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from griptape_nodes.retained_mode.events.base_events import ResultDetails
from griptape_nodes.retained_mode.events.library_events import (
    LoadAllLibrariesRequest,
    LoadAllLibrariesResultFailure,
    LoadAllLibrariesResultSuccess,
)
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes


class TestLibraryManagerLoadAllLibraries:
    """Test the load_all_libraries_request functionality in LibraryManager."""

    @pytest.mark.asyncio
    async def test_libraries_already_loaded_returns_success_without_reloading(
        self, griptape_nodes: GriptapeNodes
    ) -> None:
        """Test that when libraries are already loaded, returns success without reloading."""
        library_manager = griptape_nodes.LibraryManager()

        # Mock that libraries are already loaded and discovered libraries match loaded ones
        mock_load_config = AsyncMock()
        with (
            patch.object(library_manager, "_library_file_path_to_info", {"some_lib": "info"}),
            patch.object(library_manager, "_discover_library_files", return_value=[Path("some_lib")]),
            patch.object(library_manager, "load_all_libraries_from_config", mock_load_config),
        ):
            request = LoadAllLibrariesRequest()
            result = await library_manager.load_all_libraries_request(request)

            assert isinstance(result, LoadAllLibrariesResultSuccess)
            assert isinstance(result.result_details, ResultDetails)
            assert "already loaded" in result.result_details.result_details[0].message.lower()
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
            request = LoadAllLibrariesRequest()
            result = await library_manager.load_all_libraries_request(request)

            assert isinstance(result, LoadAllLibrariesResultSuccess)
            assert isinstance(result.result_details, ResultDetails)
            assert "successfully loaded" in result.result_details.result_details[0].message.lower()
            mock_load_config.assert_called_once()

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
            request = LoadAllLibrariesRequest()
            result = await library_manager.load_all_libraries_request(request)

            assert isinstance(result, LoadAllLibrariesResultFailure)
            assert isinstance(result.result_details, ResultDetails)
            assert "Config error" in result.result_details.result_details[0].message
