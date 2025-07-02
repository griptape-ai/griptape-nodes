from typing import Any

from griptape.artifacts import ImageUrlArtifact

from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import BaseNode, DataNode
from griptape_nodes_library.utils.image_utils import (
    create_alpha_mask,
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
        # Get input image
        input_image = self.get_parameter_value("input_image")

        if input_image is None:
            return

        # Normalize input to ImageUrlArtifact
        if isinstance(input_image, dict):
            input_image = dict_to_image_url_artifact(input_image)

        # Create mask from image
        self._create_mask(input_image)

    def after_incoming_connection(
        self,
        source_node: BaseNode,
        source_parameter: Parameter,
        target_parameter: Parameter,
    ) -> None:
        """Handle input connections and update outputs accordingly."""
        if target_parameter.name == "input_image":
            input_image = self.get_parameter_value("input_image")
            if input_image is not None:
                self._handle_input_image_change(input_image)

        return super().after_incoming_connection(source_node, source_parameter, target_parameter)

    def _handle_input_image_change(self, value: Any) -> None:
        # Normalize input image to ImageUrlArtifact
        if isinstance(value, dict):
            image_artifact = dict_to_image_url_artifact(value)
        else:
            image_artifact = value

        # Create mask from image
        self._create_mask(image_artifact)

    def after_value_set(self, parameter: Parameter, value: Any) -> None:
        if parameter.name == "input_image" and value is not None:
            self._handle_input_image_change(value)

        return super().after_value_set(parameter, value)

    def _create_mask(self, image_artifact: ImageUrlArtifact) -> None:
        """Create a mask from the input image and set as output_mask."""
        # Load image
        image_pil = load_pil_from_url(image_artifact.value)

        # Create mask from alpha channel
        mask = create_alpha_mask(image_pil)

        # Save output mask and create URL artifact
        output_artifact = save_pil_image_to_static_file(mask)
        self.set_parameter_value("output_mask", output_artifact)
        self.publish_update_to_parameter("output_mask", output_artifact)
