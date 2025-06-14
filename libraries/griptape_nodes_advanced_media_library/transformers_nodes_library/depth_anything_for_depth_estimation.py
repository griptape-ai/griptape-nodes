import contextlib
import logging
from collections.abc import Iterator

import PIL.Image
import torch  # type: ignore[reportMissingImports]
from diffusers_nodes_library.common.parameters.huggingface_repo_parameter import HuggingFaceRepoParameter
from diffusers_nodes_library.common.utils.huggingface_utils import model_cache  # type: ignore[reportMissingImports]
from diffusers_nodes_library.common.utils.logging_utils import StdoutCapture  # type: ignore[reportMissingImports]
from griptape.artifacts import ImageUrlArtifact
from pillow_nodes_library.utils import (  # type: ignore[reportMissingImports]
    image_artifact_to_pil,  # type: ignore[reportMissingImports]
    pil_to_image_artifact,  # type: ignore[reportMissingImports]
)
from transformers import AutoImageProcessor, AutoModelForDepthEstimation  # type: ignore[reportMissingImports]
from utils.image_utils import load_image_from_url_artifact

from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import AsyncResult, ControlNode

logger = logging.getLogger("diffusers_nodes_library")


class DepthAnythingForDepthEstimation(ControlNode):
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)

        self._huggingface_repo_parameter = HuggingFaceRepoParameter(
            self,
            repo_ids=[
                "depth-anything/Depth-Anything-V2-Small-hf",
                "depth-anything/Depth-Anything-V2-Large-hf",
                "depth-anything/Depth-Anything-V2-Base-hf",
                "depth-anything/Depth-Anything-V2-Metric-Outdoor-Small-hf",
                "depth-anything/Depth-Anything-V2-Metric-Outdoor-Large-hf",
                "depth-anything/Depth-Anything-V2-Metric-Outdoor-Base-hf",
                "depth-anything/Depth-Anything-V2-Metric-Indoor-Small-hf",
                "depth-anything/Depth-Anything-V2-Metric-Indoor-Base-hf",
                "depth-anything/Depth-Anything-V2-Metric-Indoor-Large-hf",
            ],
        )

        self._huggingface_repo_parameter.add_input_parameters()
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
        self.add_parameter(
            Parameter(
                name="logs",
                output_type="str",
                allowed_modes={ParameterMode.OUTPUT},
                tooltip="logs",
                ui_options={"multiline": True},
            )
        )

    def process(self) -> AsyncResult | None:
        yield lambda: self._process()

    def _process(self) -> AsyncResult | None:
        repo_id, revision = self._huggingface_repo_parameter.get_repo_revision()
        input_image_artifact = self.get_parameter_value("input_image")

        if isinstance(input_image_artifact, ImageUrlArtifact):
            input_image_artifact = load_image_from_url_artifact(input_image_artifact)
        input_image_pil = image_artifact_to_pil(input_image_artifact)
        input_image_pil = input_image_pil.convert("RGB")

        # Immediately set a preview placeholder image to make it react quickly and adjust
        # the size of the image preview on the node.
        preview_placeholder_image = PIL.Image.new("RGB", input_image_pil.size, color="black")
        self.publish_update_to_parameter("output_image", pil_to_image_artifact(preview_placeholder_image))

        self.append_value_to_parameter("logs", "Preparing models...\n")
        with self._append_stdout_to_logs():
            # Load models directly in the process method using model cache
            image_processor = model_cache.from_pretrained(
                AutoImageProcessor,
                pretrained_model_name_or_path=repo_id,
                revision=revision,
                local_files_only=True,
            )
            model = model_cache.from_pretrained(
                AutoModelForDepthEstimation,
                pretrained_model_name_or_path=repo_id,
                revision=revision,
                local_files_only=True,
            )

        # Process the image directly
        inputs = image_processor(images=input_image_pil, return_tensors="pt")

        with torch.no_grad():
            outputs = model(**inputs)

        # interpolate to original size and visualize the prediction
        post_processed_output = image_processor.post_process_depth_estimation(
            outputs,
            target_sizes=[(input_image_pil.height, input_image_pil.width)],
        )

        predicted_depth = post_processed_output[0]["predicted_depth"]
        depth = (predicted_depth - predicted_depth.min()) / (predicted_depth.max() - predicted_depth.min())
        depth = depth.detach().cpu().numpy() * 255
        output_image_pil = PIL.Image.fromarray(depth.astype("uint8"))

        output_image_artifact = pil_to_image_artifact(output_image_pil)
        self.set_parameter_value("output_image", output_image_artifact)
        self.parameter_output_values["output_image"] = output_image_artifact

    @contextlib.contextmanager
    def _append_stdout_to_logs(self) -> Iterator[None]:
        def callback(data: str) -> None:
            self.append_value_to_parameter("logs", data)

        with StdoutCapture(callback):
            yield
