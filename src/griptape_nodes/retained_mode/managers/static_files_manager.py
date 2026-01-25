import base64
import binascii
import logging
import threading
from pathlib import Path

import httpx
from xdg_base_dirs import xdg_config_home

# Parse and resolve macro
from griptape_nodes.common.macro_parser import ParsedMacro
from griptape_nodes.common.project_templates.situation import SituationFilePolicy
from griptape_nodes.drivers.storage import StorageBackend
from griptape_nodes.drivers.storage.griptape_cloud_storage_driver import GriptapeCloudStorageDriver
from griptape_nodes.drivers.storage.local_storage_driver import LocalStorageDriver
from griptape_nodes.retained_mode.events.app_events import AppInitializationComplete
from griptape_nodes.retained_mode.events.os_events import ExistingFilePolicy
from griptape_nodes.retained_mode.events.project_events import (
    GetPathForMacroRequest,
    GetPathForMacroResultSuccess,
    GetSituationRequest,
    GetSituationResultSuccess,
    MacroPath,
)
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

# Mapping from SituationFilePolicy to ExistingFilePolicy
SITUATION_TO_FILE_POLICY_MAPPING = {
    SituationFilePolicy.CREATE_NEW: ExistingFilePolicy.CREATE_NEW,
    SituationFilePolicy.OVERWRITE: ExistingFilePolicy.OVERWRITE,
    SituationFilePolicy.FAIL: ExistingFilePolicy.FAIL,
}


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

    def save_static_file(
        self,
        data: bytes,
        file_name: str,
        situation_name: str = "save_file",
        variables: dict[str, str | int] | None = None,
    ) -> str:
        """Saves a static file to the workspace directory using project situation templates.

        This is used to save files that are generated by the node, such as images or other artifacts.

        Args:
            data: The file data to save.
            file_name: Filename to save (e.g., "output.png", "image.jpg").
                Variables are automatically extracted (file_name_base, file_extension).
            situation_name: Situation template name to use for path resolution and policy.
                Defaults to "save_file". Other examples: "save_node_output", "save_preview", "copy_external_file"
            variables: Optional additional variables for macro resolution.
                These are merged with auto-extracted variables (file_name_base, file_extension).
                User-provided variables override auto-extracted ones.

        Returns:
            The URL of the saved file. Note: the actual filename may differ from the requested
            file_name when the situation uses CREATE_NEW policy.

        Raises:
            ValueError: When:
                - No current project is set
                - situation_name not found in current project
                - Situation uses PROMPT policy (must be resolved by UI first)
                - Macro resolution fails (missing variables, conflicts, etc.)
                - Path is empty after resolution
            FileExistsError: When situation policy is FAIL and file already exists
            TypeError: When unexpected result type is returned from macro resolution

        Examples:
            # Default - uses 'save_file' situation
            url = save_static_file(data, "output.png")

            # Use specific situation for organized output
            url = save_static_file(
                data,
                "result.png",
                situation_name="save_node_output",
                variables={"node_name": "ImageGen"}
            )
            # Resolves via situation macro: {outputs}/{node_name?:_}{file_name_base}{_index?:03}.{file_extension}
            # Result: /workspace/outputs/ImageGen_result.png
        """
        # Resolve path and policy via situation
        file_path, effective_policy = self._resolve_path_via_situation(
            situation_name=situation_name,
            file_name=file_name,
            variables=variables,
        )

        # Convert absolute paths inside workspace to workspace-relative for storage driver
        # The storage driver expects workspace-relative paths for files within the workspace
        if file_path.is_absolute() and file_path.is_relative_to(self.config_manager.workspace_path):
            file_path = file_path.relative_to(self.config_manager.workspace_path)

        # Pass the effective_policy to the storage driver
        response = self.storage_driver.create_signed_upload_url(file_path, effective_policy)

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
        """Get the static files directory.

        Returns:
            The directory path to use for static files, relative to the workspace directory.
        """
        return self.config_manager.get_config_value("static_files_directory", default="staticfiles")

    def _resolve_macro_path(self, macro_path: MacroPath) -> Path:
        """Resolve a MacroPath to an absolute filesystem path.

        Args:
            macro_path: MacroPath with parsed macro template and variables

        Returns:
            Absolute path to save file (from GetPathForMacroRequest result)

        Raises:
            ValueError: If macro resolution fails (missing variables, conflicts, etc.) or path is empty
            TypeError: If unexpected result type is returned from macro resolution
        """
        from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

        # Create request to ProjectManager
        request = GetPathForMacroRequest(parsed_macro=macro_path.parsed_macro, variables=macro_path.variables)

        # Send request via GriptapeNodes singleton
        result = GriptapeNodes.handle_request(request)

        if result.failed():
            error_msg = f"Failed to resolve macro path: {result.result_details}"
            logger.error(error_msg)
            raise ValueError(error_msg)

        if not isinstance(result, GetPathForMacroResultSuccess):
            error_msg = f"Unexpected result type from macro resolution: {type(result).__name__}"
            logger.error(error_msg)
            raise TypeError(error_msg)

        if not result.absolute_path:
            error_msg = "Macro resolved to empty path"
            logger.error(error_msg)
            raise ValueError(error_msg)

        # Success path at end
        return result.absolute_path

    def _extract_file_variables(self, file_name: str) -> dict[str, str]:
        """Extract standard file variables from filename.

        Args:
            file_name: Filename to parse (e.g., "output.png")

        Returns:
            Dict with file_name_base and file_extension

        Examples:
            "output.png" → {file_name_base: "output", file_extension: "png"}
            "frame.jpg" → {file_name_base: "frame", file_extension: "jpg"}
            "my.file.name.png" → {file_name_base: "my.file.name", file_extension: "png"}
        """
        path = Path(file_name)

        file_extension = path.suffix.lstrip(".")
        file_name_base = path.stem

        return {
            "file_name_base": file_name_base,
            "file_extension": file_extension,
        }

    def _map_situation_policy_to_file_policy(self, situation_policy: SituationFilePolicy) -> ExistingFilePolicy:
        """Map SituationFilePolicy to ExistingFilePolicy.

        Args:
            situation_policy: The policy from situation template

        Returns:
            Corresponding ExistingFilePolicy

        Raises:
            ValueError: If policy is PROMPT (must be resolved by UI first) or unknown policy
        """
        if situation_policy == SituationFilePolicy.PROMPT:
            error_msg = "Cannot map PROMPT policy - must be resolved by UI before save"
            raise ValueError(error_msg)

        if situation_policy not in SITUATION_TO_FILE_POLICY_MAPPING:
            error_msg = f"Unknown situation policy: {situation_policy}"
            raise ValueError(error_msg)

        return SITUATION_TO_FILE_POLICY_MAPPING[situation_policy]

    def _resolve_path_via_situation(
        self,
        situation_name: str,
        file_name: str,
        variables: dict[str, str | int] | None,
    ) -> tuple[Path, ExistingFilePolicy]:
        """Resolve file path and policy using a situation template.

        Args:
            situation_name: Name of situation to use
            file_name: Filename to parse for variables
            variables: Optional additional variables

        Returns:
            Tuple of (resolved_path, effective_policy)

        Raises:
            ValueError: If situation not found, path resolution fails, or PROMPT policy encountered
            TypeError: If unexpected result type returned
        """
        from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

        # Get situation template
        situation_request = GetSituationRequest(situation_name=situation_name)
        situation_result = GriptapeNodes.handle_request(situation_request)

        if situation_result.failed():
            error_msg = f"Failed to get situation '{situation_name}': {situation_result.result_details}"
            logger.error(error_msg)
            raise ValueError(error_msg)

        if not isinstance(situation_result, GetSituationResultSuccess):
            error_msg = f"Unexpected result type from GetSituationRequest: {type(situation_result).__name__}"
            logger.error(error_msg)
            raise TypeError(error_msg)

        situation = situation_result.situation

        # Extract file variables
        file_vars = self._extract_file_variables(file_name)

        # Merge variables (user vars override file vars)
        merged_vars = {**file_vars, **(variables or {})}

        parsed_macro = ParsedMacro(situation.macro)
        macro_path = MacroPath(parsed_macro=parsed_macro, variables=merged_vars)
        resolved_path = self._resolve_macro_path(macro_path)

        # Map policy
        effective_policy = self._map_situation_policy_to_file_policy(situation.policy.on_collision)

        # Success path at end
        return resolved_path, effective_policy
