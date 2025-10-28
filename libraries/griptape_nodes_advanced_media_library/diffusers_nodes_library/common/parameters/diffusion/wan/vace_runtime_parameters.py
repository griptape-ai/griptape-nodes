import logging
import tempfile
import uuid
from pathlib import Path
from typing import Any

import diffusers  # type: ignore[reportMissingImports]
import torch  # type: ignore[reportMissingImports]
from griptape.artifacts import ImageUrlArtifact
from griptape.artifacts.video_url_artifact import VideoUrlArtifact
from PIL import Image  # type: ignore[reportMissingImports]
from pillow_nodes_library.utils import (  # type: ignore[reportMissingImports]
    image_artifact_to_pil,
)
from utils.image_utils import load_image_from_url_artifact

from diffusers_nodes_library.common.parameters.diffusion.runtime_parameters import (
    DiffusionPipelineRuntimeParameters,
)
from griptape_nodes.exe_types.core_types import Parameter, ParameterList, ParameterMode
from griptape_nodes.exe_types.node_types import BaseNode
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

logger = logging.getLogger("diffusers_nodes_library")


class WanVacePipelineRuntimeParameters(DiffusionPipelineRuntimeParameters):
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
        self._node.add_parameter(
            Parameter(
                name="input_video",
                default_value=None,
                type="VideoUrlArtifact",
                tooltip="Input video for video-to-video generation (optional)",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="mask",
                default_value=None,
                type="VideoUrlArtifact",
                tooltip="Mask video for video-to-video generation (required when input_video is provided)",
            )
        )
        self._node.add_parameter(
            ParameterList(
                name="reference_frames",
                default_value=[],
                type="ImageArtifact",
                tooltip="Reference frames to guide video generation (optional)",
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
        self._node.remove_parameter_element_by_name("input_video")
        self._node.remove_parameter_element_by_name("mask")
        self._node.remove_parameter_element_by_name("reference_frames")

    def remove_output_parameters(self) -> None:
        self._node.remove_parameter_element_by_name("output_video")

    def _get_pipe_kwargs(self) -> dict:
        return {
            "video": self.get_input_video_pil_frames(),
            "mask": self.get_mask_pil_frames(),
            "reference_images": self.get_reference_frames_pil(),
            "prompt": self._node.get_parameter_value("prompt"),
            "negative_prompt": self._node.get_parameter_value("negative_prompt"),
            "num_frames": self.get_num_frames(),
            "guidance_scale": self._node.get_parameter_value("guidance_scale"),
            "output_type": "pil",
        }

    def validate_before_node_run(self) -> list[Exception] | None:
        errors = []

        # Validate video and mask are provided together or neither are provided
        input_video = self.get_input_video()
        mask = self.get_mask()
        prompt = self._node.get_parameter_value("prompt")

        if (input_video is None) != (mask is None):
            if input_video is None:
                errors.append(
                    ValueError(
                        "Mask is provided but input_video is missing. Both video and mask are required together."
                    )
                )
            else:
                errors.append(
                    ValueError(
                        "Input video is provided but mask is missing. Both video and mask are required together."
                    )
                )

        # Ensure there's some input for generation
        if input_video is None and not prompt.strip():
            errors.append(ValueError("Must provide either a prompt or both input_video and mask for video generation"))

        # Validate dimensions are divisible by 16
        width = self.get_width()
        height = self.get_height()
        if width % 16 != 0:
            errors.append(ValueError(f"Width ({width}) must be divisible by 16"))
        if height % 16 != 0:
            errors.append(ValueError(f"Height ({height}) must be divisible by 16"))

        return errors or None

    def get_num_frames(self) -> int:
        return int(self._node.get_parameter_value("num_frames"))

    def get_input_video(self) -> VideoUrlArtifact | None:
        return self._node.get_parameter_value("input_video")

    def get_mask(self) -> VideoUrlArtifact | None:
        return self._node.get_parameter_value("mask")

    def get_reference_frames(self) -> list:
        return self._node.get_parameter_value("reference_frames") or []

    def get_input_video_pil_frames(self) -> list[Image.Image] | None:
        input_video = self.get_input_video()
        if input_video is None:
            return None
        return self._video_artifact_to_pil_frames(input_video)

    def get_mask_pil_frames(self) -> list[Image.Image] | None:
        mask = self.get_mask()
        if mask is None:
            return None
        return [pil_frame.convert("L") for pil_frame in self._video_artifact_to_pil_frames(mask)]

    def get_reference_frames_pil(self) -> list[Image.Image] | None:
        """Get reference frames as a list of PIL Images."""
        reference_frames = self.get_reference_frames()
        if not reference_frames:
            return None

        pil_images = []
        for frame_artifact in reference_frames:
            image_artifact = frame_artifact
            if isinstance(image_artifact, ImageUrlArtifact):
                image_artifact = load_image_from_url_artifact(image_artifact)
            pil_image = image_artifact_to_pil(image_artifact)
            pil_image = pil_image.convert("RGB")
            pil_images.append(pil_image)

        return pil_images if pil_images else None

    def _video_artifact_to_pil_frames(self, video_artifact: VideoUrlArtifact) -> list[Image.Image]:
        """Convert a VideoUrlArtifact to a list of PIL Image frames."""
        if video_artifact is None:
            return []

        # Use diffusers loading utilities to convert video URL to frames
        return diffusers.utils.load_video(video_artifact.value)

    def latents_to_video_mp4(self, pipe: diffusers.WanVACEPipeline, latents: Any) -> Path:
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

    def publish_output_video_preview_latents(self, pipe: diffusers.WanVACEPipeline, latents: Any) -> None:
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
