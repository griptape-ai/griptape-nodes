import logging
import tempfile
import uuid
from pathlib import Path

import diffusers  # type: ignore[reportMissingImports]
import PIL.Image  # type: ignore[reportMissingImports]
from griptape.artifacts import ImageUrlArtifact
from griptape.artifacts.video_url_artifact import VideoUrlArtifact
from PIL import Image  # type: ignore[reportMissingImports]
from pillow_nodes_library.utils import (  # type: ignore[reportMissingImports]
    image_artifact_to_pil,
)
from utils.image_utils import load_image_from_url_artifact

from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import AsyncResult, ControlNode
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

logger = logging.getLogger("diffusers_nodes_library")


class StaticMaskWanVaceAux(ControlNode):
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)

        self.add_parameter(
            Parameter(
                name="input_video",
                input_types=["VideoUrlArtifact"],
                type="VideoUrlArtifact",
                tooltip="Input video to apply mask to",
            )
        )
        self.add_parameter(
            Parameter(
                name="mask_image",
                input_types=["ImageArtifact", "ImageUrlArtifact"],
                type="ImageArtifact",
                tooltip="Mask image (white = generate/inpaint, black = preserve)",
            )
        )
        self.add_parameter(
            Parameter(
                name="output_video",
                output_type="VideoUrlArtifact",
                tooltip="Copy of input video (for pipeline compatibility)",
                allowed_modes={ParameterMode.OUTPUT},
            )
        )
        self.add_parameter(
            Parameter(
                name="output_mask",
                output_type="VideoUrlArtifact",
                tooltip="Generated mask video with static mask applied to all frames",
                allowed_modes={ParameterMode.OUTPUT},
            )
        )

    def validate_before_node_run(self) -> list[Exception] | None:
        errors = []

        input_video = self.get_parameter_value("input_video")
        if input_video is None:
            errors.append(ValueError("Input video is required"))

        mask_image = self.get_parameter_value("mask_image")
        if mask_image is None:
            errors.append(ValueError("Mask image is required"))

        return errors or None

    def process(self) -> AsyncResult | None:
        yield lambda: self._process()

    def _process(self) -> AsyncResult | None:
        input_video = self.get_parameter_value("input_video")
        mask_image = self.get_parameter_value("mask_image")

        # Load video frames
        video_frames = diffusers.utils.load_video(input_video.value)

        if not video_frames:
            msg = "Could not load frames from input video"
            raise ValueError(msg)

        # Convert mask image to PIL, handling ImageUrlArtifact
        if isinstance(mask_image, ImageUrlArtifact):
            mask_image = load_image_from_url_artifact(mask_image)
        mask_pil = image_artifact_to_pil(mask_image)

        # Ensure mask image is RGB to match video frames
        if mask_pil.mode != "L":
            mask_pil = mask_pil.convert("L")

        # Validate dimensions match
        video_width, video_height = video_frames[0].size
        mask_width, mask_height = mask_pil.size

        if video_width != mask_width or video_height != mask_height:
            msg = f"Mask dimensions ({mask_width}x{mask_height}) must match video dimensions ({video_width}x{video_height})"
            raise ValueError(msg)

        # Create mask frames - same mask for all frames
        mask_frames = [mask_pil.copy() for _ in video_frames]

        video_frames = [frame.convert("RGB") for frame in video_frames]
        for i in range(len(video_frames)):
            new_frame = PIL.Image.new("RGB", (video_width, video_height), (128, 128, 128))
            mask_inverse = mask_frames[i].point(lambda p: 255 - p)
            new_frame.paste(video_frames[i], mask=mask_inverse)
            video_frames[i] = new_frame

        # Export videos
        video_path = self._export_frames_to_video(video_frames)
        mask_path = self._export_frames_to_video(mask_frames)

        try:
            # Save original video
            video_filename = f"{uuid.uuid4()}.mp4"
            video_url = GriptapeNodes.StaticFilesManager().save_static_file(video_path.read_bytes(), video_filename)
            self.set_parameter_value("output_video", VideoUrlArtifact(video_url))
            self.parameter_output_values["output_video"] = VideoUrlArtifact(video_url)

            # Save mask
            mask_filename = f"{uuid.uuid4()}.mp4"
            mask_url = GriptapeNodes.StaticFilesManager().save_static_file(mask_path.read_bytes(), mask_filename)
            self.set_parameter_value("output_mask", VideoUrlArtifact(mask_url))
            self.parameter_output_values["output_mask"] = VideoUrlArtifact(mask_url)

        finally:
            # Clean up temporary files
            if video_path.exists():
                video_path.unlink()
            if mask_path.exists():
                mask_path.unlink()

    def _export_frames_to_video(self, frames: list[Image.Image]) -> Path:
        """Export PIL frames to MP4 video file."""
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as temp_file:
            temp_path = Path(temp_file.name)

        try:
            diffusers.utils.export_to_video(frames, str(temp_path), fps=16)
        except Exception:
            if temp_path.exists():
                temp_path.unlink()
            raise
        else:
            return temp_path
