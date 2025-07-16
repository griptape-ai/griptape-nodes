from io import BytesIO
from typing import Any

import requests
from griptape.artifacts import ImageArtifact, ImageUrlArtifact
from PIL import Image

from griptape_nodes.exe_types.core_types import (
    Parameter,
    ParameterMode,
)
from griptape_nodes.exe_types.node_types import BaseNode, DataNode


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
                input_types=["ImageArtifact", "ImageUrlArtifact"],
                output_type="ImageArtifact",
                type="ImageArtifact",
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

    def after_incoming_connection(
        self, source_node: BaseNode, source_parameter: Parameter, target_parameter: Parameter
    ) -> None:
        image = self.get_parameter_value("image")
        if image:
            width, height = self.get_image_dimensions(image)
            self.parameter_output_values["width"] = width
            self.parameter_output_values["height"] = height
        else:
            self.parameter_output_values["width"] = 0
            self.parameter_output_values["height"] = 0
        return super().after_incoming_connection(source_node, source_parameter, target_parameter)

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
        return 0, 0

    def process(self) -> None:
        image = self.get_parameter_value("image")
        width, height = self.get_image_dimensions(image)

        self.parameter_output_values["image"] = image
        self.parameter_output_values["width"] = width
        self.parameter_output_values["height"] = height
