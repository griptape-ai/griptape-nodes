"""Unit tests for LocalWorkflowExecutor._load_project."""

from pathlib import Path, PureWindowsPath
from unittest.mock import AsyncMock, MagicMock, patch

import pytest  # type: ignore[reportMissingImports]

from griptape_nodes.bootstrap.workflow_executors.local_workflow_executor import (
    LocalExecutorError,
    LocalWorkflowExecutor,
)
from griptape_nodes.retained_mode.events.project_events import (
    LoadProjectTemplateResultSuccess,
    SetCurrentProjectResultSuccess,
)

# A Windows path that exceeds the legacy MAX_PATH (260 chars).
# Total length is ~300 characters including the drive letter.
_LONG_WINDOWS_PATH = PureWindowsPath(
    "C:\\Users\\SomeUser\\AppData\\Local\\GriptapeNodes\\Projects\\"
    + "\\".join(["a_rather_long_directory_name_that_pads_length"] * 5)
    + "\\my_project_template.yaml"
)

WINDOWS_MAX_PATH = 260
EXPECTED_REQUEST_COUNT = 2
MODULE_PATH = "griptape_nodes.bootstrap.workflow_executors.local_workflow_executor"


class TestLoadProject:
    """Tests for LocalWorkflowExecutor._load_project."""

    @pytest.mark.asyncio
    async def test_load_project_with_long_windows_path(self) -> None:
        """A Windows path exceeding MAX_PATH (260 chars) should be accepted."""
        assert len(str(_LONG_WINDOWS_PATH)) > WINDOWS_MAX_PATH

        mock_load_result = MagicMock(spec=LoadProjectTemplateResultSuccess)
        mock_load_result.project_id = "test-project-id"

        mock_set_result = MagicMock(spec=SetCurrentProjectResultSuccess)
        mock_set_result.failed.return_value = False

        with patch(f"{MODULE_PATH}.GriptapeNodes") as mock_gn:
            mock_gn.ahandle_request = AsyncMock(side_effect=[mock_load_result, mock_set_result])

            executor = LocalWorkflowExecutor.__new__(LocalWorkflowExecutor)
            project_path = Path(_LONG_WINDOWS_PATH)
            await executor._load_project(project_path)

        calls = mock_gn.ahandle_request.call_args_list
        assert len(calls) == EXPECTED_REQUEST_COUNT
        # Verify the long path was passed through to LoadProjectTemplateRequest
        load_request = calls[0].args[0]
        assert load_request.project_path == project_path

    @pytest.mark.asyncio
    async def test_load_project_raises_on_load_failure(self) -> None:
        """_load_project should raise LocalExecutorError when loading fails."""
        # Return something that is NOT a LoadProjectTemplateResultSuccess
        mock_load_result = MagicMock(spec=[])

        with patch(f"{MODULE_PATH}.GriptapeNodes") as mock_gn:
            mock_gn.ahandle_request = AsyncMock(return_value=mock_load_result)

            executor = LocalWorkflowExecutor.__new__(LocalWorkflowExecutor)
            with pytest.raises(LocalExecutorError, match="Attempted to load project template from"):
                await executor._load_project(Path("/some/project.yaml"))

    @pytest.mark.asyncio
    async def test_load_project_raises_on_set_current_failure(self) -> None:
        """_load_project should raise LocalExecutorError when setting current project fails."""
        mock_load_result = MagicMock(spec=LoadProjectTemplateResultSuccess)
        mock_load_result.project_id = "test-project-id"

        mock_set_result = MagicMock()
        mock_set_result.failed.return_value = True

        with patch(f"{MODULE_PATH}.GriptapeNodes") as mock_gn:
            mock_gn.ahandle_request = AsyncMock(side_effect=[mock_load_result, mock_set_result])

            executor = LocalWorkflowExecutor.__new__(LocalWorkflowExecutor)
            with pytest.raises(LocalExecutorError, match="Attempted to set project"):
                await executor._load_project(Path("/some/project.yaml"))

    @pytest.mark.asyncio
    async def test_load_project_success(self) -> None:
        """_load_project should complete without error on success."""
        mock_load_result = MagicMock(spec=LoadProjectTemplateResultSuccess)
        mock_load_result.project_id = "proj-123"

        mock_set_result = MagicMock(spec=SetCurrentProjectResultSuccess)
        mock_set_result.failed.return_value = False

        with patch(f"{MODULE_PATH}.GriptapeNodes") as mock_gn:
            mock_gn.ahandle_request = AsyncMock(side_effect=[mock_load_result, mock_set_result])

            executor = LocalWorkflowExecutor.__new__(LocalWorkflowExecutor)
            await executor._load_project(Path("/some/project.yaml"))

        # Verify both requests were made
        assert mock_gn.ahandle_request.call_count == EXPECTED_REQUEST_COUNT
