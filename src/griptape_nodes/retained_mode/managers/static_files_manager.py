import base64
import binascii
import logging

from xdg_base_dirs import xdg_config_home

from griptape_nodes.drivers.storage import StorageBackend
from griptape_nodes.drivers.storage.griptape_cloud_storage_driver import GriptapeCloudStorageDriver
from griptape_nodes.drivers.storage.local_storage_driver import LocalStorageDriver
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
from griptape_nodes.retained_mode.utilities.storage import StorageUtility

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

        storage_backend = config_manager.get_config_value("storage_backend", default=StorageBackend.LOCAL)

        match storage_backend:
            case StorageBackend.GTC:
                bucket_id = secrets_manager.get_secret("GT_CLOUD_BUCKET_ID")

                if not bucket_id:
                    msg = "GT_CLOUD_BUCKET_ID secret is required for gtc storage backend"
                    logger.error(msg)
                    raise ValueError(msg)

                static_files_directory = config_manager.get_config_value(
                    "static_files_directory", default="staticfiles"
                )
                storage_driver = GriptapeCloudStorageDriver(
                    bucket_id=bucket_id,
                    api_key=secrets_manager.get_secret("GT_CLOUD_API_KEY"),
                    working_dir=static_files_directory,
                )
            case StorageBackend.LOCAL:
                storage_driver = LocalStorageDriver()
            case _:
                msg = f"Invalid storage backend: {storage_backend}"
                raise ValueError(msg)

        self.storage_utility = StorageUtility(storage_driver)

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

    def on_handle_create_static_file_request(
        self,
        request: CreateStaticFileRequest,
    ) -> CreateStaticFileResultSuccess | CreateStaticFileResultFailure:
        file_name = request.file_name

        try:
            content_bytes = base64.b64decode(request.content)
        except (binascii.Error, ValueError) as e:
            msg = f"Failed to decode base64 content for file {file_name}: {e}"
            logger.error(msg)
            return CreateStaticFileResultFailure(error=msg)

        try:
            url = self.storage_utility.save_static_file(content_bytes, file_name)
        except ValueError as e:
            msg = f"Failed to create static file for file {file_name}: {e}"
            logger.error(msg)
            return CreateStaticFileResultFailure(error=msg)

        return CreateStaticFileResultSuccess(url=url)

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
        try:
            response = self.storage_utility.storage_driver.create_signed_upload_url(file_name)
        except ValueError as e:
            msg = f"Failed to create presigned URL for file {file_name}: {e}"
            logger.error(msg)
            return CreateStaticFileUploadUrlResultFailure(error=msg)

        return CreateStaticFileUploadUrlResultSuccess(
            url=response["url"], headers=response["headers"], method=response["method"]
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
        try:
            url = self.storage_utility.storage_driver.create_signed_download_url(file_name)
        except ValueError as e:
            msg = f"Failed to create presigned URL for file {file_name}: {e}"
            logger.error(msg)
            return CreateStaticFileDownloadUrlResultFailure(error=msg)

        return CreateStaticFileDownloadUrlResultSuccess(url=url)

    def save_static_file(self, data: bytes, file_name: str) -> str:
        """Saves a static file to the workspace directory.

        This is used to save files that are generated by the node, such as images or other artifacts.

        Args:
            data: The file data to save.
            file_name: The name of the file to save.

        Returns:
            The URL of the saved file.
        """
        return self.storage_utility.save_static_file(data, file_name)

    def get_static_file(self, file_name: str) -> bytes:
        """Get a static file from storage.

        Args:
            file_name: The name of the file to get.

        Returns:
            The file content as bytes.
        """
        return self.storage_utility.get_static_file(file_name)

    def delete_static_file(self, file_name: str) -> None:
        """Delete a static file from storage.

        Args:
            file_name: The name of the file to delete.

        Raises:
            ValueError: If the file could not be deleted.
        """
        return self.storage_utility.delete_static_file(file_name)
