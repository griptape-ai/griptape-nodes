import logging
import re
from pathlib import Path
from typing import Any, ClassVar
from urllib.parse import urlparse

import httpx
from griptape.artifacts import ImageUrlArtifact

from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import BaseNode
from griptape_nodes.retained_mode.events.static_file_events import (
    CreateWorkspaceFileDownloadUrlRequest,
    CreateWorkspaceFileDownloadUrlResultSuccess,
)
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

    def _generate_unique_filename_from_url(self, url: str) -> str:
        """Generate a unique filename from URL by sanitizing domain and path.

        Sanitizes domain and path separately (rather than the entire URL) to create
        shorter, more readable filenames while maintaining uniqueness.

        Examples:
            https://example.com/images/cat.jpg -> example_com_images_cat.jpg
            https://cdn.site.com/assets/output.png -> cdn_site_com_assets_output.png

        Compare to sanitizing entire URL which would produce:
            https___example_com_images_cat_jpg (less readable, includes protocol)

        Args:
            url: URL to generate filename from

        Returns:
            Sanitized filename like "example_com_path_to_image.png"

        Raises:
            ValueError: If filename cannot be determined from URL
        """
        parsed = urlparse(url)

        # Get domain without port or protocol (e.g., "example.com" -> "example_com")
        domain = parsed.netloc.split(":")[0]
        domain_sanitized = re.sub(r"[^a-zA-Z0-9]", "_", domain)

        # Get path and extract filename
        url_path = Path(parsed.path)
        if not url_path.name or not url_path.suffix:
            msg = f"Cannot determine filename with extension from URL: {url}"
            raise ValueError(msg)

        # Sanitize the path (parent directories) (e.g., "/images/assets/" -> "images_assets")
        path_parts = url_path.parent.parts
        path_sanitized = "_".join(re.sub(r"[^a-zA-Z0-9]", "_", part) for part in path_parts if part != "/")

        # Get original filename with extension
        stem = url_path.stem
        extension = url_path.suffix

        # Combine: domain_path_filename (e.g., "example_com_images_cat.jpg")
        if path_sanitized:
            unique_filename = f"{domain_sanitized}_{path_sanitized}_{stem}{extension}"
        else:
            unique_filename = f"{domain_sanitized}_{stem}{extension}"

        return unique_filename

    def attempt_load_from_url(
        self, location: URLFileLocation, current_parameter_values: dict[str, Any], timeout: float | None = None
    ) -> ArtifactLoadProviderValidationResult:
        """Attempt to load and create image artifact from URL.

        Downloads the URL to {workflow_dir}/downloads/ to avoid bloating workflow files with base64 data.
        Returns URLFileLocation so the user still sees the original URL in the parameter.
        """
        timeout_value = timeout if timeout is not None else 120.0

        # Download URL bytes to memory
        try:
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

        # Generate unique filename from URL (sanitizes domain and path)
        try:
            filename = self._generate_unique_filename_from_url(location.url)
        except ValueError as e:
            return ArtifactLoadProviderValidationResult(was_successful=False, result_details=str(e))

        # Determine download location in workflow's downloads/ directory
        download_location = ArtifactLoadProvider.generate_workflow_file_location(
            subdirectory="downloads", filename=filename
        )

        # Save downloaded bytes to disk
        try:
            self.save_bytes_to_disk(file_bytes=image_bytes, location=download_location)
        except Exception as e:
            return ArtifactLoadProviderValidationResult(
                was_successful=False, result_details=f"Failed to save downloaded file: {e}"
            )

        # Create artifact with URL to the downloaded file (not base64 data)
        artifact = ImageUrlArtifact(value=self.get_externally_accessible_url(download_location))

        # Process dynamic parameters (e.g., mask extraction)
        dynamic_updates = self._finalize_result_with_dynamic_updates(
            artifact=artifact, current_values=current_parameter_values
        )

        # Return URLFileLocation so user still sees original URL in parameter
        return ArtifactLoadProviderValidationResult(
            was_successful=True,
            artifact=artifact,
            location=location,
            dynamic_parameter_updates=dynamic_updates,
            result_details=f"Image downloaded from URL: {location.url}",
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
        """Save file bytes to disk at the specified location using direct file I/O."""
        try:
            location.absolute_path.parent.mkdir(parents=True, exist_ok=True)
            location.absolute_path.write_bytes(file_bytes)
        except Exception as e:
            msg = f"Failed to save file to disk: {location.absolute_path}"
            raise RuntimeError(msg) from e

        return location

    def _generate_workspace_filename_only(self, original_filename: str, parameter_name: str) -> str:
        """Generate filename using protocol: {node_name}_{parameter_name}_{file_name}.

        Workflow name is not included since files are organized under workflow-specific directories.
        """
        # Extract base name and extension
        base_name = Path(original_filename).stem
        extension = Path(original_filename).suffix

        if not extension:
            logger.warning("No extension found in filename %s, defaulting to .png", original_filename)
            extension = ".png"

        # Generate filename: <node_name>_<parameter_name>_<file_name>
        return f"{self.node.name}_{parameter_name}_{base_name}{extension}"

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

    def _read_bytes_from_on_disk_location(self, location: OnDiskFileLocation) -> bytes:
        """Read bytes from an on-disk file location with comprehensive error handling."""
        try:
            return location.absolute_path.read_bytes()
        except FileNotFoundError as e:
            msg = f"Source file not found: {location.absolute_path}"
            raise FileNotFoundError(msg) from e
        except PermissionError as e:
            msg = f"Permission denied reading file: {location.absolute_path}"
            raise PermissionError(msg) from e
        except OSError as e:
            msg = f"Failed to read file: {location.absolute_path}"
            raise OSError(msg) from e
        except Exception as e:
            msg = f"Unexpected error reading file: {location.absolute_path}"
            raise RuntimeError(msg) from e

    def _read_bytes_from_url_location(self, artifact: Any) -> bytes:
        """Read bytes from a downloaded URL file with comprehensive error handling.

        Args:
            artifact: The artifact containing the URL to the downloaded file

        Returns:
            File bytes from the downloaded file
        """
        # Extract filename from the artifact's URL (which points to the downloaded file)
        if isinstance(artifact, dict):
            artifact = dict_to_image_url_artifact(artifact)

        artifact_url = artifact.value

        # Parse URL and strip query string to get just the filename
        parsed = urlparse(artifact_url)
        filename = Path(parsed.path).name

        download_location = ArtifactLoadProvider.generate_workflow_file_location(
            subdirectory="downloads", filename=filename
        )

        try:
            return download_location.absolute_path.read_bytes()
        except FileNotFoundError as e:
            msg = (
                f"Downloaded file not found at {download_location.absolute_path}. Please reload the URL to re-download."
            )
            raise FileNotFoundError(msg) from e
        except PermissionError as e:
            msg = f"Permission denied reading downloaded file: {download_location.absolute_path}"
            raise PermissionError(msg) from e
        except OSError as e:
            msg = f"Failed to read downloaded file: {download_location.absolute_path}"
            raise OSError(msg) from e
        except Exception as e:
            msg = f"Unexpected error reading downloaded file: {download_location.absolute_path}"
            raise RuntimeError(msg) from e

    def copy_file_location_to_disk(
        self,
        source_location: FileLocation,
        destination_location: OnDiskFileLocation,
        artifact: Any,
    ) -> OnDiskFileLocation:
        """Copy file from source location to destination location on disk."""
        match source_location:
            case OnDiskFileLocation():
                file_bytes = self._read_bytes_from_on_disk_location(source_location)
            case URLFileLocation():
                file_bytes = self._read_bytes_from_url_location(artifact)
            case _:
                msg = f"Cannot copy from location type: {type(source_location)}"
                raise TypeError(msg)

        self.save_bytes_to_disk(file_bytes=file_bytes, location=destination_location)
        return destination_location
