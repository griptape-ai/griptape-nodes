import io
from dataclasses import dataclass
from typing import Any

from griptape.artifacts import ImageUrlArtifact
from PIL import Image

from griptape_nodes.exe_types.core_types import (
    NodeMessagePayload,
    NodeMessageResult,
    Parameter,
    ParameterGroup,
    ParameterMode,
)
from griptape_nodes.exe_types.node_types import ControlNode
from griptape_nodes.exe_types.param_types.parameter_button import ParameterButton
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes, logger
from griptape_nodes.traits.button import Button, ButtonDetailsMessagePayload
from griptape_nodes.traits.color_picker import ColorPicker
from griptape_nodes.traits.options import Options
from griptape_nodes.traits.slider import Slider
from griptape_nodes_library.utils.color_utils import NAMED_COLORS, parse_color_to_rgba
from griptape_nodes_library.utils.file_utils import generate_filename
from griptape_nodes_library.utils.image_utils import (
    dict_to_image_url_artifact,
    load_pil_from_url,
    validate_pil_format,
)

# Constants for magic numbers
NO_ZOOM = 100.0
MAX_ZOOM = 500.0
MIN_ZOOM_FACTOR = 0.1
MAX_ZOOM_FACTOR = 10.0  # Maximum zoom factor to prevent memory issues
MAX_IMAGE_DIMENSION = 32767  # Maximum safe dimension to prevent overflow
# Initial slider max values - should support 8K (8192x4320) and higher resolutions
# These are updated dynamically when an image is loaded, but need to be high enough
# to support common high-res formats before image loading
MAX_WIDTH = MAX_IMAGE_DIMENSION
MAX_HEIGHT = MAX_IMAGE_DIMENSION
ROTATION_MIN = -180.0
ROTATION_MAX = 180.0


@dataclass
class CropArea:
    """Represents a crop area with coordinates and dimensions."""

    left: int
    top: int
    right: int
    bottom: int
    center_x: float
    center_y: float

    @property
    def width(self) -> int:
        """Get the width of the crop area."""
        return self.right - self.left

    @property
    def height(self) -> int:
        """Get the height of the crop area."""
        return self.bottom - self.top


class CropImage(ControlNode):
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)

        self.MAX_WIDTH = MAX_WIDTH
        self.MAX_HEIGHT = MAX_HEIGHT
        self._processing = False  # Lock to prevent live cropping during process()

        self.add_parameter(
            Parameter(
                name="input_image",
                input_types=["ImageUrlArtifact"],
                type="ImageUrlArtifact",
                default_value=None,
                tooltip="Input image to crop",
                ui_options={"crop_image": True},
            )
        )
        self.add_parameter(
            ParameterButton(
                name="crop_button",
                label="Open Crop Editor",
                variant="secondary",
                icon="crop",
                on_click=self._open_crop_modal,
            )
        )
        with ParameterGroup(name="crop_coordinates", ui_options={"collapsed": False}) as crop_coordinates:
            Parameter(
                name="left",
                type="int",
                default_value=0,
                tooltip="Left edge of crop area in pixels",
                traits={Slider(min_val=0, max_val=self.MAX_WIDTH)},
            )

            Parameter(
                name="top",
                type="int",
                default_value=0,
                tooltip="Top edge of crop area in pixels",
                traits={Slider(min_val=0, max_val=self.MAX_HEIGHT)},
            )

            Parameter(
                name="width",
                type="int",
                default_value=0,
                tooltip="Width of crop area in pixels (0 = use full width)",
                traits={Slider(min_val=0, max_val=self.MAX_WIDTH)},
            )

            Parameter(
                name="height",
                type="int",
                default_value=0,
                tooltip="Height of crop area in pixels (0 = use full height)",
                traits={Slider(min_val=0, max_val=self.MAX_HEIGHT)},
            )
        self.add_node_element(crop_coordinates)

        with ParameterGroup(name="transform_options", ui_options={"collapsed": False}) as transform_options:
            Parameter(
                name="zoom",
                type="float",
                default_value=NO_ZOOM,
                tooltip="Zoom percentage (100 = no zoom, 200 = 2x zoom in, 50 = 0.5x zoom out)",
                traits={Slider(min_val=0.0, max_val=MAX_ZOOM)},
            )
            Parameter(
                name="rotate",
                type="float",
                default_value=0.0,
                tooltip="Rotation in degrees (-180 to 180)",
                traits={Slider(min_val=ROTATION_MIN, max_val=ROTATION_MAX)},
            )

        self.add_node_element(transform_options)
        with ParameterGroup(name="output_options", ui_options={"collapsed": True}) as output_options:
            Parameter(
                name="background_color",
                type="str",
                default_value="#00000000",
                tooltip="Background color (RGBA or hex) for transparent areas",
                traits={ColorPicker(format="hexa")},
            )
            Parameter(
                name="output_format",
                type="str",
                default_value="PNG",
                tooltip="Output format: PNG, JPEG, WEBP",
                traits={Options(choices=["PNG", "JPEG", "WEBP"])},
            )

            Parameter(
                name="output_quality",
                type="float",
                default_value=0.9,
                tooltip="Output quality (0.0 to 1.0) for lossy formats",
            )

        self.add_node_element(output_options)

        # Output parameter
        self.add_parameter(
            Parameter(
                name="output",
                type="ImageUrlArtifact",
                allowed_modes={ParameterMode.OUTPUT},
                tooltip="Cropped output image",
            )
        )

    def _open_crop_modal(self, _button: Button, _details: ButtonDetailsMessagePayload) -> NodeMessageResult:
        """Open the crop modal in the frontend."""
        # Create the open_modal payload structure
        open_modal_data = {
            "modal_type": "crop",
            "node_name": self.name,
            "parameter_name": "input_image",
        }

        # Create payload with open_modal structure
        payload = NodeMessagePayload(data={"open_modal": open_modal_data})

        # Return NodeMessageResult with the payload
        return NodeMessageResult(
            success=True,
            details="Opening crop modal",
            response=payload,
            altered_workflow_state=False,
        )

    def _crop(self) -> None:
        # Get parameters
        params = self._get_crop_parameters()

        # Load image
        try:
            img = load_pil_from_url(params["input_artifact"].value)
        except Exception as e:
            msg = f"{self.name}: Error loading image: {e}"
            logger.error(msg)
            return

        # Calculate and apply crop area
        crop_area = self._calculate_crop_area(params, img.size)
        img = self._apply_crop_transformations(img, crop_area, params)

        # Save result
        self._save_cropped_image(img, params)

    def _get_crop_parameters(self) -> dict:
        """Get all crop parameters."""
        return {
            "input_artifact": self.get_parameter_value("input_image"),
            "left": self.get_parameter_value("left"),
            "top": self.get_parameter_value("top"),
            "width": self.get_parameter_value("width"),
            "height": self.get_parameter_value("height"),
            "zoom": self.get_parameter_value("zoom"),
            "rotate": self.get_parameter_value("rotate"),
            "background_color": self.get_parameter_value("background_color"),
            "output_format": self.get_parameter_value("output_format"),
            "output_quality": self.get_parameter_value("output_quality"),
        }

    def _calculate_crop_area(self, params: dict, img_size: tuple[int, int]) -> CropArea:
        """Calculate the crop area with validation."""
        img_width, img_height = img_size
        left, top, width, height = params["left"], params["top"], params["width"], params["height"]

        # Calculate crop coordinates relative to original image
        crop_left = left
        crop_top = top
        crop_width = width if width > 0 else img_width
        crop_height = height if height > 0 else img_height

        # Ensure crop coordinates are within image bounds
        crop_left = max(0, min(crop_left, img_width))
        crop_top = max(0, min(crop_top, img_height))

        # Ensure crop dimensions are valid
        if crop_width <= 0 or crop_left + crop_width > img_width:
            crop_width = img_width - crop_left
        if crop_height <= 0 or crop_top + crop_height > img_height:
            crop_height = img_height - crop_top

        # Calculate final crop boundaries
        crop_right = crop_left + crop_width
        crop_bottom = crop_top + crop_height

        # Calculate the center of the crop area
        crop_center_x = (crop_left + crop_right) / 2
        crop_center_y = (crop_top + crop_bottom) / 2

        return CropArea(crop_left, crop_top, crop_right, crop_bottom, crop_center_x, crop_center_y)

    def _apply_crop_transformations(self, img: Image.Image, crop_area: CropArea, params: dict) -> Image.Image:
        """Apply zoom, rotation, and final crop to the image."""
        img_width, img_height = img.size

        # Apply zoom by scaling the crop area
        crop_area = self._apply_zoom_to_crop_area(crop_area, params["zoom"], img_width, img_height)

        # Apply rotation around the center of the crop area
        img = self._apply_rotation_to_image(
            img, params["rotate"], crop_area.center_x, crop_area.center_y, params["background_color"]
        )

        # Apply the final crop (the window)
        img = self._apply_final_crop(img, crop_area.left, crop_area.top, crop_area.right, crop_area.bottom)

        return img

    def _save_cropped_image(self, img: Image.Image, params: dict) -> None:
        """Save the cropped image."""
        # Validate and prepare image for saving
        save_format = params["output_format"].upper()

        # Validate that the save format is supported by PIL
        try:
            validate_pil_format(save_format, "output_format")
        except ValueError as e:
            msg = f"{self.name}: {e}"
            logger.error(msg)
            return

        output_quality = max(0.0, min(1.0, params["output_quality"]))  # Clamp to 0.0-1.0

        # Convert RGBA to RGB for JPEG format (JPEG doesn't support transparency)
        if save_format == "JPEG" and img.mode == "RGBA":
            # Create black background for transparent areas
            background = Image.new("RGB", img.size, (0, 0, 0))
            background.paste(img, mask=img.split()[-1])  # Use alpha channel as mask
            img = background

        # Determine save options
        save_options = {}
        if save_format == "JPEG":
            save_options["quality"] = int(output_quality * 100)
            save_options["optimize"] = True
        elif save_format == "WEBP":
            save_options["quality"] = int(output_quality * 100)
            save_options["lossless"] = True

        # Save result using context manager to ensure proper cleanup
        img_data = None
        with io.BytesIO() as img_byte_arr:
            img.save(img_byte_arr, format=save_format, **save_options)
            img_byte_arr.seek(0)
            img_data = img_byte_arr.getvalue()  # Returns a copy, data persists after context exit

        # Verify we have valid data before proceeding
        if img_data is None or len(img_data) == 0:
            msg = f"{self.name}: Failed to save image data"
            logger.error(msg)
            return

        # Generate meaningful filename based on workflow and node
        filename = self._generate_filename(save_format.lower())
        static_url = GriptapeNodes.StaticFilesManager().save_static_file(img_data, filename)
        self.parameter_output_values["output"] = ImageUrlArtifact(value=static_url)

    def _get_output_suffix(self, **kwargs) -> str:  # noqa: ARG002
        """Get output filename suffix."""
        return "_crop"

    def _generate_filename(self, extension: str) -> str:
        """Generate a meaningful filename based on workflow and node information."""
        # Get processing suffix
        params = self._get_crop_parameters()
        processing_suffix = self._get_output_suffix(**params)

        # Use the general filename utility but with a custom prefix
        base_filename = generate_filename(
            node_name=self.name,
            suffix=processing_suffix,
            extension=extension,
        )

        # Add the "crop" prefix that this node specifically uses
        return base_filename.replace(f"{self.name}{processing_suffix}", f"crop_{self.name}{processing_suffix}")

    def _apply_zoom_to_crop_area(self, crop_area: CropArea, zoom: float, img_width: int, img_height: int) -> CropArea:
        """Apply zoom by scaling the crop area size."""
        if zoom == NO_ZOOM:
            return crop_area

        # Scale the crop area based on zoom
        scaled_area = self._scale_crop_area(crop_area, zoom)

        # Ensure the scaled area stays within image bounds
        bounded_area = self._clamp_crop_area_to_bounds(scaled_area, img_width, img_height)

        return bounded_area

    def _scale_crop_area(self, crop_area: CropArea, zoom: float) -> CropArea:
        """Scale the crop area size based on zoom factor."""
        zoom_factor = zoom / NO_ZOOM

        # Clamp zoom_factor to prevent division by zero and extreme scaling
        zoom_factor = max(MIN_ZOOM_FACTOR, min(MAX_ZOOM_FACTOR, zoom_factor))

        # Calculate new dimensions with overflow protection
        new_width = int(crop_area.width / zoom_factor)
        new_height = int(crop_area.height / zoom_factor)

        # Clamp dimensions to prevent integer overflow
        new_width = max(1, min(new_width, MAX_IMAGE_DIMENSION))
        new_height = max(1, min(new_height, MAX_IMAGE_DIMENSION))

        # Keep center position, adjust size
        new_left = int(crop_area.center_x - new_width / 2)
        new_top = int(crop_area.center_y - new_height / 2)
        new_right = new_left + new_width
        new_bottom = new_top + new_height

        return CropArea(new_left, new_top, new_right, new_bottom, crop_area.center_x, crop_area.center_y)

    def _clamp_crop_area_to_bounds(self, crop_area: CropArea, img_width: int, img_height: int) -> CropArea:
        """Ensure crop area coordinates are within image bounds."""
        clamped_left = max(0, min(crop_area.left, img_width))
        clamped_right = max(clamped_left, min(crop_area.right, img_width))
        clamped_top = max(0, min(crop_area.top, img_height))
        clamped_bottom = max(clamped_top, min(crop_area.bottom, img_height))

        return CropArea(
            clamped_left, clamped_top, clamped_right, clamped_bottom, crop_area.center_x, crop_area.center_y
        )

    def _apply_rotation_to_image(
        self,
        img: Image.Image,
        rotate: float,
        crop_center_x: float,
        crop_center_y: float,
        background_color: str,
    ) -> Image.Image:
        """Apply rotation around the crop center point."""
        if rotate == 0.0:
            return img

        # Convert background color to RGBA
        bg_color = self._parse_color(background_color)

        # Simply rotate around the crop center point
        img = img.rotate(rotate, center=(crop_center_x, crop_center_y), expand=False, fillcolor=bg_color)

        return img

    def _apply_final_crop(
        self, img: Image.Image, crop_left: int, crop_top: int, crop_right: int, crop_bottom: int
    ) -> Image.Image:
        """Apply the final crop to the image."""
        img_width, img_height = img.size

        # Ensure crop coordinates are within the final image bounds
        crop_left = max(0, min(crop_left, img_width))
        crop_right = max(crop_left, min(crop_right, img_width))
        crop_top = max(0, min(crop_top, img_height))
        crop_bottom = max(crop_top, min(crop_bottom, img_height))

        # Apply the final crop
        if crop_right > crop_left and crop_bottom > crop_top:
            try:
                img = img.crop((crop_left, crop_top, crop_right, crop_bottom))
            except Exception as e:
                msg = f"{self.name}: Final crop failed: {e}. Using image as is."
                logger.warning(msg)
        else:
            msg = f"{self.name}: Invalid final crop coordinates, using image as is"
            logger.warning(msg)

        return img

    def process(self) -> None:
        # Set processing lock to prevent live cropping during actual processing
        self._processing = True
        try:
            self._crop()
        finally:
            self._processing = False

    def _parse_color(self, color_str: str) -> tuple[int, int, int, int]:
        """Parse color string to RGBA tuple."""
        try:
            return parse_color_to_rgba(color_str)
        except ValueError:
            # Fallback to transparent if color parsing fails
            return NAMED_COLORS["transparent"]

    def after_value_set(self, parameter: Parameter, value: Any) -> None:  # noqa: C901
        # Set the max_value for sliders based on the image size
        if parameter.name == "input_image":
            # Load image
            try:
                img = load_pil_from_url(value.value)
            except Exception as e:
                msg = f"{self.name}: Error loading image: {e}"
                logger.error(msg)
                return None
            if img.width and img.height:
                top_param = self.get_parameter_by_name("top")
                left_param = self.get_parameter_by_name("left")
                width_param = self.get_parameter_by_name("width")
                height_param = self.get_parameter_by_name("height")
                if top_param:
                    top_param.update_ui_options({"slider": {"max_val": img.height}})
                if left_param:
                    left_param.update_ui_options({"slider": {"max_val": img.width}})
                if width_param:
                    width_param.update_ui_options({"slider": {"max_val": img.width}})
                if height_param:
                    height_param.update_ui_options({"slider": {"max_val": img.height, "min_val": 0}})

        # Do live cropping for crop parameters (only when not processing)
        if not self._processing and parameter.name in [
            "left",
            "top",
            "width",
            "height",
            "zoom",
            "rotate",
            "background_color",
            "output_format",
            "output_quality",
        ]:
            # Check if image is valid
            image_exceptions = self._validate_image()
            if image_exceptions:
                # Image is not valid, don't run crop
                return None

            # Check if parameters are valid
            parameter_exceptions = self._validate_parameters()
            if parameter_exceptions:
                # Parameters are not valid, don't run crop
                return None

            # Both image and parameters are valid, run crop
            try:
                self._crop()
            except Exception as e:
                # Log error but don't crash the UI
                msg = f"{self.name}: Error during live crop: {e}"
                logger.warning(msg)

        return super().after_value_set(parameter, value)

    def _validate_image(self) -> list[Exception]:
        """Validate the input image parameter."""
        exceptions = []

        input_artifact = self.get_parameter_value("input_image")
        if not input_artifact:
            msg = f"{self.name} - Input image is required"
            exceptions.append(Exception(msg))
            return exceptions

        # Validate input artifact type
        if isinstance(input_artifact, dict):
            # Convert dict to ImageUrlArtifact for validation
            try:
                input_artifact = dict_to_image_url_artifact(input_artifact)
            except Exception as e:
                msg = f"{self.name} - Invalid image dictionary: {e}"
                exceptions.append(Exception(msg))
                return exceptions

        if not isinstance(input_artifact, ImageUrlArtifact):
            msg = f"{self.name} - Input must be an ImageUrlArtifact, got {type(input_artifact).__name__}"
            exceptions.append(Exception(msg))

        return exceptions

    def _validate_parameters(self) -> list[Exception]:
        """Validate parameter values."""
        exceptions = []

        # Validate zoom parameter
        zoom = self.get_parameter_value("zoom")
        if zoom is not None and (zoom < 0.0 or zoom > MAX_ZOOM):
            msg = f"{self.name} - Zoom must be between 0.0 and {MAX_ZOOM}, got {zoom}"
            exceptions.append(Exception(msg))

        # Validate rotation parameter
        rotate = self.get_parameter_value("rotate")
        if rotate is not None and (rotate < ROTATION_MIN or rotate > ROTATION_MAX):
            msg = f"{self.name} - Rotation must be between {ROTATION_MIN} and {ROTATION_MAX} degrees, got {rotate}"
            exceptions.append(Exception(msg))

        # Validate output quality parameter
        output_quality = self.get_parameter_value("output_quality")
        if output_quality is not None and (output_quality < 0.0 or output_quality > 1.0):
            msg = f"{self.name} - Output quality must be between 0.0 and 1.0, got {output_quality}"
            exceptions.append(Exception(msg))

        # Validate crop coordinates are non-negative
        left = self.get_parameter_value("left")
        top = self.get_parameter_value("top")
        width = self.get_parameter_value("width")
        height = self.get_parameter_value("height")

        if left is not None and left < 0:
            msg = f"{self.name} - Left coordinate must be non-negative, got {left}"
            exceptions.append(Exception(msg))

        if top is not None and top < 0:
            msg = f"{self.name} - Top coordinate must be non-negative, got {top}"
            exceptions.append(Exception(msg))

        if width is not None and width < 0:
            msg = f"{self.name} - Width must be non-negative, got {width}"
            exceptions.append(Exception(msg))

        if height is not None and height < 0:
            msg = f"{self.name} - Height must be non-negative, got {height}"
            exceptions.append(Exception(msg))

        return exceptions

    def validate_before_node_run(self) -> list[Exception] | None:
        exceptions = []

        # Validate image
        exceptions.extend(self._validate_image())

        # Validate parameters
        exceptions.extend(self._validate_parameters())

        return exceptions if exceptions else None
