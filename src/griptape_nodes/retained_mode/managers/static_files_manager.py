import base64
import binascii
import logging
import threading
from pathlib import Path

import httpx
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

        match self.storage_backend:
            case StorageBackend.GTC:
                bucket_id = secrets_manager.get_secret("GT_CLOUD_BUCKET_ID", should_error_on_not_found=False)

                if not bucket_id:
                    logger.warning(
                        "GT_CLOUD_BUCKET_ID secret is not available, falling back to local storage. Run `gtn init` to set it up."
                    )
                    self.storage_driver = LocalStorageDriver(workspace_directory)
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
                self.storage_driver = LocalStorageDriver(workspace_directory)
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

    def on_handle_create_static_file_download_url_request(
        self,
        request: CreateStaticFileDownloadUrlRequest,
    ) -> CreateStaticFileDownloadUrlResultSuccess | CreateStaticFileDownloadUrlResultFailure:
        """Handle the request to create a presigned URL for downloading a static file.

        Args:
            request: The request object containing the file name.

        Returns:
            A result object indicating success or failure.
        """
        file_name = request.file_name

        resolved_directory = self._get_static_files_directory()
        full_file_path = Path(resolved_directory) / file_name

        try:
            url = self.storage_driver.create_signed_download_url(full_file_path)
        except Exception as e:
            msg = f"Failed to create presigned URL for file {file_name}: {e}"
            return CreateStaticFileDownloadUrlResultFailure(error=msg, result_details=msg)

        return CreateStaticFileDownloadUrlResultSuccess(
            url=url, result_details="Successfully created static file download URL"
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
        file_path = Path(resolved_directory) / file_name

        response = self.storage_driver.create_signed_upload_url(file_path)

        try:
            response = httpx.request(
                response["method"], response["url"], content=data, headers=response["headers"], timeout=60
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as e:
            msg = str(e.response.json())
            logger.error(msg)
            raise ValueError(msg) from e

        url = self.storage_driver.create_signed_download_url(file_path)

        return url

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
