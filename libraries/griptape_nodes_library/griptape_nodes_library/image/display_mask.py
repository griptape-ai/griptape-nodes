from typing import Any

from griptape.artifacts import ImageUrlArtifact

from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import BaseNode, DataNode
from griptape_nodes.traits.options import Options
from griptape_nodes_library.utils.file_utils import generate_filename
from griptape_nodes_library.utils.image_utils import (
    dict_to_image_url_artifact,
    extract_channel_from_image,
    load_pil_from_url,
    save_pil_image_with_named_filename,
)


class DisplayMask(DataNode):
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)

        # Default output parameter name
        self._output_param_name = "output_mask"

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
                name=self._output_param_name,
                input_types=["ImageArtifact", "ImageUrlArtifact"],
                type="ImageUrlArtifact",
                tooltip="Generated mask image.",
                ui_options={"expander": True},
                allowed_modes={ParameterMode.OUTPUT},
            )
        )

    def _set_output_parameter_name(self, name: str) -> None:
        """Set the name of the output parameter. Must be called before adding the output parameter."""
        self._output_param_name = name

    def _get_output_parameter_name(self) -> str:
        """Get the name of the output parameter."""
        return self._output_param_name

    def process(self) -> None:
        """Process the node during execution."""
        input_image = self.get_parameter_value("input_image")
        channel = self.get_parameter_value("channel")

        if input_image is None:
            return

        # Normalize input to ImageUrlArtifact
        if isinstance(input_image, dict):
            input_image = dict_to_image_url_artifact(input_image)

        # Create mask from image
        self._extract_channel(input_image, channel)

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
        self._extract_channel(image_artifact, channel)

    def after_value_set(self, parameter: Parameter, value: Any) -> None:
        if parameter.name in ["input_image", "channel"] and value is not None:
            input_image = self.get_parameter_value("input_image")
            channel = self.get_parameter_value("channel")
            if input_image is not None:
                self._handle_input_image_change(input_image, channel)

        return super().after_value_set(parameter, value)

    def _extract_channel(self, image_artifact: ImageUrlArtifact, channel: str) -> None:
        """Extract a channel from the input image and set as output."""
        # Load image
        image_pil = load_pil_from_url(image_artifact.value)

        # Extract the specified channel as mask
        mask = extract_channel_from_image(image_pil, channel, "image")

        # Save output mask and create URL artifact with proper filename
        # Generate a meaningful filename
        filename = generate_filename(
            node_name=self.name,
            suffix="_display_mask",
            extension="png",
        )
        output_artifact = save_pil_image_with_named_filename(mask, filename, "PNG")
        output_param_name = self._get_output_parameter_name()
        self.set_parameter_value(output_param_name, output_artifact)
        self.publish_update_to_parameter(output_param_name, output_artifact)
