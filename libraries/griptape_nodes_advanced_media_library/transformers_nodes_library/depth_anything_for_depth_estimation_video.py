import logging
import tempfile
import uuid
from pathlib import Path

import diffusers  # type: ignore[reportMissingImports]
import PIL.Image
from griptape.artifacts.video_url_artifact import VideoUrlArtifact

from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import AsyncResult, ControlNode
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
from transformers_nodes_library.depth_anything_for_depth_estimation_parameters import (
    DepthAnythingForDepthEstimationParameters,
)

logger = logging.getLogger("diffusers_nodes_library")


class DepthAnythingForDepthEstimationVideo(ControlNode):
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.params = DepthAnythingForDepthEstimationParameters(self)
        self.params.add_input_parameters()
        self.add_parameter(
            Parameter(
                name="input_video",
                input_types=["VideoArtifact", "VideoUrlArtifact"],
                type="VideoArtifact",
                output_type="VideoUrlArtifact",
                tooltip="input_video",
            )
        )
        self.add_parameter(
            Parameter(
                name="output_video",
                output_type="VideoUrlArtifact",
                tooltip="The output depth video",
                allowed_modes={ParameterMode.OUTPUT},
            )
        )
        self.params.add_logs_output_parameter()

    def process(self) -> AsyncResult | None:
        yield lambda: self._process()

    def _process(self) -> AsyncResult | None:
        input_video_artifact = self.get_parameter_value("input_video")

        if input_video_artifact is None:
            msg = "Input video is required"
            raise ValueError(msg)

        self.append_value_to_parameter("logs", "Loading video frames...\n")

        # Load video frames using diffusers utilities
        input_frames = diffusers.utils.load_video(input_video_artifact.value)

        if not input_frames:
            msg = "Could not load frames from input video"
            raise ValueError(msg)

        # Create preview placeholder with first frame size
        first_frame = input_frames[0].convert("RGB")
        preview_placeholder_video = self._create_placeholder_video([first_frame])
        self.publish_update_to_parameter("output_video", preview_placeholder_video)

        self.append_value_to_parameter("logs", "Preparing models...\n")
        with self.params.append_stdout_to_logs():
            image_processor, model = self.params.load_models()

        self.append_value_to_parameter("logs", f"Processing {len(input_frames)} frames...\n")

        # Process each frame for depth estimation
        depth_frames = []
        for i, frame in enumerate(input_frames):
            frame_rgb = frame.convert("RGB")
            depth_frame = self.params.process_depth_estimation(image_processor, model, frame_rgb)
            depth_frames.append(depth_frame)

            # Log progress every 10 frames
            if (i + 1) % 10 == 0 or i == 0:
                self.append_value_to_parameter("logs", f"Processed frame {i + 1}/{len(input_frames)}\n")

        self.append_value_to_parameter("logs", "Exporting depth video...\n")

        # Export frames to video
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as temp_file_obj:
            temp_file = Path(temp_file_obj.name)

        try:
            diffusers.utils.export_to_video(depth_frames, str(temp_file), fps=16)
            output_video_artifact = self._publish_output_video(temp_file)
            self.set_parameter_value("output_video", output_video_artifact)
            self.parameter_output_values["output_video"] = output_video_artifact
        finally:
            if temp_file.exists():
                temp_file.unlink()

    def _create_placeholder_video(self, frames: list[PIL.Image.Image]) -> VideoUrlArtifact:
        """Create a placeholder video for preview purposes."""
        placeholder_frames = [self.params.create_preview_placeholder(frame.size) for frame in frames]

        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as temp_file_obj:
            temp_file = Path(temp_file_obj.name)

        try:
            diffusers.utils.export_to_video(placeholder_frames, str(temp_file), fps=16)
            return self._publish_output_video(temp_file)
        finally:
            if temp_file.exists():
                temp_file.unlink()

    def _publish_output_video(self, video_path: Path) -> VideoUrlArtifact:
        """Publish output video to static files and return artifact."""
        filename = f"{uuid.uuid4()}{video_path.suffix}"
        url = GriptapeNodes.StaticFilesManager().save_static_file(video_path.read_bytes(), filename)
        return VideoUrlArtifact(url)
