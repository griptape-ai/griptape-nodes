import logging
from pathlib import Path
from typing import Any
import uuid

from griptape.artifacts import ImageUrlArtifact
from griptape.loaders import ImageLoader
from PIL.Image import Image
from pillow_nodes_library.utils import image_artifact_to_pil  # type: ignore[reportMissingImports]

from diffusers_nodes_library.common.parameters.huggingface_repo_parameter import HuggingFaceRepoParameter
from diffusers_nodes_library.common.parameters.seed_parameter import SeedParameter
from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import BaseNode
from griptape_nodes_library.video.video_url_artifact import VideoUrlArtifact  # type: ignore[reportMissingImports]
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes  # type: ignore[reportMissingImports]

logger = logging.getLogger("diffusers_nodes_library")


class StableVideoDiffusionPipelineParameters:
    """All parameter handling for Stable Video Diffusion pipelines (image-to-video)."""

    def __init__(self, node: BaseNode):
        self._node = node
        self._huggingface_repo_parameter = HuggingFaceRepoParameter(
            node,
            repo_ids=[
                "stabilityai/stable-video-diffusion-img2vid-xt",
                "stabilityai/stable-video-diffusion-img2vid",
            ],
        )
        self._seed_parameter = SeedParameter(node)

    # --------------------------------------------------------------
    # Parameter registration helpers
    # --------------------------------------------------------------
    def add_input_parameters(self) -> None:
        self._huggingface_repo_parameter.add_input_parameters()

        self._node.add_parameter(
            Parameter(
                name="image",
                input_types=["ImageArtifact", "ImageUrlArtifact"],
                type="ImageArtifact",
                tooltip="Input image to generate video from",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="width",
                default_value=1024,
                input_types=["int"],
                type="int",
                tooltip="Frame width in pixels",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="height",
                default_value=576,
                input_types=["int"],
                type="int",
                tooltip="Frame height in pixels",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="num_frames",
                default_value=25,
                input_types=["int"],
                type="int",
                tooltip="Number of frames in output video",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="num_inference_steps",
                default_value=25,
                input_types=["int"],
                type="int",
                tooltip="Number of denoising steps",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="motion_bucket_id",
                default_value=127,
                input_types=["int"],
                type="int",
                tooltip="Motion conditioning, higher values create more motion",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="fps",
                default_value=7,
                input_types=["int"],
                type="int",
                tooltip="Frames per second of output video",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="noise_aug_strength",
                default_value=0.02,
                input_types=["float"],
                type="float",
                tooltip="Amount of noise added to conditioning image",
            )
        )

        self._seed_parameter.add_input_parameters()

    def add_output_parameters(self) -> None:
        self._node.add_parameter(
            Parameter(
                name="output_video",
                output_type="VideoUrlArtifact",
                tooltip="Generated video",
                allowed_modes={ParameterMode.OUTPUT},
            )
        )

    # --------------------------------------------------------------
    # Validation & life-cycle hooks
    # --------------------------------------------------------------
    def validate_before_node_run(self) -> list[Exception] | None:
        return self._huggingface_repo_parameter.validate_before_node_run()

    def after_value_set(self, parameter: Parameter, value: Any, modified_parameters_set: set[str]) -> None:
        self._seed_parameter.after_value_set(parameter, value, modified_parameters_set)

    def preprocess(self) -> None:
        self._seed_parameter.preprocess()

    # --------------------------------------------------------------
    # Convenience getters
    # --------------------------------------------------------------
    def get_repo_revision(self) -> tuple[str, str]:
        return self._huggingface_repo_parameter.get_repo_revision()

    def get_image(self) -> Image:
        image_artifact = self._node.get_parameter_value("image")
        if isinstance(image_artifact, ImageUrlArtifact):
            return ImageLoader().load(image_artifact.value)
        return image_artifact_to_pil(image_artifact)

    def get_width(self) -> int:
        return int(self._node.get_parameter_value("width"))

    def get_height(self) -> int:
        return int(self._node.get_parameter_value("height"))

    def get_num_frames(self) -> int:
        return int(self._node.get_parameter_value("num_frames"))

    def get_num_inference_steps(self) -> int:
        return int(self._node.get_parameter_value("num_inference_steps"))

    def get_motion_bucket_id(self) -> int:
        return int(self._node.get_parameter_value("motion_bucket_id"))

    def get_fps(self) -> int:
        return int(self._node.get_parameter_value("fps"))

    def get_noise_aug_strength(self) -> float:
        return float(self._node.get_parameter_value("noise_aug_strength"))

    def get_generator(self):
        return self._seed_parameter.get_generator()

    def get_pipe_kwargs(self) -> dict:
        return {
            "image": self.get_image(),
            "width": self.get_width(),
            "height": self.get_height(),
            "num_frames": self.get_num_frames(),
            "num_inference_steps": self.get_num_inference_steps(),
            "motion_bucket_id": self.get_motion_bucket_id(),
            "fps": self.get_fps(),
            "noise_aug_strength": self.get_noise_aug_strength(),
            "generator": self.get_generator(),
        }

    # --------------------------------------------------------------
    # Result publishing helpers
    # --------------------------------------------------------------
    def publish_output_video(self, video_path: Path) -> None:
        filename = f"{uuid.uuid4()}{video_path.suffix}"
        url = GriptapeNodes.StaticFilesManager().save_static_file(video_path.read_bytes(), filename)
        self._node.parameter_output_values["output_video"] = VideoUrlArtifact(url)
