from typing import Any

from griptape_nodes.exe_types.core_types import Parameter
from griptape_nodes.exe_types.node_types import DataNode
from griptape_nodes_library.utils.image_utils import dict_to_image_url_artifact


class LoadImage(DataNode):
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)

        # Need to define the category
        self.category = "Image"
        self.description = "Load an image"
        image_parameter = Parameter(
            name="image",
            input_types=["ImageArtifact", "ImageUrlArtifact"],
            type="ImageArtifact",
            output_type="ImageUrlArtifact",
            default_value=None,
            ui_options={"clickable_file_browser": True, "expander": True, "edit_mask": True},
            tooltip="The image that has been generated.",
        )
        self.add_parameter(image_parameter)
        # Add input parameter for model selection

    def _to_image_artifact(self, image: Any) -> Any:
        if isinstance(image, dict):
            # Preserve any existing metadata
            metadata = image.get("metadata", {})
            artifact = dict_to_image_url_artifact(image)
            if metadata:
                # Return a dictionary with metadata
                return {"type": "ImageUrlArtifact", "value": artifact.value, "metadata": metadata}
            return artifact
        return image

    def after_value_set(self, parameter: Parameter, value: Any, modified_parameters_set: set[str]) -> None:
        if parameter.name == "image":
            image_artifact = self._to_image_artifact(value)
            self.parameter_output_values["image"] = image_artifact
        return super().after_value_set(parameter, value, modified_parameters_set)

    def process(self) -> None:
        image = self.get_parameter_value("image")
        image_artifact = self._to_image_artifact(image)
        self.parameter_output_values["image"] = image_artifact
