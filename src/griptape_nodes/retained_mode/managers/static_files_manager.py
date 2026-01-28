import base64
import binascii
import logging
import threading
from pathlib import Path

import httpx
from PIL import Image
from xdg_base_dirs import xdg_config_home

from griptape_nodes.common.macro_parser import MacroSyntaxError, ParsedMacro
from griptape_nodes.drivers.storage import StorageBackend
from griptape_nodes.drivers.storage.griptape_cloud_storage_driver import GriptapeCloudStorageDriver
from griptape_nodes.drivers.storage.local_storage_driver import LocalStorageDriver
from griptape_nodes.node_library.workflow_registry import WorkflowRegistry
from griptape_nodes.retained_mode.events.app_events import AppInitializationComplete
from griptape_nodes.retained_mode.events.os_events import ExistingFilePolicy
from griptape_nodes.retained_mode.events.project_events import (
    GetPathForMacroRequest,
    GetPathForMacroResultSuccess,
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
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
from griptape_nodes.retained_mode.managers.config_manager import ConfigManager
from griptape_nodes.retained_mode.managers.event_manager import EventManager
from griptape_nodes.retained_mode.managers.secrets_manager import SecretsManager
from griptape_nodes.servers.static import STATIC_SERVER_URL, start_static_server
from griptape_nodes.utils.url_utils import uri_to_path

logger = logging.getLogger("griptape_nodes")

USER_CONFIG_PATH = xdg_config_home() / "griptape_nodes" / "griptape_nodes_config.json"

# Supported image extensions for preview generation
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".tiff", ".tif"}


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
            event_manager.add_listener_to_app_event(
                AppInitializationComplete,
                self.on_app_initialization_complete,
            )
            # TODO: Listen for shutdown event (https://github.com/griptape-ai/griptape-nodes/issues/2149) to stop static server

    def _is_preview_up_to_date(self, original_path: Path, preview_path: Path) -> bool:
        """Check if cached preview exists and is newer than the original file.

        Args:
            original_path: Path to the original image file
            preview_path: Path to the cached preview

        Returns:
            True if preview exists and is up-to-date, False otherwise
        """
        if not preview_path.exists():
            return False

        try:
            original_mtime = original_path.stat().st_mtime
            preview_mtime = preview_path.stat().st_mtime
        except OSError as e:
            logger.warning("Failed to check preview modification time: %s", e)
            return False
        else:
            return preview_mtime >= original_mtime

    def _generate_preview_if_needed(self, file_path: Path) -> Path:
        """Generate preview for an image file if needed.

        Returns path to preview file if generated/cached, or original file path if:
        - File is not an image
        - Preview generation fails

        Args:
            file_path: Path to the original file

        Returns:
            Path to preview file or original file
        """
        # Check if file is an image
        file_extension = file_path.suffix.lower()
        if file_extension not in IMAGE_EXTENSIONS:
            return file_path

        # Determine preview cache path using workflow-aware directory structure
        workspace_path = self.config_manager.workspace_path

        # Get the base directory for the original file relative to workspace
        try:
            relative_file_path = file_path.relative_to(workspace_path)
        except ValueError:
            # File is outside workspace, use absolute path structure
            logger.warning("File %s is outside workspace, using absolute path for preview", file_path)
            # For external files, use a flattened structure in workspace/thumbnails
            preview_cache_dir = workspace_path / "thumbnails" / "external"
            preview_filename = f"{file_path.stem}_{hash(str(file_path))}.webp"
            preview_path = preview_cache_dir / preview_filename
        else:
            # File is inside workspace, use workflow-aware structure
            # Replace staticfiles with thumbnails in the path
            relative_str = str(relative_file_path)
            if "staticfiles" in relative_str:
                preview_relative_str = relative_str.replace("staticfiles", "thumbnails", 1)
            else:
                # File not in staticfiles directory, use parallel thumbnails structure
                preview_relative_str = str(Path("thumbnails") / relative_file_path)

            preview_relative_path = Path(preview_relative_str).with_suffix(".webp")
            preview_path = workspace_path / preview_relative_path

        # Check if cached preview is up-to-date
        if self._is_preview_up_to_date(file_path, preview_path):
            return preview_path

        # Generate preview
        try:
            with Image.open(file_path) as original_img:
                # Convert RGBA to RGB for formats that don't support transparency
                if original_img.mode in ("RGBA", "LA", "P"):
                    # Create white background
                    background = Image.new("RGB", original_img.size, (255, 255, 255))
                    img_to_paste = original_img.convert("RGBA") if original_img.mode == "P" else original_img
                    background.paste(
                        img_to_paste, mask=img_to_paste.split()[-1] if img_to_paste.mode in ("RGBA", "LA") else None
                    )
                    processed_img = background
                elif original_img.mode != "RGB":
                    processed_img = original_img.convert("RGB")
                else:
                    processed_img = original_img.copy()

                # Resize while maintaining aspect ratio
                processed_img.thumbnail((512, 512), Image.Resampling.LANCZOS)

                # Create preview directory if it doesn't exist
                preview_path.parent.mkdir(parents=True, exist_ok=True)

                # Save preview to cache
                processed_img.save(preview_path, format="WEBP", quality=85)
        except Exception as e:
            logger.warning("Failed to generate preview for %s: %s", file_path, e)
            return file_path
        else:
            return preview_path

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

        workspace_directory = Path(self.config_manager.get_config_value("workspace_directory"))
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
            request: Request containing file_path and preview parameters.

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

        # If preview requested and file is local, generate preview
        if request.preview and bucket_id is None:
            try:
                file_path_to_use = self._generate_preview_if_needed(file_path_for_driver)
            except Exception as e:
                logger.warning("Preview generation failed for %s, using original: %s", request.file_path, e)
                file_path_to_use = file_path_for_driver
        else:
            file_path_to_use = file_path_for_driver

        try:
            url = driver.create_signed_download_url(file_path_to_use)
        except Exception as e:
            msg = f"Failed to create presigned URL for file {file_path}: {e}"
            return CreateStaticFileDownloadUrlResultFailure(error=msg, result_details=msg)

        return CreateStaticFileDownloadUrlResultSuccess(
            url=url,
            file_url=driver.get_asset_url(file_path_to_use),
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
        use_direct_save: bool = False,
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
            use_direct_save: If True, use direct storage driver save (new behavior).
                If False, use presigned URL upload (legacy behavior). Defaults to False for backward compatibility.
            skip_metadata_injection: If True, skip automatic workflow metadata injection.
                Defaults to False. Used by nodes that handle metadata explicitly (e.g., WriteImageMetadataNode).

        Returns:
            The URL of the saved file for UI display (with cache-busting). Note: the actual filename
            may differ from the requested file_name when using CREATE_NEW policy.

        Raises:
            FileExistsError: When existing_file_policy is FAIL and file already exists.
            RuntimeError: If file write fails (new behavior).
            ValueError: If file upload fails (legacy behavior).
        """
        resolved_directory = self._get_static_files_directory()
        file_path = Path(resolved_directory) / file_name

        # Inject workflow metadata if enabled (only when not using direct save)
        if (
            not use_direct_save
            and self.config_manager.get_config_value("auto_inject_workflow_metadata")
            and not skip_metadata_injection
        ):
            data = GriptapeNodes.ArtifactManager().prepare_content_for_write(data, file_name)

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
