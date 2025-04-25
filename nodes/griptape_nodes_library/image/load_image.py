from griptape.artifacts import ImageArtifact

from griptape_nodes.exe_types.core_types import Parameter
from griptape_nodes.exe_types.node_types import DataNode
from griptape_nodes_library.utils.image_utils import dict_to_image_artifact


class LoadImage(DataNode):
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
            ui_options={"clickable_file_browser": True, "expander": True},
            tooltip="The image that has been generated.",
        )
        self.add_parameter(image_parameter)
        # Add input parameter for model selection

    def process(self) -> None:
        image = self.parameter_values["image"]
        # Convert to ImageArtifact, if it's not one already.
        if isinstance(image, ImageArtifact):
            image_artifact = image  # No transform necessary.
        elif isinstance(image, dict):
            image_artifact = dict_to_image_artifact(
                image
            )  # would this ever happen? Do BlobArtifacts come in as dicts? Should we handle BlobArtifact separately?
        else:
            image_artifact = None  # I don't know how to handle this.

        if image_artifact:
            self.parameter_output_values["image"] = image_artifact
