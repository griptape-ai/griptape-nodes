from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import DataNode
from griptape_nodes_library.utils.image_utils import dict_to_image_url_artifact


class Webcam(DataNode):
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)

        image_parameter = Parameter(
            name="image",
            input_types=["ImageArtifact", "ImageUrlArtifact", "dict"],
            type="ImageArtifact",
            output_type="ImageUrlArtifact",
            ui_options={"webcam_capture_image": True, "expander": True},
            tooltip="The image that has been captured.",
            allowed_modes={ParameterMode.OUTPUT, ParameterMode.PROPERTY},
        )
        self.add_parameter(image_parameter)

    def process(self) -> None:
        image = self.get_parameter_value("image")

        if isinstance(image, dict):
            image_artifact = dict_to_image_url_artifact(image)
        else:
            image_artifact = image

        self.parameter_output_values["image"] = image_artifact
