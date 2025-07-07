from typing import Any

from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import ControlNode
from griptape_nodes.traits.compare_images import CompareImagesTrait


class CompareImages(ControlNode):
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)

        self.add_parameter(
            Parameter(
                name="A",
                input_types=["ImageUrlArtifact", "ImageArtifact"],
                tooltip="Image A",
                default_value=None,
                allowed_modes={ParameterMode.INPUT},
                type="hidden",
            )
        )

        self.add_parameter(
            Parameter(
                name="B",
                input_types=["ImageUrlArtifact", "ImageArtifact"],
                tooltip="Image B",
                default_value=None,
                allowed_modes={ParameterMode.INPUT},
                type="hidden",
            )
        )

        self.add_parameter(
            Parameter(
                name="Compare",
                type="dict",
                tooltip="Compare two images",
                default_value={"input_image_a": None, "input_image_b": None},
                allowed_modes={ParameterMode.PROPERTY},
                traits={CompareImagesTrait()},
                ui_options={"compare": True},
            )
        )

    def after_value_set(
        self,
        parameter: Parameter,
        value: Any,
    ) -> None:
        if parameter.name in {"Image_1", "Image_2"}:
            current_value = self.get_parameter_value("Compare")
            if current_value is None:
                current_value = {"input_image_a": None, "input_image_b": None}
            if parameter.name == "A":
                current_value["input_image_a"] = value
            elif parameter.name == "B":
                current_value["input_image_b"] = value
            self.set_parameter_value("Compare", current_value)
        return super().after_value_set(parameter, value)

    def process(self) -> None:
        """Process the node by creating a dictionary from the input images."""
        # Get the input images
        image_a = self.get_parameter_value("A")
        image_b = self.get_parameter_value("B")
        # Create a dictionary with the images
        result_dict = {"input_image_a": image_a, "input_image_b": image_b}

        # Set output values
        self.parameter_output_values["Compare"] = result_dict
        self.parameter_values["Compare"] = result_dict  # For get_value compatibility
