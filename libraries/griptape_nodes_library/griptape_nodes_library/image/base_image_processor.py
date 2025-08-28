import tempfile
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, ClassVar

from griptape.artifacts import ImageUrlArtifact
from PIL import Image

from griptape_nodes.exe_types.core_types import Parameter, ParameterGroup, ParameterMode
from griptape_nodes.exe_types.node_types import ControlNode
from griptape_nodes.traits.options import Options
from griptape_nodes_library.utils.image_utils import (
    dict_to_image_url_artifact,
    load_pil_from_url,
    save_pil_image_to_static_file,
    validate_pil_format,
)


class BaseImageProcessor(ControlNode, ABC):
    """Base class for image processing nodes with common PIL functionality."""

    # Default image properties constants
    DEFAULT_WIDTH = 1920
    DEFAULT_HEIGHT = 1080
    DEFAULT_QUALITY = 95

    # Common image format options
    IMAGE_FORMAT_OPTIONS: ClassVar[dict[str, str]] = {
        "PNG": "PNG (Lossless, supports transparency)",
        "JPEG": "JPEG (Lossy, good compression)",
        "WEBP": "WebP (Modern, good compression)",
        "GIF": "GIF (Supports animation)",
        "BMP": "BMP (Uncompressed)",
        "TIFF": "TIFF (High quality, large files)",
    }

    # Common resampling options for PIL
    RESAMPLING_OPTIONS: ClassVar[dict[str, str]] = {
        "NEAREST": "Nearest neighbor (fast, pixelated)",
        "BILINEAR": "Bilinear (smooth, good quality)",
        "BICUBIC": "Bicubic (high quality, slower)",
        "LANCZOS": "Lanczos (best quality, slowest)",
    }

    def __init__(self, name: str, metadata: dict[Any, Any] | None = None) -> None:
        super().__init__(name, metadata)
        self.add_parameter(
            Parameter(
                name="input_image",
                input_types=["ImageArtifact", "ImageUrlArtifact"],
                type="ImageUrlArtifact",
                tooltip="The image to process",
                ui_options={
                    "clickable_file_browser": True,
                    "expander": True,
                    "display_name": "Input Image",
                },
            )
        )

        self._setup_custom_parameters()

        # Add output format parameter
        format_param = Parameter(
            name="output_format",
            type="str",
            default_value="PNG",
            tooltip="Output image format. PNG is recommended for images with transparency.",
        )
        format_param.add_trait(Options(choices=list(self.IMAGE_FORMAT_OPTIONS.keys())))
        self.add_parameter(format_param)

        # Add quality parameter for lossy formats
        quality_param = Parameter(
            name="quality",
            type="int",
            default_value=95,
            tooltip="Image quality (1-100). Higher values mean better quality but larger files.",
        )
        self.add_parameter(quality_param)

        # Add resampling parameter for operations that resize
        resampling_param = Parameter(
            name="resampling",
            type="str",
            default_value="LANCZOS",
            tooltip="Resampling method for resize operations",
        )
        resampling_param.add_trait(Options(choices=list(self.RESAMPLING_OPTIONS.keys())))
        self.add_parameter(resampling_param)

        self.add_parameter(
            Parameter(
                name="output",
                output_type="ImageUrlArtifact",
                allowed_modes={ParameterMode.OUTPUT},
                tooltip="The processed image",
                ui_options={"pulse_on_run": True, "expander": True},
            )
        )

        self._setup_logging_group()

    @abstractmethod
    def _setup_custom_parameters(self) -> None:
        """Setup custom parameters specific to this image processor. Override in subclasses."""

    @abstractmethod
    def _get_processing_description(self) -> str:
        """Get a description of what this processor does. Override in subclasses."""

    @abstractmethod
    def _process_image(self, image: Image.Image, **kwargs) -> Image.Image:
        """Process the image using PIL. Override in subclasses."""

    def _setup_logging_group(self) -> None:
        """Setup the common logging parameter group."""
        with ParameterGroup(name="Logs") as logs_group:
            Parameter(
                name="logs",
                type="str",
                tooltip="Displays processing logs and detailed events if enabled.",
                ui_options={"multiline": True, "placeholder_text": "Logs"},
                allowed_modes={ParameterMode.OUTPUT},
            )
        logs_group.ui_options = {"hide": True}  # Hide the logs group by default
        self.add_node_element(logs_group)

    def _get_resampling_method(self) -> Image.Resampling:
        """Get PIL resampling method from parameter value."""
        resampling = self.get_parameter_value("resampling") or "LANCZOS"
        
        resampling_map = {
            "NEAREST": Image.Resampling.NEAREST,
            "BILINEAR": Image.Resampling.BILINEAR,
            "BICUBIC": Image.Resampling.BICUBIC,
            "LANCZOS": Image.Resampling.LANCZOS,
        }
        
        return resampling_map.get(resampling, Image.Resampling.LANCZOS)

    def _get_quality_setting(self) -> int:
        """Get quality setting for lossy formats."""
        quality = self.get_parameter_value("quality") or 95
        return max(1, min(100, quality))  # Clamp between 1-100

    def _get_output_format(self) -> str:
        """Get output format with validation."""
        format_str = self.get_parameter_value("output_format") or "PNG"
        validate_pil_format(format_str, "output_format")
        return format_str

    def _validate_image_input(self) -> list[Exception] | None:
        """Common image input validation."""
        exceptions = []

        # Validate that we have an image
        input_image = self.parameter_values.get("input_image")
        if not input_image:
            msg = f"{self.name}: Input image parameter is required"
            exceptions.append(ValueError(msg))

        # Make sure it's an image artifact
        if not isinstance(input_image, ImageUrlArtifact):
            msg = f"{self.name}: Input image parameter must be an ImageUrlArtifact"
            exceptions.append(ValueError(msg))

        # Make sure it has a value
        if hasattr(input_image, "value") and not input_image.value:  # type: ignore  # noqa: PGH003
            msg = f"{self.name}: Input image parameter must have a value"
            exceptions.append(ValueError(msg))

        return exceptions if exceptions else None

    def _get_image_input_data(self) -> tuple[str, Image.Image]:
        """Get image input URL and load PIL Image."""
        input_image = self.parameter_values.get("input_image")
        
        # Normalize dict input to ImageUrlArtifact
        if isinstance(input_image, dict):
            input_image = dict_to_image_url_artifact(input_image)
        
        if input_image is None or not hasattr(input_image, "value") or not input_image.value:
            raise ValueError("Input image is required and must have a valid value")
        
        input_url = input_image.value
        pil_image = load_pil_from_url(input_url)
        
        return input_url, pil_image

    def _create_temp_output_file(self, format_extension: str) -> tuple[str, Path]:
        """Create a temporary output file and return path."""
        with tempfile.NamedTemporaryFile(suffix=f".{format_extension}", delete=False) as output_file:
            output_path = Path(output_file.name)
        return str(output_path), output_path

    def _save_image_artifact(self, image: Image.Image, format_extension: str, suffix: str = "") -> ImageUrlArtifact:
        """Save PIL image to static file and return ImageUrlArtifact."""
        # Get output format and quality settings
        output_format = self._get_output_format()
        quality = self._get_quality_setting()
        
        # For now, use the basic save function since it doesn't support quality
        # TODO: Enhance save_pil_image_to_static_file to support quality parameter
        output_artifact = save_pil_image_to_static_file(
            image, 
            image_format=output_format
        )
        
        return output_artifact

    def _log_image_properties(self, image: Image.Image) -> None:
        """Log detected image properties."""
        self.append_value_to_parameter(
            "logs", f"Input image: {image.width}x{image.height}, mode: {image.mode}\n"
        )

    def _log_format_settings(self, output_format: str, quality: int) -> None:
        """Log output format and quality settings."""
        if output_format in ["JPEG", "WEBP"]:
            self.append_value_to_parameter(
                "logs", f"Output format: {output_format}, quality: {quality}\n"
            )
        else:
            self.append_value_to_parameter(
                "logs", f"Output format: {output_format} (lossless)\n"
            )

    def validate_before_node_run(self) -> list[Exception] | None:
        """Common image input validation."""
        exceptions = []

        # Use base class validation for image input
        base_exceptions = self._validate_image_input()
        if base_exceptions:
            exceptions.extend(base_exceptions)

        # Add custom validation from subclasses
        custom_exceptions = self._validate_custom_parameters()
        if custom_exceptions:
            exceptions.extend(custom_exceptions)

        return exceptions if exceptions else None

    def _validate_custom_parameters(self) -> list[Exception] | None:
        """Validate custom parameters. Override in subclasses if needed."""
        return None

    def _process(self, input_url: str, pil_image: Image.Image, **kwargs) -> None:
        """Common processing wrapper."""
        try:
            self.append_value_to_parameter("logs", f"{self._get_processing_description()}\n")

            # Log input image properties
            self._log_image_properties(pil_image)

            # Get output settings
            output_format = self._get_output_format()
            quality = self._get_quality_setting()
            self._log_format_settings(output_format, quality)

            # Process image using the custom implementation
            processed_image = self._process_image(pil_image, **kwargs)

            # Get output suffix from subclass
            suffix = self._get_output_suffix(**kwargs)

            # Save processed image
            output_artifact = self._save_image_artifact(processed_image, output_format.lower(), suffix)

            self.append_value_to_parameter(
                "logs", f"Successfully processed image with suffix: {suffix}.{output_format.lower()}\n"
            )

            # Save to parameter
            self.parameter_output_values["output"] = output_artifact

        except Exception as e:
            error_message = str(e)
            msg = f"{self.name}: Error processing image: {error_message}"
            self.append_value_to_parameter("logs", f"ERROR: {msg}\n")
            raise ValueError(msg) from e

    def _get_output_suffix(self, **kwargs) -> str:  # noqa: ARG002
        """Get the output filename suffix. Override in subclasses if needed."""
        return ""

    def _get_custom_parameters(self) -> dict[str, Any]:
        """Get custom parameters for processing. Override in subclasses if needed."""
        return {}

    def process(self) -> None:
        """Common processing entry point."""
        # Get image input data
        input_url, pil_image = self._get_image_input_data()

        # Get custom parameters from subclasses
        custom_params = self._get_custom_parameters()

        # Initialize logs
        self.append_value_to_parameter("logs", f"[Processing {self._get_processing_description()}..]\n")

        try:
            # Run the image processing
            self.append_value_to_parameter("logs", "[Started image processing..]\n")
            self._process(input_url, pil_image, **custom_params)
            self.append_value_to_parameter("logs", "[Finished image processing.]\n")

        except Exception as e:
            error_message = str(e)
            msg = f"{self.name}: Error processing image: {error_message}"
            self.append_value_to_parameter("logs", f"ERROR: {msg}\n")
            raise ValueError(msg) from e

    def _generate_filename(self, suffix: str = "", extension: str = "png") -> str:
        """Generate a meaningful filename based on workflow and node information."""
        from datetime import UTC, datetime

        # Get workflow and node context
        workflow_name = "unknown_workflow"
        node_name = self.name

        # Try to get workflow name from context
        try:
            from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

            context_manager = GriptapeNodes.ContextManager()
            workflow_name = context_manager.get_current_workflow_name()
        except Exception as e:
            self.append_value_to_parameter("logs", f"Warning: Error getting workflow name: {e}\n")

        # Clean up names for filename use
        workflow_name = "".join(c for c in workflow_name if c.isalnum() or c in ("-", "_")).rstrip()
        node_name = "".join(c for c in node_name if c.isalnum() or c in ("-", "_")).rstrip()

        # Get current timestamp for cache busting
        timestamp = int(datetime.now(UTC).timestamp())

        # Create filename with meaningful structure and timestamp as query parameter
        filename = f"{workflow_name}_{node_name}{suffix}.{extension}?t={timestamp}"

        return filename
