"""PIL-based thumbnail generator using Pillow."""

from __future__ import annotations

from io import BytesIO
from pathlib import Path
from typing import Any

from PIL import Image

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


class PILThumbnailGenerator(BaseArtifactPreviewGenerator):
    """PIL-based thumbnail generator with dimension constraints.

    Resizes images to fit within max_width x max_height while preserving aspect ratio.
    """

    def __init__(
        self,
        source_file_location: str,
        preview_format: str,
        destination_preview_directory: str,
        destination_preview_file_name: str,
        params: dict[str, Any],
    ) -> None:
        """Initialize the generator.

        Args:
            source_file_location: Path to the source image file
            preview_format: Target format (webp, jpg, png)
            destination_preview_directory: Directory where the preview should be saved
            destination_preview_file_name: Filename for the preview
            params: Generator parameters (max_width, max_height - both required)
        """
        super().__init__(
            source_file_location, preview_format, destination_preview_directory, destination_preview_file_name, params
        )

        # Validate parameters using class method
        errors = self.validate_parameters(params)
        if errors:
            msg = f"Invalid parameters: {', '.join(errors)}"
            raise ValueError(msg)

        # Extract validated parameters
        self.max_width = params["max_width"]
        self.max_height = params["max_height"]

    @classmethod
    def get_friendly_name(cls) -> str:
        """Human-readable name."""
        return "Standard Thumbnail Generation"

    @classmethod
    def get_supported_source_formats(cls) -> set[str]:
        """Source formats this generator can process."""
        return {"png", "jpg", "jpeg", "gif", "bmp", "webp", "tiff", "tif", "tga"}

    @classmethod
    def get_supported_preview_formats(cls) -> set[str]:
        """Preview formats this generator produces."""
        return {"webp", "jpg", "png"}

    @classmethod
    def get_parameters(cls) -> dict[str, ProviderValue]:
        """Generator-specific parameters."""
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
        }

    @classmethod
    def validate_parameters(cls, params: dict[str, Any]) -> list[str] | None:
        """Validate parameters against schema.

        Args:
            params: Parameter dict to validate

        Returns:
            None if valid, otherwise list of error messages
        """
        errors = []
        schema = cls.get_parameters()

        # Check structural match (keys present)
        schema_keys = set(schema.keys())
        param_keys = set(params.keys())

        if schema_keys != param_keys:
            missing = schema_keys - param_keys
            extra = param_keys - schema_keys
            if missing:
                errors.append(f"Missing required parameters: {missing}")
            if extra:
                errors.append(f"Unknown parameters: {extra}")
            return errors

        # Validate each parameter
        cls._validate_positive_int(params, "max_width", errors)
        cls._validate_positive_int(params, "max_height", errors)

        if errors:
            return errors

        return None

    @staticmethod
    def _validate_positive_int(params: dict[str, Any], key: str, errors: list[str]) -> None:
        """Validate that a parameter is a positive integer."""
        value = params.get(key)
        if not isinstance(value, int):
            errors.append(f"{key} must be an integer, got {type(value).__name__}")
        elif value <= 0:
            errors.append(f"{key} must be positive, got {value}")

    async def attempt_generate_preview(self) -> str:
        """Execute preview generation.

        Raises:
            FileNotFoundError: If source image not found
            TypeError: If image cannot be loaded or format unsupported
            OSError: If preview generation fails (PIL/Pillow errors)
        """
        # Read the source image file
        read_request = ReadFileRequest(
            file_path=self.source_file_location, workspace_only=False, should_transform_image_content_to_thumbnail=False
        )
        read_result = GriptapeNodes.handle_request(read_request)

        if not isinstance(read_result, ReadFileResultSuccess):
            msg = f"Failed to read source image: {read_result.result_details}"
            raise FileNotFoundError(msg)

        # Type guard: read_result is now ReadFileResultSuccess
        image_data = read_result.content
        if isinstance(image_data, str):
            msg = "Source file is text, not binary image data"
            raise TypeError(msg)

        with Image.open(BytesIO(image_data)) as img:
            # Calculate thumbnail size (preserves aspect ratio, fits within max dimensions)
            img.thumbnail((self.max_width, self.max_height), Image.Resampling.LANCZOS)

            # Save to BytesIO
            output_buffer = BytesIO()
            img.save(output_buffer, format=self.preview_format.upper())
            output_bytes = output_buffer.getvalue()

        # Construct full path for writing
        destination_path = str(Path(self.destination_preview_directory) / self.destination_preview_file_name)

        # Write the preview file
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
