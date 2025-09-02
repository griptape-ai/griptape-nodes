from typing import Any

from griptape.artifacts import ImageUrlArtifact

from griptape_nodes.exe_types.core_types import Parameter, ParameterMessage, ParameterMode
from griptape_nodes.exe_types.node_types import DataNode
from griptape_nodes_library.utils.three_d_utils import dict_to_three_d_url_artifact


class LoadThreeD(DataNode):
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)

        # Need to define the category
        self.category = "3D"
        self.description = "Load a 3D file"
        three_d_parameter = Parameter(
            name="3d",
            input_types=["ThreeDArtifact", "ThreeDUrlArtifact"],
            type="ThreeDUrlArtifact",
            output_type="ThreeDUrlArtifact",
            default_value=None,
            ui_options={"clickable_file_browser": True, "expander": True},
            tooltip="The 3D file that has been loaded.",
        )
        self.add_parameter(three_d_parameter)

        self.add_node_element(
            ParameterMessage(
                variant="none",
                name="help_message",
                value='To output an image of the model, click "Save Snapshot".',
                ui_options={"text_align": "text-center"},
            )
        )
        image_parameter = Parameter(
            name="image",
            type="ImageUrlArtifact",
            default_value=None,
            tooltip="The image of the 3D file.",
            allowed_modes={ParameterMode.PROPERTY, ParameterMode.OUTPUT},
        )
        self.add_parameter(image_parameter)

    def after_value_set(
        self,
        parameter: Parameter,
        value: Any,
    ) -> None:
        if parameter.name == "3d":
            image_url = value.get("metadata", {}).get("imageUrl")
            if image_url:
                image_artifact = ImageUrlArtifact(value=image_url)
                self.set_parameter_value("image", image_artifact)
                self.parameter_output_values["image"] = image_artifact
                self.hide_message_by_name("help_message")
            else:
                self.show_message_by_name("help_message")

        return super().after_value_set(parameter, value)

    def process(self) -> None:
        three_d = self.get_parameter_value("3d")
        image = self.get_parameter_value("image")

        if isinstance(three_d, dict):
            three_d_artifact = dict_to_three_d_url_artifact(three_d)
        else:
            three_d_artifact = three_d

        self.parameter_output_values["image"] = image
        self.parameter_output_values["3d"] = three_d_artifact
