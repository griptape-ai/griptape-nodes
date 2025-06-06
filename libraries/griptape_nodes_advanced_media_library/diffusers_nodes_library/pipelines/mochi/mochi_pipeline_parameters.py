import logging
from typing import Any

import diffusers  # type: ignore[reportMissingImports]
from video_nodes_library.utils import frames_to_video_artifact  # type: ignore[reportMissingImports]

from diffusers_nodes_library.common.parameters.huggingface_repo_parameter import HuggingFaceRepoParameter
from diffusers_nodes_library.common.parameters.seed_parameter import SeedParameter
from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import BaseNode

logger = logging.getLogger("diffusers_nodes_library")


class MochiPipelineParameters:
    def __init__(self, node: BaseNode):
        self._node = node
        self._huggingface_repo_parameter = HuggingFaceRepoParameter(
            node,
            repo_ids=[
                "genmo/mochi-1-preview",
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
                tooltip="prompt",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="negative_prompt",
                default_value="",
                input_types=["str"],
                type="str",
                tooltip="optional negative_prompt",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="width",
                default_value=848,
                input_types=["int"],
                type="int",
                tooltip="width",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="height",
                default_value=480,
                input_types=["int"],
                type="int",
                tooltip="height",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="num_frames",
                default_value=19,
                input_types=["int"],
                type="int",
                tooltip="num_frames",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="num_inference_steps",
                default_value=64,
                input_types=["int"],
                type="int",
                tooltip="num_inference_steps",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="guidance_scale",
                default_value=4.5,
                input_types=["float"],
                type="float",
                tooltip="guidance_scale",
            )
        )
        self._seed_parameter.add_input_parameters()

    def add_output_parameters(self) -> None:
        self._node.add_parameter(
            Parameter(
                name="output_video",
                output_type="VideoArtifact",
                tooltip="The output video",
                allowed_modes={ParameterMode.OUTPUT},
            )
        )

    def validate_before_node_run(self) -> list[Exception] | None:
        errors = self._huggingface_repo_parameter.validate_before_node_run()
        return errors or None

    def after_value_set(self, parameter: Parameter, value: Any, modified_parameters_set: set[str]) -> None:
        self._seed_parameter.after_value_set(parameter, value, modified_parameters_set)

    def preprocess(self) -> None:
        self._seed_parameter.preprocess()

    def get_repo_revision(self) -> tuple[str, str]:
        return self._huggingface_repo_parameter.get_repo_revision()

    def publish_output_video_preview_placeholder(self) -> None:
        width = int(self._node.parameter_values["width"])
        height = int(self._node.parameter_values["height"])
        num_frames = int(self._node.parameter_values["num_frames"])
        # Create a placeholder video with black frames
        import numpy as np
        placeholder_frames = [np.zeros((height, width, 3), dtype=np.uint8) for _ in range(num_frames)]
        placeholder_video_artifact = frames_to_video_artifact(placeholder_frames, fps=8)
        self._node.publish_update_to_parameter("output_video", placeholder_video_artifact)

    def get_prompt(self) -> str:
        return self._node.get_parameter_value("prompt")

    def get_negative_prompt(self) -> str:
        return self._node.get_parameter_value("negative_prompt")

    def get_width(self) -> int:
        return int(self._node.get_parameter_value("width"))

    def get_height(self) -> int:
        return int(self._node.get_parameter_value("height"))

    def get_num_frames(self) -> int:
        return int(self._node.get_parameter_value("num_frames"))

    def get_num_inference_steps(self) -> int:
        return int(self._node.get_parameter_value("num_inference_steps"))

    def get_guidance_scale(self) -> float:
        return float(self._node.get_parameter_value("guidance_scale"))

    def get_pipe_kwargs(self) -> dict:
        return {
            "prompt": self.get_prompt(),
            "negative_prompt": self.get_negative_prompt(),
            "width": self.get_width(),
            "height": self.get_height(),
            "num_frames": self.get_num_frames(),
            "num_inference_steps": self.get_num_inference_steps(),
            "guidance_scale": self.get_guidance_scale(),
            "generator": self._seed_parameter.get_generator(),
        }

    def publish_output_video(self, output_frames: list) -> None:
        video_artifact = frames_to_video_artifact(output_frames, fps=8)
        self._node.set_parameter_value("output_video", video_artifact)
        self._node.parameter_output_values["output_video"] = video_artifact