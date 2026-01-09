import logging
import tempfile
import uuid
from pathlib import Path
from typing import Any

import diffusers  # type: ignore[reportMissingImports]
import torch  # type: ignore[reportMissingImports]
from griptape.artifacts.video_url_artifact import VideoUrlArtifact

from diffusers_nodes_library.common.parameters.diffusion.ltx2.validation import (
    get_nearest_valid_dimension,
    get_valid_num_frames_hint,
    is_valid_dimension,
    is_valid_num_frames,
)
from diffusers_nodes_library.common.parameters.diffusion.runtime_parameters import (
    DiffusionPipelineRuntimeParameters,
)
from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import BaseNode
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

logger = logging.getLogger("diffusers_nodes_library")


class LTX2PipelineRuntimeParameters(DiffusionPipelineRuntimeParameters):
    def __init__(self, node: BaseNode):
        super().__init__(node)

    def _add_input_parameters(self) -> None:
        self._node.add_parameter(
            Parameter(
                name="prompt",
                default_value="",
                type="str",
                tooltip="Prompt for video generation",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="negative_prompt",
                default_value="",
                type="str",
                tooltip="Negative prompt (optional)",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="num_frames",
                default_value=97,
                type="int",
                tooltip="Number of frames to generate (must be divisible by 8 + 1, e.g., 9, 17, 25, ..., 97)",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="guidance_scale",
                default_value=7.5,
                type="float",
                tooltip="CFG guidance scale (higher = more prompt adherence)",
            )
        )

    def add_output_parameters(self) -> None:
        self._node.add_parameter(
            Parameter(
                name="output_video",
                output_type="VideoUrlArtifact",
                tooltip="Generated video",
                allowed_modes={ParameterMode.OUTPUT},
            )
        )

    def _remove_input_parameters(self) -> None:
        self._node.remove_parameter_element_by_name("prompt")
        self._node.remove_parameter_element_by_name("negative_prompt")
        self._node.remove_parameter_element_by_name("num_frames")
        self._node.remove_parameter_element_by_name("guidance_scale")

    def remove_output_parameters(self) -> None:
        self._node.remove_parameter_element_by_name("output_video")

    def after_value_set(self, parameter: Parameter, value: Any) -> None:
        super().after_value_set(parameter, value)

        # Validate num_frames follows the pattern (n * 8) + 1
        if parameter.name == "num_frames" and value is not None:
            num_frames = int(value)
            if not is_valid_num_frames(num_frames):
                hint = get_valid_num_frames_hint(num_frames)
                logger.warning(
                    "num_frames (%d) is invalid. LTX-2 requires num_frames to follow pattern (n x 8) + 1. %s",
                    num_frames,
                    hint,
                )

        # Validate width is divisible by 32
        if parameter.name == "width" and value is not None:
            width = int(value)
            if not is_valid_dimension(width):
                nearest = get_nearest_valid_dimension(width)
                logger.warning(
                    "width (%d) must be divisible by 32. Nearest valid value: %d",
                    width,
                    nearest,
                )

        # Validate height is divisible by 32
        if parameter.name == "height" and value is not None:
            height = int(value)
            if not is_valid_dimension(height):
                nearest = get_nearest_valid_dimension(height)
                logger.warning(
                    "height (%d) must be divisible by 32. Nearest valid value: %d",
                    height,
                    nearest,
                )

    def validate_before_node_run(self) -> list[Exception] | None:
        errors = []

        # Validate num_frames follows the pattern (n * 8) + 1
        num_frames = self.get_num_frames()
        if not is_valid_num_frames(num_frames):
            hint = get_valid_num_frames_hint(num_frames)
            errors.append(ValueError(f"num_frames ({num_frames}) is invalid. {hint}"))

        # Validate dimensions are divisible by 32 (LTX-2 requirement)
        width = self.get_width()
        height = self.get_height()
        if not is_valid_dimension(width):
            nearest = get_nearest_valid_dimension(width)
            errors.append(ValueError(f"Width ({width}) must be divisible by 32. Nearest valid value: {nearest}"))
        if not is_valid_dimension(height):
            nearest = get_nearest_valid_dimension(height)
            errors.append(ValueError(f"Height ({height}) must be divisible by 32. Nearest valid value: {nearest}"))

        return errors or None

    def _get_pipe_kwargs(self) -> dict:
        return {
            "prompt": self._node.get_parameter_value("prompt"),
            "negative_prompt": self._node.get_parameter_value("negative_prompt"),
            "num_frames": self.get_num_frames(),
            "guidance_scale": self._node.get_parameter_value("guidance_scale"),
            "output_type": "pil",
        }

    def get_num_frames(self) -> int:
        return int(self._node.get_parameter_value("num_frames"))

    def latents_to_video_mp4(self, pipe: diffusers.LTX2Pipeline, latents: Any) -> Path:
        """Convert latents to video frames and export as MP4 file."""
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as temp_file_obj:
            temp_file = Path(temp_file_obj.name)

        try:
            # Convert latents to video frames using VAE decode
            latents = latents.to(pipe.vae.dtype)

            # Apply latents normalization as per the LTX pipeline
            latents_mean = (
                torch.tensor(pipe.vae.config.latents_mean)
                .view(1, pipe.vae.config.z_dim, 1, 1, 1)
                .to(latents.device, latents.dtype)
            )
            latents_std = 1.0 / torch.tensor(pipe.vae.config.latents_std).view(1, pipe.vae.config.z_dim, 1, 1, 1).to(
                latents.device, latents.dtype
            )
            latents = latents / latents_std + latents_mean

            # Decode latents to video using VAE
            video = pipe.vae.decode(latents, return_dict=False)[0]
            frames = pipe.video_processor.postprocess_video(video, output_type="pil")[0]

            # Export frames to video
            diffusers.utils.export_to_video(frames, str(temp_file), fps=24)
        except Exception:
            # Clean up on error
            if temp_file.exists():
                temp_file.unlink()
            raise
        else:
            return temp_file

    def publish_output_video_preview_latents(self, pipe: diffusers.LTX2Pipeline, latents: Any) -> None:
        """Publish a preview video from latents during generation."""
        preview_video_path = None
        try:
            preview_video_path = self.latents_to_video_mp4(pipe, latents)
            filename = f"preview_{uuid.uuid4()}.mp4"
            url = GriptapeNodes.StaticFilesManager().save_static_file(preview_video_path.read_bytes(), filename)
            self._node.publish_update_to_parameter("output_video", VideoUrlArtifact(url))
        except Exception as e:
            logger.warning("Failed to generate video preview from latents: %s", e)
        finally:
            # Clean up temporary file
            if preview_video_path is not None and preview_video_path.exists():
                preview_video_path.unlink()

    def publish_output_video(self, video_path: Path) -> None:
        filename = f"{uuid.uuid4()}{video_path.suffix}"
        url = GriptapeNodes.StaticFilesManager().save_static_file(video_path.read_bytes(), filename)
        self._node.parameter_output_values["output_video"] = VideoUrlArtifact(url)
