from io import BytesIO
from typing import Any

import httpx
from griptape.artifacts import ImageUrlArtifact
from PIL import Image

from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import BaseNode, DataNode
from griptape_nodes.retained_mode.griptape_nodes import logger
from griptape_nodes_library.utils.image_utils import (
    dict_to_image_url_artifact,
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
                allowed_modes={ParameterMode.INPUT},
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

        # Normalize dict input to ImageUrlArtifact
        if isinstance(input_mask, dict):
            input_mask = dict_to_image_url_artifact(input_mask)

        # Invert the mask
        self._invert_mask(input_mask)

    def after_incoming_connection(
        self,
        source_node: BaseNode,
        source_parameter: Parameter,
        target_parameter: Parameter,
        modified_parameters_set: set[str],
    ) -> None:
        """Handle input connections and update outputs accordingly."""
        if target_parameter.name == "input_mask":
            input_mask = self.get_parameter_value("input_mask")
            if input_mask is not None:
                self._handle_input_mask_change(input_mask, modified_parameters_set)

        return super().after_incoming_connection(
            source_node, source_parameter, target_parameter, modified_parameters_set
        )

    def _handle_input_mask_change(self, value: Any, modified_parameters_set: set[str]) -> None:
        # Normalize input mask to ImageUrlArtifact if needed
        mask_artifact = value
        if isinstance(value, dict):
            mask_artifact = dict_to_image_url_artifact(value)

        # Invert the mask
        self._invert_mask(mask_artifact)
        modified_parameters_set.add("output_mask")

    def after_value_set(self, parameter: Parameter, value: Any, modified_parameters_set: set[str]) -> None:
        if parameter.name == "input_mask" and value is not None:
            self._handle_input_mask_change(value, modified_parameters_set)

        logger.info(f"modified_parameters_set: {modified_parameters_set}")
        return super().after_value_set(parameter, value, modified_parameters_set)

    def _invert_mask(self, mask_artifact: ImageUrlArtifact) -> None:
        """Invert the input mask and set as output_mask."""
        # Load mask
        mask_pil = self.load_pil_from_url(mask_artifact.value)

        # Convert to grayscale if needed
        if mask_pil.mode != "L":
            mask_pil = mask_pil.convert("L")

        # Invert the mask
        inverted_mask = Image.eval(mask_pil, lambda x: 255 - x)

        # Save output mask and create URL artifact
        output_artifact = save_pil_image_to_static_file(inverted_mask)
        self.set_parameter_value("output_mask", output_artifact)
        self.publish_update_to_parameter("output_mask", output_artifact)

    def load_pil_from_url(self, url: str) -> Image.Image:
        """Load image from URL using httpx."""
        response = httpx.get(url, timeout=30)
        response.raise_for_status()
        return Image.open(BytesIO(response.content))
