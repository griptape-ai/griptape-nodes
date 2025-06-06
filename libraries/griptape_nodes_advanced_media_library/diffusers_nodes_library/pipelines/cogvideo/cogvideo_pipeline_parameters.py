import logging
import tempfile
import uuid
from pathlib import Path
from typing import Any

import diffusers  # type: ignore[reportMissingImports]

from diffusers_nodes_library.common.parameters.huggingface_repo_parameter import HuggingFaceRepoParameter  # type: ignore[reportMissingImports]
from diffusers_nodes_library.common.parameters.seed_parameter import SeedParameter  # type: ignore[reportMissingImports]
from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import BaseNode
from artifact_utils.video_url_artifact import VideoUrlArtifact  # type: ignore[reportMissingImports]
from src.griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes  # type: ignore[reportMissingImports]

logger = logging.getLogger("diffusers_nodes_library")


class CogvideoPipelineParameters:
    def __init__(self, node: BaseNode):
        self._node = node
        self._huggingface_repo_parameter = HuggingFaceRepoParameter(
            node,
            repo_ids=[
                "THUDM/CogVideoX-2b",
                "THUDM/CogVideoX-5b",
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
                tooltip="Optional negative prompt to guide what not to generate",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="num_frames",
                default_value=49,
                input_types=["int"],
                type="int",
                tooltip="Number of frames to generate (must be divisible by 4 + 1)",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="height",
                default_value=480,
                input_types=["int"],
                type="int",
                tooltip="Height of the generated video in pixels",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="width",
                default_value=720,
                input_types=["int"],
                type="int",
                tooltip="Width of the generated video in pixels",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="num_inference_steps",
                default_value=50,
                input_types=["int"],
                type="int",
                tooltip="Number of denoising steps for generation",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="guidance_scale",
                default_value=6.0,
                input_types=["float"],
                type="float",
                tooltip="Higher values follow the text prompt more closely",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="fps",
                default_value=8,
                input_types=["int"],
                type="int",
                tooltip="Frames per second for the output video",
            )
        )
        self._seed_parameter.add_input_parameters()

    def add_output_parameters(self) -> None:
        self._node.add_parameter(
            Parameter(
                name="output_video",
                output_type="VideoUrlArtifact",
                tooltip="The generated video",
                allowed_modes={ParameterMode.OUTPUT},
            )
        )

    def validate_before_node_run(self) -> list[Exception] | None:
        errors = self._huggingface_repo_parameter.validate_before_node_run()
        
        # Validate that num_frames follows CogVideo requirements
        num_frames = self.get_num_frames()
        if (num_frames - 1) % 4 != 0:
            if errors is None:
                errors = []
            errors.append(ValueError(f"num_frames must be divisible by 4 + 1, got {num_frames}"))
        
        return errors or None

    def after_value_set(self, parameter: Parameter, value: Any, modified_parameters_set: set[str]) -> None:
        self._seed_parameter.after_value_set(parameter, value, modified_parameters_set)

    def preprocess(self) -> None:
        self._seed_parameter.preprocess()

    def get_repo_revision(self) -> tuple[str, str]:
        return self._huggingface_repo_parameter.get_repo_revision()

    def get_prompt(self) -> str:
        return self._node.get_parameter_value("prompt")

    def get_negative_prompt(self) -> str:
        return self._node.get_parameter_value("negative_prompt")

    def get_num_frames(self) -> int:
        return int(self._node.get_parameter_value("num_frames"))

    def get_height(self) -> int:
        return int(self._node.get_parameter_value("height"))

    def get_width(self) -> int:
        return int(self._node.get_parameter_value("width"))

    def get_num_inference_steps(self) -> int:
        return int(self._node.get_parameter_value("num_inference_steps"))

    def get_guidance_scale(self) -> float:
        return float(self._node.get_parameter_value("guidance_scale"))

    def get_fps(self) -> int:
        return int(self._node.get_parameter_value("fps"))

    def get_pipe_kwargs(self) -> dict:
        kwargs = {
            "prompt": self.get_prompt(),
            "num_frames": self.get_num_frames(),
            "height": self.get_height(),
            "width": self.get_width(),
            "num_inference_steps": self.get_num_inference_steps(),
            "guidance_scale": self.get_guidance_scale(),
            "generator": self._seed_parameter.get_generator(),
        }
        
        negative_prompt = self.get_negative_prompt()
        if negative_prompt:
            kwargs["negative_prompt"] = negative_prompt
            
        return kwargs

    def publish_output_video(self, video_frames: Any) -> None:
        temp_file = Path(tempfile.NamedTemporaryFile(suffix=".mp4", delete=False).name)
        try:
            fps = self.get_fps()
            diffusers.utils.export_to_video(video_frames, str(temp_file), fps=fps)
            
            filename = f"{uuid.uuid4()}.mp4"
            url = GriptapeNodes.StaticFilesManager().save_static_file(temp_file.read_bytes(), filename)
            self._node.parameter_output_values["output_video"] = VideoUrlArtifact(url)
        finally:
            if temp_file.exists():
                temp_file.unlink()