from io import BytesIO
from typing import Any

import httpx
from griptape.artifacts import ImageUrlArtifact
from PIL import Image

from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import BaseNode, DataNode
from griptape_nodes_library.utils.image_utils import (
    create_alpha_mask,
    load_pil_from_url,
    normalize_image_input,
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
                allowed_modes={ParameterMode.INPUT},
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
        input_image = normalize_image_input(input_image)

        # Create mask from image
        self._create_mask(input_image)

    def after_incoming_connection(
        self,
        source_node: BaseNode,
        source_parameter: Parameter,
        target_parameter: Parameter,
        modified_parameters_set: set[str],
    ) -> None:
        """Handle input connections and update outputs accordingly."""
        if target_parameter.name == "input_image":
            input_image = self.get_parameter_value("input_image")
            if input_image is not None:
                self._handle_input_image_change(input_image, modified_parameters_set)

        return super().after_incoming_connection(
            source_node, source_parameter, target_parameter, modified_parameters_set
        )

    def _handle_input_image_change(self, value: Any, modified_parameters_set: set[str]) -> None:
        # Normalize input image to ImageUrlArtifact
        image_artifact = normalize_image_input(value)

        # Create mask from image
        self._create_mask(image_artifact)
        modified_parameters_set.add("output_mask")

    def after_value_set(self, parameter: Parameter, value: Any, modified_parameters_set: set[str]) -> None:
        if parameter.name == "input_image" and value is not None:
            self._handle_input_image_change(value, modified_parameters_set)

        return super().after_value_set(parameter, value, modified_parameters_set)

    def _create_mask(self, image_artifact: ImageUrlArtifact) -> None:
        """Create a mask from the input image and set as output_mask."""
        # Load image
        image_pil = load_pil_from_url(image_artifact.value)

        # Create mask from alpha channel
        mask_rgb = create_alpha_mask(image_pil)

        # Save output mask and create URL artifact
        output_artifact = save_pil_image_to_static_file(mask_rgb)
        self.set_parameter_value("output_mask", output_artifact)
        self.publish_update_to_parameter("output_mask", output_artifact)

    def load_pil_from_url(self, url: str) -> Image.Image:
        """Load image from URL using httpx."""
        response = httpx.get(url, timeout=30)
        response.raise_for_status()
        return Image.open(BytesIO(response.content))
