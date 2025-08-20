from enum import StrEnum
from typing import Any, NamedTuple

from griptape.artifacts import ImageUrlArtifact
from PIL import Image

from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import ControlNode
from griptape_nodes.traits.options import Options
from griptape_nodes_library.utils.color_utils import NAMED_COLORS
from griptape_nodes_library.utils.image_utils import (
    dict_to_image_url_artifact,
    load_pil_from_url,
    save_pil_image_to_static_file,
)


class ImagePosition(StrEnum):
    """Position options for placing the original image within the extended canvas."""

    CENTER = "center"
    TOP_LEFT = "top_left"
    TOP_RIGHT = "top_right"
    BOTTOM_LEFT = "bottom_left"
    BOTTOM_RIGHT = "bottom_right"
    TOP = "top"
    BOTTOM = "bottom"
    LEFT = "left"
    RIGHT = "right"


class BackgroundColorConfig(NamedTuple):
    """Configuration for background colors including image and mask colors."""

    image_mode: str  # PIL image mode (RGB or RGBA)
    bg_color: tuple[int, int, int] | tuple[int, int, int, int] | None  # Background color or None for transparent
    mask_bg_color: tuple[int, int, int] | tuple[int, int, int, int]  # Mask background color
    mask_fg_color: tuple[int, int, int] | tuple[int, int, int, int]  # Mask foreground color


# Background color configuration table
BACKGROUND_COLOR_CONFIGS = {}
for key, value in NAMED_COLORS.items():
    BACKGROUND_COLOR_CONFIGS[key] = BackgroundColorConfig(
        image_mode="RGBA",
        bg_color=value,  # Background color
        mask_bg_color=value if key == "transparent" else NAMED_COLORS["white"],
        mask_fg_color=NAMED_COLORS["black"],  # Black mask foreground (original image area)
    )


# Common aspect ratio presets (pure ratios without fixed pixels)
# Organized by: Custom, Square, Landscape (ascending ratio), Portrait (ascending ratio)
ASPECT_RATIO_PRESETS = {
    # Custom option
    "custom": None,
    # Square
    "1:1 square": (1, 1),
    # Landscape ratios (ascending by first number)
    "2:1 landscape": (2, 1),
    "3:1 landscape": (3, 1),
    "3:2 landscape": (3, 2),
    "4:1 landscape": (4, 1),
    "4:3 landscape": (4, 3),
    "5:1 landscape": (5, 1),
    "16:9 landscape": (16, 9),
    "16:10 landscape": (16, 10),
    "16:12 landscape": (16, 12),
    "18:9 landscape": (18, 9),
    "19:9 landscape": (19, 9),
    "20:9 landscape": (20, 9),
    "21:9 landscape": (21, 9),
    "22:9 landscape": (22, 9),
    "24:9 landscape": (24, 9),
    "32:9 landscape": (32, 9),
    # Portrait ratios (ascending by first number)
    "1:2 portrait": (1, 2),
    "1:3 portrait": (1, 3),
    "1:4 portrait": (1, 4),
    "1:5 portrait": (1, 5),
    "2:3 portrait": (2, 3),
    "3:4 portrait": (3, 4),
    "4:5 portrait": (4, 5),
    "5:6 portrait": (5, 6),
    "5:8 portrait": (5, 8),
    "6:7 portrait": (6, 7),
    "7:8 portrait": (7, 8),
    "8:9 portrait": (8, 9),
    "9:10 portrait": (9, 10),
    "9:16 portrait": (9, 16),
    "9:18 portrait": (9, 18),
    "9:19 portrait": (9, 19),
    "9:20 portrait": (9, 20),
    "9:21 portrait": (9, 21),
    "9:22 portrait": (9, 22),
    "9:24 portrait": (9, 24),
    "9:32 portrait": (9, 32),
    "10:11 portrait": (10, 11),
    "10:16 portrait": (10, 16),
    "11:12 portrait": (11, 12),
    "12:13 portrait": (12, 13),
    "12:16 portrait": (12, 16),
    "13:14 portrait": (13, 14),
    "14:15 portrait": (14, 15),
    "15:16 portrait": (15, 16),
}


class ExtendCanvas(ControlNode):
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)

        self.category = "Image"
        self.description = "Extend canvas around an image to fit target aspect ratios or custom dimensions"

        # Input image parameter
        self.add_parameter(
            Parameter(
                name="input_image",
                default_value=None,
                input_types=["ImageUrlArtifact", "ImageArtifact"],
                output_type="ImageUrlArtifact",
                type="ImageArtifact",
                tooltip="The input image to extend canvas around",
                ui_options={"hide_property": True},
                allowed_modes={ParameterMode.INPUT, ParameterMode.OUTPUT},
            )
        )

        # Aspect ratio preset parameter
        self._aspect_ratio_preset = Parameter(
            name="aspect_ratio_preset",
            input_types=["str"],
            type="str",
            output_type="str",
            tooltip="Select a preset aspect ratio or 'custom' to set manual dimensions",
            default_value="1:1 square",
            allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY, ParameterMode.OUTPUT},
            traits={Options(choices=list(ASPECT_RATIO_PRESETS.keys()))},
        )
        self.add_parameter(self._aspect_ratio_preset)

        # Custom pixel extensions (used when preset is 'custom')
        self._custom_top_parameter = Parameter(
            name="top",
            input_types=["int"],
            type="int",
            output_type="int",
            tooltip="Pixels to extend canvas on the top side",
            default_value=0,
            allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY, ParameterMode.OUTPUT},
            ui_options={"hide": True},
        )
        self.add_parameter(self._custom_top_parameter)

        self._custom_bottom_parameter = Parameter(
            name="bottom",
            input_types=["int"],
            type="int",
            output_type="int",
            tooltip="Pixels to extend canvas on the bottom side",
            default_value=0,
            allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY, ParameterMode.OUTPUT},
            ui_options={"hide": True},
        )
        self.add_parameter(self._custom_bottom_parameter)

        self._custom_left_parameter = Parameter(
            name="left",
            input_types=["int"],
            type="int",
            output_type="int",
            tooltip="Pixels to extend canvas on the left side",
            default_value=0,
            allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY, ParameterMode.OUTPUT},
            ui_options={"hide": True},
        )
        self.add_parameter(self._custom_left_parameter)

        self._custom_right_parameter = Parameter(
            name="right",
            input_types=["int"],
            type="int",
            output_type="int",
            tooltip="Pixels to extend canvas on the right side",
            default_value=0,
            allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY, ParameterMode.OUTPUT},
            ui_options={"hide": True},
        )
        self.add_parameter(self._custom_right_parameter)

        # Position parameter (only applies to preset modes, not custom)
        position_choices = [pos.value for pos in ImagePosition]
        self._position_parameter = Parameter(
            name="position",
            input_types=["str"],
            type="str",
            output_type="str",
            tooltip="Position of the original image within the extended canvas",
            default_value=ImagePosition.CENTER.value,  # Convert enum to string
            allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY, ParameterMode.OUTPUT},
            traits={Options(choices=position_choices)},
        )
        self.add_parameter(self._position_parameter)

        # Background color parameter
        background_color_choices = ["black", "white", "transparent", "magenta", "green", "blue"]
        self._background_color_parameter = Parameter(
            name="background_color",
            input_types=["str"],
            type="str",
            output_type="str",
            tooltip="Background color for the extended canvas areas",
            default_value="black",
            allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY, ParameterMode.OUTPUT},
            traits={Options(choices=background_color_choices)},
        )
        self.add_parameter(self._background_color_parameter)

        # Upscale factor parameter
        self.add_parameter(
            Parameter(
                name="upscale_factor",
                input_types=["float"],
                type="float",
                output_type="float",
                tooltip="Factor to upscale the calculated dimensions",
                default_value=1.0,
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY, ParameterMode.OUTPUT},
            )
        )

        # Output extended image
        self.add_parameter(
            Parameter(
                name="extended_image",
                output_type="ImageUrlArtifact",
                tooltip="The image with extended canvas",
                ui_options={"expander": True},
                allowed_modes={ParameterMode.OUTPUT},
            )
        )

        # Output mask
        self.add_parameter(
            Parameter(
                name="canvas_mask",
                output_type="ImageUrlArtifact",
                tooltip="Mask where black = original image, the selected background color = extended canvas areas",
                ui_options={"expander": True},
                allowed_modes={ParameterMode.OUTPUT},
            )
        )

    def process(self) -> None:
        input_image = self.get_parameter_value("input_image")
        if input_image is None:
            return

        # Normalize input to ImageUrlArtifact
        if isinstance(input_image, dict):
            input_image = dict_to_image_url_artifact(input_image)

        # Get parameters
        aspect_ratio_preset = self.get_parameter_value("aspect_ratio_preset")
        upscale_factor = self.get_parameter_value("upscale_factor")

        # Calculate target dimensions
        if aspect_ratio_preset != "custom" and aspect_ratio_preset in ASPECT_RATIO_PRESETS:
            # Get the ratio from preset
            ratio_width, ratio_height = ASPECT_RATIO_PRESETS[aspect_ratio_preset]

            # Load original image to get current dimensions
            original_image = load_pil_from_url(input_image.value)
            original_width, original_height = original_image.size

            # Calculate target dimensions based on original image size and ratio
            # We'll maintain the larger dimension and calculate the other based on the ratio
            if original_width / original_height > ratio_width / ratio_height:
                # Original image is wider than target ratio, extend height
                target_width = original_width
                target_height = int(original_width * ratio_height / ratio_width)
            else:
                # Original image is taller than target ratio, extend width
                target_height = original_height
                target_width = int(original_height * ratio_width / ratio_height)
        else:
            # For custom mode, extend by explicit pixel margins
            original_image = load_pil_from_url(input_image.value)
            original_width, original_height = original_image.size

            top_ext = max(0, int(self.get_parameter_value("top") or 0))
            bottom_ext = max(0, int(self.get_parameter_value("bottom") or 0))
            left_ext = max(0, int(self.get_parameter_value("left") or 0))
            right_ext = max(0, int(self.get_parameter_value("right") or 0))

            target_width = original_width + left_ext + right_ext
            target_height = original_height + top_ext + bottom_ext

        # Apply upscale factor
        if upscale_factor != 1.0:
            target_width = int(target_width * upscale_factor)
            target_height = int(target_height * upscale_factor)

        # Calculate custom offsets if needed
        custom_offsets = None
        if aspect_ratio_preset == "custom":
            custom_offsets = (
                max(0, int(self.get_parameter_value("left") or 0)),
                max(0, int(self.get_parameter_value("top") or 0)),
            )

        # Process the image
        self._extend_image(input_image, target_width, target_height, custom_offsets)

    def after_value_set(self, parameter: Parameter, value: Any) -> None:
        # Show/hide parameters based on aspect ratio preset selection
        if parameter == self._aspect_ratio_preset:
            if value == "custom":
                # Custom mode: show custom parameters, hide position
                self.show_parameter_by_name(self._custom_top_parameter.name)
                self.show_parameter_by_name(self._custom_bottom_parameter.name)
                self.show_parameter_by_name(self._custom_left_parameter.name)
                self.show_parameter_by_name(self._custom_right_parameter.name)
                self.hide_parameter_by_name(self._position_parameter.name)
            else:
                # Preset mode: hide custom parameters, show position
                self.hide_parameter_by_name(self._custom_top_parameter.name)
                self.hide_parameter_by_name(self._custom_bottom_parameter.name)
                self.hide_parameter_by_name(self._custom_left_parameter.name)
                self.hide_parameter_by_name(self._custom_right_parameter.name)
                self.show_parameter_by_name(self._position_parameter.name)

        # Don't auto-process - let user run manually
        return super().after_value_set(parameter, value)

    def _extend_image(
        self,
        image_artifact: ImageUrlArtifact,
        target_width: int,
        target_height: int,
        custom_offsets: tuple[int, int] | None = None,
    ) -> None:
        """Extend the image and create the mask."""
        position_str = self.get_parameter_value("position") or ImagePosition.CENTER
        position = ImagePosition(position_str)

        # Load original image
        original_image = load_pil_from_url(image_artifact.value)
        original_width, original_height = original_image.size

        # Ensure we're actually extending (target should be larger than original)
        # If target is smaller, we'll use the larger of the two dimensions
        final_width = max(target_width, original_width)
        final_height = max(target_height, original_height)

        # Get background color from parameter and look up configuration
        background_color_str = self.get_parameter_value("background_color") or "black"
        color_config = BACKGROUND_COLOR_CONFIGS[background_color_str]

        # Create new canvas with the final dimensions using color configuration
        new_image = Image.new(color_config.image_mode, (final_width, final_height), color_config.bg_color)
        mask_image = Image.new(color_config.image_mode, (final_width, final_height), color_config.mask_bg_color)

        # Calculate position for original image
        if custom_offsets is not None:
            # Place image with left, top offsets
            x, y = custom_offsets
        else:
            x, y = self._calculate_position(
                original_width,
                original_height,
                final_width,
                final_height,
                position,
            )

        # Paste original image
        new_image.paste(original_image, (x, y))

        # Create mask using foreground color for the original image area
        mask_image.paste(color_config.mask_fg_color, (x, y, x + original_width, y + original_height))

        # Save outputs
        extended_artifact = save_pil_image_to_static_file(new_image)
        mask_artifact = save_pil_image_to_static_file(mask_image)

        # Set outputs
        self.set_parameter_value("extended_image", extended_artifact)
        self.set_parameter_value("canvas_mask", mask_artifact)

        # Publish updates
        self.publish_update_to_parameter("extended_image", extended_artifact)
        self.publish_update_to_parameter("canvas_mask", mask_artifact)

    def _calculate_position(
        self, original_width: int, original_height: int, target_width: int, target_height: int, position: ImagePosition
    ) -> tuple[int, int]:
        """Calculate the position to place the original image based on position enum."""
        match position:
            case ImagePosition.CENTER:
                x = (target_width - original_width) // 2
                y = (target_height - original_height) // 2
            case ImagePosition.TOP_LEFT:
                x, y = 0, 0
            case ImagePosition.TOP_RIGHT:
                x = target_width - original_width
                y = 0
            case ImagePosition.BOTTOM_LEFT:
                x = 0
                y = target_height - original_height
            case ImagePosition.BOTTOM_RIGHT:
                x = target_width - original_width
                y = target_height - original_height
            case ImagePosition.TOP:
                x = (target_width - original_width) // 2
                y = 0
            case ImagePosition.BOTTOM:
                x = (target_width - original_width) // 2
                y = target_height - original_height
            case ImagePosition.LEFT:
                x = 0
                y = (target_height - original_height) // 2
            case ImagePosition.RIGHT:
                x = target_width - original_width
                y = (target_height - original_height) // 2
            case _:
                msg = f"Invalid position: {position}"
                raise ValueError(msg)

        return x, y
