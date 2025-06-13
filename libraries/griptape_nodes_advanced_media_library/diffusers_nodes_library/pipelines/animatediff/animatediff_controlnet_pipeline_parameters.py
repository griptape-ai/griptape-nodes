import logging
import uuid
from pathlib import Path
from typing import Any

from artifact_utils.video_url_artifact import VideoUrlArtifact  # type: ignore[reportMissingImports]
from griptape.artifacts import ImageUrlArtifact
from griptape.loaders import ImageLoader
from PIL.Image import Image
from pillow_nodes_library.utils import (  # type: ignore[reportMissingImports]
    image_artifact_to_pil,
)

from diffusers_nodes_library.common.parameters.huggingface_repo_parameter import HuggingFaceRepoParameter
from diffusers_nodes_library.common.parameters.seed_parameter import SeedParameter
from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import BaseNode
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes  # type: ignore[reportMissingImports]

logger = logging.getLogger("diffusers_nodes_library")


class AnimateDiffControlNetPipelineParameters:
    """All parameter handling for AnimateDiffControlNet pipelines (text-to-video with ControlNet)."""

    def __init__(self, node: BaseNode):
        self._node = node
        self._huggingface_repo_parameter = HuggingFaceRepoParameter(
            node,
            repo_ids=[
                "SG161222/Realistic_Vision_V5.1_noVAE",
                "emilianJR/epiCRealism",
            ],
        )
        self._controlnet_repo_parameter = HuggingFaceRepoParameter(
            node,
            parameter_name="controlnet_repo",
            repo_ids=[
                "lllyasviel/sd-controlnet-canny",
                "lllyasviel/sd-controlnet-depth",
                "lllyasviel/sd-controlnet-hed",
                "lllyasviel/sd-controlnet-mlsd",
                "lllyasviel/sd-controlnet-normal",
                "lllyasviel/sd-controlnet-openpose",
                "lllyasviel/sd-controlnet-scribble",
                "lllyasviel/sd-controlnet-seg",
            ],
        )
        self._motion_adapter_repo_parameter = HuggingFaceRepoParameter(
            node,
            parameter_name="motion_adapter_repo",
            repo_ids=[
                "guoyww/animatediff-motion-adapter-v1-5-2",
                "guoyww/animatediff-motion-adapter-v1-5-3",
            ],
        )
        self._seed_parameter = SeedParameter(node)

    # --------------------------------------------------------------
    # Parameter registration helpers
    # --------------------------------------------------------------
    def add_input_parameters(self) -> None:
        self._huggingface_repo_parameter.add_input_parameters()
        self._controlnet_repo_parameter.add_input_parameters()
        self._motion_adapter_repo_parameter.add_input_parameters()

        self._node.add_parameter(
            Parameter(
                name="control_image",
                input_types=["ImageArtifact", "ImageUrlArtifact"],
                type="ImageArtifact",
                tooltip="Control image for ControlNet guidance",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="prompt",
                default_value="",
                input_types=["str"],
                type="str",
                tooltip="Text prompt",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="negative_prompt",
                default_value="",
                input_types=["str"],
                type="str",
                tooltip="Negative prompt (optional)",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="guidance_scale",
                default_value=7.5,
                input_types=["float"],
                type="float",
                tooltip="CFG guidance scale",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="controlnet_conditioning_scale",
                default_value=1.0,
                input_types=["float"],
                type="float",
                tooltip="ControlNet conditioning scale",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="width",
                default_value=512,
                input_types=["int"],
                type="int",
                tooltip="Frame width in pixels",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="height",
                default_value=512,
                input_types=["int"],
                type="int",
                tooltip="Frame height in pixels",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="num_frames",
                default_value=16,
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
        errors = []

        base_errors = self._huggingface_repo_parameter.validate_before_node_run()
        if base_errors:
            errors.extend(base_errors)

        controlnet_errors = self._controlnet_repo_parameter.validate_before_node_run()
        if controlnet_errors:
            errors.extend(controlnet_errors)

        motion_adapter_errors = self._motion_adapter_repo_parameter.validate_before_node_run()
        if motion_adapter_errors:
            errors.extend(motion_adapter_errors)

        return errors or None

    def after_value_set(self, parameter: Parameter, value: Any, modified_parameters_set: set[str]) -> None:
        self._seed_parameter.after_value_set(parameter, value, modified_parameters_set)

    def preprocess(self) -> None:
        self._seed_parameter.preprocess()

    # --------------------------------------------------------------
    # Convenience getters
    # --------------------------------------------------------------
    def get_repo_revision(self) -> tuple[str, str]:
        return self._huggingface_repo_parameter.get_repo_revision()

    def get_controlnet_repo_revision(self) -> tuple[str, str]:
        return self._controlnet_repo_parameter.get_repo_revision()

    def get_motion_adapter_repo_revision(self) -> tuple[str, str]:
        return self._motion_adapter_repo_parameter.get_repo_revision()

    def get_control_image_pil(self) -> Image:
        control_image_artifact = self._node.get_parameter_value("control_image")
        if isinstance(control_image_artifact, ImageUrlArtifact):
            control_image_artifact = ImageLoader().parse(control_image_artifact.to_bytes())
        control_image_pil = image_artifact_to_pil(control_image_artifact)
        return control_image_pil.convert("RGB")

    def get_prompt(self) -> str:
        return self._node.get_parameter_value("prompt")

    def get_negative_prompt(self) -> str:
        return self._node.get_parameter_value("negative_prompt")

    def get_guidance_scale(self) -> float:
        return float(self._node.get_parameter_value("guidance_scale"))

    def get_controlnet_conditioning_scale(self) -> float:
        return float(self._node.get_parameter_value("controlnet_conditioning_scale"))

    def get_width(self) -> int:
        return int(self._node.get_parameter_value("width"))

    def get_height(self) -> int:
        return int(self._node.get_parameter_value("height"))

    def get_num_frames(self) -> int:
        return int(self._node.get_parameter_value("num_frames"))

    def get_num_inference_steps(self) -> int:
        return int(self._node.get_parameter_value("num_inference_steps"))

    def get_generator(self) -> Any:
        return self._seed_parameter.get_generator()

    def get_pipe_kwargs(self) -> dict:
        return {
            "prompt": self.get_prompt(),
            "negative_prompt": self.get_negative_prompt(),
            "image": self.get_control_image_pil(),
            "guidance_scale": self.get_guidance_scale(),
            "controlnet_conditioning_scale": self.get_controlnet_conditioning_scale(),
            "width": self.get_width(),
            "height": self.get_height(),
            "num_frames": self.get_num_frames(),
            "num_inference_steps": self.get_num_inference_steps(),
            "generator": self.get_generator(),
        }

    def publish_output_video(self, video_path: Path) -> None:
        filename = f"{uuid.uuid4()}{video_path.suffix}"
        url = GriptapeNodes.StaticFilesManager().save_static_file(video_path.read_bytes(), filename)
        self._node.parameter_output_values["output_video"] = VideoUrlArtifact(url)
