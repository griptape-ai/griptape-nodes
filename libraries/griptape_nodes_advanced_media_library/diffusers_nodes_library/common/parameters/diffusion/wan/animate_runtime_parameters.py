import logging
import tempfile
import uuid
from pathlib import Path
from typing import Any

import diffusers  # type: ignore[reportMissingImports]
import PIL.Image
import torch  # type: ignore[reportMissingImports]
from griptape.artifacts import ImageUrlArtifact
from griptape.artifacts.video_url_artifact import VideoUrlArtifact
from griptape.loaders import ImageLoader
from PIL.Image import Image
from pillow_nodes_library.utils import (  # type: ignore[reportMissingImports]
    image_artifact_to_pil,
)

from diffusers_nodes_library.common.parameters.diffusion.runtime_parameters import (
    DiffusionPipelineRuntimeParameters,
)
from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import BaseNode
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
from griptape_nodes.traits.options import Options

logger = logging.getLogger("diffusers_nodes_library")


class WanAnimatePipelineRuntimeParameters(DiffusionPipelineRuntimeParameters):
    def __init__(self, node: BaseNode):
        super().__init__(node)

    def _add_input_parameters(self) -> None:
        self._node.add_parameter(
            Parameter(
                name="input_image",
                type="ImageArtifact",
                tooltip="Input image for animation",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="pose_video",
                type="VideoArtifact",
                tooltip="Pose keypoint video for motion control",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="face_video",
                type="VideoArtifact",
                tooltip="Facial feature video for expression control",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="background_video",
                default_value=None,
                type="VideoArtifact",
                tooltip="Optional background video for replace mode",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="mask_video",
                default_value=None,
                type="VideoArtifact",
                tooltip="Optional mask video for replace mode",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="prompt",
                default_value="",
                type="str",
                tooltip="Prompt for animation generation",
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
        mode_choices = ["animate", "replace"]
        self._node.add_parameter(
            Parameter(
                name="mode",
                default_value="animate",
                type="str",
                tooltip="Generation mode: 'animate' or 'replace'",
                traits={Options(choices=mode_choices)},
            )
        )
        self._node.add_parameter(
            Parameter(
                name="num_frames",
                default_value=77,
                type="int",
                tooltip="Number of frames to generate",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="guidance_scale",
                default_value=1.0,
                type="float",
                tooltip="CFG guidance scale (typically lower for animate, default 1.0)",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="segment_frame_length",
                default_value=77,
                type="int",
                tooltip="Frame count per generation segment",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="prev_segment_conditioning_frames",
                default_value=1,
                type="int",
                tooltip="Frames used for temporal guidance between segments",
            )
        )

        # Hide background_video and mask_video by default (only for "replace" mode)
        self._node.hide_parameter_by_name("background_video")
        self._node.hide_parameter_by_name("mask_video")

    def add_output_parameters(self) -> None:
        self._node.add_parameter(
            Parameter(
                name="output_video",
                output_type="VideoUrlArtifact",
                tooltip="The generated animation video",
                allowed_modes={ParameterMode.OUTPUT},
            )
        )

    def _remove_input_parameters(self) -> None:
        self._node.remove_parameter_element_by_name("input_image")
        self._node.remove_parameter_element_by_name("pose_video")
        self._node.remove_parameter_element_by_name("face_video")
        self._node.remove_parameter_element_by_name("background_video")
        self._node.remove_parameter_element_by_name("mask_video")
        self._node.remove_parameter_element_by_name("prompt")
        self._node.remove_parameter_element_by_name("negative_prompt")
        self._node.remove_parameter_element_by_name("mode")
        self._node.remove_parameter_element_by_name("num_frames")
        self._node.remove_parameter_element_by_name("guidance_scale")
        self._node.remove_parameter_element_by_name("segment_frame_length")
        self._node.remove_parameter_element_by_name("prev_segment_conditioning_frames")

    def remove_output_parameters(self) -> None:
        self._node.remove_parameter_element_by_name("output_video")

    def after_value_set(self, parameter: Parameter, value: Any) -> None:
        if parameter.name == "mode":
            if value == "replace":
                self._node.show_parameter_by_name("background_video")
                self._node.show_parameter_by_name("mask_video")
            else:
                self._node.hide_parameter_by_name("background_video")
                self._node.hide_parameter_by_name("mask_video")

    def validate_before_node_run(self) -> list[Exception] | None:
        errors = []

        mode = self._node.get_parameter_value("mode")
        if mode not in ["animate", "replace"]:
            errors.append(ValueError(f"{self._node.name}: mode must be 'animate' or 'replace', got '{mode}'"))

        if mode == "replace":
            background_video = self._node.get_parameter_value("background_video")
            if background_video is None:
                errors.append(
                    ValueError(f"{self._node.name}: background_video is required when mode is 'replace'")
                )

        return errors or None

    def get_input_image_pil(self) -> Image:
        input_image_artifact = self._node.get_parameter_value("input_image")
        if isinstance(input_image_artifact, ImageUrlArtifact):
            input_image_artifact = ImageLoader().parse(input_image_artifact.to_bytes())
        input_image_pil = image_artifact_to_pil(input_image_artifact)
        return input_image_pil.convert("RGB")

    def get_video_frames_from_artifact(self, video_artifact: Any) -> list[Image] | None:
        """Load video frames from a VideoArtifact using diffusers.utils.load_video."""
        if video_artifact is None:
            return None

        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as temp_file:
            temp_path = Path(temp_file.name)
            temp_path.write_bytes(video_artifact.to_bytes())

        try:
            frames = diffusers.utils.load_video(str(temp_path))  # type: ignore[reportPrivateImportUsage]
            return frames
        finally:
            if temp_path.exists():
                temp_path.unlink()

    def get_num_frames(self) -> int:
        return int(self._node.get_parameter_value("num_frames"))

    def _get_pipe_kwargs(self) -> dict:
        image = self.get_input_image_pil()
        pose_video = self.get_video_frames_from_artifact(
            self._node.get_parameter_value("pose_video")
        )
        face_video = self.get_video_frames_from_artifact(
            self._node.get_parameter_value("face_video")
        )
        background_video = self.get_video_frames_from_artifact(
            self._node.get_parameter_value("background_video")
        )
        mask_video = self.get_video_frames_from_artifact(
            self._node.get_parameter_value("mask_video")
        )

        kwargs = {
            "image": image,
            "pose_video": pose_video,
            "face_video": face_video,
            "prompt": self._node.get_parameter_value("prompt"),
            "negative_prompt": self._node.get_parameter_value("negative_prompt"),
            "mode": self._node.get_parameter_value("mode"),
            "num_frames": self.get_num_frames(),
            "guidance_scale": self._node.get_parameter_value("guidance_scale"),
            "segment_frame_length": int(self._node.get_parameter_value("segment_frame_length")),
            "prev_segment_conditioning_frames": int(
                self._node.get_parameter_value("prev_segment_conditioning_frames")
            ),
            "output_type": "pil",
        }

        if background_video is not None:
            kwargs["background_video"] = background_video
        if mask_video is not None:
            kwargs["mask_video"] = mask_video

        return kwargs

    def publish_output_video_preview_placeholder(self) -> None:
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as temp_file:
            temp_path = Path(temp_file.name)
        try:
            black_frame = PIL.Image.new("RGB", (320, 240), color="black")
            frames = [black_frame]
            diffusers.utils.export_to_video(frames, str(temp_path), fps=1)  # type: ignore[reportPrivateImportUsage]
            filename = f"placeholder_{uuid.uuid4()}.mp4"
            url = GriptapeNodes.StaticFilesManager().save_static_file(temp_path.read_bytes(), filename)
            self._node.publish_update_to_parameter("output_video", VideoUrlArtifact(url))
        finally:
            if temp_path.exists():
                temp_path.unlink()

    def latents_to_video_mp4(self, pipe: Any, latents: Any) -> Path:
        """Convert latents to video frames and export as MP4 file."""
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as temp_file_obj:
            temp_file = Path(temp_file_obj.name)

        try:
            latents = latents.to(pipe.vae.dtype)

            latents_mean = (
                torch.tensor(pipe.vae.config.latents_mean)
                .view(1, pipe.vae.config.z_dim, 1, 1, 1)
                .to(latents.device, latents.dtype)
            )
            latents_std = 1.0 / torch.tensor(pipe.vae.config.latents_std).view(1, pipe.vae.config.z_dim, 1, 1, 1).to(
                latents.device, latents.dtype
            )
            latents = latents / latents_std + latents_mean

            video = pipe.vae.decode(latents, return_dict=False)[0]
            frames = pipe.video_processor.postprocess_video(video, output_type="pil")[0]

            diffusers.utils.export_to_video(frames, str(temp_file), fps=16)  # type: ignore[reportPrivateImportUsage]
        except Exception:
            if temp_file.exists():
                temp_file.unlink()
            raise
        else:
            return temp_file

    def publish_output_video_preview_latents(self, pipe: Any, latents: Any) -> None:
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
            if preview_video_path is not None and preview_video_path.exists():
                preview_video_path.unlink()

    def publish_output_video(self, video_path: Path) -> None:
        filename = f"{uuid.uuid4()}{video_path.suffix}"
        url = GriptapeNodes.StaticFilesManager().save_static_file(video_path.read_bytes(), filename)
        self._node.parameter_output_values["output_video"] = VideoUrlArtifact(url)
