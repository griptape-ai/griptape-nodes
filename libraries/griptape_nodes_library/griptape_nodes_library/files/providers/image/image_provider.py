import logging
import re
from pathlib import Path
from typing import Any, ClassVar
from urllib.parse import urlparse

import httpx
from griptape.artifacts import ImageUrlArtifact
from PIL import Image, ImageDraw, ImageFont

from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import BaseNode
from griptape_nodes.retained_mode.events.static_file_events import (
    CreateWorkspaceFileDownloadUrlRequest,
    CreateWorkspaceFileDownloadUrlResultSuccess,
)
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
from griptape_nodes.traits.options import Options
from griptape_nodes_library.files.providers.artifact_provider import (
    ArtifactParameterDetails,
    ArtifactProvider,
    ArtifactProviderValidationResult,
    ExternalFileLocation,
    FileLocation,
    OnDiskFileLocation,
    ProjectFileLocation,
    URLFileLocation,
)
from griptape_nodes_library.utils.image_utils import (
    dict_to_image_url_artifact,
    extract_channel_from_image,
    load_pil_from_url,
    save_pil_image_with_named_filename,
)

logger = logging.getLogger("griptape_nodes")


class ImageProvider(ArtifactProvider):
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

    # Maximum dimensions for thumbnail previews (width, height)
    THUMBNAIL_MAX_SIZE: ClassVar[tuple[int, int]] = (1024, 1024)

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
        location = ArtifactProvider.determine_file_location(file_location_input)

        if isinstance(location, (ProjectFileLocation, ExternalFileLocation)):
            return self._can_handle_path(file_location_input)
        if isinstance(location, URLFileLocation):
            return self._can_handle_url(file_location_input)

        msg = f"Unsupported file location type: {type(location)}"
        logger.warning(msg)
        return False

    def attempt_load_from_file_location(
        self,
        file_location_str: str,
        current_parameter_values: dict[str, Any],
    ) -> ArtifactProviderValidationResult:
        """Attempt to load and create image artifact from an ambiguous file location string.

        This method disambiguates the file location (URL, project path, or external path)
        and routes to the appropriate specialized loader method.
        """
        location = ArtifactProvider.determine_file_location(file_location_str)

        if isinstance(location, URLFileLocation):
            return self.attempt_load_from_url(location, current_parameter_values)

        if isinstance(location, (ProjectFileLocation, ExternalFileLocation)):
            return self.attempt_load_from_filesystem_path(
                location=location,
                current_parameter_values=current_parameter_values,
            )

        return ArtifactProviderValidationResult(
            was_successful=False, result_details=f"Unsupported file location type: {type(location)}"
        )

    def attempt_load_from_filesystem_path(
        self,
        location: OnDiskFileLocation,
        current_parameter_values: dict[str, Any],
    ) -> ArtifactProviderValidationResult:
        """Attempt to load image from filesystem path."""
        try:
            # Validate file exists
            if not location.absolute_path.exists():
                return ArtifactProviderValidationResult(
                    was_successful=False, result_details=f"File not found: {location.absolute_path}"
                )
        except FileNotFoundError:
            return ArtifactProviderValidationResult(
                was_successful=False, result_details=f"File not found: {location.absolute_path}"
            )
        except PermissionError:
            return ArtifactProviderValidationResult(
                was_successful=False, result_details=f"Permission denied: {location.absolute_path}"
            )
        except ValueError as e:
            return ArtifactProviderValidationResult(was_successful=False, result_details=str(e))
        except Exception as e:
            return ArtifactProviderValidationResult(was_successful=False, result_details=f"Image loading failed: {e}")

        artifact = ImageUrlArtifact(value=self.get_externally_accessible_url(location))

        dynamic_updates = self._finalize_result_with_dynamic_updates(
            artifact=artifact, current_values=current_parameter_values
        )

        # Generate thumbnail preview
        preview_artifact = self._generate_thumbnail(artifact, location)

        if isinstance(location, ProjectFileLocation):
            result_details = f"File loaded: {self.get_source_path(location)}"
        elif isinstance(location, ExternalFileLocation):
            result_details = f"File outside project: {self.get_source_path(location)}"
        else:
            result_details = f"File loaded from: {self.get_source_path(location)}"

        return ArtifactProviderValidationResult(
            was_successful=True,
            artifact=artifact,
            location=location,
            dynamic_parameter_updates=dynamic_updates,
            preview_artifact=preview_artifact,
            result_details=result_details,
        )

    def attempt_load_from_url(
        self, location: URLFileLocation, current_parameter_values: dict[str, Any], timeout: float | None = None
    ) -> ArtifactProviderValidationResult:
        """Attempt to load and create image artifact from URL.

        Downloads the URL to {workflow_dir}/inputs/ to avoid bloating workflow files with base64 data.
        Returns URLFileLocation so the user still sees the original URL in the parameter.
        """
        timeout_value = timeout if timeout is not None else 120.0

        # Download URL bytes to memory
        try:
            response = httpx.get(location.url, timeout=timeout_value)
            response.raise_for_status()
            image_bytes = response.content
        except httpx.HTTPStatusError as e:
            return ArtifactProviderValidationResult(
                was_successful=False,
                result_details=f"HTTP {e.response.status_code} error downloading {location.url}: {e}",
            )
        except httpx.RequestError as e:
            return ArtifactProviderValidationResult(
                was_successful=False, result_details=f"Network error downloading {location.url}: {e}"
            )
        except Exception as e:
            return ArtifactProviderValidationResult(was_successful=False, result_details=f"URL download failed: {e}")

        # Generate unique filename from URL (sanitizes domain and path)
        try:
            filename = self._generate_unique_filename_from_url(location.url)
        except ValueError as e:
            return ArtifactProviderValidationResult(was_successful=False, result_details=str(e))

        # Determine download location in project's inputs/ directory
        download_location = ArtifactProvider.generate_project_file_location(subdirectory="inputs", filename=filename)

        # Save downloaded bytes to disk
        try:
            self.save_bytes_to_disk(file_bytes=image_bytes, location=download_location)
        except Exception as e:
            return ArtifactProviderValidationResult(
                was_successful=False, result_details=f"Failed to save downloaded file: {e}"
            )

        # Create artifact with URL to the downloaded file (not base64 data)
        artifact = ImageUrlArtifact(value=self.get_externally_accessible_url(download_location))

        # Process dynamic parameters (e.g., mask extraction)
        dynamic_updates = self._finalize_result_with_dynamic_updates(
            artifact=artifact, current_values=current_parameter_values
        )

        # Generate thumbnail preview (use download_location for mirrored structure)
        preview_artifact = self._generate_thumbnail(artifact, download_location)

        # Return URLFileLocation so user still sees original URL in parameter
        return ArtifactProviderValidationResult(
            was_successful=True,
            artifact=artifact,
            location=location,
            dynamic_parameter_updates=dynamic_updates,
            preview_artifact=preview_artifact,
            result_details=f"Image downloaded from URL: {location.url}",
        )

    def save_bytes_to_disk(self, *, file_bytes: bytes, location: OnDiskFileLocation) -> OnDiskFileLocation:
        """Save file bytes to disk at the specified location using direct file I/O."""
        try:
            location.absolute_path.parent.mkdir(parents=True, exist_ok=True)
            location.absolute_path.write_bytes(file_bytes)
        except Exception as e:
            msg = f"Failed to save file to disk: {location.absolute_path}"
            raise RuntimeError(msg) from e

        return location

    def get_externally_accessible_url(self, location: FileLocation) -> str:
        """Convert file location to URL the frontend can fetch."""
        if isinstance(location, ProjectFileLocation):
            # Generate staticfiles URL for project file
            request = CreateWorkspaceFileDownloadUrlRequest(file_name=str(location.project_relative_path))
            result = GriptapeNodes.StaticFilesManager().on_handle_create_workspace_file_download_url_request(request)

            if isinstance(result, CreateWorkspaceFileDownloadUrlResultSuccess):
                return result.url

            msg = f"Failed to create download URL for project file: {location.project_relative_path}"
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
        if isinstance(location, ProjectFileLocation):
            return str(location.project_relative_path)
        if isinstance(location, ExternalFileLocation):
            return str(location.absolute_path)
        if isinstance(location, URLFileLocation):
            return location.url

        msg = f"Unsupported location type: {type(location)}"
        raise TypeError(msg)

    def get_source_path(self, location: FileLocation) -> str:
        """Get the original source path/URL provided by user."""
        if isinstance(location, ProjectFileLocation):
            return str(location.project_relative_path)
        if isinstance(location, ExternalFileLocation):
            return str(location.absolute_path)
        if isinstance(location, URLFileLocation):
            return location.url

        msg = f"Unsupported location type: {type(location)}"
        raise TypeError(msg)

    def is_location_external_to_project(self, location: FileLocation) -> bool:
        """Returns True if location is outside project and can be copied."""
        return isinstance(location, (ExternalFileLocation, URLFileLocation))

    def get_location_display_detail(self, location: FileLocation) -> str:
        """Get the URL or path detail to show user."""
        if isinstance(location, ProjectFileLocation):
            return str(location.project_relative_path)
        if isinstance(location, ExternalFileLocation):
            return str(location.absolute_path)
        if isinstance(location, URLFileLocation):
            return location.url

        msg = f"Unsupported location type: {type(location)}"
        raise TypeError(msg)

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

    def revalidate_for_execution(
        self,
        location: FileLocation,
        current_artifact: Any,
        current_parameter_values: dict[str, Any],
    ) -> ArtifactProviderValidationResult:
        """Revalidate image at execution time."""
        match location:
            case URLFileLocation():
                # Re-download URL for fresh content
                return self.attempt_load_from_url(location=location, current_parameter_values=current_parameter_values)

            case ProjectFileLocation() | ExternalFileLocation():
                # Local files: Trust they're still accessible
                # No filesystem checks - errors surface naturally if file missing
                display_path = self.get_display_path(location)
                return ArtifactProviderValidationResult(
                    was_successful=True,
                    artifact=current_artifact,
                    location=location,
                    dynamic_parameter_updates={},
                    result_details=f"File ready: {display_path}",
                )

            case _:
                return ArtifactProviderValidationResult(
                    was_successful=False, result_details="Unknown file location type. Please report this issue."
                )

    def _can_handle_path(self, file_path_str: str) -> bool:
        """Lightweight check if this provider can handle the given filesystem path."""
        try:
            file_path = Path(file_path_str)
            return file_path.suffix.lower() in self.SUPPORTED_EXTENSIONS
        except (ValueError, OSError, AttributeError):
            return False

    def _can_handle_url(self, url_input: str) -> bool:
        """Lightweight check if this provider can handle the given URL."""
        if not ArtifactProvider.is_url(url_input):
            return False

        # Use proper content-type detection
        # For now, check URL path extension as fallback
        try:
            url_path = Path(url_input).suffix.lower()
        except (ValueError, OSError):
            return False

        return url_path in self.SUPPORTED_EXTENSIONS

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

    def _generate_project_filename_only(self, original_filename: str, parameter_name: str) -> str:
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
            filename = self._generate_project_filename_only(
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

    @staticmethod
    def _generate_xmp_metadata(original_location: FileLocation) -> bytes:
        """Generate XMP metadata with Griptape Nodes custom namespace.

        Args:
            original_location: Original file location to embed in metadata

        Returns:
            XMP metadata as bytes
        """
        # Determine source location string
        match original_location:
            case ProjectFileLocation() | ExternalFileLocation():
                source_location_str = str(original_location.absolute_path)
            case _:
                source_location_str = str(original_location)

        # Create XMP packet with Griptape Nodes namespace
        xmp_template = f"""<?xpacket begin="" id="W5M0MpCehiHzreSzNTczkc9d"?>
<x:xmpmeta xmlns:x="adobe:ns:meta/">
  <rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">
    <rdf:Description rdf:about=""
        xmlns:griptape="https://griptape.ai/ns/griptape-nodes/1.0/">
      <griptape:sourceLocation>{source_location_str}</griptape:sourceLocation>
    </rdf:Description>
  </rdf:RDF>
</x:xmpmeta>
<?xpacket end="w"?>"""

        return xmp_template.encode("utf-8")

    def _generate_thumbnail(  # noqa: PLR0911
        self,
        artifact: ImageUrlArtifact,
        original_location: FileLocation,
    ) -> ImageUrlArtifact | None:
        """Generate thumbnail preview that mirrors original file structure.

        Creates thumbnail in previews/ subdirectory, maintaining the same relative path structure.
        Images smaller than THUMBNAIL_MAX_SIZE are not upscaled. If thumbnail generation fails,
        attempts to create a fallback error image.

        Args:
            artifact: Original image artifact to create thumbnail from
            original_location: Location of the original file

        Returns:
            ImageUrlArtifact for the thumbnail, or None if all generation attempts fail
        """
        # Generate preview location first (needs to succeed for both normal and fallback paths)
        try:
            preview_location = ArtifactProvider.generate_preview_location(original_location)
        except Exception as e:
            logger.warning("Unexpected error generating preview location for %s: %s", original_location, e)
            return None

        # Ensure preview directory exists
        try:
            preview_location.absolute_path.parent.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            logger.warning("Failed to create preview directory %s: %s", preview_location.absolute_path.parent, e)
            return None

        # Load and process the original image
        try:
            image_pil = load_pil_from_url(artifact.value)
        except Exception as e:
            logger.warning("Failed to load image from %s for thumbnail generation: %s", artifact.value, e)
            return self._generate_fallback_thumbnail(preview_location, "Failed to load image", original_location)

        # Create thumbnail (only shrinks if larger than max size, preserves aspect ratio)
        try:
            image_pil.thumbnail(self.THUMBNAIL_MAX_SIZE, Image.Resampling.LANCZOS)
        except Exception as e:
            logger.warning("Failed to resize image for thumbnail: %s", e)
            return self._generate_fallback_thumbnail(preview_location, "Failed to resize image", original_location)

        # Save thumbnail as WebP with XMP metadata
        try:
            xmp_metadata = self._generate_xmp_metadata(original_location)
            image_pil.save(preview_location.absolute_path, format="WEBP", quality=85, xmp=xmp_metadata)
        except Exception as e:
            logger.warning("Failed to save thumbnail to %s: %s", preview_location.absolute_path, e)
            return self._generate_fallback_thumbnail(preview_location, "Failed to save thumbnail", original_location)

        # Get externally accessible URL for the preview
        try:
            preview_url = self.get_externally_accessible_url(preview_location)
        except Exception as e:
            logger.warning("Failed to get preview URL for %s: %s", preview_location.absolute_path, e)
            return None

        return ImageUrlArtifact(value=preview_url)

    def _generate_fallback_thumbnail(
        self, preview_location: OnDiskFileLocation, error_text: str, original_location: FileLocation
    ) -> ImageUrlArtifact | None:
        """Generate a fallback error thumbnail with text.

        Args:
            preview_location: Where to save the fallback thumbnail
            error_text: Error message to display
            original_location: Original file location to embed in metadata

        Returns:
            ImageUrlArtifact for the fallback thumbnail, or None if creation fails
        """
        error_image_width = 400
        error_image_height = 400

        # Create a simple error image (gray with text)
        try:
            error_image = Image.new("RGB", (error_image_width, error_image_height), color=(200, 200, 200))
        except Exception as e:
            logger.warning("Failed to create fallback image: %s", e)
            return None

        # Draw error text
        try:
            draw = ImageDraw.Draw(error_image)
            font = ImageFont.load_default()
            text = f"Failed to create\nthumbnail:\n{error_text}"
            # Center text at center of image
            center_x = error_image_width // 2
            center_y = error_image_height // 2
            draw.multiline_text(
                (center_x, center_y), text, fill=(100, 100, 100), font=font, anchor="mm", align="center"
            )
        except Exception as e:
            logger.warning("Failed to draw text on fallback image: %s", e)
            return None

        # Save as WebP with XMP metadata
        try:
            xmp_metadata = self._generate_xmp_metadata(original_location)
            error_image.save(preview_location.absolute_path, format="WEBP", quality=85, xmp=xmp_metadata)
        except Exception as e:
            logger.warning("Failed to save fallback thumbnail to %s: %s", preview_location.absolute_path, e)
            return None

        # Get URL
        try:
            preview_url = self.get_externally_accessible_url(preview_location)
        except Exception as e:
            logger.warning("Failed to get URL for fallback thumbnail: %s", e)
            return None

        return ImageUrlArtifact(value=preview_url)

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

        download_location = ArtifactProvider.generate_project_file_location(subdirectory="inputs", filename=filename)

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
