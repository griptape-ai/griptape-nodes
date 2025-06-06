import logging
from typing import Any

import diffusers  # type: ignore[reportMissingImports]
import PIL.Image
from PIL.Image import Image
from pillow_nodes_library.utils import pil_to_image_artifact  # type: ignore[reportMissingImports]

from diffusers_nodes_library.common.parameters.huggingface_repo_parameter import HuggingFaceRepoParameter
from diffusers_nodes_library.common.parameters.seed_parameter import SeedParameter
from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import BaseNode

logger = logging.getLogger("diffusers_nodes_library")


class PiaPipelineParameters:
    def __init__(self, node: BaseNode):
        self._node = node
        self._huggingface_repo_parameter = HuggingFaceRepoParameter(
            node,
            repo_ids=[
                "SG161222/Realistic_Vision_V6.0_B1_noVAE",
                "runwayml/stable-diffusion-v1-5",
            ],
        )
        self._seed_parameter = SeedParameter(node)

    def add_input_parameters(self) -> None:
        self._huggingface_repo_parameter.add_input_parameters()
        
        self._node.add_parameter(
            Parameter(
                name="image",
                input_types=["ImageArtifact"],
                type="ImageArtifact",
                allowed_modes={ParameterMode.INPUT},
                tooltip="Input image to animate",
            )
        )
        
        self._node.add_parameter(
            Parameter(
                name="prompt",
                input_types=["str"],
                type="str",
                allowed_modes={ParameterMode.INPUT},
                tooltip="Text prompt describing the desired animation",
            )
        )
        
        self._node.add_parameter(
            Parameter(
                name="negative_prompt",
                input_types=["str"],
                type="str",
                allowed_modes=set(),
                tooltip="Negative prompt to guide what to avoid",
                default_value="",
            )
        )
        
        self._node.add_parameter(
            Parameter(
                name="num_frames",
                input_types=["int"],
                type="int",
                allowed_modes=set(),
                tooltip="Number of frames to generate",
                default_value=16,
            )
        )
        
        self._node.add_parameter(
            Parameter(
                name="num_inference_steps",
                input_types=["int"],
                type="int",
                allowed_modes=set(),
                tooltip="Number of denoising steps",
                default_value=20,
            )
        )
        
        self._node.add_parameter(
            Parameter(
                name="guidance_scale",
                input_types=["float"],
                type="float",
                allowed_modes=set(),
                tooltip="Guidance scale for classifier-free guidance",
                default_value=7.0,
            )
        )
        
        self._node.add_parameter(
            Parameter(
                name="motion_scale",
                input_types=["int"],
                type="int",
                allowed_modes=set(),
                tooltip="Motion scale (0-8): 0-2 increase motion, 3-5 looping motion, 6-8 motion with style transfer",
                default_value=0,
            )
        )
        
        self._node.add_parameter(
            Parameter(
                name="motion_adapter_repo_id",
                input_types=["str"],
                type="str",
                allowed_modes=set(),
                tooltip="Motion adapter model repository ID",
                default_value="openmmlab/PIA-condition-adapter",
            )
        )
        
        self._seed_parameter.add_input_parameters()

    def add_output_parameters(self) -> None:
        self._node.add_parameter(
            Parameter(
                name="output_video",
                type="VideoUrlArtifact",
                allowed_modes={ParameterMode.OUTPUT},
                tooltip="Generated animated video",
            )
        )

    def validate_before_node_run(self) -> list[Exception] | None:
        errors = []
        
        if not self._node.get_parameter_value("image"):
            errors.append(ValueError("Input image is required"))
        if not self._node.get_parameter_value("prompt"):
            errors.append(ValueError("Prompt is required"))
            
        motion_scale = self._node.get_parameter_value("motion_scale")
        if motion_scale < 0 or motion_scale > 8:
            errors.append(ValueError("Motion scale must be between 0 and 8"))
            
        return errors if errors else None

    def preprocess(self) -> None:
        self._seed_parameter.preprocess()

    def get_repo_revision(self) -> tuple[str, str]:
        return self._huggingface_repo_parameter.get_repo_revision()

    def get_motion_adapter_repo_id(self) -> str:
        return self._node.get_parameter_value("motion_adapter_repo_id")

    def get_num_inference_steps(self) -> int:
        return self._node.get_parameter_value("num_inference_steps")

    def get_pipe_kwargs(self) -> dict[str, Any]:
        return {
            "image": self._get_input_image(),
            "prompt": self._node.get_parameter_value("prompt"),
            "negative_prompt": self._node.get_parameter_value("negative_prompt"),
            "num_frames": self._node.get_parameter_value("num_frames"),
            "num_inference_steps": self._node.get_parameter_value("num_inference_steps"),
            "guidance_scale": self._node.get_parameter_value("guidance_scale"),
            "motion_scale": self._node.get_parameter_value("motion_scale"),
            "generator": self._seed_parameter.get_generator(),
        }

    def _get_input_image(self) -> Image:
        image_artifact = self._node.get_parameter_value("image")
        return image_artifact.value

    def publish_output_video_preview_placeholder(self) -> None:
        self._node.publish_parameter_value("output_video", None)

    def publish_output_video_preview_latents(self, pipe: diffusers.PIAPipeline, latents: Any) -> None:
        """Publish preview of current latents during generation"""
        pass

    def publish_output_video(self, output_video_path: str) -> None:
        from artifact_utils.video_url_artifact import VideoUrlArtifact  # type: ignore[reportMissingImports]
        
        output_video_artifact = VideoUrlArtifact(value=output_video_path)
        self._node.publish_parameter_value("output_video", output_video_artifact)