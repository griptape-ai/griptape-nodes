import logging
import math
import tempfile
import uuid
from pathlib import Path

import diffusers  # type: ignore[reportMissingImports]
import numpy as np
import PIL.Image
import torch  # type: ignore[reportMissingImports]
from griptape.artifacts.video_url_artifact import VideoUrlArtifact
from PIL import Image
from pillow_nodes_library.utils import video_url_artifact_to_pil_images  # type: ignore[reportMissingImports]
from utils.directory_utils import check_cleanup_intermediates_directory

from diffusers_nodes_library.common.parameters.diffusion.runtime_parameters import (
    DiffusionPipelineRuntimeParameters,
)
from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import BaseNode
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

logger = logging.getLogger("diffusers_nodes_library")


class DepthCrafterPipelineRuntimeParameters(DiffusionPipelineRuntimeParameters):
    def __init__(self, node: BaseNode):
        super().__init__(node)

    def _add_input_parameters(self) -> None:
        self._node.add_parameter(
            Parameter(
                name="video",
                input_types=["VideoArtifact", "VideoUrlArtifact"],
                type="VideoUrlArtifact",
                tooltip="Input video for depth estimation",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="force_size",
                default_value=True,
                type="bool",
                tooltip="Automatically resize video frames to be multiples of 64 pixels",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="guidance_scale",
                default_value=1.0,
                type="float",
                tooltip="Classifier-free guidance scale. Higher values encourage alignment with prompts at the expense of image quality (1 - 1.2 recommended)",
                ui_options={"slider": {"min_val": 0.1, "max_val": 10.0}, "step": 0.1},
            )
        )
        self._node.add_parameter(
            Parameter(
                name="window_size",
                default_value=75,
                type="int",
                tooltip="Window size for sliding window processing of long videos. This can be lowered to save on VRAM at the expense of taking longer to render (75-110 is recommended)",
                ui_options={"slider": {"min_val": 1, "max_val": 200}},
            )
        )
        self._node.add_parameter(
            Parameter(
                name="overlap",
                default_value=25,
                type="int",
                tooltip="Overlap between windows during sliding window processing (25 recommended)",
                ui_options={"slider": {"min_val": 0, "max_val": 100}},
            )
        )
        self._node.add_parameter(
            Parameter(
                name="decode_chunk_size",
                default_value=6,
                type="int",
                tooltip="Number of frames to process at once during VAE encoding/decoding. Lower values use less VRAM but are slower.",
                ui_options={"slider": {"min_val": 1, "max_val": 16}},
            )
        )

    def _remove_input_parameters(self) -> None:
        self._node.remove_parameter_element_by_name("video")
        self._node.remove_parameter_element_by_name("force_size")
        self._node.remove_parameter_element_by_name("guidance_scale")
        self._node.remove_parameter_element_by_name("window_size")
        self._node.remove_parameter_element_by_name("overlap")
        self._node.remove_parameter_element_by_name("decode_chunk_size")

    def add_input_parameters(self) -> None:
        self._add_input_parameters()
        # Override to add num_inference_steps after custom params
        self._node.add_parameter(
            Parameter(
                name="num_inference_steps",
                default_value=5,
                type="int",
                tooltip="The number of denoising steps. More denoising steps usually lead to higher quality at the expense of slower inference.",
            )
        )

    def remove_input_parameters(self) -> None:
        self._node.remove_parameter_element_by_name("num_inference_steps")
        self._remove_input_parameters()

    def add_output_parameters(self) -> None:
        self._node.add_parameter(
            Parameter(
                name="output_video",
                output_type="VideoUrlArtifact",
                tooltip="Output depth map video",
                allowed_modes={ParameterMode.OUTPUT},
            )
        )

    def remove_output_parameters(self) -> None:
        self._node.remove_parameter_element_by_name("output_video")

    def _get_pipe_kwargs(self) -> dict:
        return {
            "guidance_scale": self._node.get_parameter_value("guidance_scale"),
            "window_size": self._node.get_parameter_value("window_size"),
            "overlap": self._node.get_parameter_value("overlap"),
        }

    def publish_output_image_preview_placeholder(self) -> None:
        # Create a small black video placeholder
        check_cleanup_intermediates_directory()

        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as temp_file:
            temp_path = Path(temp_file.name)
        try:
            # Create a single black frame and export as 1-frame video
            black_frame = PIL.Image.new("RGB", (320, 240), color="black")
            frames = [black_frame]
            diffusers.utils.export_to_video(frames, str(temp_path), fps=1)
            filename = f"placeholder_{uuid.uuid4()}.mp4"
            url = GriptapeNodes.StaticFilesManager().save_static_file(temp_path.read_bytes(), filename)
            self._node.publish_update_to_parameter("output_video", VideoUrlArtifact(url))
        finally:
            if temp_path.exists():
                temp_path.unlink()

    def get_input_video_frames(self) -> list[Image.Image]:
        """Load video frames from the input video artifact."""
        video_artifact = self._node.get_parameter_value("video")
        if video_artifact is None:
            msg = f"{self._node.name} requires a video input"
            logger.error(msg)
            raise ValueError(msg)

        # Convert VideoUrlArtifact to PIL images
        frames = video_url_artifact_to_pil_images(video_artifact)
        return frames

    def process_pipeline(self, pipe: diffusers.DiffusionPipeline) -> None:  # noqa: PLR0915
        self._node.log_params.append_to_logs("Loading video frames...\n")  # type: ignore[reportAttributeAccessIssue]

        # Load video frames
        frames = self.get_input_video_frames()
        num_frames = len(frames)

        if num_frames == 0:
            msg = f"{self._node.name} received empty video"
            logger.error(msg)
            raise ValueError(msg)

        self._node.log_params.append_to_logs(f"Loaded {num_frames} frames\n")  # type: ignore[reportAttributeAccessIssue]

        # Get dimensions from first frame
        first_frame = frames[0]
        orig_width, orig_height = first_frame.size

        # Handle force_size parameter
        force_size = self._node.get_parameter_value("force_size")
        if force_size:
            # Round to nearest multiple of 64
            width = round(orig_width / 64) * 64
            height = round(orig_height / 64) * 64
            # Ensure minimum size is 64
            width = max(64, width)
            height = max(64, height)

            if width != orig_width or height != orig_height:
                self._node.log_params.append_to_logs(  # type: ignore[reportAttributeAccessIssue]
                    f"Resizing input from {orig_width}x{orig_height} to {width}x{height} (multiples of 64)\n"
                )
                frames = [frame.resize((width, height), Image.Resampling.BILINEAR) for frame in frames]
        else:
            # Check if dimensions are multiples of 64
            if orig_width % 64 != 0 or orig_height % 64 != 0:
                msg = (
                    f"Input video dimensions ({orig_width}x{orig_height}) are not multiples of 64. "
                    f"Please resize your video to a multiple of 64 (e.g., {round(orig_width / 64) * 64}x{round(orig_height / 64) * 64}) "
                    f"or enable the 'force_size' option."
                )
                logger.error(msg)
                raise ValueError(msg)
            width = orig_width
            height = orig_height

        # Convert frames to numpy array then to torch tensor
        frames_np = np.stack([np.array(frame) for frame in frames])  # [B, H, W, C]
        frames_tensor = torch.from_numpy(frames_np).permute(0, 3, 1, 2).float() / 255.0  # [B, C, H, W]
        frames_tensor = torch.clamp(frames_tensor, 0, 1)

        # Prepare for inference
        num_inference_steps = self.get_num_inference_steps()
        window_size = self._node.get_parameter_value("window_size")
        overlap = self._node.get_parameter_value("overlap")

        # Calculate number of windows for progress tracking
        if num_frames > window_size:
            num_windows = math.ceil((num_frames - window_size) / (window_size - overlap)) + 1
        else:
            num_windows = 1

        total_steps = num_inference_steps * num_windows

        self._node.log_params.append_to_logs(f"Processing {num_frames} frames with {num_windows} window(s)...\n")  # type: ignore[reportAttributeAccessIssue]
        self._node.progress_bar_component.initialize(total_steps)  # type: ignore[reportAttributeAccessIssue]

        step_count = 0

        def progress_callback(_step: int) -> None:
            nonlocal step_count
            step_count += 1
            self._node.progress_bar_component.increment()  # type: ignore[reportAttributeAccessIssue]
            if step_count % num_inference_steps == 0:
                window_num = step_count // num_inference_steps
                self._node.log_params.append_to_logs(  # type: ignore[reportAttributeAccessIssue]
                    f"Completed window {window_num} of {num_windows}\n"
                )

        # Run the pipeline
        self._node.log_params.append_to_logs("Running depth estimation...\n")  # type: ignore[reportAttributeAccessIssue]

        decode_chunk_size = self._node.get_parameter_value("decode_chunk_size")

        with torch.inference_mode():
            result = pipe(
                frames_tensor,
                height=height,
                width=width,
                output_type="pt",
                num_inference_steps=num_inference_steps,
                guidance_scale=self._node.get_parameter_value("guidance_scale"),
                window_size=window_size,
                overlap=overlap,
                decode_chunk_size=decode_chunk_size,
                track_time=False,
                progress_callback=progress_callback,
            )

        depth_frames = result.frames[0]  # [B, C, H, W] in PyTorch format when output_type="pt"

        self._node.log_params.append_to_logs("Post-processing depth maps...\n")  # type: ignore[reportAttributeAccessIssue]

        # Convert from PyTorch format [B, C, H, W] to numpy format [B, H, W, C]
        depth_frames = depth_frames.permute(0, 2, 3, 1)  # [B, H, W, C]

        # Convert to grayscale depth map
        depth_frames = depth_frames.sum(dim=-1) / depth_frames.shape[-1]  # [B, H, W]

        # Normalize depth maps
        depth_min = depth_frames.min()
        depth_max = depth_frames.max()
        depth_frames = (depth_frames - depth_min) / (depth_max - depth_min + 1e-8)

        # Convert back to 3-channel format for video output
        depth_frames = depth_frames.unsqueeze(-1).repeat(1, 1, 1, 3)  # [B, H, W, 3]

        # Convert back to original size if it was resized
        if (width != orig_width or height != orig_height) and force_size:
            self._node.log_params.append_to_logs(  # type: ignore[reportAttributeAccessIssue]
                f"Resizing output from {width}x{height} back to {orig_width}x{orig_height}\n"
            )
            depth_tensor = depth_frames.permute(0, 3, 1, 2)  # [B, C, H, W]
            depth_tensor = torch.nn.functional.interpolate(
                depth_tensor,
                size=(orig_height, orig_width),
                mode="bilinear",
                align_corners=False,
            )
            depth_frames = depth_tensor.permute(0, 2, 3, 1)  # [B, H, W, C]

        # Convert to PIL images
        depth_frames_np = (depth_frames.cpu().numpy() * 255).astype(np.uint8)
        depth_pil_frames = [Image.fromarray(frame) for frame in depth_frames_np]

        # Export to video
        self._node.log_params.append_to_logs("Exporting depth video...\n")  # type: ignore[reportAttributeAccessIssue]

        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as temp_file_obj:
            temp_file_path = Path(temp_file_obj.name)

        try:
            # Get FPS from input video artifact, default to 30
            video_artifact = self._node.get_parameter_value("video")
            fps = getattr(video_artifact, "fps", 30)

            diffusers.utils.export_to_video(depth_pil_frames, str(temp_file_path), fps=fps)
            self.publish_output_video(temp_file_path)
        finally:
            if temp_file_path.exists():
                temp_file_path.unlink()

        self._node.log_params.append_to_logs("Done.\n")  # type: ignore[reportAttributeAccessIssue]

    def publish_output_video(self, video_path: Path) -> None:
        filename = f"{uuid.uuid4()}{video_path.suffix}"
        url = GriptapeNodes.StaticFilesManager().save_static_file(video_path.read_bytes(), filename)
        video_artifact = VideoUrlArtifact(url)
        self._node.publish_update_to_parameter("output_video", video_artifact)
        self._node.set_parameter_value("output_video", video_artifact)
        self._node.parameter_output_values["output_video"] = video_artifact
