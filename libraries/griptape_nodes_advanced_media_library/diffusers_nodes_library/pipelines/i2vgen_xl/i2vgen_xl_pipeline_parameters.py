import logging
from pathlib import Path
from typing import Any
import uuid

from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

import diffusers  # type: ignore[reportMissingImports]
import PIL.Image
from PIL.Image import Image
from griptape.artifacts import ImageUrlArtifact
from griptape.loaders import ImageLoader
from PIL.Image import Image
from pillow_nodes_library.utils import (  # type: ignore[reportMissingImports]
    image_artifact_to_pil,
    pil_to_image_artifact,
)

from artifact_utils.video_url_artifact import VideoUrlArtifact  # type: ignore[reportMissingImports]

from diffusers_nodes_library.common.parameters.huggingface_repo_parameter import HuggingFaceRepoParameter
from diffusers_nodes_library.common.parameters.seed_parameter import SeedParameter
from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import BaseNode

logger = logging.getLogger("diffusers_nodes_library")


class I2VGenXLPipelineParameters:
    """Wrapper around the collection of parameters needed for I2VGen-XL pipelines."""

    def __init__(self, node: BaseNode):
        self._node = node
        self._huggingface_repo_parameter = HuggingFaceRepoParameter(
            node,
            repo_ids=[
                "ali-vilab/i2vgen-xl",
            ],
        )
        self._seed_parameter = SeedParameter(node)

    def add_input_parameters(self) -> None:
        self._huggingface_repo_parameter.add_input_parameters()
        
        self._node.add_parameter(
            Parameter(
                name="input_image",
                input_types=["ImageArtifact", "ImageUrlArtifact"],
                type="ImageArtifact",
                tooltip="Input image to animate",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="prompt",
                default_value="",
                input_types=["str"],
                type="str",
                tooltip="Text prompt describing the motion",
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
                default_value=9.0,
                input_types=["float"],
                type="float",
                tooltip="CFG / guidance scale",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="target_fps",
                default_value=16,
                input_types=["int"],
                type="int",
                tooltip="Target FPS for the output video",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="num_frames",
                default_value=16,
                input_types=["int"],
                type="int",
                tooltip="Number of frames to generate",
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
                output_type="VideoUrlArtifact",
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

    def get_input_image(self) -> Image:
        input_image_artifact = self._node.get_parameter_value("input_image")
        if isinstance(input_image_artifact, ImageUrlArtifact):
            # Load from URL if it's an ImageUrlArtifact
            loader = ImageLoader()
            return loader.load(input_image_artifact.value).value
        else:
            # Convert from ImageArtifact to PIL
            return image_artifact_to_pil(input_image_artifact)

    def get_prompt(self) -> str:
        return self._node.get_parameter_value("prompt")

    def get_negative_prompt(self) -> str:
        return self._node.get_parameter_value("negative_prompt")

    def get_guidance_scale(self) -> float:
        return float(self._node.get_parameter_value("guidance_scale"))

    def get_target_fps(self) -> int:
        return int(self._node.get_parameter_value("target_fps"))

    def get_num_frames(self) -> int:
        return int(self._node.get_parameter_value("num_frames"))

    def get_num_inference_steps(self) -> int:
        return int(self._node.get_parameter_value("num_inference_steps"))

    def get_generator(self):
        return self._seed_parameter.get_generator()

    def get_pipe_kwargs(self) -> dict:
        return {
            "image": self.get_input_image(),
            "prompt": self.get_prompt(),
            "negative_prompt": self.get_negative_prompt(),
            "guidance_scale": self.get_guidance_scale(),
            "target_fps": self.get_target_fps(),
            "num_frames": self.get_num_frames(),
            "num_inference_steps": self.get_num_inference_steps(),
            "generator": self.get_generator(),
        }

    # ------------------------------------------------------------------
    # Video output helpers
    # ------------------------------------------------------------------
    def publish_output_video(self, video_frames) -> None:
        """Save video frames and publish as VideoUrlArtifact."""
        # Create a temporary file for the video
        temp_video_path = Path(tempfile.gettempdir()) / f"i2vgen_xl_output_{uuid.uuid4().hex}.mp4"
        
        # Save video using diffusers export_to_video utility
        diffusers.utils.export_to_video(video_frames, str(temp_video_path), fps=self.get_target_fps())
        
        # Create VideoUrlArtifact and save to storage
        video_artifact = VideoUrlArtifact(value=f"file://{temp_video_path}")
        storage_driver = GriptapeNodes.get_storage_driver()
        persistent_video_path = storage_driver.save_video_from_artifact(video_artifact)
        final_video_artifact = VideoUrlArtifact(value=persistent_video_path)
        
        self._node.set_parameter_value("output_video", final_video_artifact)
        self._node.parameter_output_values["output_video"] = final_video_artifact