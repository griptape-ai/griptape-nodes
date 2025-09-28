import logging
import time
from pathlib import Path
from typing import Any, ClassVar, NamedTuple, cast

import httpx
from griptape.artifacts import ImageUrlArtifact

from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import BaseNode
from griptape_nodes.retained_mode.events.static_file_events import (
    CreateWorkspaceFileDownloadUrlRequest,
    CreateWorkspaceFileDownloadUrlResultFailure,
    CreateWorkspaceFileDownloadUrlResultSuccess,
)
from griptape_nodes.retained_mode.events.workflow_events import LoadWorkflowMetadata, LoadWorkflowMetadataResultSuccess
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
from griptape_nodes.traits.options import Options
from griptape_nodes_library.files.path_utils import PathUtils
from griptape_nodes_library.files.providers.artifact_load_provider import (
    ArtifactLoadProvider,
    ArtifactLoadProviderValidationResult,
    ArtifactParameterDetails,
)
from griptape_nodes_library.utils.image_utils import (
    dict_to_image_url_artifact,
    extract_channel_from_image,
    load_pil_from_url,
    save_pil_image_with_named_filename,
)

logger = logging.getLogger("griptape_nodes")

# File handling strategy:
# - Files inside workspace: Use relative path from workspace root for serving
# - Files outside workspace: Copy to workspace uploads directory with generated filename
# - URLs: Download to workspace uploads directory
# - All saved files go to: {workflow_dir}/static_files/uploads/{workflow_name}_{node_name}_{parameter_name}_{file_name}


class PathProcessResult(NamedTuple):
    """Result of processing a file path for serving.

    internal_url: URL for serving the file (relative path for workspace files, cache-busted URL for copied files)
    saved_path: Full filesystem path where file was saved (None if file was already inside workspace)
    """

    internal_url: str
    saved_path: str | None


class FileDownloadResult(NamedTuple):
    """Result of downloading and saving a file from URL.

    internal_url: Cache-busted relative URL for serving the downloaded file
    saved_path: Full filesystem path where the downloaded file was saved
    """

    internal_url: str
    saved_path: str


class ImageLoadProvider(ArtifactLoadProvider):
    def __init__(self, node: BaseNode, *, path_parameter: Parameter) -> None:
        """Initialize image provider with required parameters."""
        super().__init__(node, path_parameter=path_parameter)

        # Create and store our own dynamic parameters
        self.mask_channel_parameter = Parameter(
            name="mask_channel",
            type="str",
            tooltip="Channel to extract as mask (red, green, blue, or alpha).",
            default_value="alpha",
            ui_options={"hide": True},
        )
        self.mask_channel_parameter.add_trait(Options(choices=["red", "green", "blue", "alpha"]))

        self.output_mask_parameter = Parameter(
            name="output_mask",
            type="ImageUrlArtifact",
            tooltip="The Mask for the image",
            ui_options={"expander": True, "hide": True},
            allowed_modes={ParameterMode.OUTPUT},
        )

    # Use same extensions as LoadImage for consistency
    SUPPORTED_EXTENSIONS: ClassVar[set[str]] = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg"}

    @property
    def provider_name(self) -> str:
        return "Image"

    @property
    def artifact_type(self) -> str:
        return "ImageUrlArtifact"

    @property
    def supported_extensions(self) -> set[str]:
        return self.SUPPORTED_EXTENSIONS

    @property
    def url_content_type_prefix(self) -> str:
        return "image/"

    @property
    def default_extension(self) -> str:
        return ".png"

    def get_artifact_parameter_details(self) -> ArtifactParameterDetails:
        return ArtifactParameterDetails(
            input_types=["ImageUrlArtifact", "ImageArtifact", "str"],
            type="ImageUrlArtifact",
            output_type="ImageUrlArtifact",
        )

    def get_artifact_ui_options(self) -> dict[str, Any]:
        """Get image-specific UI options including mask editing."""
        return {
            "display_name": "Image",
            "clickable_file_browser": True,
            "expander": True,
            "edit_mask": True,
        }

    def get_additional_parameters(self) -> list[Parameter]:
        """Get image-specific parameters."""
        return [self.mask_channel_parameter, self.output_mask_parameter]

    def can_handle_path(self, path_input: str) -> bool:
        """Lightweight check if this provider can handle the given file path."""
        # LoadFile already checks for empty paths, so we assume non-empty here
        path_str = PathUtils.normalize_path_input(path_input)
        if not path_str:
            return False

        try:
            file_path = PathUtils.to_path_object(path_str)
        except (ValueError, OSError, PermissionError):
            return False

        if not file_path:
            return False

        return file_path.suffix.lower() in self.SUPPORTED_EXTENSIONS

    def can_handle_url(self, url_input: str) -> bool:
        """Lightweight check if this provider can handle the given URL."""
        if not PathUtils.is_url(url_input):
            return False

        # Use proper content-type detection
        # For now, check URL path extension as fallback
        try:
            url_path = Path(url_input).suffix.lower()
        except (ValueError, OSError):
            return False

        return url_path in self.SUPPORTED_EXTENSIONS

    def can_handle_artifact(self, artifact_input: Any) -> bool:
        """Lightweight check if this provider can handle the given artifact."""
        url = self._extract_url_from_artifact_input(artifact_input)
        return url is not None

    def attempt_load_from_path(
        self, path_input: str, current_parameter_values: dict[str, Any]
    ) -> ArtifactLoadProviderValidationResult:
        """Attempt to load and create image artifact from path input."""
        path_str = PathUtils.normalize_path_input(path_input)
        if not path_str:
            return ArtifactLoadProviderValidationResult(was_successful=False, result_details="Empty path provided")

        try:
            # Process file path for serving (copy to workspace if needed)
            path_result = self._process_path_to_internal_url(path_str)
        except FileNotFoundError:
            return ArtifactLoadProviderValidationResult(
                was_successful=False, result_details=f"File not found: {path_input}"
            )
        except PermissionError:
            return ArtifactLoadProviderValidationResult(
                was_successful=False, result_details=f"Permission denied accessing file: {path_input}"
            )
        except Exception as e:
            return ArtifactLoadProviderValidationResult(
                was_successful=False, result_details=f"Image loading failed: {e}"
            )

        # Create the image artifact
        artifact = ImageUrlArtifact(value=path_result.internal_url)

        # Process dynamic parameters (mask extraction)
        dynamic_updates = self._finalize_result_with_dynamic_updates(
            artifact=artifact, current_values=current_parameter_values
        )

        # Build result details
        result_details = f"Image loaded successfully from {path_str}"
        if path_result.saved_path:
            result_details += f" and saved to {path_result.saved_path}"

        return ArtifactLoadProviderValidationResult(
            was_successful=True,
            artifact=artifact,
            internal_url=path_result.internal_url,
            path=path_str,
            dynamic_parameter_updates=dynamic_updates,
            result_details=result_details,
        )

    def attempt_load_from_url(
        self, url_input: str, current_parameter_values: dict[str, Any]
    ) -> ArtifactLoadProviderValidationResult:
        """Attempt to load and create image artifact from URL input."""
        try:
            # Download directly to workspace (no intermediate disk save)
            download_result = self._download_url_to_workspace(url=url_input)
        except httpx.HTTPStatusError as e:
            return ArtifactLoadProviderValidationResult(
                was_successful=False, result_details=f"HTTP {e.response.status_code} error downloading {url_input}: {e}"
            )
        except httpx.RequestError as e:
            return ArtifactLoadProviderValidationResult(
                was_successful=False, result_details=f"Network error downloading {url_input}: {e}"
            )
        except Exception as e:
            return ArtifactLoadProviderValidationResult(
                was_successful=False, result_details=f"URL download failed: {e}"
            )

        # Create the image artifact
        artifact = ImageUrlArtifact(value=download_result.saved_path)

        # Process dynamic parameters (mask extraction)
        dynamic_updates = self._finalize_result_with_dynamic_updates(
            artifact=artifact, current_values=current_parameter_values
        )

        return ArtifactLoadProviderValidationResult(
            was_successful=True,
            artifact=artifact,
            internal_url=download_result.internal_url,
            path=url_input,
            dynamic_parameter_updates=dynamic_updates,
            result_details=f"Image downloaded successfully from {url_input} and saved to {download_result.saved_path}",
        )

    def attempt_load_from_artifact(
        self, artifact_input: Any, current_parameter_values: dict[str, Any]
    ) -> ArtifactLoadProviderValidationResult:
        """Attempt to load and normalize image artifact input."""
        # Normalize input to ImageUrlArtifact if it's a dict
        normalized_artifact = artifact_input
        if isinstance(artifact_input, dict):
            try:
                normalized_artifact = dict_to_image_url_artifact(artifact_input)
            except Exception as e:
                return ArtifactLoadProviderValidationResult(
                    was_successful=False, result_details=f"Cannot convert dict to ImageUrlArtifact: {e}"
                )

        # Extract URL from artifact
        url = self._extract_url_from_artifact_input(normalized_artifact)
        if not url:
            return ArtifactLoadProviderValidationResult(
                was_successful=False,
                result_details=f"Cannot extract URL from artifact of type: {type(normalized_artifact).__name__}",
            )

        # Extract URL for display path with robust error handling
        try:
            display_path = self._extract_url_from_artifact_for_display(artifact_input) or url
        except ValueError as e:
            return ArtifactLoadProviderValidationResult(
                was_successful=False, result_details=f"Invalid artifact format: {e}"
            )

        # Process dynamic parameters (mask extraction)
        dynamic_updates = self._finalize_result_with_dynamic_updates(
            artifact=normalized_artifact, current_values=current_parameter_values
        )

        return ArtifactLoadProviderValidationResult(
            was_successful=True,
            artifact=normalized_artifact,
            internal_url=url,
            path=display_path,
            dynamic_parameter_updates=dynamic_updates,
            result_details=f"Image artifact processed successfully from {display_path}",
        )

    def _extract_url_from_artifact_for_display(self, artifact_value: Any) -> str:
        """Extract URL from artifact value for display purposes.

        Handles dict, ImageUrlArtifact, and str formats with robust error handling.

        Returns:
            The extracted URL string

        Raises:
            ValueError: If the artifact value type is not supported
        """
        if not artifact_value:
            return ""

        match artifact_value:
            # Handle dictionary format (most common from UI)
            case dict():
                url = artifact_value.get("value")
            # Handle ImageUrlArtifact objects
            case ImageUrlArtifact():
                url = artifact_value.value
            # Handle raw strings
            case str():
                url = artifact_value
            case _:
                # Generate error message for unsupported types
                expected_types = "dict, ImageUrlArtifact, or str"
                error_msg = (
                    f"Unsupported artifact value type: {type(artifact_value).__name__}. Expected: {expected_types}"
                )
                raise ValueError(error_msg)

        # Return empty string if no URL found (safer than None for display)
        return url or ""

    def _process_path_to_internal_url(self, path_str: str) -> PathProcessResult:
        """Process file path for serving: use relative path if in workspace, otherwise copy to workspace."""
        file_path = Path(path_str)
        workspace_path = GriptapeNodes.ConfigManager().workspace_path

        # Check if file is inside workspace
        try:
            # If this succeeds, file is inside workspace - get proper download URL
            resolved_file_path = file_path.resolve()
            relative_path = resolved_file_path.relative_to(workspace_path.resolve())

            # Use new workspace file download request (bypasses static files directory logic)
            download_request = CreateWorkspaceFileDownloadUrlRequest(file_name=relative_path.as_posix())
            download_result = GriptapeNodes.handle_request(download_request)

            if isinstance(download_result, CreateWorkspaceFileDownloadUrlResultFailure):
                msg = f"Failed to create workspace file download URL: {download_result.error}"
                raise TypeError(msg)

            success_result = cast("CreateWorkspaceFileDownloadUrlResultSuccess", download_result)
            internal_url = success_result.url
            return PathProcessResult(internal_url=internal_url, saved_path=str(resolved_file_path))
        except ValueError:
            # File is outside workspace - copy it to workspace uploads directory
            copy_result = self._copy_file_to_workspace(file_path=file_path)
            return PathProcessResult(internal_url=copy_result.saved_path, saved_path=copy_result.saved_path)

    def _copy_file_to_workspace(self, *, file_path: Path) -> FileDownloadResult:
        """Copy file from outside workspace to workspace uploads directory."""
        try:
            file_bytes = file_path.read_bytes()
        except FileNotFoundError as e:
            msg = f"Source file not found: {file_path}"
            raise FileNotFoundError(msg) from e
        except PermissionError as e:
            msg = f"Permission denied reading file: {file_path}"
            raise PermissionError(msg) from e
        except OSError as e:
            msg = f"Error reading file: {file_path}"
            raise OSError(msg) from e

        # Use unified save method
        return self._save_bytes_to_workspace(
            file_bytes=file_bytes, original_filename=file_path.name, parameter_name=self.path_parameter.name
        )

    def _download_url_to_workspace(self, *, url: str) -> FileDownloadResult:
        """Download URL and save directly to workspace uploads directory."""
        # Download the image (no intermediate disk save)
        try:
            response = httpx.get(url, timeout=30.0)
            response.raise_for_status()
            file_bytes = response.content
        except httpx.RequestError as e:
            msg = f"Network error downloading {url}"
            raise RuntimeError(msg) from e
        except httpx.HTTPStatusError as e:
            msg = f"HTTP {e.response.status_code} error downloading {url}"
            raise RuntimeError(msg) from e

        # Extract filename from URL, default to image with proper extension
        url_path = Path(url)
        if url_path.suffix.lower() in self.SUPPORTED_EXTENSIONS:
            original_filename = url_path.name
        else:
            # No valid extension - use png as default with warning
            logger.warning("No valid image extension found in URL %s, defaulting to .png", url)
            original_filename = f"{url_path.stem or 'downloaded_image'}.png"

        # Use unified save method
        return self._save_bytes_to_workspace(
            file_bytes=file_bytes, original_filename=original_filename, parameter_name=self.path_parameter.name
        )

    def _save_bytes_to_workspace(
        self, *, file_bytes: bytes, original_filename: str, parameter_name: str
    ) -> FileDownloadResult:
        """Unified method for saving bytes to workspace with proper error handling."""
        # Generate filename using protocol: {workflow_name}_{node_name}_{parameter_name}_{file_name}
        filename = self._generate_workspace_filename_only(
            original_filename=original_filename, parameter_name=parameter_name
        )

        # Save to workspace uploads directory - StaticFilesManager handles directory resolution
        upload_path = f"uploads/{filename}"
        try:
            saved_path = GriptapeNodes.StaticFilesManager().save_static_file(file_bytes, upload_path)
        except Exception as e:
            msg = f"Failed to save file to workspace: {upload_path}"
            raise RuntimeError(msg) from e

        # Return internal URL with cache buster
        timestamp = int(time.time())
        internal_url = f"staticfiles/uploads/{filename}?t={timestamp}"
        return FileDownloadResult(internal_url=internal_url, saved_path=saved_path)

    def _generate_workspace_filename_only(self, original_filename: str, parameter_name: str) -> str:
        """Generate filename using protocol: {workflow_name}_{node_name}_{parameter_name}_{file_name}."""
        # Get workflow name - this MUST succeed for the protocol to work
        try:
            workflow_name = GriptapeNodes.ContextManager().get_current_workflow_name()
        except Exception as e:
            msg = "Cannot generate workspace filename: no current workflow context"
            raise RuntimeError(msg) from e

        # Extract base name and extension
        base_name = Path(original_filename).stem
        extension = Path(original_filename).suffix

        if not extension:
            logger.warning("No extension found in filename %s, defaulting to .png", original_filename)
            extension = ".png"

        # Generate filename: <workflow_name>_<node_name>_<parameter_name>_<file_name>
        return f"{workflow_name}_{self.node.name}_{parameter_name}_{base_name}{extension}"

    def _generate_workspace_filename(self, original_filename: str, parameter_name: str) -> str:
        """Generate absolute file path for workspace uploads: {workflow_dir}/static_files/uploads/{workflow_name}_{node_name}_{parameter_name}_{file_name}."""
        # Get workflow name - this MUST succeed for the protocol to work
        try:
            workflow_name = GriptapeNodes.ContextManager().get_current_workflow_name()
        except Exception as e:
            msg = "Cannot generate workspace filename: no current workflow context"
            raise RuntimeError(msg) from e

        # Get workflow directory - use the workflow name to construct the path
        # LoadWorkflowMetadata validates the workflow exists, so we can construct the path
        load_metadata_request = LoadWorkflowMetadata(file_name=f"{workflow_name}.py")
        load_metadata_result = GriptapeNodes.handle_request(load_metadata_request)

        if not isinstance(load_metadata_result, LoadWorkflowMetadataResultSuccess):
            msg = f"Failed to load workflow metadata for {workflow_name}"
            raise RuntimeError(msg)  # noqa: TRY004

        # Use the workflow name to construct the path since metadata validation succeeded
        workspace_path = GriptapeNodes.ConfigManager().workspace_path
        workflow_file_path = f"{workflow_name}.py"
        full_workflow_path = workspace_path / workflow_file_path
        workflow_dir = full_workflow_path.parent

        # Extract base name and extension
        base_name = Path(original_filename).stem
        extension = Path(original_filename).suffix

        if not extension:
            logger.warning("No extension found in filename %s, defaulting to .png", original_filename)
            extension = ".png"

        # Generate filename: <workflow_name>_<node_name>_<parameter_name>_<file_name>
        filename = f"{workflow_name}_{self.node.name}_{parameter_name}_{base_name}{extension}"

        # Return full path: {workflow_dir}/static_files/uploads/{filename}
        return str(workflow_dir / "static_files" / "uploads" / filename)

    def _extract_url_from_artifact_input(self, artifact_input: Any) -> str | None:
        """Extract URL from various artifact input formats."""
        if isinstance(artifact_input, ImageUrlArtifact):
            return artifact_input.value
        if isinstance(artifact_input, dict):
            return artifact_input.get("value")
        if isinstance(artifact_input, str):
            return artifact_input
        # Check for ImageArtifact types that might have a value attribute
        if hasattr(artifact_input, "value") and artifact_input.value:
            return artifact_input.value
        return None

    def _extract_display_path_from_url(self, url: str) -> str:
        """Extract user-friendly display path from internal URL."""
        # For file:// URLs, extract the file path
        if url.startswith("file://"):
            return url[7:]  # Remove "file://" prefix
        # For HTTP URLs, return as-is for display
        return url

    def _finalize_result_with_dynamic_updates(self, *, artifact: Any, current_values: dict[str, Any]) -> dict[str, Any]:
        """Process image-specific dynamic parameter updates (mask extraction)."""
        updates = {}

        mask_channel = current_values.get(self.mask_channel_parameter.name)
        if not mask_channel or not artifact:
            return updates

        try:
            # Normalize input to ImageUrlArtifact
            if isinstance(artifact, dict):
                artifact = dict_to_image_url_artifact(artifact)
        except Exception as e:
            logger.warning("Failed to normalize artifact for mask extraction: %s", e)
            updates["output_mask"] = None
            return updates

        if not isinstance(artifact, ImageUrlArtifact):
            return updates

        try:
            # Load and process image
            image_pil = load_pil_from_url(artifact.value)
            mask = extract_channel_from_image(image_pil, mask_channel, "image")
        except Exception as e:
            logger.warning("Failed to extract mask channel '%s': %s", mask_channel, e)
            updates["output_mask"] = None
            return updates

        try:
            # Save mask using filename-only approach
            filename = self._generate_workspace_filename_only(
                original_filename="mask.png", parameter_name=self.output_mask_parameter.name
            )
            output_artifact = save_pil_image_with_named_filename(mask, filename, "PNG")
            logger.debug(
                "ImageLoadProvider: Mask saved successfully as artifact: %s",
                output_artifact.value if hasattr(output_artifact, "value") else output_artifact,
            )
            updates["output_mask"] = output_artifact
        except Exception as e:
            logger.warning("Failed to save mask: %s", e)
            updates["output_mask"] = None

        return updates
