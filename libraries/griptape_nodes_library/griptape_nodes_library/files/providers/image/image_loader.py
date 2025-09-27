from typing import Any, ClassVar

from griptape.artifacts import ImageUrlArtifact

from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.retained_mode.griptape_nodes import logger
from griptape_nodes.traits.options import Options
from griptape_nodes_library.files.path_utils import PathUtils
from griptape_nodes_library.files.providers.artifact_load_provider import ArtifactLoadProvider, ArtifactParameterDetails
from griptape_nodes_library.files.providers.validation_result import ProviderValidationResult
from griptape_nodes_library.utils.file_utils import generate_filename
from griptape_nodes_library.utils.image_utils import (
    dict_to_image_url_artifact,
    extract_channel_from_image,
    load_pil_from_url,
    save_pil_image_with_named_filename,
)


class ImageLoadProvider(ArtifactLoadProvider):
    """Provider for loading and processing image files."""

    SUPPORTED_EXTENSIONS: ClassVar[set[str]] = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg"}

    def __init__(self, artifact: Any = None, internal_url: str = "", path: str = "") -> None:
        """Initialize image provider with artifact information."""
        super().__init__(artifact, internal_url, path)

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
        return "png"

    def get_artifact_parameter_details(self) -> ArtifactParameterDetails:
        return ArtifactParameterDetails(
            input_types=["ImageUrlArtifact", "ImageArtifact", "str"],
            type="ImageUrlArtifact",
            output_type="ImageUrlArtifact",
            display_name="Image",
        )

    def get_artifact_ui_options(self) -> dict[str, Any]:
        """Get image-specific UI options including mask editing."""
        return {
            "clickable_file_browser": True,
            "expander": True,
            "edit_mask": True,
            "display_name": "Image or Path to Image",
        }

    def get_additional_parameters(self) -> list[Parameter]:
        """Get image-specific parameters."""
        # Mask channel parameter
        channel_param = Parameter(
            name="mask_channel",
            type="str",
            tooltip="Channel to extract as mask (red, green, blue, or alpha).",
            default_value="alpha",
            ui_options={"hide": True},
        )
        channel_param.add_trait(Options(choices=["red", "green", "blue", "alpha"]))

        # Output mask parameter
        output_mask_param = Parameter(
            name="output_mask",
            type="ImageUrlArtifact",
            tooltip="The Mask for the image",
            ui_options={"expander": True, "hide": True},
            allowed_modes={ParameterMode.OUTPUT},
        )

        return [channel_param, output_mask_param]

    def validate_from_path(self, path_input: str, current_parameter_values: dict[str, Any]) -> ProviderValidationResult:  # noqa: PLR0911
        """Validate and process a path input into complete image loading result."""
        errors = []

        try:
            # Normalize and validate path
            path_str = PathUtils.normalize_path_input(path_input)
            if not path_str:
                # Empty path is valid - just return success with empty values
                return ProviderValidationResult()

            # Check if it's a supported image file
            if PathUtils.is_url(path_str):
                # For URLs, do basic check
                if not any(ext in path_str.lower() for ext in self.SUPPORTED_EXTENSIONS):
                    errors.append(
                        f"URL does not appear to be a supported image format: {', '.join(self.SUPPORTED_EXTENSIONS)}"
                    )
            else:
                # For file paths, check extension
                file_path = PathUtils.to_path_object(path_str)
                if not file_path:
                    errors.append(f"Invalid path format: {path_str}")
                    return ProviderValidationResult(error_messages=errors)

                if file_path.suffix.lower() not in self.SUPPORTED_EXTENSIONS:
                    errors.append(
                        f"Unsupported image format: {file_path.suffix}. Supported: {', '.join(self.SUPPORTED_EXTENSIONS)}"
                    )
                    return ProviderValidationResult(error_messages=errors)

                if not file_path.exists():
                    errors.append(f"Image file not found: {file_path}")
                    return ProviderValidationResult(error_messages=errors)

            # Process the path to internal URL
            internal_url = self._process_path_to_internal_url(path_str)

            # Create the image artifact
            artifact = ImageUrlArtifact(value=internal_url)

            # Validate the image can actually be loaded
            try:
                load_pil_from_url(internal_url)
            except Exception as e:
                errors.append(f"Cannot load image from URL: {e}")
                return ProviderValidationResult(error_messages=errors)

            # Process dynamic parameters (mask extraction)
            dynamic_updates = self._process_mask_extraction(artifact, current_parameter_values)

            return ProviderValidationResult(
                artifact=artifact, internal_url=internal_url, path=path_str, dynamic_parameter_updates=dynamic_updates
            )

        except Exception as e:
            errors.append(f"Image validation failed: {e}")
            return ProviderValidationResult(error_messages=errors)

    def validate_from_artifact(
        self, artifact_input: Any, current_parameter_values: dict[str, Any]
    ) -> ProviderValidationResult:
        """Validate and process an artifact input into complete image loading result."""
        errors = []

        try:
            # Normalize input to ImageUrlArtifact if it's a dict
            normalized_artifact = artifact_input
            if isinstance(artifact_input, dict):
                try:
                    normalized_artifact = dict_to_image_url_artifact(artifact_input)
                except Exception as e:
                    errors.append(f"Cannot convert dict to ImageUrlArtifact: {e}")
                    return ProviderValidationResult(error_messages=errors)

            # Extract URL from artifact
            url = self._extract_url_from_artifact_input(normalized_artifact)
            if not url:
                errors.append(f"Cannot extract URL from artifact of type: {type(normalized_artifact).__name__}")
                return ProviderValidationResult(error_messages=errors)

            # Validate the image can be loaded
            try:
                load_pil_from_url(url)
            except Exception as e:
                errors.append(f"Cannot load image from artifact URL: {e}")
                return ProviderValidationResult(error_messages=errors)

            # Create display path from URL
            display_path = self._extract_display_path_from_url(url)

            # Process dynamic parameters (mask extraction)
            dynamic_updates = self._process_mask_extraction(normalized_artifact, current_parameter_values)

            return ProviderValidationResult(
                artifact=normalized_artifact,
                internal_url=url,
                path=display_path,
                dynamic_parameter_updates=dynamic_updates,
            )

        except Exception as e:
            errors.append(f"Artifact validation failed: {e}")
            return ProviderValidationResult(error_messages=errors)

    def _process_path_to_internal_url(self, path_str: str) -> str:
        """Convert file path or external URL to internal serving URL."""
        if PathUtils.is_url(path_str):
            # External URLs can be used directly - no need to download for now
            return path_str

        # Local file path - for now return absolute path as URL
        # In production this would upload to static serving
        from pathlib import Path

        file_path = Path(path_str)
        if file_path.is_absolute():
            return f"file://{file_path}"
        return f"file://{file_path.resolve()}"

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

    def _process_mask_extraction(self, artifact: Any, current_values: dict[str, Any]) -> dict[str, Any]:
        """Process mask extraction if mask_channel is set."""
        updates = {}

        mask_channel = current_values.get("mask_channel")
        if not mask_channel or not artifact:
            return updates

        try:
            # Normalize input to ImageUrlArtifact
            if isinstance(artifact, dict):
                artifact = dict_to_image_url_artifact(artifact)

            if not isinstance(artifact, ImageUrlArtifact):
                return updates

            # Load image and extract the specified channel as mask
            image_pil = load_pil_from_url(artifact.value)
            mask = extract_channel_from_image(image_pil, mask_channel, "image")

            # Generate filename based on current node context (if available)
            # For now use a simple approach since we don't have node reference
            filename = generate_filename(
                node_name="image_load",  # Default node name
                suffix="_load_mask",
                extension="png",
            )
            output_artifact = save_pil_image_with_named_filename(mask, filename, "PNG")

            # Return the mask as a dynamic parameter update
            updates["output_mask"] = output_artifact

        except Exception as e:
            # Use warning for mask extraction failures to match load_image.py behavior
            logger.warning(f"Mask extraction failed: {e}")

        return updates
