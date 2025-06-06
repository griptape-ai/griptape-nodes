import logging
from pathlib import Path
from typing import Any
import uuid
import tempfile

from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

import diffusers  # type: ignore[reportMissingImports]
import PIL.Image
from PIL.Image import Image

from griptape_nodes_library.video.video_url_artifact import VideoUrlArtifact  # type: ignore[reportMissingImports]
from pillow_nodes_library.utils import pil_to_image_artifact  # type: ignore[reportMissingImports]

from diffusers_nodes_library.common.parameters.huggingface_repo_parameter import HuggingFaceRepoParameter
from diffusers_nodes_library.common.parameters.seed_parameter import SeedParameter
from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import BaseNode

logger = logging.getLogger("diffusers_nodes_library")


class TextToVideoSynthesisPipelineParameters:
    def __init__(self, node: BaseNode):
        self._node = node
        self._huggingface_repo_parameter = HuggingFaceRepoParameter(
            node,
            repo_ids=[
                "damo-vilab/text-to-video-ms-1.7b",
            ],
        )
        self._seed_parameter = SeedParameter(node)

    def add_input_parameters(self) -> None:
        self._huggingface_repo_parameter.add_input_parameters()
        self._node.add_parameter(
            Parameter(
                name="prompt",
                default_value="",
                input_types=["str"],
                type="str",
                tooltip="Text prompt describing the video to generate",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="negative_prompt",
                default_value="",
                input_types=["str"],
                type="str",
                tooltip="Optional negative prompt",
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
                name="guidance_scale",
                default_value=9.0,
                input_types=["float"],
                type="float",
                tooltip="Guidance scale for classifier-free guidance",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="num_frames",
                default_value=16,
                input_types=["int"],
                type="int",
                tooltip="Number of video frames to generate",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="height",
                default_value=320,
                input_types=["int"],
                type="int",
                tooltip="Height of generated video",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="width",
                default_value=576,
                input_types=["int"],
                type="int",
                tooltip="Width of generated video",
            )
        )
        self._seed_parameter.add_input_parameters()

    def add_output_parameters(self) -> None:
        self._node.add_parameter(
            Parameter(
                name="video",
                input_types=[],
                type="VideoUrlArtifact",
                allowed_modes={ParameterMode.OUTPUT},
                tooltip="Generated video",
            )
        )

    def after_value_set(self, parameter: Parameter, value: Any, modified_parameters_set: set[str]) -> None:
        self._huggingface_repo_parameter.after_value_set(parameter, value, modified_parameters_set)
        self._seed_parameter.after_value_set(parameter, value, modified_parameters_set)

    def validate_before_node_run(self) -> list[Exception] | None:
        errors = []
        
        repo_errors = self._huggingface_repo_parameter.validate_before_node_run()
        if repo_errors:
            errors.extend(repo_errors)
            
        seed_errors = self._seed_parameter.validate_before_node_run()
        if seed_errors:
            errors.extend(seed_errors)
            
        return errors if errors else None

    def preprocess(self) -> None:
        self._huggingface_repo_parameter.preprocess()
        self._seed_parameter.preprocess()

    def get_repo_revision(self) -> tuple[str, str]:
        return self._huggingface_repo_parameter.get_repo_revision()

    def get_num_inference_steps(self) -> int:
        return self._node.get_parameter_value("num_inference_steps")

    def get_pipe_kwargs(self) -> dict[str, Any]:
        return {
            "prompt": self._node.get_parameter_value("prompt"),
            "negative_prompt": self._node.get_parameter_value("negative_prompt") or None,
            "num_inference_steps": self._node.get_parameter_value("num_inference_steps"),
            "guidance_scale": self._node.get_parameter_value("guidance_scale"),
            "height": self._node.get_parameter_value("height"),
            "width": self._node.get_parameter_value("width"),
            "num_frames": self._node.get_parameter_value("num_frames"),
            "generator": self._seed_parameter.get_generator(),
        }

    def publish_output_video(self, frames: list[PIL.Image.Image]) -> None:
        """Convert PIL frames to video and publish as output parameter."""
        # Create temporary video file
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as temp_file:
            temp_path = Path(temp_file.name)
        
        # Convert frames to video using imageio
        import imageio
        with imageio.get_writer(str(temp_path), fps=8) as writer:
            for frame in frames:
                writer.append_data(frame)
        
        # Create video artifact
        video_artifact = VideoUrlArtifact(
            value=str(temp_path),
            url=str(temp_path),
            name=f"text_to_video_{uuid.uuid4().hex[:8]}.mp4"
        )
        
        self._node.set_parameter_value("video", video_artifact)