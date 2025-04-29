from griptape.artifacts import ImageUrlArtifact
from griptape.loaders import ImageLoader

from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import DataNode
from griptape_nodes_library.utils.image_utils import dict_to_image_artifact


class LoadImage(DataNode):
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)

        # Need to define the category
        self.category = "Image"
        self.description = "Load an image"

        self.add_parameter(
            Parameter(
                name="filepath",
                input_types=["str"],
                type="str",
                output_type="str",
                ui_options={
                    "clickable_file_browser": True,
                    "filetypes": ["jpg", "jpeg", "png", "gif", "bmp", "webp"],
                    "placeholder_text": "The path to the image file.",
                },
                tooltip="Path to the image file.",
            )
        )
        self.add_parameter(
            Parameter(
                name="image",
                input_types=["ImageArtifact", "BlobArtifact", "ImageUrlArtifact"],
                type="ImageUrlArtifact",
                output_type="ImageUrlArtifact",
                ui_options={"clickable_file_browser": True, "expander": True},
                allowed_modes={ParameterMode.OUTPUT, ParameterMode.PROPERTY},
                tooltip="The image that has been generated.",
            )
        )
        # Add input parameter for model selection

    def process(self) -> None:
        image = self.parameter_values["image"]

        if isinstance(image, ImageUrlArtifact):
            image_artifact = ImageLoader().parse(image.to_bytes())
        else:
            # Convert to ImageArtifact
            image_artifact = dict_to_image_artifact(image)

        self.parameter_output_values["image"] = image_artifact
