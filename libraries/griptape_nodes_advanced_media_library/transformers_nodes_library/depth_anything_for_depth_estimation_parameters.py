import contextlib
import logging
from collections.abc import Iterator

import PIL.Image
import torch  # type: ignore[reportMissingImports]
from diffusers_nodes_library.common.utils.huggingface_utils import model_cache  # type: ignore[reportMissingImports]
from diffusers_nodes_library.common.utils.logging_utils import StdoutCapture  # type: ignore[reportMissingImports]
from transformers import AutoImageProcessor, AutoModelForDepthEstimation  # type: ignore[reportMissingImports]

from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import BaseNode
from griptape_nodes.exe_types.param_components.huggingface.huggingface_repo_parameter import HuggingFaceRepoParameter

logger = logging.getLogger("diffusers_nodes_library")


class DepthAnythingForDepthEstimationParameters:
    def __init__(self, node: BaseNode):
        self._node = node
        self._huggingface_repo_parameter = HuggingFaceRepoParameter(
            node,
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

    def add_input_parameters(self) -> None:
        self._huggingface_repo_parameter.add_input_parameters()

    def add_logs_output_parameter(self) -> None:
        self._node.add_parameter(
            Parameter(
                name="logs",
                output_type="str",
                allowed_modes={ParameterMode.OUTPUT},
                tooltip="logs",
                ui_options={"multiline": True},
            )
        )

    def get_repo_revision(self) -> tuple[str, str]:
        return self._huggingface_repo_parameter.get_repo_revision()

    def load_models(self) -> tuple[AutoImageProcessor, AutoModelForDepthEstimation]:
        repo_id, revision = self.get_repo_revision()

        # Load models using model cache
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

        return image_processor, model

    def process_depth_estimation(
        self, image_processor: AutoImageProcessor, model: AutoModelForDepthEstimation, input_image_pil: PIL.Image.Image
    ) -> PIL.Image.Image:
        # Process the image
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
        return PIL.Image.fromarray(depth.astype("uint8"))

    def create_preview_placeholder(self, size: tuple[int, int]) -> PIL.Image.Image:
        return PIL.Image.new("RGB", size, color="black")

    @contextlib.contextmanager
    def append_stdout_to_logs(self) -> Iterator[None]:
        def callback(data: str) -> None:
            self._node.append_value_to_parameter("logs", data)

        with StdoutCapture(callback):
            yield
