from griptape_nodes.exe_types.core_types import Parameter, ParameterUIOptions, ParameterMode
from griptape_nodes.exe_types.node_types import DataNode


class LoadImageNode(DataNode):
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)

        # Need to define the category
        self.category = "Image"
        self.description = "Load an image"
        self.add_parameter(
            Parameter(
                name="image",
                allowed_modes={ParameterMode.OUTPUT},
                output_type="ImageArtifact",
                default_value=None,
                tooltip="The loaded image",
            )
        )
        # Add input parameter for model selection

    def process(self) -> None:
        print("We need to do something with this image node..")
        self.parameter_output_values["image"] = self.parameter_values["image"]
