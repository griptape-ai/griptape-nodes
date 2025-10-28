import logging
import tempfile
import uuid
from pathlib import Path
from typing import Any

import diffusers  # type: ignore[reportMissingImports]
import torch  # type: ignore[reportMissingImports]
from griptape.artifacts.video_url_artifact import VideoUrlArtifact

from diffusers_nodes_library.common.parameters.diffusion.runtime_parameters import (
    DiffusionPipelineRuntimeParameters,
)
from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import BaseNode
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

logger = logging.getLogger("diffusers_nodes_library")


class WanPipelineRuntimeParameters(DiffusionPipelineRuntimeParameters):
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
                default_value=81,
                type="int",
                tooltip="Number of frames to generate (model-specific)",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="guidance_scale",
                default_value=5.0,
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

    def latents_to_video_mp4(self, pipe: diffusers.WanPipeline, latents: Any) -> Path:
        """Convert latents to video frames and export as MP4 file."""
        self.get_num_frames()
        self.get_width()
        self.get_height()

        # First convert latents to frames using the VAE
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as temp_file_obj:
            temp_file = Path(temp_file_obj.name)

        try:
            # Convert latents to video frames using VAE decode
            latents = latents.to(pipe.vae.dtype)

            # Apply latents normalization as per the WAN pipeline
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
            diffusers.utils.export_to_video(frames, str(temp_file), fps=16)
        except Exception:
            # Clean up on error
            if temp_file.exists():
                temp_file.unlink()
            raise
        else:
            return temp_file

    def publish_output_video_preview_latents(self, pipe: diffusers.WanPipeline, latents: Any) -> None:
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
