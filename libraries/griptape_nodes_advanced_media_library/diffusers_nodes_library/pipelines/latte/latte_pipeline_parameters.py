import logging
from typing import Any

import numpy as np
from artifact_utils.video_utils import numpy_video_to_video_artifact  # type: ignore[reportMissingImports]

import diffusers  # type: ignore[reportMissingImports]

from diffusers_nodes_library.common.parameters.huggingface_repo_parameter import (
    HuggingFaceRepoParameter,
)
from diffusers_nodes_library.common.parameters.seed_parameter import SeedParameter
from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import BaseNode

logger = logging.getLogger("diffusers_nodes_library")


class LattePipelineParameters:
    """Wrapper around the collection of parameters needed for Latte pipelines."""

    def __init__(self, node: BaseNode):
        self._node = node
        self._huggingface_repo_parameter = HuggingFaceRepoParameter(
            node,
            repo_ids=[
                "maxin-cn/Latte-1",
            ],
        )
        self._seed_parameter = SeedParameter(node)

    # ---------------------------------------------------------------------
    # Parameter registration helpers
    # ---------------------------------------------------------------------
    def add_input_parameters(self) -> None:
        self._huggingface_repo_parameter.add_input_parameters()

        self._node.add_parameter(
            Parameter(
                name="prompt",
                default_value="",
                input_types=["str"],
                type="str",
                tooltip="Text prompt for video generation",
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
                tooltip="CFG / guidance scale",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="width",
                default_value=512,
                input_types=["int"],
                type="int",
                tooltip="Width in pixels",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="height",
                default_value=512,
                input_types=["int"],
                type="int",
                tooltip="Height in pixels",
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
                name="num_inference_steps",
                default_value=50,
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
                output_type="VideoArtifact",
                tooltip="Generated video",
                allowed_modes={ParameterMode.OUTPUT},
            )
        )

    # ------------------------------------------------------------------
    # Validation / life-cycle hooks
    # ------------------------------------------------------------------
    def validate_before_node_run(self) -> list[Exception] | None:
        errors = self._huggingface_repo_parameter.validate_before_node_run()
        return errors or None

    def after_value_set(
        self, parameter: Parameter, value: Any, modified_parameters_set: set[str]
    ) -> None:
        self._seed_parameter.after_value_set(parameter, value, modified_parameters_set)

    def preprocess(self) -> None:
        self._seed_parameter.preprocess()

    # ------------------------------------------------------------------
    # Convenience getters
    # ------------------------------------------------------------------
    def get_repo_revision(self) -> tuple[str, str]:
        return self._huggingface_repo_parameter.get_repo_revision()

    def get_prompt(self) -> str:
        return self._node.get_parameter_value("prompt")

    def get_negative_prompt(self) -> str:
        return self._node.get_parameter_value("negative_prompt")

    def get_guidance_scale(self) -> float:
        return float(self._node.get_parameter_value("guidance_scale"))

    def get_width(self) -> int:
        return int(self._node.get_parameter_value("width"))

    def get_height(self) -> int:
        return int(self._node.get_parameter_value("height"))

    def get_num_frames(self) -> int:
        return int(self._node.get_parameter_value("num_frames"))

    def get_num_inference_steps(self) -> int:
        return int(self._node.get_parameter_value("num_inference_steps"))

    def get_generator(self):
        return self._seed_parameter.get_generator()

    def get_pipe_kwargs(self) -> dict:
        return {
            "prompt": self.get_prompt(),
            "negative_prompt": self.get_negative_prompt(),
            "guidance_scale": self.get_guidance_scale(),
            "width": self.get_width(),
            "height": self.get_height(),
            "num_frames": self.get_num_frames(),
            "num_inference_steps": self.get_num_inference_steps(),
            "generator": self.get_generator(),
        }

    # ------------------------------------------------------------------
    # Preview helpers
    # ------------------------------------------------------------------
    def publish_output_video_preview_placeholder(self) -> None:
        width = self.get_width()
        height = self.get_height()
        num_frames = self.get_num_frames()
        # Create a black video placeholder
        preview_placeholder_video = np.zeros((num_frames, height, width, 3), dtype=np.uint8)
        self._node.publish_update_to_parameter(
            "output_video", numpy_video_to_video_artifact(preview_placeholder_video)
        )

    def publish_output_video(self, output_video: np.ndarray) -> None:
        video_artifact = numpy_video_to_video_artifact(output_video)
        self._node.set_parameter_value("output_video", video_artifact)
        self._node.parameter_output_values["output_video"] = video_artifact