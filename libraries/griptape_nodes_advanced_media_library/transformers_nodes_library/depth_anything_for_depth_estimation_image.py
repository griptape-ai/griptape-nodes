import logging

from griptape.artifacts import ImageUrlArtifact
from pillow_nodes_library.utils import (  # type: ignore[reportMissingImports]
    image_artifact_to_pil,  # type: ignore[reportMissingImports]
    pil_to_image_artifact,  # type: ignore[reportMissingImports]
)
from utils.image_utils import load_image_from_url_artifact

from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import AsyncResult, ControlNode
from transformers_nodes_library.depth_anything_for_depth_estimation_parameters import (
    DepthAnythingForDepthEstimationParameters,
)

logger = logging.getLogger("diffusers_nodes_library")


class DepthAnythingForDepthEstimationImage(ControlNode):
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.params = DepthAnythingForDepthEstimationParameters(self)
        self.params.add_input_parameters()
        self.add_parameter(
            Parameter(
                name="input_image",
                input_types=["ImageArtifact", "ImageUrlArtifact"],
                type="ImageArtifact",
                tooltip="input_image",
            )
        )
        self.add_parameter(
            Parameter(
                name="output_image",
                output_type="ImageArtifact",
                tooltip="The output image",
                allowed_modes={ParameterMode.OUTPUT},
            )
        )
        self.params.add_logs_output_parameter()

    def process(self) -> AsyncResult | None:
        yield lambda: self._process()

    def _process(self) -> AsyncResult | None:
        input_image_artifact = self.get_parameter_value("input_image")

        if isinstance(input_image_artifact, ImageUrlArtifact):
            input_image_artifact = load_image_from_url_artifact(input_image_artifact)
        input_image_pil = image_artifact_to_pil(input_image_artifact)
        input_image_pil = input_image_pil.convert("RGB")

        # Immediately set a preview placeholder image to make it react quickly and adjust
        # the size of the image preview on the node.
        preview_placeholder_image = self.params.create_preview_placeholder(input_image_pil.size)
        self.publish_update_to_parameter("output_image", pil_to_image_artifact(preview_placeholder_image))

        self.append_value_to_parameter("logs", "Preparing models...\n")
        with self.params.append_stdout_to_logs():
            image_processor, model = self.params.load_models()

        # Process the image using shared parameters
        output_image_pil = self.params.process_depth_estimation(image_processor, model, input_image_pil)

        output_image_artifact = pil_to_image_artifact(output_image_pil)
        self.set_parameter_value("output_image", output_image_artifact)
        self.parameter_output_values["output_image"] = output_image_artifact
