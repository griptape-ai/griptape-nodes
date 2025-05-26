from typing import Any

from griptape_nodes.exe_types.core_types import Parameter, ParameterMessage, ParameterMode
from griptape_nodes.exe_types.node_types import DataNode

# from griptape_nodes_library.utils.gltf_utils import dict_to_gltf_url_artifact


class LoadGLTF(DataNode):
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)

        # Need to define the category
        self.category = "3D"
        self.description = "Load a GLTF file"
        gltf_parameter = Parameter(
            name="gltf",
            input_types=["GLTFArtifact", "GLTFUrlArtifact"],
            type="GLTFArtifact",
            output_type="GLTFUrlArtifact",
            default_value=None,
            ui_options={"clickable_file_browser": True, "expander": True},
            tooltip="The GLTF file that has been loaded.",
        )
        self.add_parameter(gltf_parameter)

        self.add_node_element(
            ParameterMessage(
                variant="none",
                name="help_message",
                value='To output an image of the model, click "Save Snapshot".',
            )
        )
        image_parameter = Parameter(
            name="image",
            type="ImageUrlArtifact",
            default_value=None,
            tooltip="The image of the GLTF file.",
            allowed_modes={ParameterMode.PROPERTY, ParameterMode.OUTPUT},
            ui_options={"hide": True},
        )
        self.add_parameter(image_parameter)

    def after_value_set(self, parameter: Parameter, value: Any, modified_parameters_set: set[str]) -> None:
        if parameter.name == "gltf":
            image_url = value.get("imageUrl")
            if image_url:
                self.set_parameter_value("image", image_url)
                self.parameter_output_values["image"] = image_url
                self.show_parameter_by_name("image")
                self.hide_message_by_name("help_message")
            else:
                self.show_message_by_name("help_message")
                self.hide_parameter_by_name("image")

            modified_parameters_set.add("image")
        return super().after_value_set(parameter, value, modified_parameters_set)

    def process(self) -> None:
        gltf = self.get_parameter_value("gltf")
        self.parameter_output_values["gltf"] = gltf
        self.parameter_output_values["image"] = gltf.get("imageUrl")
