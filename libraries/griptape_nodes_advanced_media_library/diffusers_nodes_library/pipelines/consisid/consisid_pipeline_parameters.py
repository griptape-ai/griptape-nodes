import logging
from typing import Any, List

import diffusers  # type: ignore[reportMissingImports]
import PIL.Image
from PIL.Image import Image
from pillow_nodes_library.utils import pil_to_image_artifact  # type: ignore[reportMissingImports]
from artifact_utils.video_utils import frames_to_video_artifact  # type: ignore[reportMissingImports]

from diffusers_nodes_library.common.parameters.huggingface_repo_parameter import HuggingFaceRepoParameter
from diffusers_nodes_library.common.parameters.seed_parameter import SeedParameter
from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import BaseNode

logger = logging.getLogger("diffusers_nodes_library")


class ConsisidPipelineParameters:
    def __init__(self, node: BaseNode):
        self._node = node
        self._huggingface_repo_parameter = HuggingFaceRepoParameter(
            node,
            repo_ids=[
                "BestWishYsh/ConsisID-preview",
            ],
        )
        self._seed_parameter = SeedParameter(node)

    def add_input_parameters(self) -> None:
        self._huggingface_repo_parameter.add_input_parameters()
        self._node.add_parameter(
            Parameter(
                name="image",
                input_types=["griptape_nodes_library.exe_types.core_types.ImageArtifact"],
                type="griptape_nodes_library.exe_types.core_types.ImageArtifact",
                allowed_modes={ParameterMode.CONNECTION},
                tooltip="Reference image for identity preservation",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="prompt",
                input_types=["str"],
                type="str",
                allowed_modes={ParameterMode.MANUAL},
                tooltip="Text prompt to guide video generation",
                default_value="A person dancing in the rain",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="negative_prompt",
                input_types=["str"],
                type="str",
                allowed_modes={ParameterMode.MANUAL},
                tooltip="Negative text prompt to guide what not to generate",
                default_value="blurry, low quality, distorted face",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="num_frames",
                input_types=["int"],
                type="int",
                allowed_modes={ParameterMode.MANUAL},
                tooltip="Number of video frames to generate",
                default_value=49,
            )
        )
        self._node.add_parameter(
            Parameter(
                name="num_inference_steps",
                input_types=["int"],
                type="int",
                allowed_modes={ParameterMode.MANUAL},
                tooltip="Number of denoising steps",
                default_value=50,
            )
        )
        self._node.add_parameter(
            Parameter(
                name="guidance_scale",
                input_types=["float"],
                type="float",
                allowed_modes={ParameterMode.MANUAL},
                tooltip="Guidance scale for classifier-free guidance",
                default_value=6.0,
            )
        )
        self._seed_parameter.add_input_parameters()

    def add_output_parameters(self) -> None:
        self._node.add_parameter(
            Parameter(
                name="video",
                input_types=[],
                type="griptape_nodes_library.exe_types.core_types.VideoArtifact",
                allowed_modes=set(),
                tooltip="Generated video preserving identity from input image",
            )
        )

    def get_repo_revision(self) -> tuple[str, str]:
        return self._huggingface_repo_parameter.get_repo_revision()

    def get_num_inference_steps(self) -> int:
        return self._node.get_input_parameter_value("num_inference_steps")

    def get_pipe_kwargs(self) -> dict[str, Any]:
        image_artifact = self._node.get_input_parameter_value("image")
        image_pil = PIL.Image.open(image_artifact.value)
        
        return {
            "image": image_pil,
            "prompt": self._node.get_input_parameter_value("prompt"),
            "negative_prompt": self._node.get_input_parameter_value("negative_prompt") or None,
            "num_frames": self._node.get_input_parameter_value("num_frames"),
            "num_inference_steps": self._node.get_input_parameter_value("num_inference_steps"),
            "guidance_scale": self._node.get_input_parameter_value("guidance_scale"),
            "generator": self._seed_parameter.get_generator(),
        }

    def publish_output_video_preview_placeholder(self) -> None:
        num_frames = self._node.get_input_parameter_value("num_frames")
        placeholder_frames = [PIL.Image.new("RGB", (720, 480), (128, 128, 128)) for _ in range(num_frames)]
        video_artifact = frames_to_video_artifact(placeholder_frames, fps=8)
        self._node.set_output_parameter_value("video", video_artifact)

    def publish_output_video(self, frames: List[Image]) -> None:
        video_artifact = frames_to_video_artifact(frames, fps=8)
        self._node.set_output_parameter_value("video", video_artifact)

    def validate_before_node_run(self) -> list[Exception]:
        errors = []
        
        image_artifact = self._node.get_input_parameter_value("image")
        if image_artifact is None:
            errors.append(ValueError("Reference image is required"))
            
        num_frames = self._node.get_input_parameter_value("num_frames")
        if num_frames < 1:
            errors.append(ValueError("Number of frames must be at least 1"))
        if num_frames > 100:
            errors.append(ValueError("Number of frames should not exceed 100 for memory reasons"))
            
        return errors

    def preprocess(self) -> None:
        pass

    def after_value_set(self, parameter: Parameter, value: Any, modified_parameters_set: set[str]) -> None:
        pass