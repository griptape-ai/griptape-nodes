import io
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from griptape.artifacts import ImageArtifact, ImageUrlArtifact
from PIL import Image

from griptape_nodes.exe_types.core_types import Parameter, ParameterGroup, ParameterMode
from griptape_nodes.exe_types.node_types import ControlNode
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes, logger
from griptape_nodes.traits.options import Options
from griptape_nodes.traits.slider import Slider
from griptape_nodes_library.utils.color_utils import parse_color_to_rgba
from griptape_nodes_library.utils.image_utils import (
    dict_to_image_url_artifact,
    load_pil_from_url,
)

# Constants for magic numbers
NO_ZOOM = 100.0
MAX_ZOOM = 300.0
MIN_ZOOM_FACTOR = 0.1
MAX_IMAGE_DIMENSION = 32767  # Maximum safe dimension to prevent overflow
MAX_WIDTH = 4000
MAX_HEIGHT = 4000


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
        self.category = "Image"
        self.description = "Crop an image to a specific size."

        self.add_parameter(
            Parameter(
                name="input_image",
                input_types=["ImageUrlArtifact", "ImageArtifact"],
                type="ImageUrlArtifact",
                default_value=None,
                tooltip="Input image to crop",
                ui_options={"crop_image": True},
            )
        )

        with ParameterGroup(name="crop_coordinates", ui_options={"collapsed": False}) as crop_coordinates:
            Parameter(
                name="left",
                type="int",
                default_value=0,
                tooltip="Left edge of crop area in pixels",
                traits={Slider(min_val=0, max_val=MAX_WIDTH)},
            )

            Parameter(
                name="top",
                type="int",
                default_value=0,
                tooltip="Top edge of crop area in pixels",
                traits={Slider(min_val=0, max_val=MAX_HEIGHT)},
            )

            Parameter(
                name="width",
                type="int",
                default_value=0,
                tooltip="Width of crop area in pixels (0 = use full width)",
                traits={Slider(min_val=0, max_val=MAX_WIDTH)},
            )

            Parameter(
                name="height",
                type="int",
                default_value=0,
                tooltip="Height of crop area in pixels (0 = use full height)",
                traits={Slider(min_val=0, max_val=MAX_HEIGHT)},
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
                traits={Slider(min_val=-180.0, max_val=180.0)},
            )

        self.add_node_element(transform_options)
        with ParameterGroup(name="output_options", ui_options={"collapsed": True}) as output_options:
            Parameter(
                name="background_color",
                type="str",
                default_value="#00000000",
                tooltip="Background color (RGBA or hex) for transparent areas",
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

    def _crop(self) -> None:
        # Get parameters
        params = self._get_crop_parameters()

        # Load image
        img = self._load_image(params["input_artifact"])
        if img is None:
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

    def _load_image(self, input_artifact: ImageUrlArtifact | ImageArtifact) -> Image.Image | None:
        """Load image from artifact."""
        try:
            if isinstance(input_artifact, ImageUrlArtifact):
                return load_pil_from_url(input_artifact.value)
            # Must be ImageArtifact due to validation
            return Image.open(io.BytesIO(input_artifact.value))
        except Exception as e:
            msg = f"{self.name}: Error loading image: {e}"
            logger.error(msg)
            return None

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
        # Save result
        img_byte_arr = io.BytesIO()

        # Determine save format and options
        save_format = params["output_format"].upper()
        save_options = {}

        if save_format == "JPEG":
            save_options["quality"] = int(params["output_quality"] * 100)
            save_options["optimize"] = True
        elif save_format == "WEBP":
            save_options["quality"] = int(params["output_quality"] * 100)
            save_options["lossless"] = False

        img.save(img_byte_arr, format=save_format, **save_options)
        img_byte_arr = img_byte_arr.getvalue()

        # Generate meaningful filename based on workflow and node
        filename = self._generate_filename(save_format.lower())
        static_url = GriptapeNodes.StaticFilesManager().save_static_file(img_byte_arr, filename)
        self.parameter_output_values["output"] = ImageUrlArtifact(value=static_url)

    def _generate_filename(self, extension: str) -> str:
        """Generate a meaningful filename based on workflow and node information."""
        # Get workflow and node context
        workflow_name = "unknown_workflow"
        node_name = self.name

        # Try to get workflow name from context
        try:
            context_manager = GriptapeNodes.ContextManager()
            workflow_name = context_manager.get_current_workflow_name()
        except Exception as e:
            msg = f"{self.name}: Error getting workflow name: {e}"
            logger.warning(msg)

        # Clean up names for filename use
        workflow_name = "".join(c for c in workflow_name if c.isalnum() or c in ("-", "_")).rstrip()
        node_name = "".join(c for c in node_name if c.isalnum() or c in ("-", "_")).rstrip()

        # Get current timestamp for cache busting
        timestamp = int(datetime.now(UTC).timestamp())

        # Create filename with meaningful structure and timestamp as query parameter
        filename = f"crop_{workflow_name}_{node_name}.{extension}?t={timestamp}"

        return filename

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
        zoom_factor = max(MIN_ZOOM_FACTOR, zoom_factor)

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
        self._crop()

    def _parse_color(self, color_str: str) -> tuple[int, int, int, int]:
        """Parse color string to RGBA tuple."""
        try:
            return parse_color_to_rgba(color_str)
        except ValueError:
            # Fallback to transparent if color parsing fails
            return (0, 0, 0, 0)

    def after_value_set(self, parameter: Parameter, value: Any) -> None:
        # Do live cropping for crop parameters
        if parameter.name in [
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
            # Only run crop if we have a valid input image
            input_artifact = self.get_parameter_value("input_image")
            if input_artifact and isinstance(input_artifact, (ImageUrlArtifact, ImageArtifact)):
                try:
                    self._crop()
                except Exception as e:
                    # Log error but don't crash the UI
                    msg = f"{self.name}: Error during live crop: {e}"
                    logger.warning(msg)

        return super().after_value_set(parameter, value)

    def validate_before_node_run(self) -> list[Exception] | None:
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

        if not isinstance(input_artifact, (ImageUrlArtifact, ImageArtifact)):
            msg = (
                f"{self.name} - Input must be an ImageUrlArtifact or ImageArtifact, got {type(input_artifact).__name__}"
            )
            exceptions.append(Exception(msg))

        return exceptions
