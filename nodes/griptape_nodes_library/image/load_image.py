import base64

from griptape.artifacts import ImageArtifact
from griptape.loaders import ImageLoader

from griptape_nodes.exe_types.core_types import Parameter
from griptape_nodes.exe_types.node_types import DataNode


def dict_to_image_artifact(image_dict, image_format=None) -> ImageArtifact:
    # Get the base64 encoded string
    base64_data = image_dict["value"]

    # If the base64 string has a prefix like "data:image/png;base64,", remove it
    if "base64," in base64_data:
        base64_data = base64_data.split("base64,")[1]

    # Decode the base64 string to bytes
    image_bytes = base64.b64decode(base64_data)

    # Determine the format from the MIME type if not specified
    if not image_format and "type" in image_dict:
        # Extract format from MIME type (e.g., 'image/png' -> 'png')
        mime_format = image_dict["type"].split("/")[1] if "/" in image_dict["type"] else None
        image_format = mime_format

    # Method 1: Use ImageLoader to parse and get all metadata
    loader = ImageLoader(format=image_format)
    image_artifact = loader.try_parse(image_bytes)

    return image_artifact


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
        # Convert to ImageArtifact
        image_artifact = dict_to_image_artifact(image)

        self.parameter_output_values["image"] = image_artifact
