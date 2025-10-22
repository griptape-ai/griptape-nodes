from io import BytesIO
from typing import Any

from griptape.artifacts import ImageArtifact, ImageUrlArtifact
from PIL import Image

from griptape_nodes.exe_types.core_types import Parameter, ParameterGroup, ParameterMode
from griptape_nodes.exe_types.node_types import DataNode
from griptape_nodes_library.utils.image_utils import (
    calculate_aspect_ratio,
    get_image_color_info,
    get_image_dimensions_from_artifact,
    get_image_format_from_artifact,
    load_pil_from_url,
)


class ImageDetails(DataNode):
    """Extract detailed information from an image including dimensions, aspect ratio, color space, and format."""

    def __init__(
        self,
        name: str,
        metadata: dict[Any, Any] | None = None,
        value: Any = None,
    ) -> None:
        super().__init__(name, metadata)

        # Add input parameter for the image
        self.add_parameter(
            Parameter(
                name="image",
                default_value=value,
                input_types=["ImageUrlArtifact", "ImageArtifact"],
                type="ImageUrlArtifact",
                tooltip="The image to analyze",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            )
        )

        # Dimensions group (default open)
        with ParameterGroup(name="Dimensions") as dimensions_group:
            self._width_parameter = Parameter(
                name="width",
                type="int",
                default_value=0,
                output_type="int",
                tooltip="Image width in pixels",
                allowed_modes={ParameterMode.OUTPUT},
                settable=False,
            )

            self._height_parameter = Parameter(
                name="height",
                type="int",
                default_value=0,
                output_type="int",
                tooltip="Image height in pixels",
                allowed_modes={ParameterMode.OUTPUT},
                settable=False,
            )

            self._ratio_str_parameter = Parameter(
                name="ratio_str",
                type="str",
                default_value="0:0",
                output_type="str",
                tooltip="Aspect ratio as string (e.g., '16:9')",
                allowed_modes={ParameterMode.OUTPUT},
                settable=False,
            )

            self._ratio_decimal_parameter = Parameter(
                name="ratio_decimal",
                type="float",
                default_value=0.0,
                output_type="float",
                tooltip="Aspect ratio as decimal (width/height)",
                allowed_modes={ParameterMode.OUTPUT},
                settable=False,
            )
        self.add_node_element(dimensions_group)

        # Color Details group (collapsed by default)
        with ParameterGroup(name="Color Details", ui_options={"collapsed": True}) as color_group:
            self._color_space_parameter = Parameter(
                name="color_space",
                type="str",
                default_value="UNKNOWN",
                output_type="str",
                tooltip="Color space/mode (e.g., 'RGB', 'RGBA', 'L')",
                allowed_modes={ParameterMode.OUTPUT},
                settable=False,
            )

            self._channels_parameter = Parameter(
                name="channels",
                type="int",
                default_value=0,
                output_type="int",
                tooltip="Number of color channels",
                allowed_modes={ParameterMode.OUTPUT},
                settable=False,
            )
        self.add_node_element(color_group)

        # Image Format group (collapsed by default)
        with ParameterGroup(name="Image Format", ui_options={"collapsed": True}) as format_group:
            self._format_parameter = Parameter(
                name="format",
                type="str",
                default_value="UNKNOWN",
                output_type="str",
                tooltip="Image format (e.g., 'JPEG', 'PNG', 'WEBP')",
                allowed_modes={ParameterMode.OUTPUT},
                settable=False,
            )
        self.add_node_element(format_group)

    def set_parameter_value(
        self,
        param_name: str,
        value: Any,
        *,
        initial_setup: bool = False,
        emit_change: bool = True,
        skip_before_value_set: bool = False,
    ) -> None:
        """Override to update outputs immediately when image parameter is set."""
        super().set_parameter_value(
            param_name,
            value,
            initial_setup=initial_setup,
            emit_change=emit_change,
            skip_before_value_set=skip_before_value_set,
        )

        if param_name == "image":
            self._update_image_details(value)

    def _update_image_details(self, image: ImageUrlArtifact | ImageArtifact | None) -> None:
        """Update all output values based on the image."""
        # Failure case: no image provided
        if image is None:
            self._set_default_values()
            return

        # Extract dimensions
        width, height = get_image_dimensions_from_artifact(image)

        # Failure case: could not get dimensions
        if width == 0 and height == 0:
            self._set_default_values()
            return

        self.parameter_output_values["width"] = width
        self.parameter_output_values["height"] = height

        # Calculate aspect ratio
        ratio = calculate_aspect_ratio(width, height)
        if ratio is None or (ratio[0] == 0 and ratio[1] == 0):
            ratio_str = "0:0"
            ratio_decimal = 0.0
        else:
            ratio_str = f"{ratio[0]}:{ratio[1]}"
            ratio_decimal = ratio[0] / ratio[1]

        self.parameter_output_values["ratio_str"] = ratio_str
        self.parameter_output_values["ratio_decimal"] = ratio_decimal

        # Extract color information and format
        pil_image = self._load_pil_image(image)

        # Failure case: could not load PIL image
        if pil_image is None:
            self._set_default_color_and_format_values()
            return

        # Success path: extract color and format information
        color_info = get_image_color_info(pil_image)
        self.parameter_output_values["color_space"] = color_info.color_space
        self.parameter_output_values["channels"] = color_info.channels

        image_format = get_image_format_from_artifact(image)
        self.parameter_output_values["format"] = image_format

    def process(self) -> None:
        """Extract and output all image details.

        Note: The actual extraction happens in set_parameter_value when the image
        parameter is set, so this method just refreshes the outputs.
        """
        image = self.get_parameter_value("image")
        self._update_image_details(image)

    def _load_pil_image(self, image: ImageUrlArtifact | ImageArtifact) -> Image.Image | None:
        """Load PIL Image from artifact."""
        if isinstance(image, ImageArtifact):
            try:
                return Image.open(BytesIO(image.value))
            except (OSError, ValueError):
                # OSError: corrupted or unsupported image file
                # ValueError: invalid image data
                return None

        if isinstance(image, ImageUrlArtifact):
            try:
                return load_pil_from_url(image.value)
            except (OSError, ValueError):
                # OSError: network error, corrupted file, or unsupported format
                # ValueError: invalid URL or image data
                return None

        return None

    def _set_default_values(self) -> None:
        """Set all output values to defaults."""
        self.parameter_output_values["width"] = 0
        self.parameter_output_values["height"] = 0
        self.parameter_output_values["ratio_str"] = "0:0"
        self.parameter_output_values["ratio_decimal"] = 0.0
        self._set_default_color_and_format_values()

    def _set_default_color_and_format_values(self) -> None:
        """Set color and format output values to defaults."""
        self.parameter_output_values["color_space"] = "UNKNOWN"
        self.parameter_output_values["channels"] = 0
        self.parameter_output_values["format"] = "UNKNOWN"
