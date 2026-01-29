"""Tests for WorkflowRegistry functionality."""

import os
import platform
from pathlib import Path

from griptape_nodes.node_library.workflow_registry import WorkflowRegistry
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes


class TestWorkflowRegistry:
    """Test suite for WorkflowRegistry functionality."""

    def test_get_complete_file_path_with_absolute_path(self) -> None:
        """Test that get_complete_file_path returns absolute paths as-is."""
        # Use a platform-appropriate absolute path
        if os.name == "nt":  # Windows
            absolute_path = "C:\\absolute\\path\\to\\workflow.py"
        else:  # Unix-like
            absolute_path = "/absolute/path/to/workflow.py"

        result = WorkflowRegistry.get_complete_file_path(absolute_path)

        # On Windows, paths starting with / are not considered absolute
        # so they get treated as relative paths
        if os.name == "nt" and absolute_path.startswith("/"):
            # On Windows, Unix-style paths are relative
            assert Path(result).is_absolute()
        else:
            assert result == absolute_path

    def test_get_complete_file_path_with_unix_style_on_windows(self) -> None:
        """Test Unix-style paths on Windows (treated as relative)."""
        unix_style_path = "/absolute/path/to/workflow.py"
        result = WorkflowRegistry.get_complete_file_path(unix_style_path)

        if os.name == "nt":  # Windows
            # Unix-style paths are treated as relative on Windows
            # The result should be the workspace path + the Unix path
            assert result.endswith("\\absolute\\path\\to\\workflow.py")
            # Verify it's been made absolute
            assert Path(result).is_absolute()
        else:
            # On Unix, this is an absolute path
            assert result == unix_style_path

    def test_get_complete_file_path_with_absolute_windows_path(self) -> None:
        """Test that get_complete_file_path handles Windows absolute paths."""
        windows_path = "C:\\Users\\test\\workflow.py"

        result = WorkflowRegistry.get_complete_file_path(windows_path)

        # On Windows, it should be returned as-is
        # On Unix systems, Path.is_absolute() returns False for Windows paths,
        # so it will be treated as relative
        if platform.system() == "Windows":
            assert result == windows_path
        else:
            # On Unix, Windows paths are treated as relative
            assert result.endswith("C:\\Users\\test\\workflow.py")

    def test_get_complete_file_path_with_relative_path(self, griptape_nodes: GriptapeNodes) -> None:
        """Test that get_complete_file_path resolves relative paths to workspace."""
        relative_path = "workflows/my_workflow.py"

        # Get the actual workspace path from the config manager
        workspace_path = griptape_nodes.ConfigManager().workspace_path

        result = WorkflowRegistry.get_complete_file_path(relative_path)

        expected = str(workspace_path / relative_path)
        assert result == expected

    def test_get_complete_file_path_with_home_expansion(self) -> None:
        """Test that get_complete_file_path handles paths with home directory expansion."""
        home_path = "~/workflows/my_workflow.py"

        # Home paths starting with ~ are NOT considered absolute by Path.is_absolute()
        # so they will be treated as relative paths
        result = WorkflowRegistry.get_complete_file_path(home_path)

        # Should be treated as relative and appended to workspace
        if os.name == "nt":  # Windows
            # On Windows, ~ is just a regular character in the path
            assert result.endswith("~\\workflows\\my_workflow.py")
        else:
            # On Unix, ~ is also treated as relative (not expanded)
            assert result.endswith("~/workflows/my_workflow.py")

    def test_get_complete_file_path_with_current_dir_relative(self, griptape_nodes: GriptapeNodes) -> None:
        """Test that get_complete_file_path handles current directory relative paths."""
        current_dir_path = "./my_workflow.py"

        # Get the actual workspace path from the config manager
        workspace_path = griptape_nodes.ConfigManager().workspace_path

        result = WorkflowRegistry.get_complete_file_path(current_dir_path)

        expected = str(workspace_path / current_dir_path)
        assert result == expected

    def test_get_complete_file_path_with_parent_dir_relative(self, griptape_nodes: GriptapeNodes) -> None:
        """Test that get_complete_file_path handles parent directory relative paths."""
        parent_dir_path = "../external/my_workflow.py"

        # Get the actual workspace path from the config manager
        workspace_path = griptape_nodes.ConfigManager().workspace_path

        result = WorkflowRegistry.get_complete_file_path(parent_dir_path)

        # resolve_workspace_path normalizes the path by resolving .. components
        expected = str((workspace_path / parent_dir_path).resolve())
        assert result == expected
