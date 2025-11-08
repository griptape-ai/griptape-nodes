import io
import tempfile
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, ClassVar

from griptape.artifacts import ImageUrlArtifact
from PIL import Image

from griptape_nodes.exe_types.core_types import Parameter, ParameterGroup, ParameterMode
from griptape_nodes.exe_types.node_types import AsyncResult, SuccessFailureNode
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes, logger
from griptape_nodes.traits.options import Options
from griptape_nodes_library.utils.file_utils import generate_filename
from griptape_nodes_library.utils.image_utils import (
    dict_to_image_url_artifact,
    load_pil_from_url,
)


class BaseImageProcessor(SuccessFailureNode, ABC):
    """Base class for image processing nodes with common functionality."""

    # Default image properties constants
    DEFAULT_WIDTH = 1920
    DEFAULT_HEIGHT = 1080
    DEFAULT_QUALITY = 95

    # Common resample filter options for different quality needs
    RESAMPLE_FILTER_OPTIONS: ClassVar[dict[str, str]] = {
        "nearest": "Nearest neighbor (fastest, lowest quality)",
        "box": "Box (good for downscaling)",
        "bilinear": "Bilinear (good balance)",
        "hamming": "Hamming (good for downscaling)",
        "bicubic": "Bicubic (high quality, slower)",
        "lanczos": "Lanczos (highest quality, slowest)",
    }

    # Common image format options
    IMAGE_FORMAT_OPTIONS: ClassVar[dict[str, str]] = {
        "auto": "Auto (preserve input format)",
        "PNG": "PNG (lossless, good for graphics)",
        "JPEG": "JPEG (lossy, good for photos)",
        "WEBP": "WebP (modern, good compression)",
    }

    # Extended format options for specialized use cases
    EXTENDED_FORMAT_OPTIONS: ClassVar[dict[str, str]] = {
        "BMP": "BMP (uncompressed, large files)",
        "TIFF": "TIFF (high quality, large files)",
    }

    def __init__(self, name: str, metadata: dict[Any, Any] | None = None) -> None:
        super().__init__(name, metadata)

        # Add image input parameter
        self.add_parameter(
            Parameter(
                name="input_image",
                input_types=["ImageUrlArtifact", "ImageArtifact"],
                type="ImageUrlArtifact",
                tooltip="The image to process",
                ui_options={
                    "clickable_file_browser": True,
                    "expander": True,
                },
            )
        )

        self._setup_custom_parameters()

        # Add output format parameter
        format_param = Parameter(
            name="output_format",
            type="str",
            default_value="auto",
            tooltip="Output image format. Choose 'auto' to preserve input format, or select a specific format.",
        )
        format_param.add_trait(Options(choices=list(self.IMAGE_FORMAT_OPTIONS.keys())))
        self.add_parameter(format_param)

        # Add quality parameter for lossy formats
        quality_param = Parameter(
            name="quality",
            type="string",
            default_value=str(self.DEFAULT_QUALITY),
            tooltip="Image quality for lossy formats (1-100, higher is better)",
        )
        quality_param.add_trait(Options(choices=["50", "60", "70", "80", "85", "90", "95", "100"]))
        self.add_parameter(quality_param)

        # Add output parameter
        self.add_parameter(
            Parameter(
                name="output",
                output_type="ImageUrlArtifact",
                allowed_modes={ParameterMode.OUTPUT},
                tooltip="The processed image",
                ui_options={"pulse_on_run": True, "expander": True},
            )
        )

        # Add status parameters using the SuccessFailureNode helper method
        self._create_status_parameters(
            result_details_tooltip="Details about the image processing result",
            result_details_placeholder="Details on the image processing will be presented here.",
            parameter_group_initially_collapsed=True,
        )

        self._setup_logging_group()

    @abstractmethod
    def _setup_custom_parameters(self) -> None:
        """Setup custom parameters specific to this image processor. Override in subclasses."""

    @abstractmethod
    def _get_processing_description(self) -> str:
        """Get a description of what this processor does. Override in subclasses."""

    @abstractmethod
    def _process_image(self, pil_image: Image.Image, **kwargs) -> Image.Image:
        """Process the PIL image. Override in subclasses."""

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

    def _validate_image_input(self) -> list[Exception] | None:
        """Common image input validation."""
        exceptions = []

        # Only validate if there's actually a value to validate
        image = self.parameter_values.get("input_image")
        if image is not None and (not hasattr(image, "value") or not image.value):
            msg = f"{self.name}: Input image parameter must have a valid value"
            exceptions.append(ValueError(msg))

        return exceptions if exceptions else None

    def _get_image_input_data(self) -> tuple[Image.Image, str]:
        """Get PIL image and detected format."""
        image = self.parameter_values.get("input_image")

        if not image:
            msg = f"{self.name}: Input image parameter is required"
            raise ValueError(msg)

        # Convert to ImageUrlArtifact if needed
        if hasattr(image, "to_dict"):
            image = dict_to_image_url_artifact(image.to_dict())

        # Ensure we have a valid image artifact with a value
        if not hasattr(image, "value") or not image.value:
            msg = f"{self.name}: Input image parameter must have a valid value"
            raise ValueError(msg)

        # Load PIL image using existing utility
        pil_image = load_pil_from_url(image.value)

        # Detect format
        detected_format = self._detect_image_format(pil_image)

        return pil_image, detected_format

    def _detect_image_format(self, pil_image: Image.Image) -> str:
        """Detect the format of the PIL image."""
        if pil_image.format:
            return pil_image.format.upper()

        # Default to PNG if format can't be detected
        return "PNG"

    def _get_output_format(self, input_format: str) -> str:
        """Get the output format based on user preference."""
        output_format = self.get_parameter_value("output_format") or "auto"

        if output_format == "auto":
            return input_format

        return output_format

    def _get_quality_setting(self) -> int:
        """Get the quality setting for lossy formats."""
        quality_value = self.get_parameter_value("quality")
        if quality_value is None:
            return self.DEFAULT_QUALITY
        return int(quality_value)

    def _create_temp_output_file(self, format_extension: str) -> tuple[str, Path]:
        """Create a temporary output file and return path."""
        with tempfile.NamedTemporaryFile(suffix=f".{format_extension.lower()}", delete=False) as output_file:
            output_path = Path(output_file.name)
        return str(output_path), output_path

    def _determine_target_mode(self, current_mode: str, format_extension: str) -> str:  # noqa: PLR0911, PLR0912, C901
        """Determine the target mode for conversion based on current mode and format.

        Args:
            current_mode: The current PIL image mode
            format_extension: The target format (e.g., "JPEG", "PNG", "WEBP")

        Returns:
            str: The target mode to convert to

        Raises:
            ValueError: If the format is unknown/unsupported
        """
        format_upper = format_extension.upper()

        match format_upper:
            case "JPEG" | "JPG":
                match current_mode:
                    case "RGBA":
                        return "RGB"
                    case "LA":
                        return "L"
                    case "P":
                        return "RGB"
                    case "CMYK":
                        return "RGB"

            case "PNG":
                match current_mode:
                    case "CMYK":
                        return "RGB"

            case "WEBP":
                match current_mode:
                    case "CMYK":
                        return "RGB"
                    case "L":
                        return "RGB"
                    case "LA":
                        return "RGBA"
                    case "P":
                        return "RGB"
                    case "1":
                        return "RGB"

            case "BMP":
                match current_mode:
                    case "CMYK":
                        return "RGB"
                    case "RGBA":
                        return "RGB"
                    case "LA":
                        return "L"

            case "TIFF":
                # TIFF supports almost everything, no conversions needed
                pass

            case _:
                msg = f"{self.name}: Unsupported image format '{format_extension}'"
                raise ValueError(msg)

        # Success path: current mode is compatible
        return current_mode

    def _create_converted_image_for_format_if_necessary(
        self, pil_image: Image.Image, format_extension: str
    ) -> Image.Image | None:
        """Convert image to compatible mode if necessary for the target format.

        Args:
            pil_image: The PIL Image to check and potentially convert
            format_extension: The target format (e.g., "JPEG", "PNG", "WEBP")

        Returns:
            Image.Image | None: A new converted image if conversion was necessary, None if original is compatible
        """
        current_mode = pil_image.mode

        # Determine target mode for conversion
        target_mode = self._determine_target_mode(current_mode, format_extension)

        # If target mode is same as current mode, no conversion needed
        if target_mode == current_mode:
            return None

        # Log the conversion
        logger.warning(
            f"{self.name}: Converting image from mode '{current_mode}' to '{target_mode}' for {format_extension.upper()} format"
        )

        # Special handling for RGBA -> RGB: composite with white background
        if current_mode == "RGBA" and target_mode == "RGB":
            background = Image.new("RGB", pil_image.size, (255, 255, 255))
            background.paste(pil_image, mask=pil_image.split()[3])  # Use alpha channel as mask
            return background

        # Standard conversion for all other cases
        converted_image = pil_image.copy()
        return converted_image.convert(target_mode)

    def _save_image_artifact(self, pil_image: Image.Image, format_extension: str, suffix: str = "") -> ImageUrlArtifact:
        """Save PIL image to static file and return ImageUrlArtifact."""
        # Generate meaningful filename based on workflow and node
        filename = self._generate_filename(suffix, format_extension)

        # Check if image needs conversion for the target format.
        # This will create a copy in the new format ONLY if the source image required a conversion
        # (does not alter the original).
        converted_image = self._create_converted_image_for_format_if_necessary(pil_image, format_extension)
        image_to_save = converted_image if converted_image is not None else pil_image

        # Convert PIL image to bytes and save with our custom filename
        buffer = io.BytesIO()
        image_to_save.save(buffer, format=format_extension.upper())
        image_bytes = buffer.getvalue()

        # Save to static file with our custom filename
        url = GriptapeNodes.StaticFilesManager().save_static_file(image_bytes, filename)
        return ImageUrlArtifact(url)

    def _pil_to_bytes(self, pil_image: Image.Image, format_extension: str) -> bytes:
        """Convert PIL image to bytes in the specified format."""
        # Use existing utility for basic conversion
        # Note: This utility doesn't support quality settings, so we keep this method
        # for cases where we need quality control
        output_format = format_extension.upper()
        quality = self._get_quality_setting()

        # Check if image needs conversion for the target format.
        # This will create a copy in the new format ONLY if the source image required a conversion
        # (does not alter the original).
        converted_image = self._create_converted_image_for_format_if_necessary(pil_image, format_extension)
        image_to_save = converted_image if converted_image is not None else pil_image

        # Prepare save options
        save_kwargs = {}

        if output_format in ["JPEG", "JPG"]:
            save_kwargs["quality"] = quality
            save_kwargs["optimize"] = True
        elif output_format == "WEBP":
            save_kwargs["quality"] = quality
            save_kwargs["lossless"] = False
        elif output_format == "PNG":
            save_kwargs["optimize"] = True

        # Convert to bytes
        buffer = io.BytesIO()
        image_to_save.save(buffer, format=output_format, **save_kwargs)
        buffer.seek(0)
        return buffer.getvalue()

    def _cleanup_temp_file(self, file_path: Path) -> None:
        """Clean up temporary file with error handling."""
        try:
            file_path.unlink(missing_ok=True)
        except Exception as e:
            self.append_value_to_parameter("logs", f"Warning: Failed to clean up temporary file: {e}\n")

    def _log_image_properties(self, pil_image: Image.Image) -> None:
        """Log detected image properties."""
        self.append_value_to_parameter(
            "logs",
            f"Processing image: {pil_image.width}x{pil_image.height}, mode: {pil_image.mode}, format: {pil_image.format}\n",
        )

    def _log_format_detection(self, detected_format: str) -> None:
        """Log detected image format."""
        self.append_value_to_parameter("logs", f"Detected image format: {detected_format}\n")

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

        # If there are validation errors, set the status to failure
        if exceptions:
            error_messages = [str(e) for e in exceptions]
            error_details = f"Validation failed: {'; '.join(error_messages)}"
            self._set_status_results(was_successful=False, result_details=f"FAILURE: {error_details}")

        return exceptions if exceptions else None

    def _validate_custom_parameters(self) -> list[Exception] | None:
        """Validate custom parameters. Override in subclasses if needed."""
        return None

    def _process(self, pil_image: Image.Image, detected_format: str, **kwargs) -> None:
        """Common processing wrapper."""
        self.append_value_to_parameter("logs", f"{self._get_processing_description()}\n")

        # Process image using the custom implementation
        processed_image = self._process_image(pil_image, **kwargs)

        # Get output format
        output_format = self._get_output_format(detected_format)

        # Get output suffix from subclass
        suffix = self._get_output_suffix(**kwargs)

        # Save processed image
        output_artifact = self._save_image_artifact(processed_image, output_format, suffix)

        self.append_value_to_parameter(
            "logs", f"Successfully processed image with suffix: {suffix}.{output_format.lower()}\n"
        )

        # Save to parameter
        self.parameter_output_values["output"] = output_artifact

    def _get_output_suffix(self, **kwargs) -> str:  # noqa: ARG002
        """Get the output filename suffix. Override in subclasses if needed."""
        return ""

    def process(self) -> AsyncResult[None]:
        """Main workflow execution method following LoadImage pattern."""
        # Reset execution state and result details at the start of each run
        self._clear_execution_status()

        # Clear output values to prevent downstream nodes from getting stale data on errors
        self.parameter_output_values["output"] = None

        # Get input image
        input_image = self.get_parameter_value("input_image")

        if input_image is None:
            error_details = "No input image provided"
            self._set_status_results(was_successful=False, result_details=f"FAILURE: {error_details}")
            self._handle_failure_exception(RuntimeError(error_details))
            return

        try:
            # Get image input data
            pil_image, detected_format = self._get_image_input_data()
            self._log_format_detection(detected_format)
            self._log_image_properties(pil_image)

            # Get custom parameters from subclasses
            custom_params = self._get_custom_parameters()

            # Initialize logs
            self.append_value_to_parameter("logs", f"[Processing {self._get_processing_description()}..]\n")

            # Run the image processing
            self.append_value_to_parameter("logs", "[Started image processing..]\n")
            yield lambda: self._process(pil_image, detected_format, **custom_params)
            self.append_value_to_parameter("logs", "[Finished image processing.]\n")

            # Success case
            success_details = f"Successfully processed image: {self._get_processing_description()} ({pil_image.width}x{pil_image.height})"
            self._set_status_results(was_successful=True, result_details=f"SUCCESS: {success_details}")
            logger.info(f"{self.__class__.__name__} '{self.name}': {success_details}")

        except Exception as e:
            error_details = f"Failed to process image: {e}"
            self._set_status_results(was_successful=False, result_details=f"FAILURE: {error_details}")
            logger.error(f"{self.__class__.__name__} '{self.name}': {error_details}")
            self._handle_failure_exception(e)

    def _get_custom_parameters(self) -> dict[str, Any]:
        """Get custom parameters for processing. Override in subclasses if needed."""
        return {}

    def _generate_filename(self, suffix: str = "", extension: str = "png") -> str:
        """Generate a meaningful filename based on workflow and node information."""
        return generate_filename(
            node_name=self.name,
            suffix=suffix,
            extension=extension,
        )

    def _generate_processed_image_filename(self, extension: str = "png") -> str:
        """Generate a meaningful filename for processed images with processing parameters."""
        # Get the processing suffix from the node's _get_output_suffix method if it exists
        processing_suffix = ""
        try:
            # Get current processing parameters
            custom_params = self._get_custom_parameters()
            if custom_params:
                processing_suffix = self._get_output_suffix(**custom_params)
        except Exception:
            # If _get_output_suffix doesn't exist or fails, use empty suffix
            processing_suffix = ""

        return self._generate_filename(processing_suffix, extension)
