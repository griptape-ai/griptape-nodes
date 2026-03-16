import base64
import binascii
import logging
import threading
from pathlib import Path
from typing import NamedTuple

from xdg_base_dirs import xdg_config_home

from griptape_nodes.common.macro_parser import MacroSyntaxError, ParsedMacro
from griptape_nodes.common.project_templates.situation import SituationFilePolicy
from griptape_nodes.drivers.storage import StorageBackend
from griptape_nodes.drivers.storage.griptape_cloud_storage_driver import GriptapeCloudStorageDriver
from griptape_nodes.drivers.storage.local_storage_driver import LocalStorageDriver
from griptape_nodes.files.path_utils import FilenameParts
from griptape_nodes.retained_mode.events.app_events import AppInitializationComplete
from griptape_nodes.retained_mode.events.os_events import ExistingFilePolicy
from griptape_nodes.retained_mode.events.project_events import (
    GetPathForMacroRequest,
    GetPathForMacroResultSuccess,
    GetSituationRequest,
    GetSituationResultSuccess,
)
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
)
from griptape_nodes.retained_mode.file_metadata.sidecar_metadata import SidecarContent, build_sidecar_metadata
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
from griptape_nodes.retained_mode.managers.config_manager import ConfigManager
from griptape_nodes.retained_mode.managers.event_manager import EventManager
from griptape_nodes.retained_mode.managers.secrets_manager import SecretsManager
from griptape_nodes.servers.static import STATIC_SERVER_URL, start_static_server
from griptape_nodes.utils.url_utils import uri_to_path

logger = logging.getLogger("griptape_nodes")

SAVE_STATIC_FILE_SITUATION = "save_static_file"

USER_CONFIG_PATH = xdg_config_home() / "griptape_nodes" / "griptape_nodes_config.json"


class ResolvedStaticFilePath(NamedTuple):
    """Resolved static file path and its write policy.

    Attributes:
        path: Absolute path where the static file should be written.
        policy: How to handle an existing file at that path.
        file_metadata: Situation context to pass to WriteFileRequest for sidecar generation.
    """

    path: Path
    policy: ExistingFilePolicy
    file_metadata: SidecarContent | None = None


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
        self.secrets_manager = secrets_manager

        self.storage_backend = config_manager.get_config_value("storage_backend", default=StorageBackend.LOCAL)
        workspace_directory = config_manager.workspace_path

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

        resolved = self._resolve_static_file_path(file_name)
        if resolved is None:
            msg = f"Attempted to create upload URL for '{file_name}'. Failed because the project template is missing the '{SAVE_STATIC_FILE_SITUATION}' situation."
            return CreateStaticFileUploadUrlResultFailure(error=msg, result_details=msg)

        try:
            response = self.storage_driver.create_signed_upload_url(resolved.path, file_metadata=resolved.file_metadata)
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
        resolved = self._resolve_static_file_path(request.file_name)
        if resolved is None:
            msg = f"Attempted to create download URL for '{request.file_name}'. Failed because the project template is missing the '{SAVE_STATIC_FILE_SITUATION}' situation."
            return CreateStaticFileDownloadUrlResultFailure(error=msg, result_details=msg)

        try:
            url = self.storage_driver.create_signed_download_url(resolved.path)
        except Exception as e:
            msg = f"Failed to create presigned URL for file {request.file_name}: {e}"
            return CreateStaticFileDownloadUrlResultFailure(error=msg, result_details=msg)

        return CreateStaticFileDownloadUrlResultSuccess(
            url=url,
            file_url=self.storage_driver.get_asset_url(resolved.path),
            result_details="Successfully created static file download URL",
        )

    def _create_cloud_storage_driver(self, bucket_id: str) -> GriptapeCloudStorageDriver | None:
        """Create a GriptapeCloudStorageDriver instance for the given bucket_id.

        Args:
            bucket_id: The bucket ID to use

        Returns:
            GriptapeCloudStorageDriver instance if API key is available, None otherwise
        """
        api_key = self.secrets_manager.get_secret("GT_CLOUD_API_KEY", should_error_on_not_found=False)

        if not api_key:
            return None

        workspace_directory = self.config_manager.workspace_path
        static_files_directory = self.config_manager.get_config_value("static_files_directory", default="staticfiles")

        return GriptapeCloudStorageDriver(
            workspace_directory,
            bucket_id=bucket_id,
            api_key=api_key,
            static_files_directory=static_files_directory,
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
        file_path = request.file_path

        # Resolve macro paths (e.g. "{outputs}/file.png") before further processing
        try:
            parsed = ParsedMacro(file_path)
        except MacroSyntaxError as e:
            msg = f"Attempted to create download URL. Failed with file_path='{file_path}' because the path has invalid macro syntax: {e}"
            logger.warning(msg)
            return CreateStaticFileDownloadUrlResultFailure(error=msg, result_details=msg)

        if parsed.get_variables():
            resolve_result = GriptapeNodes.handle_request(
                GetPathForMacroRequest(parsed_macro=parsed, variables=request.macro_variables)
            )
            if not isinstance(resolve_result, GetPathForMacroResultSuccess):
                msg = f"Attempted to create download URL. Failed with file_path='{file_path}' because macro resolution failed: {resolve_result.result_details}"
                return CreateStaticFileDownloadUrlResultFailure(error=msg, result_details=msg)
            file_path = str(resolve_result.absolute_path)

        # Detect if this is a Griptape Cloud URL and extract bucket_id
        bucket_id = GriptapeCloudStorageDriver.extract_bucket_id_from_url(file_path)

        if bucket_id is not None:
            driver = self._create_cloud_storage_driver(bucket_id)
            if driver is None:
                msg = f"Attempted to create download URL for Griptape Cloud file. Failed with file_path='{file_path}' because GT_CLOUD_API_KEY secret is not available."
                return CreateStaticFileDownloadUrlResultFailure(error=msg, result_details=msg)

            # For cloud URLs, pass the full URL to the driver
            file_path_for_driver = Path(file_path)
        else:
            driver = self.storage_driver
            # For local paths, convert URI to path
            file_path_for_driver = Path(uri_to_path(file_path))

        try:
            url = driver.create_signed_download_url(file_path_for_driver)
        except Exception as e:
            msg = f"Failed to create presigned URL for file {file_path}: {e}"
            return CreateStaticFileDownloadUrlResultFailure(error=msg, result_details=msg)

        return CreateStaticFileDownloadUrlResultSuccess(
            url=url,
            file_url=driver.get_asset_url(file_path_for_driver),
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
        existing_file_policy: ExistingFilePolicy | None = None,
        *,
        skip_metadata_injection: bool = False,
    ) -> str:
        """Saves a static file to the workspace directory.

        This is used to save files that are generated by the node, such as images or other artifacts.

        Args:
            data: The file data to save.
            file_name: The name of the file to save.
            existing_file_policy: How to handle existing files. When None, uses the policy from the
                save_static_file situation.
                - OVERWRITE: Replace existing file content
                - CREATE_NEW: Auto-generate unique filename (e.g., file_1.txt, file_2.txt)
                - FAIL: Raise FileExistsError if file exists
            skip_metadata_injection: If True, skip automatic workflow metadata injection.

        Returns:
            The URL of the saved file for UI display (with cache-busting). Note: the actual filename
            may differ from the requested file_name when using CREATE_NEW policy.

        Raises:
            FileExistsError: When existing_file_policy is FAIL and file already exists.
            RuntimeError: If the project template is missing the save_static_file situation, or if the file write fails.
        """
        resolved = self._resolve_static_file_path(file_name)
        if resolved is None:
            msg = f"Attempted to save static file '{file_name}'. Failed because the project template is missing the '{SAVE_STATIC_FILE_SITUATION}' situation."
            raise RuntimeError(msg)

        file_path = resolved.path

        if existing_file_policy is None:
            effective_policy = resolved.policy
        else:
            effective_policy = existing_file_policy

        try:
            saved_path = self.storage_driver.save_file(
                file_path,
                data,
                effective_policy,
                skip_metadata_injection=skip_metadata_injection,
                file_metadata=resolved.file_metadata,
            )
        except FileExistsError:
            raise
        except Exception as e:
            msg = f"Failed to save static file {file_name}: {e}"
            logger.error(msg)
            raise RuntimeError(msg) from e
        return self.storage_driver.create_signed_download_url(Path(saved_path))

    def _resolve_static_file_path(self, file_name: str) -> ResolvedStaticFilePath | None:
        """Resolve the file path for a static file using the save_static_file situation.

        Args:
            file_name: The name of the file (e.g., "output.png").

        Returns:
            ResolvedStaticFilePath if situation resolution succeeds, or None on failure.
        """
        situation_result = GriptapeNodes.handle_request(GetSituationRequest(situation_name=SAVE_STATIC_FILE_SITUATION))
        if not isinstance(situation_result, GetSituationResultSuccess):
            logger.warning(
                "Project template does not include '%s' situation; static files will save to the default directory. "
                "Projects using StaticFilesManager.save_static_file require this situation in their project template.",
                SAVE_STATIC_FILE_SITUATION,
            )
            return None

        situation = situation_result.situation

        parts = FilenameParts.from_filename(file_name)

        try:
            parsed_macro = ParsedMacro(situation.macro)
        except MacroSyntaxError as e:
            logger.warning("Failed to parse %s situation macro: %s", SAVE_STATIC_FILE_SITUATION, e)
            return None

        macro_result = GriptapeNodes.handle_request(
            GetPathForMacroRequest(
                parsed_macro=parsed_macro,
                variables={"file_name_base": parts.stem, "file_extension": parts.extension},
            )
        )
        if not isinstance(macro_result, GetPathForMacroResultSuccess):
            logger.warning(
                "Failed to resolve %s situation path: %s", SAVE_STATIC_FILE_SITUATION, macro_result.result_details
            )
            return None

        workspace_dir = GriptapeNodes.ConfigManager().workspace_path
        try:
            # Resolve both sides to ensure drive letters match on Windows (drive-relative vs absolute paths).
            workspace_relative_path = macro_result.absolute_path.resolve().relative_to(workspace_dir.resolve())
        except ValueError:
            static_files_dir = self.config_manager.get_config_value("static_files_directory", default="staticfiles")
            workspace_relative_path = Path(static_files_dir) / file_name
            logger.warning(
                "Resolved %s situation path %s is outside workspace %s. "
                "Falling back to workspace staticfiles directory: %s",
                SAVE_STATIC_FILE_SITUATION,
                macro_result.absolute_path,
                workspace_dir,
                workspace_relative_path,
            )

        policy = self._map_situation_policy(situation.policy.on_collision)
        variables = {"file_name_base": parts.stem, "file_extension": parts.extension}
        metadata = build_sidecar_metadata(SAVE_STATIC_FILE_SITUATION, situation, variables)
        return ResolvedStaticFilePath(path=workspace_relative_path, policy=policy, file_metadata=metadata)

    @staticmethod
    def _map_situation_policy(situation_policy: SituationFilePolicy) -> ExistingFilePolicy:
        """Map a SituationFilePolicy to an ExistingFilePolicy.

        Args:
            situation_policy: The situation policy to map.

        Returns:
            The corresponding ExistingFilePolicy.
        """
        match situation_policy:
            case SituationFilePolicy.OVERWRITE:
                return ExistingFilePolicy.OVERWRITE
            case SituationFilePolicy.FAIL:
                return ExistingFilePolicy.FAIL
            case SituationFilePolicy.CREATE_NEW | SituationFilePolicy.PROMPT:
                return ExistingFilePolicy.CREATE_NEW
