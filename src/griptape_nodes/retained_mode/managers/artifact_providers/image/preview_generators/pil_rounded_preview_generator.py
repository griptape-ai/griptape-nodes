"""Rounded image preview generator using PIL/Pillow."""

from __future__ import annotations

from io import BytesIO
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw

from griptape_nodes.retained_mode.events.os_events import (
    ExistingFilePolicy,
    ReadFileRequest,
    ReadFileResultSuccess,
    WriteFileRequest,
    WriteFileResultSuccess,
)
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
from griptape_nodes.retained_mode.managers.artifact_providers.base_artifact_preview_generator import (
    BaseArtifactPreviewGenerator,
)
from griptape_nodes.retained_mode.managers.artifact_providers.base_artifact_provider import (
    ProviderValue,
)


class PILRoundedPreviewGenerator(BaseArtifactPreviewGenerator):
    """Generate image previews with rounded corners and transparent backgrounds.

    Uses PIL/Pillow to create thumbnails with rounded corners. Corners are transparent
    for PNG/WEBP output formats, or composited onto white background for JPEG.
    """

    def __init__(
        self,
        source_file_location: str,
        preview_format: str,
        destination_preview_directory: str,
        destination_preview_file_name: str,
        params: dict[str, Any],
    ) -> None:
        """Initialize the rounded preview generator.

        Args:
            source_file_location: Path to the source artifact file
            preview_format: Target format for the preview (e.g., "png", "jpg", "webp")
            destination_preview_directory: Directory where the preview should be saved
            destination_preview_file_name: Filename for the preview
            params: Generator-specific parameters

        Raises:
            TypeError: If parameters are invalid (wrong type or value)
        """
        super().__init__(
            source_file_location,
            preview_format,
            destination_preview_directory,
            destination_preview_file_name,
            params,
        )

        # Extract parameters
        self.max_width = params["max_width"]
        self.max_height = params["max_height"]
        self.corner_radius = params["corner_radius"]

        # Validate max dimensions
        if not isinstance(self.max_width, int) or self.max_width <= 0:
            msg = f"max_width must be positive int, got {self.max_width}"
            raise TypeError(msg)
        if not isinstance(self.max_height, int) or self.max_height <= 0:
            msg = f"max_height must be positive int, got {self.max_height}"
            raise TypeError(msg)

        # Validate corner_radius
        if not isinstance(self.corner_radius, int) or self.corner_radius < 0:
            msg = f"corner_radius must be non-negative int, got {self.corner_radius}"
            raise TypeError(msg)

    @classmethod
    def get_friendly_name(cls) -> str:
        """Human-readable name for this generator.

        Returns:
            The friendly name for this generator
        """
        return "Rounded Image Preview Generation"

    @classmethod
    def get_supported_source_formats(cls) -> set[str]:
        """Source formats this generator can process.

        Returns:
            Set of lowercase file extensions WITHOUT leading dots
        """
        return {"png", "jpg", "jpeg", "gif", "bmp", "webp", "tiff", "tif", "tga"}

    @classmethod
    def get_supported_preview_formats(cls) -> set[str]:
        """Preview formats this generator produces.

        Returns:
            Set of lowercase preview format extensions WITHOUT leading dots
        """
        return {"webp", "jpg", "png"}

    @classmethod
    def get_parameters(cls) -> dict[str, ProviderValue]:
        """Get metadata about generator parameters.

        Returns:
            Dict mapping parameter names to their metadata
        """
        return {
            "max_width": ProviderValue(
                default_value=1024,
                required=True,
                json_schema_type="integer",
                description="Maximum width in pixels for generated preview",
            ),
            "max_height": ProviderValue(
                default_value=1024,
                required=True,
                json_schema_type="integer",
                description="Maximum height in pixels for generated preview",
            ),
            "corner_radius": ProviderValue(
                default_value=20,
                required=True,
                json_schema_type="integer",
                description="Radius of rounded corners in pixels (0 = no rounding)",
            ),
        }

    async def attempt_generate_preview(self) -> str:
        """Attempt to generate preview file with rounded corners.

        Writes file to destination directory using provided filename.

        Returns:
            Filename of generated preview

        Raises:
            FileNotFoundError: If source image cannot be read
            TypeError: If source file is not binary image data
            OSError: If preview write fails
        """
        # Step 1: Read source file
        read_request = ReadFileRequest(
            file_path=self.source_file_location,
            workspace_only=False,
            should_transform_image_content_to_thumbnail=False,
        )
        read_result = GriptapeNodes.handle_request(read_request)

        if not isinstance(read_result, ReadFileResultSuccess):
            msg = f"Failed to read source image: {read_result.result_details}"
            raise FileNotFoundError(msg)

        # Step 2: Verify binary data
        image_data = read_result.content
        if isinstance(image_data, str):
            msg = "Source file is text, not binary image data"
            raise TypeError(msg)

        # Step 3: Process image with PIL
        with Image.open(BytesIO(image_data)) as img:
            # Resize to fit max dimensions (preserves aspect ratio)
            img.thumbnail((self.max_width, self.max_height), Image.Resampling.LANCZOS)

            # Convert to RGBA for alpha channel support
            if img.mode != "RGBA":
                rgba_img = img.convert("RGBA")
            else:
                rgba_img = img

            # Apply rounded corners
            rounded_img = self._apply_rounded_corners(rgba_img, self.corner_radius)

            # Handle format-specific output
            if self.preview_format.lower() in ("jpg", "jpeg"):
                # JPEG doesn't support transparency - composite onto white background
                white_background = Image.new("RGB", rounded_img.size, (255, 255, 255))
                white_background.paste(rounded_img, (0, 0), rounded_img)
                final_img = white_background
            else:
                # PNG/WEBP support transparency
                final_img = rounded_img

            # Save to buffer
            output_buffer = BytesIO()
            # Normalize format for PIL (JPG -> JPEG)
            pil_format = "JPEG" if self.preview_format.lower() == "jpg" else self.preview_format.upper()
            final_img.save(output_buffer, format=pil_format)
            output_bytes = output_buffer.getvalue()

        # Step 4: Write output file
        destination_path = str(Path(self.destination_preview_directory) / self.destination_preview_file_name)

        write_request = WriteFileRequest(
            file_path=destination_path,
            content=output_bytes,
            create_parents=True,
            existing_file_policy=ExistingFilePolicy.OVERWRITE,
        )
        write_result = GriptapeNodes.handle_request(write_request)

        if not isinstance(write_result, WriteFileResultSuccess):
            msg = f"Failed to write preview image: {write_result.result_details}"
            raise OSError(msg)

        return self.destination_preview_file_name

    def _apply_rounded_corners(self, img: Image.Image, radius: int) -> Image.Image:
        """Apply rounded corners to image using alpha mask.

        Args:
            img: Source image (will be converted to RGBA if needed)
            radius: Corner radius in pixels (will be clamped to prevent over-rounding)

        Returns:
            RGBA image with transparent rounded corners
        """
        # Skip if no rounding requested
        if radius <= 0:
            return img

        # Clamp radius to prevent over-rounding
        max_radius = min(img.width, img.height) // 2
        effective_radius = min(radius, max_radius)

        # Create mask for rounded corners
        mask = Image.new("L", img.size, 0)
        draw = ImageDraw.Draw(mask)
        draw.rounded_rectangle([(0, 0), (img.width - 1, img.height - 1)], radius=effective_radius, fill=255)

        # Apply mask to alpha channel
        img.putalpha(mask)
        return img
