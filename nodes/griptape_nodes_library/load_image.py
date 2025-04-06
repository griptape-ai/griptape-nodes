from griptape_nodes.exe_types.core_types import Parameter, ParameterUIOptions
from griptape_nodes.exe_types.node_types import DataNode
from griptape_nodes.retained_mode.griptape_nodes import logger


class LoadImageNode(DataNode):
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)

        # Need to define the category
        self.category = "Image"
        self.description = "Load an image"
        image_parameter = Parameter(
            name="image",
            input_types=["ImageArtifact", "BlobArtifact"],
            type="ImageArtifact",
            output_type="ImageArtifact",
            ui_options=ParameterUIOptions(
                image_type_options=ParameterUIOptions.ImageType(clickable_file_browser=True, expander=True)
            ),
            tooltip="The image that has been generated.",
        )
        self.add_parameter(image_parameter)
        # Add input parameter for model selection

    def process(self) -> None:
        logger.info(type(self.parameter_values["image"]))

        self.parameter_output_values["image"] = self.parameter_values["image"]
