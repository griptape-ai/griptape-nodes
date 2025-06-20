from typing import Any

from griptape.artifacts import ImageUrlArtifact
from PIL import Image

from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import BaseNode, DataNode
from griptape_nodes_library.utils.image_utils import (
    dict_to_image_url_artifact,
    load_pil_from_url,
    save_pil_image_to_static_file,
)


class InvertMask(DataNode):
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)

        self.add_parameter(
            Parameter(
                name="input_mask",
                default_value=None,
                input_types=["ImageArtifact", "ImageUrlArtifact"],
                output_type="ImageArtifact",
                type="ImageArtifact",
                tooltip="The mask to invert",
                ui_options={"hide_property": True},
                allowed_modes={ParameterMode.INPUT, ParameterMode.OUTPUT},
            )
        )

        self.add_parameter(
            Parameter(
                name="output_mask",
                input_types=["ImageArtifact", "ImageUrlArtifact"],
                type="ImageUrlArtifact",
                tooltip="Inverted mask image.",
                ui_options={"expander": True},
                allowed_modes={ParameterMode.OUTPUT},
            )
        )

    def process(self) -> None:
        # Get input mask
        input_mask = self.get_parameter_value("input_mask")

        if input_mask is None:
            return

        # Normalize input to ImageUrlArtifact
        if isinstance(input_mask, dict):
            input_mask = dict_to_image_url_artifact(input_mask)

        # Invert the mask
        self._invert_mask(input_mask)

    def after_incoming_connection(
        self,
        source_node: BaseNode,
        source_parameter: Parameter,
        target_parameter: Parameter,
    ) -> None:
        """Handle input connections and update outputs accordingly."""
        if target_parameter.name == "input_mask":
            input_mask = self.get_parameter_value("input_mask")
            if input_mask is not None:
                self._handle_input_mask_change(input_mask)

        return super().after_incoming_connection(source_node, source_parameter, target_parameter)

    def _handle_input_mask_change(self, value: Any) -> None:
        # Normalize input mask to ImageUrlArtifact
        if isinstance(value, dict):
            mask_artifact = dict_to_image_url_artifact(value)
        else:
            mask_artifact = value

        # Invert the mask
        self._invert_mask(mask_artifact)

    def after_value_set(self, parameter: Parameter, value: Any) -> None:
        if parameter.name == "input_mask" and value is not None:
            self._handle_input_mask_change(value)

        return super().after_value_set(parameter, value)

    def _invert_mask(self, mask_artifact: ImageUrlArtifact) -> None:
        """Invert the input mask and set as output_mask."""
        # Load mask
        mask_pil = load_pil_from_url(mask_artifact.value)

        # If image has alpha channel, use and invert the alpha channel
        if mask_pil.mode == "RGBA":
            alpha = mask_pil.getchannel("A")
            mask_to_invert = alpha
        # Convert to grayscale if needed
        elif mask_pil.mode != "L":
            mask_to_invert = mask_pil.convert("L")
        else:
            mask_to_invert = mask_pil

        # Invert the mask
        inverted_mask = Image.eval(mask_to_invert, lambda x: 255 - x)

        # Save output mask and create URL artifact
        output_artifact = save_pil_image_to_static_file(inverted_mask, image_format="PNG")
        self.set_parameter_value("output_mask", output_artifact)
        self.publish_update_to_parameter("output_mask", output_artifact)
