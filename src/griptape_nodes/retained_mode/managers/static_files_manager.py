import base64
import binascii
import logging
import threading
from pathlib import Path
from typing import Any

import httpx
from xdg_base_dirs import xdg_config_home

from griptape_nodes.drivers.storage import StorageBackend
from griptape_nodes.drivers.storage.griptape_cloud_storage_driver import GriptapeCloudStorageDriver
from griptape_nodes.drivers.storage.local_storage_driver import LocalStorageDriver
from griptape_nodes.node_library.workflow_registry import WorkflowRegistry
from griptape_nodes.retained_mode.events.app_events import AppInitializationComplete
from griptape_nodes.retained_mode.events.os_events import ExistingFilePolicy
from griptape_nodes.retained_mode.events.static_file_events import (
    CreateStaticFileDownloadUrlFromPathRequest,
    CreateStaticFileDownloadUrlRequest,
    CreateStaticFileDownloadUrlResultFailure,
    CreateStaticFileDownloadUrlResultSuccess,
    CreateStaticFileRequest,
    CreateStaticFileResultFailure,
    CreateStaticFileResultSuccess,
    CreateStaticFileUploadUrlRequest,
    CreateStaticFileUploadUrlResultFailure,
    CreateStaticFileUploadUrlResultSuccess,
    LoadAndSaveFromLocationRequest,
    LoadAndSaveFromLocationResultFailure,
    LoadAndSaveFromLocationResultSuccess,
    LoadBase64DataUriFromLocationRequest,
    LoadBase64DataUriFromLocationResultFailure,
    LoadBase64DataUriFromLocationResultSuccess,
    LoadBytesFromLocationRequest,
    LoadBytesFromLocationResultFailure,
    LoadBytesFromLocationResultSuccess,
)
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
from griptape_nodes.retained_mode.managers.config_manager import ConfigManager
from griptape_nodes.retained_mode.managers.event_manager import EventManager
from griptape_nodes.retained_mode.managers.image_metadata_injector import inject_workflow_metadata_if_image
from griptape_nodes.retained_mode.managers.secrets_manager import SecretsManager
from griptape_nodes.servers.static import STATIC_SERVER_URL, start_static_server
from griptape_nodes.utils.url_utils import is_url_or_path, uri_to_path

logger = logging.getLogger("griptape_nodes")

USER_CONFIG_PATH = xdg_config_home() / "griptape_nodes" / "griptape_nodes_config.json"


def _extract_artifact_value(artifact_or_value: Any) -> str | bytes | None:  # noqa: PLR0911
    """Extract value from artifact or return raw value.

    Internal helper to normalize different artifact representations.

    Args:
        artifact_or_value: Any artifact or value type

    Returns:
        Extracted string/bytes value, or None if extraction fails
    """
    if artifact_or_value is None:
        return None

    # Already a string or bytes?
    if isinstance(artifact_or_value, str):
        stripped = artifact_or_value.strip()
        return stripped if stripped else None
    if isinstance(artifact_or_value, bytes):
        return artifact_or_value

    # Dictionary format: {"type": "...", "value": "..."}
    if isinstance(artifact_or_value, dict):
        value = artifact_or_value.get("value")
        if value:
            return value
    # Artifact objects with .value attribute
    elif hasattr(artifact_or_value, "value"):
        value = artifact_or_value.value
        if isinstance(value, (str, bytes)) and value:
            return value
    # ImageArtifact with .base64 attribute
    elif hasattr(artifact_or_value, "base64"):
        b64 = artifact_or_value.base64
        if isinstance(b64, str) and b64:
            return b64

    return None


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
                CreateStaticFileDownloadUrlFromPathRequest,
                self.on_handle_create_static_file_download_url_from_path_request,
            )
            event_manager.assign_manager_to_request_type(
                LoadBytesFromLocationRequest, self.on_handle_load_bytes_from_location_request
            )
            event_manager.assign_manager_to_request_type(
                LoadBase64DataUriFromLocationRequest, self.on_handle_load_base64_data_uri_from_location_request
            )
            event_manager.assign_manager_to_request_type(
                LoadAndSaveFromLocationRequest, self.on_handle_load_and_save_from_location_request
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
            file_url=self.storage_driver.get_asset_url(Path(response["file_path"])),
            result_details="Successfully created static file upload URL",
        )

    def on_handle_create_static_file_download_url_request(
        self,
        request: CreateStaticFileDownloadUrlRequest,
    ) -> CreateStaticFileDownloadUrlResultSuccess | CreateStaticFileDownloadUrlResultFailure:
        """Handle the request to create a presigned URL for downloading a static file from the staticfiles directory.

        Args:
            request: The request object containing the file name.

        Returns:
            A result object indicating success or failure.
        """
        resolved_directory = self._get_static_files_directory()
        full_file_path = Path(resolved_directory) / request.file_name

        try:
            url = self.storage_driver.create_signed_download_url(full_file_path)
        except Exception as e:
            msg = f"Failed to create presigned URL for file {request.file_name}: {e}"
            return CreateStaticFileDownloadUrlResultFailure(error=msg, result_details=msg)

        return CreateStaticFileDownloadUrlResultSuccess(
            url=url,
            file_url=self.storage_driver.get_asset_url(full_file_path),
            result_details="Successfully created static file download URL",
        )

    def on_handle_create_static_file_download_url_from_path_request(
        self,
        request: CreateStaticFileDownloadUrlFromPathRequest,
    ) -> CreateStaticFileDownloadUrlResultSuccess | CreateStaticFileDownloadUrlResultFailure:
        """Handle request to create download URL from arbitrary file path.

        Args:
            request: Request containing file_path parameter.

        Returns:
            Result with download URL or failure message.
        """
        full_file_path = Path(uri_to_path(request.file_path))

        try:
            # TODO: use the driver appropriate for the file format. i.e. If local path use LocalStorageDriver, if GTC path use GriptapeCloudStorageDriver https://github.com/griptape-ai/griptape-nodes/issues/3739
            url = self.storage_driver.create_signed_download_url(full_file_path)
        except Exception as e:
            msg = f"Failed to create presigned URL for file {request.file_path}: {e}"
            return CreateStaticFileDownloadUrlResultFailure(error=msg, result_details=msg)

        return CreateStaticFileDownloadUrlResultSuccess(
            url=url,
            file_url=self.storage_driver.get_asset_url(full_file_path),
            result_details="Successfully created static file download URL",
        )

    def on_app_initialization_complete(self, _payload: AppInitializationComplete) -> None:
        # Start static server in daemon thread if enabled
        if isinstance(self.storage_driver, LocalStorageDriver):
            threading.Thread(target=start_static_server, daemon=True, name="static-server").start()

    def save_static_file(
        self,
        data: bytes,
        file_name: str,
        existing_file_policy: ExistingFilePolicy = ExistingFilePolicy.OVERWRITE,
        *,
        use_direct_save: bool = True,
        skip_metadata_injection: bool = False,
    ) -> str:
        """Saves a static file to the workspace directory.

        This is used to save files that are generated by the node, such as images or other artifacts.

        Args:
            data: The file data to save.
            file_name: The name of the file to save.
            existing_file_policy: How to handle existing files. Defaults to OVERWRITE for backward compatibility.
                - OVERWRITE: Replace existing file content (default)
                - CREATE_NEW: Auto-generate unique filename (e.g., file_1.txt, file_2.txt)
                - FAIL: Raise FileExistsError if file exists
            use_direct_save: If True, use direct storage driver save (returns stable paths).
                If False, use presigned URL upload (returns ephemeral signed URLs).
                Defaults to True (direct save is now the standard behavior).
            skip_metadata_injection: If True, skip automatic workflow metadata injection.
                Defaults to False. Used by nodes that handle metadata explicitly (e.g., WriteImageMetadataNode).

        Returns:
            The path/URL of the saved file. With use_direct_save=True (default), returns stable storage path.
            With use_direct_save=False, returns signed download URL with cache-busting.
            Note: the actual filename may differ from the requested file_name when using CREATE_NEW policy.

        Raises:
            FileExistsError: When existing_file_policy is FAIL and file already exists.
            RuntimeError: If file write fails (direct save mode).
            ValueError: If file upload fails (presigned URL mode).
        """
        resolved_directory = self._get_static_files_directory()
        file_path = Path(resolved_directory) / file_name

        # Inject workflow metadata if enabled
        if (
            self.config_manager.get_config_value("auto_inject_workflow_metadata", default=True)
            and not skip_metadata_injection
        ):
            try:
                data = inject_workflow_metadata_if_image(data, file_name)
            except Exception as e:
                logger.warning("Failed to inject workflow metadata into %s: %s", file_name, e)

        # NEW BEHAVIOR: Direct save via storage driver
        if use_direct_save:
            try:
                saved_path = self.storage_driver.save_file(file_path, data, existing_file_policy)
            except FileExistsError:
                raise
            except Exception as e:
                msg = f"Failed to save static file {file_name}: {e}"
                logger.error(msg)
                raise RuntimeError(msg) from e
            return saved_path

        # OLD BEHAVIOR: Presigned URL upload
        response = self.storage_driver.create_signed_upload_url(file_path, existing_file_policy)
        resolved_file_path = Path(response["file_path"])

        try:
            upload_response = httpx.request(
                response["method"], response["url"], content=data, headers=response["headers"], timeout=60
            )
            upload_response.raise_for_status()
        except httpx.HTTPStatusError as e:
            msg = str(e.response.json()) if hasattr(e, "response") else str(e)
            logger.error(msg)
            raise ValueError(msg) from e

        url = self.storage_driver.create_signed_download_url(resolved_file_path)
        return url

    def _get_static_files_directory(self) -> str:
        """Get the appropriate static files directory based on the current workflow context.

        Returns:
            The directory path to use for static files, relative to the workspace directory.
            If a workflow is active, returns the staticfiles subdirectory within the
            workflow's directory relative to workspace. Otherwise, returns the staticfiles
            subdirectory relative to workspace.
        """
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

    @staticmethod
    def _decode_data_uri(data_uri: str, context_name: str) -> bytes:
        """Decode base64 data from data URI."""
        # Extract base64 portion after comma
        if "," in data_uri:
            _, b64_data = data_uri.split(",", 1)
        else:
            b64_data = data_uri.split(":", 1)[1]

        try:
            return base64.b64decode(b64_data)
        except binascii.Error as e:
            msg = f"{context_name}: Invalid base64 data in data URI: {e}"
            raise ValueError(msg) from e

    async def on_handle_load_bytes_from_location_request(  # noqa: PLR0911
        self,
        request: LoadBytesFromLocationRequest,
    ) -> LoadBytesFromLocationResultSuccess | LoadBytesFromLocationResultFailure:
        """Handle request to load bytes from location string.

        Args:
            request: Request containing location and timeout

        Returns:
            Success result with content bytes or failure result with error details
        """
        # Guard: Validate location is not empty
        if not request.location:
            return LoadBytesFromLocationResultFailure(result_details="Cannot load from empty location")

        # Guard: Validate location is a string
        if not isinstance(request.location, str):
            return LoadBytesFromLocationResultFailure(
                result_details=f"Location must be a string, got {type(request.location).__name__}"
            )

        location = request.location.strip()

        # Guard: Validate stripped location is not empty
        if not location:
            return LoadBytesFromLocationResultFailure(result_details="Cannot load from whitespace-only location")

        # Check for data URI: "data:image/png;base64,..."
        if location.startswith("data:"):
            try:
                content = StaticFilesManager._decode_data_uri(location, "location")
                return LoadBytesFromLocationResultSuccess(content=content, result_details="Decoded data URI")
            except ValueError as e:
                return LoadBytesFromLocationResultFailure(result_details=str(e))

        # Check if it's a URL or path
        if is_url_or_path(location):
            try:
                content = await StaticFilesManager._download_from_url(location, request.timeout, "location")
                return LoadBytesFromLocationResultSuccess(
                    content=content, result_details=f"Downloaded from {location[:100]}"
                )
            except httpx.TimeoutException as e:
                return LoadBytesFromLocationResultFailure(result_details=str(e))
            except httpx.HTTPError as e:
                return LoadBytesFromLocationResultFailure(result_details=str(e))

        # Assume it's raw base64 without prefix
        try:
            content = base64.b64decode(location)
            return LoadBytesFromLocationResultSuccess(content=content, result_details="Decoded base64")
        except binascii.Error:
            return LoadBytesFromLocationResultFailure(
                result_details=f"Location is not a URL, path, or valid base64: {location[:100]}..."
            )

    async def on_handle_load_base64_data_uri_from_location_request(  # noqa: PLR0911
        self,
        request: LoadBase64DataUriFromLocationRequest,
    ) -> LoadBase64DataUriFromLocationResultSuccess | LoadBase64DataUriFromLocationResultFailure:
        """Handle request to load from location as base64 data URI.

        Args:
            request: Request containing artifact_or_url, timeout, and media_type

        Returns:
            Success result with data URI string or failure result with error details
        """
        # Guard: Check for None/empty
        if request.artifact_or_url is None:
            return LoadBase64DataUriFromLocationResultFailure(result_details="Cannot load None artifact")

        # Extract value
        value = _extract_artifact_value(request.artifact_or_url)
        if value is None:
            return LoadBase64DataUriFromLocationResultFailure(result_details="Cannot extract value from artifact")

        # If bytes, encode directly
        if isinstance(value, bytes):
            b64 = base64.b64encode(value).decode("utf-8")
            return LoadBase64DataUriFromLocationResultSuccess(
                data_uri=f"data:{request.media_type};base64,{b64}",
                result_details="Encoded bytes to data URI",
            )

        # Must be string
        if not isinstance(value, str):
            return LoadBase64DataUriFromLocationResultFailure(
                result_details=f"Unexpected value type: {type(value).__name__}"
            )

        # Already a data URI? Return as-is
        if value.startswith("data:"):
            return LoadBase64DataUriFromLocationResultSuccess(data_uri=value, result_details="Already a data URI")

        # URL or path? Download then encode
        if is_url_or_path(value):
            # Use new LoadBytesFromLocationRequest
            load_request = LoadBytesFromLocationRequest(location=value, timeout=request.timeout)
            load_result = await self.on_handle_load_bytes_from_location_request(load_request)

            if isinstance(load_result, LoadBytesFromLocationResultSuccess):
                b64 = base64.b64encode(load_result.content).decode("utf-8")
                return LoadBase64DataUriFromLocationResultSuccess(
                    data_uri=f"data:{request.media_type};base64,{b64}",
                    result_details="Downloaded and encoded to data URI",
                )

            return LoadBase64DataUriFromLocationResultFailure(result_details=load_result.result_details)

        # Assume raw base64 - just add data URI prefix
        return LoadBase64DataUriFromLocationResultSuccess(
            data_uri=f"data:{request.media_type};base64,{value}",
            result_details="Added data URI prefix to base64",
        )

    async def on_handle_load_and_save_from_location_request(
        self,
        request: LoadAndSaveFromLocationRequest,
    ) -> LoadAndSaveFromLocationResultSuccess | LoadAndSaveFromLocationResultFailure:
        """Handle request to load bytes from location and save to storage.

        Args:
            request: Request containing location, filename, timeout, artifact_type, and existing_file_policy

        Returns:
            Success result with artifact/path or failure result with error details
        """
        # Download bytes
        load_request = LoadBytesFromLocationRequest(location=request.location, timeout=request.timeout)
        load_result = await self.on_handle_load_bytes_from_location_request(load_request)

        if isinstance(load_result, LoadBytesFromLocationResultSuccess):
            # Type narrowing: load_result is LoadBytesFromLocationResultSuccess
            # Save to static storage with use_direct_save=True
            try:
                saved_path = self.save_static_file(
                    load_result.content,
                    request.filename,
                    existing_file_policy=request.existing_file_policy,
                    use_direct_save=True,
                )
            except Exception as e:
                return LoadAndSaveFromLocationResultFailure(result_details=f"Failed to save {request.filename}: {e}")

            # Success: return artifact or raw path
            if request.artifact_type:
                artifact = request.artifact_type(value=saved_path, name=request.filename)
                return LoadAndSaveFromLocationResultSuccess(
                    artifact=artifact, result_details=f"Downloaded and saved as {request.filename}"
                )

            return LoadAndSaveFromLocationResultSuccess(
                artifact=saved_path, result_details=f"Downloaded and saved as {request.filename}"
            )

        return LoadAndSaveFromLocationResultFailure(
            result_details=f"Failed to load from {request.location}: {load_result.result_details}"
        )

    @staticmethod
    async def _download_from_url(url: str, timeout: float, context_name: str) -> bytes:  # noqa: ASYNC109
        """Download content from URL using httpx."""
        try:
            async with httpx.AsyncClient() as client:
                logger.debug("%s: Downloading from %s...", context_name, url[:100])
                resp = await client.get(url, timeout=timeout)
                resp.raise_for_status()
                return resp.content
        except httpx.TimeoutException as e:
            msg = f"{context_name}: Download timed out after {timeout}s: {url}"
            raise httpx.TimeoutException(msg) from e
        except httpx.HTTPError as e:
            msg = f"{context_name}: Download failed: {e}"
            raise httpx.HTTPError(msg) from e
