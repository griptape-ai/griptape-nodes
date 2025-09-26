import re
from pathlib import Path
from typing import Any


class PathUtils:
    """Utilities for cross-platform path handling and workspace detection."""

    @staticmethod
    def normalize_path_input(path_input: Any) -> str:
        """Normalize various path inputs to a string.

        Args:
            path_input: Path input (string, Path, or other)

        Returns:
            Normalized string representation
        """
        if path_input is None:
            return ""

        if isinstance(path_input, Path):
            return str(path_input)

        # Convert to string and strip surrounding quotes
        path_str = str(path_input).strip()
        return PathUtils._strip_surrounding_quotes(path_str)

    @staticmethod
    def _strip_surrounding_quotes(path_str: str) -> str:
        """Strip surrounding quotes only if they match (from 'Copy as Pathname')."""
        if len(path_str) >= 2 and (  # noqa: PLR2004
            (path_str.startswith("'") and path_str.endswith("'"))
            or (path_str.startswith('"') and path_str.endswith('"'))
        ):
            return path_str[1:-1]
        return path_str

    @staticmethod
    def to_path_object(path_input: Any) -> Path | None:
        """Convert input to a Path object.

        Args:
            path_input: Path input to convert

        Returns:
            Path object or None if input is empty/invalid
        """
        normalized = PathUtils.normalize_path_input(path_input)
        if not normalized:
            return None

        return Path(normalized)

    @staticmethod
    def is_url(path_str: str) -> bool:
        """Check if the path string is a URL.

        Args:
            path_str: Path string to check

        Returns:
            True if the string is a URL
        """
        return path_str.startswith(("http://", "https://"))

    @staticmethod
    def is_within_workspace(file_path: Path, workspace_path: Path) -> bool:
        """Check if a file path is within the workspace directory.

        Args:
            file_path: File path to check
            workspace_path: Workspace root path

        Returns:
            True if file is within workspace
        """
        try:
            # Make both paths absolute for comparison
            abs_file = file_path.resolve()
            abs_workspace = workspace_path.resolve()
        except (OSError, ValueError):
            # If path resolution fails, assume not in workspace
            return False

        # Check if file path starts with workspace path
        return abs_workspace in abs_file.parents or abs_file == abs_workspace

    @staticmethod
    def make_workspace_relative(file_path: Path, workspace_path: Path) -> Path:
        """Make a file path relative to the workspace.

        Args:
            file_path: Absolute file path
            workspace_path: Workspace root path

        Returns:
            Path relative to workspace

        Raises:
            ValueError: If file is not within workspace
        """
        try:
            abs_file = file_path.resolve()
            abs_workspace = workspace_path.resolve()
            return abs_file.relative_to(abs_workspace)
        except ValueError as e:
            msg = f"File path '{file_path}' is not within workspace '{workspace_path}'"
            raise ValueError(msg) from e

    @staticmethod
    def get_display_path(file_path: Path, workspace_path: Path) -> str:
        """Get the appropriate display path for the user.

        For files within workspace: returns workspace-relative path
        For files outside workspace: returns absolute path

        Args:
            file_path: File path to display
            workspace_path: Workspace root path

        Returns:
            String path appropriate for display
        """
        if PathUtils.is_within_workspace(file_path, workspace_path):
            try:
                relative_path = PathUtils.make_workspace_relative(file_path, workspace_path)
                return str(relative_path)
            except ValueError:
                # Fallback to absolute if relative conversion fails
                pass

        return str(file_path.resolve())

    @staticmethod
    def generate_upload_filename(
        workflow_name: str,
        node_name: str,
        parameter_name: str,
        original_filename: str,
    ) -> str:
        """Generate a collision-free filename for uploaded files.

        Args:
            workflow_name: Name of the current workflow
            node_name: Name of the node
            parameter_name: Name of the parameter
            original_filename: Original filename

        Returns:
            Generated collision-free filename
        """

        # Sanitize components for filename safety
        def sanitize(name: str) -> str:
            """Replace unsafe characters with underscores."""
            return re.sub(r'[<>:"/\\|?*]', "_", name)

        safe_workflow = sanitize(workflow_name)
        safe_node = sanitize(node_name)
        safe_param = sanitize(parameter_name)
        safe_filename = sanitize(original_filename)

        return f"{safe_workflow}_{safe_node}_{safe_param}_{safe_filename}"

    @staticmethod
    def resolve_file_path(path_str: str, workspace_path: Path) -> Path:
        """Resolve a path string to an absolute Path object.

        Handles both absolute paths and workspace-relative paths.

        Args:
            path_str: Path string to resolve
            workspace_path: Workspace root path for resolving relative paths

        Returns:
            Absolute Path object

        Raises:
            FileNotFoundError: If the resolved path doesn't exist
            ValueError: If path_str is invalid
        """
        if not path_str:
            msg = "Path string cannot be empty"
            raise ValueError(msg)

        path = Path(path_str)

        if path.is_absolute():
            resolved_path = path.resolve()
        else:
            # Treat as workspace-relative
            resolved_path = (workspace_path / path).resolve()

        if not resolved_path.exists():
            msg = f"File not found: {resolved_path}"
            raise FileNotFoundError(msg)

        if not resolved_path.is_file():
            file_type = "directory" if resolved_path.is_dir() else "special file"
            msg = f"Path is not a file: {resolved_path} (found: {file_type})"
            raise ValueError(msg)

        return resolved_path
