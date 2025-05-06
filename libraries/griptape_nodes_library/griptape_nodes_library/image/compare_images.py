from typing import Any

from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import ControlNode
from griptape_nodes.traits.compare_images import CompareImagesTrait


class CompareImages(ControlNode):
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)

        self.add_parameter(
            Parameter(
                name="Image_1",
                input_types=["ImageUrlArtifact", "ImageArtifact"],
                tooltip="Image 1",
                default_value=None,
                allowed_modes={ParameterMode.INPUT},
                type="hidden",
            )
        )

        self.add_parameter(
            Parameter(
                name="Image_2",
                input_types=["ImageUrlArtifact", "ImageArtifact"],
                tooltip="Image 2",
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
                default_value={"input_image_1": None, "input_image_2": None},
                allowed_modes={ParameterMode.PROPERTY},
                traits={CompareImagesTrait()},
                ui_options={"compare": True},
            )
        )

    def after_value_set(self, parameter: Parameter, value: Any, modified_parameters_set: set[str]) -> None:
        if parameter.name in {"Image_1", "Image_2"}:
            current_value = self.get_parameter_value("Compare")
            if current_value is None:
                current_value = {"input_image_1": None, "input_image_2": None}
            if parameter.name == "Image_1":
                current_value["input_image_1"] = value
            elif parameter.name == "Image_2":
                current_value["input_image_2"] = value
            self.set_parameter_value("Compare", current_value)
            modified_parameters_set.add("Compare")
        return super().after_value_set(parameter, value, modified_parameters_set)

    def process(self) -> None:
        """Process the node by creating a dictionary from the input images."""
        # Get the input images
        image_1 = self.get_parameter_value("Image_1")
        image_2 = self.get_parameter_value("Image_2")
        # Create a dictionary with the images
        result_dict = {"input_image_1": image_1, "input_image_2": image_2}

        # Set output values
        self.parameter_output_values["Compare"] = result_dict
        self.parameter_values["Compare"] = result_dict  # For get_value compatibility
