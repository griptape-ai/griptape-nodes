import logging
from pathlib import Path

from griptape_nodes.retained_mode.events.os_events import (
    ExistingFilePolicy,
    ReadFileRequest,
    ReadFileResultSuccess,
    WriteFileRequest,
    WriteFileResultSuccess,
)
from griptape_nodes.retained_mode.managers.config_manager import ConfigManager

logger = logging.getLogger("griptape_nodes")


class FileManager:
    """File I/O convenience layer for nodes.

    Provides simple file read/write API for nodes that wraps OSManager's
    ReadFileRequest/WriteFileRequest. All file writes return file:// URIs
    to keep nodes independent of HTTP serving concerns.

    This manager is for node file operations only. For editor file transfers
    (presigned URLs), use StaticFilesManager instead.
    """

    def __init__(self, config_manager: ConfigManager) -> None:
        """Initialize the FileManager.

        Args:
            config_manager: The ConfigManager instance to access workspace path.
        """
        self.config_manager = config_manager

    def write_file(
        self,
        data: bytes,
        file_name: str,
        existing_file_policy: ExistingFilePolicy = ExistingFilePolicy.OVERWRITE,
    ) -> str:
        """Write a file and return its file:// URI.

        Writes file to the static files directory (workflow-aware) and returns
        a file:// URI that can be used in artifacts. The URI points to the absolute
        path of the written file.

        Args:
            data: File content as bytes
            file_name: Name of the file to create (extension included)
            existing_file_policy: How to handle existing files (default: OVERWRITE)
                - OVERWRITE: Replace existing file
                - CREATE_NEW: Auto-generate unique filename (file_1.ext, file_2.ext)
                - FAIL: Raise error if file exists

        Returns:
            file:// URI of the written file (e.g., file:///absolute/path/to/file.png)

        Raises:
            ValueError: If file write fails

        Example:
            >>> image_bytes = buffer.getvalue()
            >>> file_uri = GriptapeNodes.FileManager().write_file(image_bytes, "output.png")
            >>> artifact = ImageUrlArtifact(file_uri)
        """
        from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

        # Resolve static files directory (workflow-aware)
        resolved_directory = self._get_static_files_directory()
        file_path = Path(resolved_directory) / file_name

        # Get absolute path for the file
        workspace_path = self.config_manager.workspace_path
        absolute_file_path = workspace_path / file_path

        # Write file using WriteFileRequest
        result = GriptapeNodes.handle_request(
            WriteFileRequest(
                file_path=str(absolute_file_path),
                content=data,
                existing_file_policy=existing_file_policy,
            )
        )

        if isinstance(result, WriteFileResultSuccess):
            # Convert the written file path to file:// URI
            written_path = Path(result.final_file_path)
            return written_path.as_uri()

        # Failed - raise ValueError for backward compatibility
        error_msg = f"Failed to write file {file_name}: {result.result_details}"
        logger.error(error_msg)
        raise ValueError(error_msg)

    def read_file(
        self,
        file_path: str,
        encoding: str = "utf-8",
        workspace_only: bool | None = False,  # noqa: FBT001, FBT002
        should_transform_image_content_to_thumbnail: bool = False,  # noqa: FBT001, FBT002
    ) -> bytes:
        """Read file contents and return as bytes.

        Convenience method that wraps ReadFileRequest for reading files.
        Text files are automatically encoded to bytes using the specified encoding.

        Args:
            file_path: Path to the file to read (absolute or workspace-relative)
            encoding: Text encoding for text files (default: 'utf-8')
            workspace_only: If True, restrict to workspace directory.
                           If False (default), allow system-wide access.
                           If None, no workspace constraints (cloud).
            should_transform_image_content_to_thumbnail: If True, convert images
                           to thumbnail data URLs. Default False for raw file access.

        Returns:
            File content as bytes

        Raises:
            ValueError: If file cannot be read (not found, permission denied, etc.)

        Example:
            >>> content = GriptapeNodes.FileManager().read_file("config.json")
            >>> image_bytes = GriptapeNodes.FileManager().read_file("image.png")
        """
        from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

        result = GriptapeNodes.handle_request(
            ReadFileRequest(
                file_path=file_path,
                encoding=encoding,
                workspace_only=workspace_only,
                should_transform_image_content_to_thumbnail=should_transform_image_content_to_thumbnail,
            )
        )

        if isinstance(result, ReadFileResultSuccess):
            # Convert str to bytes if needed (text files)
            if isinstance(result.content, str):
                return result.content.encode(encoding)
            return result.content

        error_msg = f"Failed to read file {file_path}: {result.result_details}"
        logger.error(error_msg)
        raise ValueError(error_msg)

    async def aread_file(
        self,
        file_path: str,
        encoding: str = "utf-8",
        workspace_only: bool | None = False,  # noqa: FBT001, FBT002
        should_transform_image_content_to_thumbnail: bool = False,  # noqa: FBT001, FBT002
    ) -> bytes:
        """Read file contents asynchronously and return as bytes.

        Async version of read_file(). Convenience method that wraps ReadFileRequest
        for reading files. Text files are automatically encoded to bytes using the
        specified encoding.

        Args:
            file_path: Path to the file to read (absolute or workspace-relative)
            encoding: Text encoding for text files (default: 'utf-8')
            workspace_only: If True, restrict to workspace directory.
                           If False (default), allow system-wide access.
                           If None, no workspace constraints (cloud).
            should_transform_image_content_to_thumbnail: If True, convert images
                           to thumbnail data URLs. Default False for raw file access.

        Returns:
            File content as bytes

        Raises:
            ValueError: If file cannot be read (not found, permission denied, etc.)

        Example:
            >>> content = await GriptapeNodes.FileManager().aread_file("config.json")
            >>> image_bytes = await GriptapeNodes.FileManager().aread_file("image.png")
        """
        from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

        result = await GriptapeNodes.ahandle_request(
            ReadFileRequest(
                file_path=file_path,
                encoding=encoding,
                workspace_only=workspace_only,
                should_transform_image_content_to_thumbnail=should_transform_image_content_to_thumbnail,
            )
        )

        if isinstance(result, ReadFileResultSuccess):
            # Convert str to bytes if needed (text files)
            if isinstance(result.content, str):
                return result.content.encode(encoding)
            return result.content

        error_msg = f"Failed to read file {file_path}: {result.result_details}"
        logger.error(error_msg)
        raise ValueError(error_msg)

    def _get_static_files_directory(self) -> str:
        """Get the appropriate static files directory based on the current workflow context.

        Returns:
            The directory path to use for static files, relative to the workspace directory.
            If a workflow is active, returns the staticfiles subdirectory within the
            workflow's directory relative to workspace. Otherwise, returns the staticfiles
            subdirectory relative to workspace.
        """
        from griptape_nodes.node_library.workflow_registry import WorkflowRegistry
        from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

        workspace_path = self.config_manager.workspace_path
        static_files_subdir = self.config_manager.get_config_value("static_files_directory", default="staticfiles")

        # Check if there's an active workflow context
        context_manager = GriptapeNodes.ContextManager()
        if context_manager.has_current_workflow():
            try:
                # Get the current workflow name and its file path
                workflow_name = context_manager.get_current_workflow_name()
                workflow = WorkflowRegistry.get_workflow_by_name(workflow_name)

                # Get the directory containing the workflow file
                workflow_file_path = Path(WorkflowRegistry.get_complete_file_path(workflow.file_path))
                workflow_directory = workflow_file_path.parent

                # Make the workflow directory relative to workspace
                relative_workflow_dir = workflow_directory.relative_to(workspace_path)
                return str(relative_workflow_dir / static_files_subdir)

            except (KeyError, AttributeError) as e:
                # If anything goes wrong getting workflow info, fall back to workspace-relative
                logger.warning("Failed to get workflow directory for static files, using workspace: %s", e)
            except ValueError as e:
                # If workflow directory is not within workspace, fall back to workspace-relative
                logger.warning("Workflow directory is outside workspace, using workspace-relative static files: %s", e)

        # If no workflow context or workflow lookup failed, return just the static files subdirectory
        return static_files_subdir
