import logging
from pathlib import Path
from typing import Any
import uuid

from griptape_nodes_library.video.video_url_artifact import VideoUrlArtifact  # type: ignore[reportMissingImports]

from diffusers_nodes_library.common.parameters.huggingface_repo_parameter import HuggingFaceRepoParameter  # type: ignore[reportMissingImports]
from diffusers_nodes_library.common.parameters.seed_parameter import SeedParameter  # type: ignore[reportMissingImports]
from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import BaseNode
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes  # type: ignore[reportMissingImports]

logger = logging.getLogger("diffusers_nodes_library")


class AllegroPipelineParameters:
    """Handles all Allegro pipeline related parameters for the AllegroPipeline node."""

    def __init__(self, node: BaseNode):
        self._node = node
        # By default we expose the canonical Allegro model on the Hub. Additional fine-tunes can be added later.
        self._huggingface_repo_parameter = HuggingFaceRepoParameter(
            node,
            repo_ids=[
                "rhymes-ai/Allegro",
            ],
        )
        self._seed_parameter = SeedParameter(node)

    # -------------------------------------------------------------------------
    # Parameter registration helpers
    # -------------------------------------------------------------------------

    def add_input_parameters(self) -> None:
        """Register all input parameters on the parent node."""
        self._huggingface_repo_parameter.add_input_parameters()

        self._node.add_parameter(
            Parameter(
                name="prompt",
                default_value="",
                input_types=["str"],
                type="str",
                tooltip="Prompt",
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
                name="width",
                default_value=576,
                input_types=["int"],
                type="int",
                tooltip="Video frame width",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="height",
                default_value=1024,
                input_types=["int"],
                type="int",
                tooltip="Video frame height",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="num_frames",
                default_value=40,
                input_types=["int"],
                type="int",
                tooltip="Number of frames to generate",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="num_inference_steps",
                default_value=100,
                input_types=["int"],
                type="int",
                tooltip="Number of denoising steps",
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

        # Seed helpers are standard across pipelines.
        self._seed_parameter.add_input_parameters()

    def add_output_parameters(self) -> None:
        """Register output parameters (currently only the final video URL)."""
        self._node.add_parameter(
            Parameter(
                name="output_video",
                output_type="VideoUrlArtifact",
                tooltip="The generated video clip",
                allowed_modes={ParameterMode.OUTPUT},
            )
        )

    # -------------------------------------------------------------------------
    # Validation & lifecycle hooks
    # -------------------------------------------------------------------------

    def validate_before_node_run(self) -> list[Exception] | None:
        errors = self._huggingface_repo_parameter.validate_before_node_run()
        return errors or None

    def after_value_set(self, parameter: Parameter, value: Any, modified_parameters_set: set[str]) -> None:
        self._seed_parameter.after_value_set(parameter, value, modified_parameters_set)

    def preprocess(self) -> None:
        self._seed_parameter.preprocess()

    # -------------------------------------------------------------------------
    # Convenience getters
    # -------------------------------------------------------------------------

    def get_repo_revision(self) -> tuple[str, str]:
        return self._huggingface_repo_parameter.get_repo_revision()

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
        """Return a dictionary of keyword arguments to pass to the Allegro pipeline."""
        return {
            "prompt": self.get_prompt(),
            "negative_prompt": self.get_negative_prompt(),
            "num_frames": self.get_num_frames(),
            "height": self.get_height(),
            "width": self.get_width(),
            "num_inference_steps": self.get_num_inference_steps(),
            "guidance_scale": self.get_guidance_scale(),
            "generator": self._seed_parameter.get_generator(),
            # Always ask the pipeline to return PIL images so that export_to_video works as expected.
            "output_type": "pil",
        }

    # -------------------------------------------------------------------------
    # Helpers for publishing results to the frontend
    # -------------------------------------------------------------------------

    def publish_output_video(self, video_file: Path) -> None:
        """Persist the video to the static files store and publish the resulting URL as output."""
        filename = f"{uuid.uuid4()}{video_file.suffix}"
        url = (
            GriptapeNodes.StaticFilesManager().save_static_file(video_file.read_bytes(), filename)
        )  # type: ignore[attr-defined]
        self._node.parameter_output_values["output_video"] = VideoUrlArtifact(url)