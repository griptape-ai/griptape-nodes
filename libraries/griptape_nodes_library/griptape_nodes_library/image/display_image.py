from io import BytesIO
from typing import Any

import requests
from griptape.artifacts import ImageArtifact, ImageUrlArtifact
from PIL import Image

from griptape_nodes.exe_types.core_types import (
    Parameter,
    ParameterMode,
)
from griptape_nodes.exe_types.node_types import DataNode
from griptape_nodes.retained_mode.griptape_nodes import logger


class DisplayImage(DataNode):
    def __init__(
        self,
        name: str,
        metadata: dict[Any, Any] | None = None,
        value: Any = None,
    ) -> None:
        super().__init__(name, metadata)

        # Add parameter for the image
        self.add_parameter(
            Parameter(
                name="image",
                default_value=value,
                input_types=["ImageUrlArtifact", "ImageArtifact"],
                output_type="ImageUrlArtifact",
                type="ImageUrlArtifact",
                tooltip="The image to display",
                allowed_modes={ParameterMode.INPUT, ParameterMode.OUTPUT, ParameterMode.PROPERTY},
            )
        )
        self.add_parameter(
            Parameter(
                name="width",
                type="int",
                default_value=0,
                tooltip="The width of the image",
                allowed_modes={ParameterMode.OUTPUT},
                ui_options={"hide": True},
            )
        )
        self.add_parameter(
            Parameter(
                name="height",
                type="int",
                default_value=0,
                tooltip="The height of the image",
                allowed_modes={ParameterMode.OUTPUT},
                ui_options={"hide": True},
            )
        )

    def _update_output(self) -> None:
        """Update the output image and dimensions."""
        image = self.get_parameter_value("image")
        # Update output value for downstream connections
        self.parameter_output_values["image"] = image
        # Update dimensions
        width, height = self.get_image_dimensions(image) if image else (0, 0)
        self.parameter_output_values["width"] = width
        self.parameter_output_values["height"] = height

    def after_value_set(self, parameter: Parameter, value: Any) -> None:
        if parameter.name == "image":
            self._update_output()
        return super().after_value_set(parameter, value)

    def get_image_dimensions(self, image: ImageArtifact | ImageUrlArtifact) -> tuple[int, int]:
        """Get image dimensions from either ImageArtifact or ImageUrlArtifact."""
        if isinstance(image, ImageArtifact):
            return image.width, image.height
        if isinstance(image, ImageUrlArtifact):
            response = requests.get(image.value, timeout=30)
            response.raise_for_status()
            image_data = response.content
            pil_image = Image.open(BytesIO(image_data))
            return pil_image.width, pil_image.height
        if image:
            logger.warning(f"{self.name}: Could not determine image dimensions, as it is not a valid image")
        return 0, 0

    def process(self) -> None:
        """Process the node during execution."""
        self._update_output()
