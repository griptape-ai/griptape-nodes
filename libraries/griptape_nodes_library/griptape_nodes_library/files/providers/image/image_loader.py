import logging
from pathlib import Path
from typing import Any, ClassVar

import httpx
from griptape.artifacts import ImageUrlArtifact

from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import BaseNode
from griptape_nodes.retained_mode.events.static_file_events import (
    CreateWorkspaceFileDownloadUrlRequest,
    CreateWorkspaceFileDownloadUrlResultSuccess,
)
from griptape_nodes.retained_mode.events.workflow_events import LoadWorkflowMetadata, LoadWorkflowMetadataResultSuccess
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
from griptape_nodes.traits.options import Options
from griptape_nodes_library.files.providers.artifact_load_provider import (
    ArtifactLoadProvider,
    ArtifactLoadProviderValidationResult,
    ArtifactParameterDetails,
    ExternalFileLocation,
    FileLocation,
    OnDiskFileLocation,
    URLFileLocation,
    WorkspaceFileLocation,
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
            "expander": True,
            "edit_mask": True,
        }

    def get_additional_parameters(self) -> list[Parameter]:
        """Get image-specific parameters."""
        return [self.mask_channel_parameter, self.output_mask_parameter]

    def can_handle_file_location(self, file_location_input: str) -> bool:
        """Lightweight check if this provider can handle the given file location input."""
        location = ArtifactLoadProvider.determine_file_location(file_location_input)

        if isinstance(location, (WorkspaceFileLocation, ExternalFileLocation)):
            return self._can_handle_path(file_location_input)
        if isinstance(location, URLFileLocation):
            return self._can_handle_url(file_location_input)

        msg = f"Unsupported file location type: {type(location)}"
        logger.warning(msg)
        return False

    def _can_handle_path(self, file_path_str: str) -> bool:
        """Lightweight check if this provider can handle the given filesystem path."""
        try:
            file_path = Path(file_path_str)
            return file_path.suffix.lower() in self.SUPPORTED_EXTENSIONS
        except (ValueError, OSError, AttributeError):
            return False

    def _can_handle_url(self, url_input: str) -> bool:
        """Lightweight check if this provider can handle the given URL."""
        if not ArtifactLoadProvider.is_url(url_input):
            return False

        # Use proper content-type detection
        # For now, check URL path extension as fallback
        try:
            url_path = Path(url_input).suffix.lower()
        except (ValueError, OSError):
            return False

        return url_path in self.SUPPORTED_EXTENSIONS

    def attempt_load_from_file_location(
        self,
        file_location_str: str,
        current_parameter_values: dict[str, Any],
    ) -> ArtifactLoadProviderValidationResult:
        """Attempt to load and create image artifact from an ambiguous file location string.

        This method disambiguates the file location (URL, workspace path, or external path)
        and routes to the appropriate specialized loader method.
        """
        location = ArtifactLoadProvider.determine_file_location(file_location_str)

        if isinstance(location, URLFileLocation):
            return self.attempt_load_from_url(location, current_parameter_values)

        if isinstance(location, (WorkspaceFileLocation, ExternalFileLocation)):
            return self.attempt_load_from_filesystem_path(
                location=location,
                current_parameter_values=current_parameter_values,
            )

        return ArtifactLoadProviderValidationResult(
            was_successful=False, result_details=f"Unsupported file location type: {type(location)}"
        )

    def attempt_load_from_filesystem_path(
        self,
        location: OnDiskFileLocation,
        current_parameter_values: dict[str, Any],
    ) -> ArtifactLoadProviderValidationResult:
        """Attempt to load image from filesystem path."""
        try:
            # Validate file exists
            if not location.absolute_path.exists():
                return ArtifactLoadProviderValidationResult(
                    was_successful=False, result_details=f"File not found: {location.absolute_path}"
                )
        except FileNotFoundError:
            return ArtifactLoadProviderValidationResult(
                was_successful=False, result_details=f"File not found: {location.absolute_path}"
            )
        except PermissionError:
            return ArtifactLoadProviderValidationResult(
                was_successful=False, result_details=f"Permission denied: {location.absolute_path}"
            )
        except ValueError as e:
            return ArtifactLoadProviderValidationResult(was_successful=False, result_details=str(e))
        except Exception as e:
            return ArtifactLoadProviderValidationResult(
                was_successful=False, result_details=f"Image loading failed: {e}"
            )

        artifact = ImageUrlArtifact(value=self.get_externally_accessible_url(location))

        dynamic_updates = self._finalize_result_with_dynamic_updates(
            artifact=artifact, current_values=current_parameter_values
        )

        if isinstance(location, WorkspaceFileLocation):
            result_details = f"File loaded: {self.get_source_path(location)}"
        elif isinstance(location, ExternalFileLocation):
            result_details = f"File outside workspace: {self.get_source_path(location)}"
        else:
            result_details = f"File loaded from: {self.get_source_path(location)}"

        return ArtifactLoadProviderValidationResult(
            was_successful=True,
            artifact=artifact,
            location=location,
            dynamic_parameter_updates=dynamic_updates,
            result_details=result_details,
        )

    def attempt_load_from_url(
        self, location: URLFileLocation, current_parameter_values: dict[str, Any], timeout: float | None = None
    ) -> ArtifactLoadProviderValidationResult:
        """Attempt to load and create image artifact from URL."""
        # Use provided timeout or default to 120 seconds
        timeout_value = timeout if timeout is not None else 120.0

        try:
            # Download to memory (no disk write)
            response = httpx.get(location.url, timeout=timeout_value)
            response.raise_for_status()
            image_bytes = response.content
        except httpx.HTTPStatusError as e:
            return ArtifactLoadProviderValidationResult(
                was_successful=False,
                result_details=f"HTTP {e.response.status_code} error downloading {location.url}: {e}",
            )
        except httpx.RequestError as e:
            return ArtifactLoadProviderValidationResult(
                was_successful=False, result_details=f"Network error downloading {location.url}: {e}"
            )
        except Exception as e:
            return ArtifactLoadProviderValidationResult(
                was_successful=False, result_details=f"URL download failed: {e}"
            )

        # Create data URI for in-memory display
        import base64

        encoded = base64.b64encode(image_bytes).decode("utf-8")

        # Detect format from content-type or URL extension
        content_type = response.headers.get("content-type", "")
        if "image/" in content_type:
            format_type = content_type.split("/")[-1]
        else:
            format_type = Path(location.url).suffix.lstrip(".") or "png"

        data_uri = f"data:image/{format_type};base64,{encoded}"
        artifact = ImageUrlArtifact(value=data_uri)

        # Process dynamic parameters (mask extraction - deferred for URLs)
        dynamic_updates = self._finalize_result_with_dynamic_updates(
            artifact=artifact, current_values=current_parameter_values
        )

        # Return the location passed in
        return ArtifactLoadProviderValidationResult(
            was_successful=True,
            artifact=artifact,
            location=location,
            dynamic_parameter_updates=dynamic_updates,
            result_details=f"Image loaded from URL: {location.url}",
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

    def save_bytes_to_disk(self, *, file_bytes: bytes, location: OnDiskFileLocation) -> OnDiskFileLocation:
        """Save file bytes to disk at the specified location."""
        if isinstance(location, WorkspaceFileLocation):
            # Use StaticFilesManager for workspace files
            workspace_relative_path = str(location.workspace_relative_path)
            try:
                GriptapeNodes.StaticFilesManager().save_static_file(file_bytes, workspace_relative_path)
            except Exception as e:
                msg = f"Failed to save file to workspace: {workspace_relative_path}"
                raise RuntimeError(msg) from e
        elif isinstance(location, ExternalFileLocation):
            # Write directly to filesystem for external files
            try:
                location.absolute_path.parent.mkdir(parents=True, exist_ok=True)
                location.absolute_path.write_bytes(file_bytes)
            except Exception as e:
                msg = f"Failed to save file to disk: {location.absolute_path}"
                raise RuntimeError(msg) from e
        else:
            msg = f"Cannot save to location type: {type(location)}"
            raise TypeError(msg)

        return location

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

    def get_externally_accessible_url(self, location: FileLocation) -> str:
        """Convert file location to URL the frontend can fetch."""
        if isinstance(location, WorkspaceFileLocation):
            # Generate staticfiles URL for workspace file
            request = CreateWorkspaceFileDownloadUrlRequest(file_name=str(location.workspace_relative_path))
            result = GriptapeNodes.StaticFilesManager().on_handle_create_workspace_file_download_url_request(request)

            if isinstance(result, CreateWorkspaceFileDownloadUrlResultSuccess):
                return result.url

            msg = f"Failed to create download URL for workspace file: {location.workspace_relative_path}"
            raise RuntimeError(msg)

        if isinstance(location, ExternalFileLocation):
            # Use StaticFilesManager to create external file URL
            return GriptapeNodes.StaticFilesManager().create_external_file_url(location.absolute_path)

        if isinstance(location, URLFileLocation):
            # URL can be used directly
            return location.url

        msg = f"Unsupported location type: {type(location)}"
        raise TypeError(msg)

    def get_display_path(self, location: FileLocation) -> str:
        """Get user-facing path string for UI display."""
        if isinstance(location, WorkspaceFileLocation):
            return str(location.workspace_relative_path)
        if isinstance(location, ExternalFileLocation):
            return str(location.absolute_path)
        if isinstance(location, URLFileLocation):
            return location.url

        msg = f"Unsupported location type: {type(location)}"
        raise TypeError(msg)

    def get_source_path(self, location: FileLocation) -> str:
        """Get the original source path/URL provided by user."""
        if isinstance(location, WorkspaceFileLocation):
            return str(location.workspace_relative_path)
        if isinstance(location, ExternalFileLocation):
            return str(location.absolute_path)
        if isinstance(location, URLFileLocation):
            return location.url

        msg = f"Unsupported location type: {type(location)}"
        raise TypeError(msg)

    def is_location_external_to_workspace(self, location: FileLocation) -> bool:
        """Returns True if location is outside workspace and can be copied."""
        return isinstance(location, (ExternalFileLocation, URLFileLocation))

    def get_location_display_detail(self, location: FileLocation) -> str:
        """Get the URL or path detail to show user."""
        if isinstance(location, WorkspaceFileLocation):
            return str(location.workspace_relative_path)
        if isinstance(location, ExternalFileLocation):
            return str(location.absolute_path)
        if isinstance(location, URLFileLocation):
            return location.url

        msg = f"Unsupported location type: {type(location)}"
        raise TypeError(msg)

    def copy_location_to_workspace(
        self,
        location: FileLocation,
        artifact: Any,
        parameter_name: str,
    ) -> WorkspaceFileLocation:
        """Copy file from location to workspace."""
        if isinstance(location, ExternalFileLocation):
            # Read bytes from external file
            try:
                file_bytes = location.absolute_path.read_bytes()
            except FileNotFoundError as e:
                msg = f"Source file not found: {location.absolute_path}"
                raise FileNotFoundError(msg) from e
            except PermissionError as e:
                msg = f"Permission denied reading file: {location.absolute_path}"
                raise PermissionError(msg) from e

            original_filename = location.absolute_path.name

        elif isinstance(location, URLFileLocation):
            # Extract bytes from artifact
            from griptape_nodes_library.utils.image_utils import dict_to_image_url_artifact

            # Convert to ImageUrlArtifact if it's a dict
            if isinstance(artifact, dict):
                artifact = dict_to_image_url_artifact(artifact)

            # Use Griptape's built-in to_bytes()
            try:
                file_bytes = artifact.to_bytes()
            except Exception as e:
                msg = f"Failed to get image bytes from artifact: {e}"
                raise RuntimeError(msg) from e

            # Extract filename from URL
            url_path = Path(location.url)
            original_filename = url_path.name or "downloaded_image.png"

        else:
            msg = f"Cannot copy workspace location to workspace: {type(location)}"
            raise TypeError(msg)

        # Generate workspace filename
        filename = self._generate_workspace_filename_only(
            original_filename=original_filename, parameter_name=parameter_name
        )
        workspace_relative_path = Path("uploads") / filename

        # Get absolute path for the workspace location
        workspace_path = GriptapeNodes.ConfigManager().workspace_path
        absolute_path = workspace_path / "static_files" / workspace_relative_path

        # Create WorkspaceFileLocation
        workspace_location = WorkspaceFileLocation(
            workspace_relative_path=workspace_relative_path,
            absolute_path=absolute_path,
        )

        # Save to disk and return the workspace location
        self.save_bytes_to_disk(
            file_bytes=file_bytes,
            location=workspace_location,
        )
        return workspace_location
