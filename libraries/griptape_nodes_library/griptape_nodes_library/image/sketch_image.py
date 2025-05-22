from griptape_nodes.exe_types.core_types import Parameter
from griptape_nodes.exe_types.node_types import DataNode
from griptape_nodes_library.utils.image_utils import dict_to_image_url_artifact


class SketchImage(DataNode):
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)

        self.category = "Image"
        self.description = "Sketch an image (optionally on top of another image)."

        self.add_parameter(
            Parameter(
                name="image",
                input_types=["ImageArtifact", "ImageUrlArtifact"],
                type="ImageArtifact",
                tooltip="Optional base image to draw over.",
                ui_options={"optional": True, "expander": True, "canvas": True},
            )
        )

    def process(self) -> None:
        # Get values
        image = self.get_parameter_value("image")

        # Normalize
        if isinstance(image, dict):
            image = dict_to_image_url_artifact(image)

        # Set outputs
        self.parameter_output_values["image"] = image
