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
                ui_options={"hide_property": True},
            )
        )

        self.add_parameter(
            Parameter(
                name="Image_2",
                input_types=["ImageUrlArtifact", "ImageArtifact"],
                tooltip="Image 2",
                default_value=None,
                allowed_modes={ParameterMode.INPUT},
                ui_options={"hide_property": True},
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

    def after_value_set(
        self,
        parameter: Parameter,
        value: Any,
    ) -> None:
        if parameter.name not in {"Image_1", "Image_2"}:
            return super().after_value_set(parameter, value)

        # Get current images
        image_1 = self.get_parameter_value("Image_1")
        image_2 = self.get_parameter_value("Image_2")

        # Create result dictionary with current images
        result_dict = {"input_image_1": image_1, "input_image_2": image_2}

        # Update Compare parameter value
        self.set_parameter_value("Compare", result_dict)

        # Update output values for downstream connections
        self.parameter_output_values["Compare"] = result_dict

        return super().after_value_set(parameter, value)

    def process(self) -> None:
        """Process the node - logic handled in after_value_set."""
