from io import BytesIO
from typing import Any

import httpx
from griptape.artifacts import ImageUrlArtifact
from PIL import Image, ImageDraw, ImageFont

from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import SuccessFailureNode
from griptape_nodes.retained_mode.events.static_file_events import (
    CreateStaticFileDownloadUrlRequest,
    CreateStaticFileDownloadUrlResultFailure,
    CreateStaticFileDownloadUrlResultSuccess,
    CreateStaticFileUploadUrlRequest,
    CreateStaticFileUploadUrlResultFailure,
    CreateStaticFileUploadUrlResultSuccess,
)
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes, logger
from griptape_nodes.traits.options import Options
from griptape_nodes_library.utils.color_utils import NAMED_COLORS, parse_color_to_rgba
from griptape_nodes_library.utils.file_utils import generate_filename

# Constants
TEXT_PREVIEW_LENGTH = 50


class AddTextToImage(SuccessFailureNode):
    """Node to create an image with text rendered on it."""

    def __init__(self, name: str, metadata: dict[Any, Any] | None = None) -> None:
        super().__init__(name, metadata)

        # Get list of named colors for dropdown options
        color_options = list(NAMED_COLORS.keys())

        # Image dimensions parameters
        self.add_parameter(
            Parameter(
                name="width",
                type="int",
                default_value=512,
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY, ParameterMode.OUTPUT},
                tooltip="Width of the image in pixels",
            )
        )

        self.add_parameter(
            Parameter(
                name="height",
                type="int",
                default_value=512,
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY, ParameterMode.OUTPUT},
                tooltip="Height of the image in pixels",
            )
        )

        # Background color parameter
        self.add_parameter(
            Parameter(
                name="background_color",
                type="str",
                default_value="white",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY, ParameterMode.OUTPUT},
                tooltip="Background color of the image",
                traits={Options(choices=color_options)},
            )
        )

        # Text content parameter
        self.add_parameter(
            Parameter(
                name="text",
                type="str",
                default_value="Hello, world!",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY, ParameterMode.OUTPUT},
                tooltip="Text to render on the image",
                ui_options={"multiline": True, "placeholder_text": "Enter text to render on image"},
            )
        )

        # Text color parameter
        self.add_parameter(
            Parameter(
                name="text_color",
                type="str",
                default_value="black",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY, ParameterMode.OUTPUT},
                tooltip="Color of the text",
                traits={Options(choices=color_options)},
            )
        )

        # Image output parameter
        self.add_parameter(
            Parameter(
                name="image",
                type="ImageUrlArtifact",
                allowed_modes={ParameterMode.OUTPUT},
                tooltip="The generated image with text",
                ui_options={"pulse_on_run": True},
                settable=False,
            )
        )

        # Add status parameters using the helper method
        self._create_status_parameters(
            result_details_tooltip="Details about the text-to-image operation result",
            result_details_placeholder="Details on the text rendering will be presented here.",
        )

    def _validate_parameters(self, width: int, height: int, background_color: str, text_color: str, text: str) -> None:
        """Validate input parameters and raise ValueError if invalid."""
        if not isinstance(width, int) or width <= 0:
            msg = f"Width must be a positive integer, got: {width}"
            raise ValueError(msg)

        if not isinstance(height, int) or height <= 0:
            msg = f"Height must be a positive integer, got: {height}"
            raise ValueError(msg)

        if background_color not in NAMED_COLORS:
            msg = f"Invalid background color: {background_color}"
            raise ValueError(msg)

        if text_color not in NAMED_COLORS:
            msg = f"Invalid text color: {text_color}"
            raise ValueError(msg)

        if not text or not text.strip():
            msg = "Text cannot be empty"
            raise ValueError(msg)

    def _create_image_with_text(
        self,
        width: int,
        height: int,
        bg_rgba: tuple[int, int, int, int],
        text_rgba: tuple[int, int, int, int],
        text: str,
    ) -> Image.Image:
        """Create image with text and return PIL Image."""
        # Create image with background color
        image = Image.new("RGB", (width, height), bg_rgba[:3])
        draw = ImageDraw.Draw(image)

        # Load font
        try:
            font = ImageFont.load_default()
        except Exception as font_error:
            msg = f"Failed to load font: {font_error}"
            raise RuntimeError(msg) from font_error

        # Get text positioning
        try:
            bbox = draw.textbbox((0, 0), text, font=font)
            text_width = bbox[2] - bbox[0]
            text_height = bbox[3] - bbox[1]
            x = (width - text_width) // 2
            y = (height - text_height) // 2
        except Exception as text_error:
            msg = f"Failed to calculate text positioning: {text_error}"
            raise RuntimeError(msg) from text_error

        # Draw text
        try:
            draw.text((x, y), text, fill=text_rgba[:3], font=font)
        except Exception as draw_error:
            msg = f"Failed to draw text: {draw_error}"
            raise RuntimeError(msg) from draw_error

        return image

    def _get_success_message(self, width: int, height: int, text: str) -> str:
        """Generate success message with text preview."""
        text_preview = text[:TEXT_PREVIEW_LENGTH]
        if len(text) > TEXT_PREVIEW_LENGTH:
            text_preview += "..."
        return f"Successfully created {width}x{height} image with text: '{text_preview}'"

    def _set_success_output_values(
        self, width: int, height: int, background_color: str, text_color: str, text: str
    ) -> None:
        """Set output parameter values on success."""
        self.parameter_output_values["width"] = width
        self.parameter_output_values["height"] = height
        self.parameter_output_values["background_color"] = background_color
        self.parameter_output_values["text_color"] = text_color
        self.parameter_output_values["text"] = text

    def _set_failure_output_values(self) -> None:
        """Set output parameter values to defaults on failure."""
        self.parameter_output_values["width"] = 0
        self.parameter_output_values["height"] = 0
        self.parameter_output_values["background_color"] = ""
        self.parameter_output_values["text_color"] = ""
        self.parameter_output_values["text"] = ""
        self.parameter_output_values["image"] = None

    def process(self) -> None:
        # Reset execution state and set failure defaults
        self._clear_execution_status()
        self._set_failure_output_values()

        # Get parameter values
        width = self.get_parameter_value("width")
        height = self.get_parameter_value("height")
        background_color = self.get_parameter_value("background_color")
        text = self.get_parameter_value("text")
        text_color = self.get_parameter_value("text_color")

        # Validation failures - early returns
        try:
            self._validate_parameters(width, height, background_color, text_color, text)
        except ValueError as validation_error:
            error_details = f"Parameter validation failed: {validation_error}"
            self._set_status_results(was_successful=False, result_details=f"FAILURE: {error_details}")
            logger.error(f"AddTextToImage '{self.name}': {error_details}")
            self._handle_failure_exception(validation_error)
            return

        # Color parsing failures
        try:
            bg_rgba = parse_color_to_rgba(background_color)
            text_rgba = parse_color_to_rgba(text_color)
        except Exception as color_error:
            error_details = f"Color parsing failed: {color_error}"
            self._set_status_results(was_successful=False, result_details=f"FAILURE: {error_details}")
            logger.error(f"AddTextToImage '{self.name}': {error_details}")
            self._handle_failure_exception(color_error)
            return

        # Image creation failures
        try:
            image = self._create_image_with_text(width, height, bg_rgba, text_rgba, text)
        except Exception as image_error:
            error_details = f"Image creation failed: {image_error}"
            self._set_status_results(was_successful=False, result_details=f"FAILURE: {error_details}")
            logger.error(f"AddTextToImage '{self.name}': {error_details}")
            self._handle_failure_exception(image_error)
            return

        # Image upload failures
        try:
            image_artifact = self._upload_image_to_static_storage(image)
        except Exception as upload_error:
            error_details = f"Failed to upload image: {upload_error}"
            self._set_status_results(was_successful=False, result_details=f"FAILURE: {error_details}")
            logger.error(f"AddTextToImage '{self.name}': {error_details}")
            self._handle_failure_exception(upload_error)
            return

        # Success path - all validations and processing completed successfully
        self._set_success_output_values(width, height, background_color, text_color, text)
        self.parameter_output_values["image"] = image_artifact

        success_details = self._get_success_message(width, height, text)
        self._set_status_results(was_successful=True, result_details=f"SUCCESS: {success_details}")
        logger.info(f"AddTextToImage '{self.name}': {success_details}")

    def _upload_image_to_static_storage(self, image: Image.Image) -> ImageUrlArtifact:
        """Upload PIL Image to static storage and return ImageUrlArtifact."""
        # Convert PIL Image to PNG bytes in memory
        img_bytes = BytesIO()
        image.save(img_bytes, format="PNG")
        img_data = img_bytes.getvalue()

        # Generate filename
        filename = generate_filename(
            node_name=self.name,
            suffix="_text_image",
            extension="png",
        )

        # Create upload URL request
        upload_request = CreateStaticFileUploadUrlRequest(file_name=filename)
        upload_result = GriptapeNodes.handle_request(upload_request)

        if isinstance(upload_result, CreateStaticFileUploadUrlResultFailure):
            error_msg = f"Failed to create upload URL for file '{filename}': {upload_result.error}"
            raise RuntimeError(error_msg)  # noqa: TRY004

        if not isinstance(upload_result, CreateStaticFileUploadUrlResultSuccess):
            error_msg = f"Static file API returned unexpected result type: {type(upload_result).__name__}"
            raise RuntimeError(error_msg)  # noqa: TRY004

        # Upload the PNG bytes
        try:
            response = httpx.request(
                upload_result.method,
                upload_result.url,
                content=img_data,
                headers=upload_result.headers,
                timeout=60,
            )
            response.raise_for_status()
        except Exception as e:
            error_msg = f"Failed to upload image data: {e}"
            raise RuntimeError(error_msg) from e

        # Get download URL
        download_request = CreateStaticFileDownloadUrlRequest(file_name=filename)
        download_result = GriptapeNodes.handle_request(download_request)

        if isinstance(download_result, CreateStaticFileDownloadUrlResultFailure):
            error_msg = f"Failed to create download URL for file '{filename}': {download_result.error}"
            raise RuntimeError(error_msg)  # noqa: TRY004

        if not isinstance(download_result, CreateStaticFileDownloadUrlResultSuccess):
            error_msg = f"Static file API returned unexpected download result type: {type(download_result).__name__}"
            raise RuntimeError(error_msg)  # noqa: TRY004

        # Create and return ImageUrlArtifact
        return ImageUrlArtifact(value=download_result.url)
