import base64
import binascii
import logging
import threading
from pathlib import Path
from urllib.parse import unquote, urlparse

from xdg_base_dirs import xdg_config_home

from griptape_nodes.drivers.storage import StorageBackend
from griptape_nodes.drivers.storage.griptape_cloud_storage_driver import GriptapeCloudStorageDriver
from griptape_nodes.drivers.storage.local_storage_driver import LocalStorageDriver
from griptape_nodes.retained_mode.events.app_events import AppInitializationComplete
from griptape_nodes.retained_mode.events.static_file_events import (
    CreateStaticFileDownloadUrlRequest,
    CreateStaticFileDownloadUrlResultFailure,
    CreateStaticFileDownloadUrlResultSuccess,
    CreateStaticFileRequest,
    CreateStaticFileResultFailure,
    CreateStaticFileResultSuccess,
    CreateStaticFileUploadUrlRequest,
    CreateStaticFileUploadUrlResultFailure,
    CreateStaticFileUploadUrlResultSuccess,
    ResolveStaticFilePathRequest,
    ResolveStaticFilePathResultFailure,
    ResolveStaticFilePathResultSuccess,
)
from griptape_nodes.retained_mode.managers.config_manager import ConfigManager
from griptape_nodes.retained_mode.managers.event_manager import EventManager
from griptape_nodes.retained_mode.managers.secrets_manager import SecretsManager
from griptape_nodes.servers.static import start_static_server

logger = logging.getLogger("griptape_nodes")

USER_CONFIG_PATH = xdg_config_home() / "griptape_nodes" / "griptape_nodes_config.json"


class StaticFilesManager:
    """A class to manage the creation and management of static files."""

    def __init__(
        self,
        config_manager: ConfigManager,
        secrets_manager: SecretsManager,
        event_manager: EventManager | None = None,
    ) -> None:
        """Initialize the StaticFilesManager.

        Args:
            config_manager: The ConfigManager instance to use for accessing the workspace path.
            event_manager: The EventManager instance to use for event handling.
            secrets_manager: The SecretsManager instance to use for accessing secrets.
        """
        self.config_manager = config_manager

        self.storage_backend = config_manager.get_config_value("storage_backend", default=StorageBackend.LOCAL)
        workspace_directory = Path(config_manager.get_config_value("workspace_directory"))

        # Build base URL for LocalStorageDriver from configured base URL
        from griptape_nodes.servers.static import STATIC_SERVER_URL

        base_url_config = config_manager.get_config_value("static_server_base_url")
        base_url = f"{base_url_config}{STATIC_SERVER_URL}"

        match self.storage_backend:
            case StorageBackend.GTC:
                bucket_id = secrets_manager.get_secret("GT_CLOUD_BUCKET_ID", should_error_on_not_found=False)

                if not bucket_id:
                    logger.warning(
                        "GT_CLOUD_BUCKET_ID secret is not available, falling back to local storage. Run `gtn init` to set it up."
                    )
                    self.storage_driver = LocalStorageDriver(workspace_directory, base_url=base_url)
                else:
                    static_files_directory = config_manager.get_config_value(
                        "static_files_directory", default="staticfiles"
                    )
                    self.storage_driver = GriptapeCloudStorageDriver(
                        workspace_directory,
                        bucket_id=bucket_id,
                        api_key=secrets_manager.get_secret("GT_CLOUD_API_KEY"),
                        static_files_directory=static_files_directory,
                    )
            case StorageBackend.LOCAL:
                self.storage_driver = LocalStorageDriver(workspace_directory, base_url=base_url)
            case _:
                msg = f"Invalid storage backend: {self.storage_backend}"
                raise ValueError(msg)

        if event_manager is not None:
            event_manager.assign_manager_to_request_type(
                CreateStaticFileRequest, self.on_handle_create_static_file_request
            )
            event_manager.assign_manager_to_request_type(
                CreateStaticFileUploadUrlRequest, self.on_handle_create_static_file_upload_url_request
            )
            event_manager.assign_manager_to_request_type(
                CreateStaticFileDownloadUrlRequest, self.on_handle_create_static_file_download_url_request
            )
            event_manager.assign_manager_to_request_type(
                ResolveStaticFilePathRequest, self.on_handle_resolve_static_file_path_request
            )
            event_manager.add_listener_to_app_event(
                AppInitializationComplete,
                self.on_app_initialization_complete,
            )
            # TODO: Listen for shutdown event (https://github.com/griptape-ai/griptape-nodes/issues/2149) to stop static server

    def on_handle_create_static_file_request(
        self,
        request: CreateStaticFileRequest,
    ) -> CreateStaticFileResultSuccess | CreateStaticFileResultFailure:
        file_name = request.file_name

        try:
            content_bytes = base64.b64decode(request.content)
        except (binascii.Error, ValueError) as e:
            msg = f"Failed to decode base64 content for file {file_name}: {e}"
            return CreateStaticFileResultFailure(error=msg, result_details=msg)

        try:
            url = self.save_static_file(content_bytes, file_name)
        except Exception as e:
            msg = f"Failed to create static file for file {file_name}: {e}"
            return CreateStaticFileResultFailure(error=msg, result_details=msg)

        return CreateStaticFileResultSuccess(url=url, result_details=f"Successfully created static file: {url}")

    def on_handle_create_static_file_upload_url_request(
        self,
        request: CreateStaticFileUploadUrlRequest,
    ) -> CreateStaticFileUploadUrlResultSuccess | CreateStaticFileUploadUrlResultFailure:
        """Handle the request to create a presigned URL for uploading a static file.

        Args:
            request: The request object containing the file name.

        Returns:
            A result object indicating success or failure.
        """
        file_name = request.file_name

        resolved_directory = self._get_static_files_directory()
        full_file_path = Path(resolved_directory) / file_name

        try:
            response = self.storage_driver.create_signed_upload_url(full_file_path)
        except Exception as e:
            msg = f"Failed to create presigned URL for file {file_name}: {e}"
            return CreateStaticFileUploadUrlResultFailure(error=msg, result_details=msg)

        return CreateStaticFileUploadUrlResultSuccess(
            url=response["url"],
            headers=response["headers"],
            method=response["method"],
            result_details="Successfully created static file upload URL",
        )

    def _resolve_file_path_for_download(self, file_path: str) -> tuple[Path, bool, str | None]:
        """Resolve a file path for download URL creation.

        This method handles both absolute and workspace-relative paths. Files inside the
        workspace are served from their workspace-relative location. Files outside the
        workspace are served directly from their absolute path location.

        Args:
            file_path: Path to the file (absolute or workspace-relative)

        Returns:
            Tuple of (path, is_external, error_message). If error_message is not None,
            an error occurred and path/is_external should not be used.
            - path: workspace-relative path if inside workspace, absolute path if external
            - is_external: True if file is outside workspace, False if inside
        """
        workspace_path = self.config_manager.workspace_path

        # Check if it's a file:// URI and extract the path
        parsed = urlparse(file_path)
        if parsed.scheme == "file":
            # Extract absolute path from file:// URI and decode percent-encoding
            path = Path(unquote(parsed.path))
        else:
            # Convert to Path object
            path = Path(file_path)

        # Resolve relative paths relative to workspace
        if not path.is_absolute():
            path = workspace_path / path

        # Check if file exists
        if not path.exists():
            return Path(), False, f"File not found: {file_path}"

        if not path.is_file():
            return Path(), False, f"Path is not a file: {file_path}"

        # Check if file is inside workspace
        try:
            # This will raise ValueError if path is not relative to workspace_path
            workspace_relative = path.relative_to(workspace_path)
        except ValueError:
            # File is outside workspace, return absolute path and mark as external
            return path, True, None
        else:
            # File is inside workspace, return workspace-relative path
            return workspace_relative, False, None

    def on_handle_create_static_file_download_url_request(
        self,
        request: CreateStaticFileDownloadUrlRequest,
    ) -> CreateStaticFileDownloadUrlResultSuccess | CreateStaticFileDownloadUrlResultFailure:
        """Handle the request to create a presigned URL for downloading a static file.

        Args:
            request: The request object containing either file_name or file_path.

        Returns:
            A result object indicating success or failure.
        """
        # Validate that exactly one of file_name or file_path is provided
        if request.file_name is None and request.file_path is None:
            msg = "Either file_name or file_path must be provided"
            return CreateStaticFileDownloadUrlResultFailure(error=msg, result_details=msg)

        if request.file_name is not None and request.file_path is not None:
            msg = "Only one of file_name or file_path should be provided, not both"
            return CreateStaticFileDownloadUrlResultFailure(error=msg, result_details=msg)

        # Determine which path to use
        is_external = False
        if request.file_path is not None:
            # Use new path resolution logic
            full_file_path, is_external, error = self._resolve_file_path_for_download(request.file_path)
            if error is not None:
                return CreateStaticFileDownloadUrlResultFailure(error=error, result_details=error)
        else:
            # Use legacy file_name logic for backward compatibility
            # At this point, file_name must be not None due to earlier validation
            file_name = request.file_name
            if file_name is None:
                msg = "file_name is None but should have been validated"
                return CreateStaticFileDownloadUrlResultFailure(error=msg, result_details=msg)
            resolved_directory = self._get_static_files_directory()
            full_file_path = Path(resolved_directory) / file_name

        try:
            url = self.storage_driver.create_signed_download_url(full_file_path, is_external=is_external)
        except Exception as e:
            file_ref = request.file_path or request.file_name
            msg = f"Failed to create presigned URL for file {file_ref}: {e}"
            return CreateStaticFileDownloadUrlResultFailure(error=msg, result_details=msg)

        return CreateStaticFileDownloadUrlResultSuccess(
            url=url, result_details="Successfully created static file download URL"
        )

    def on_handle_resolve_static_file_path_request(
        self,
        request: ResolveStaticFilePathRequest,
    ) -> ResolveStaticFilePathResultSuccess | ResolveStaticFilePathResultFailure:
        """Handle the request to resolve a static file URL back to its original file path.

        Args:
            request: The request object containing the URL to resolve.

        Returns:
            A result object indicating success (with file path) or failure.
        """
        url = request.url

        # Only local storage driver supports URL resolution
        if not isinstance(self.storage_driver, LocalStorageDriver):
            msg = f"URL resolution not supported for storage backend: {self.storage_backend}"
            return ResolveStaticFilePathResultFailure(result_details=msg)

        # Get the base URL from the storage driver
        base_url = self.storage_driver.base_url

        # Strip query parameters (cache busting)
        url_without_query = url.split("?")[0]

        # Check if URL starts with base_url
        if not url_without_query.startswith(base_url):
            msg = f"URL does not match local static storage base URL: {url} (expected prefix: {base_url})"
            return ResolveStaticFilePathResultFailure(result_details=msg)

        # Strip base_url prefix to get the path part
        relative_url_path = url_without_query[len(base_url) :]

        # Remove leading slash if present
        relative_url_path = relative_url_path.removeprefix("/")

        # Check if it's an external file path
        if relative_url_path.startswith("external/"):
            # External file: reconstruct absolute path
            # Remove 'external/' prefix
            absolute_path_str = relative_url_path[len("external/") :]
            # Add back leading slash for absolute paths
            file_path = Path(f"/{absolute_path_str}")
        else:
            # Internal file: relative to workspace
            # The path is already workspace-relative
            file_path = self.config_manager.workspace_path / relative_url_path

        # Verify file exists
        if not file_path.exists():
            msg = f"Resolved file path does not exist: {file_path}"
            return ResolveStaticFilePathResultFailure(result_details=msg)

        if not file_path.is_file():
            msg = f"Resolved path is not a file: {file_path}"
            return ResolveStaticFilePathResultFailure(result_details=msg)

        # Return file:// URI
        file_uri = file_path.absolute().as_uri()
        return ResolveStaticFilePathResultSuccess(
            file_uri=file_uri, result_details=f"Successfully resolved URL to file URI: {file_uri}"
        )

    def on_app_initialization_complete(self, _payload: AppInitializationComplete) -> None:
        # Start static server in daemon thread if enabled
        if isinstance(self.storage_driver, LocalStorageDriver):
            threading.Thread(target=start_static_server, daemon=True, name="static-server").start()

    def save_static_file(self, data: bytes, file_name: str) -> str:
        """Saves a static file to the workspace directory.

        This is used to save files that are generated by the node, such as images or other artifacts.

        Args:
            data: The file data to save.
            file_name: The name of the file to save.

        Returns:
            The URL of the saved file.
        """
        resolved_directory = self._get_static_files_directory()
        file_path = (self.config_manager.workspace_path / Path(resolved_directory) / file_name).resolve()

        file_path.write_bytes(data)

        return file_path.as_uri()

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
