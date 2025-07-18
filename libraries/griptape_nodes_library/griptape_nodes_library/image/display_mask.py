from typing import Any

from griptape.artifacts import ImageUrlArtifact

from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import BaseNode, DataNode
from griptape_nodes.traits.options import Options
from griptape_nodes_library.utils.image_utils import (
    dict_to_image_url_artifact,
    load_pil_from_url,
    save_pil_image_to_static_file,
)


class DisplayMask(DataNode):
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)

        self.add_parameter(
            Parameter(
                name="input_image",
                default_value=None,
                input_types=["ImageArtifact", "ImageUrlArtifact"],
                output_type="ImageArtifact",
                type="ImageArtifact",
                tooltip="The image to create a mask from",
                ui_options={"hide_property": True},
                allowed_modes={ParameterMode.INPUT, ParameterMode.OUTPUT},
            )
        )

        channel_param = Parameter(
            name="channel",
            type="str",
            tooltip="Channel to extract as mask (red, green, blue, or alpha).",
            default_value="alpha",
            ui_options={"expander": True, "edit_mask": True, "edit_mask_paint_mask": True},
        )
        channel_param.add_trait(Options(choices=["red", "green", "blue", "alpha"]))
        self.add_parameter(channel_param)

        self.add_parameter(
            Parameter(
                name="output_mask",
                input_types=["ImageArtifact", "ImageUrlArtifact"],
                type="ImageUrlArtifact",
                tooltip="Generated mask image.",
                ui_options={"expander": True},
                allowed_modes={ParameterMode.OUTPUT},
            )
        )

    def process(self) -> None:
        # Get input image and channel
        input_image = self.get_parameter_value("input_image")
        channel = self.get_parameter_value("channel")

        if input_image is None:
            return

        # Normalize input to ImageUrlArtifact
        if isinstance(input_image, dict):
            input_image = dict_to_image_url_artifact(input_image)

        # Create mask from image
        self._create_mask(input_image, channel)

    def after_incoming_connection(
        self,
        source_node: BaseNode,
        source_parameter: Parameter,
        target_parameter: Parameter,
    ) -> None:
        """Handle input connections and update outputs accordingly."""
        if target_parameter.name == "input_image":
            input_image = self.get_parameter_value("input_image")
            channel = self.get_parameter_value("channel")
            if input_image is not None:
                self._handle_input_image_change(input_image, channel)

        return super().after_incoming_connection(source_node, source_parameter, target_parameter)

    def _handle_input_image_change(self, value: Any, channel: str) -> None:
        # Normalize input image to ImageUrlArtifact
        if isinstance(value, dict):
            image_artifact = dict_to_image_url_artifact(value)
        else:
            image_artifact = value

        # Create mask from image
        self._create_mask(image_artifact, channel)

    def after_value_set(self, parameter: Parameter, value: Any) -> None:
        if parameter.name in ["input_image", "channel"] and value is not None:
            input_image = self.get_parameter_value("input_image")
            channel = self.get_parameter_value("channel")
            if input_image is not None:
                self._handle_input_image_change(input_image, channel)

        return super().after_value_set(parameter, value)

    def _extract_channel_as_mask(self, image_pil: Any, channel: str) -> Any:  # noqa: C901, PLR0911, PLR0912
        """Extract the specified channel from the image as a mask."""
        match image_pil.mode:
            case "RGB":
                if channel == "red":
                    r, _, _ = image_pil.split()
                    return r
                if channel == "green":
                    _, g, _ = image_pil.split()
                    return g
                if channel == "blue":
                    _, _, b = image_pil.split()
                    return b
                # alpha not available in RGB, use red as fallback
                r, _, _ = image_pil.split()
                return r
            case "RGBA":
                if channel == "red":
                    r, _, _, _ = image_pil.split()
                    return r
                if channel == "green":
                    _, g, _, _ = image_pil.split()
                    return g
                if channel == "blue":
                    _, _, b, _ = image_pil.split()
                    return b
                if channel == "alpha":
                    _, _, _, a = image_pil.split()
                    return a
                # Fallback to red channel
                r, _, _, _ = image_pil.split()
                return r
            case "L":
                # Grayscale image - use directly
                return image_pil
            case "LA":
                if channel == "alpha":
                    _, a = image_pil.split()
                    return a
                # Use grayscale channel
                l, _ = image_pil.split()
                return l
            case _:
                msg = f"{self.name}: Unsupported image mode: {image_pil.mode}"
                raise ValueError(msg)

    def _create_mask(self, image_artifact: ImageUrlArtifact, channel: str) -> None:
        """Create a mask from the input image using the specified channel and set as output_mask."""
        # Load image
        image_pil = load_pil_from_url(image_artifact.value)

        # Extract the specified channel as mask
        mask = self._extract_channel_as_mask(image_pil, channel)

        # Save output mask and create URL artifact
        output_artifact = save_pil_image_to_static_file(mask)
        self.set_parameter_value("output_mask", output_artifact)
        self.publish_update_to_parameter("output_mask", output_artifact)
