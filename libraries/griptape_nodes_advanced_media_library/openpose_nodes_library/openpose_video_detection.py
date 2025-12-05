import copy
import logging
import os
import subprocess
import tempfile
import uuid
from pathlib import Path
from typing import Any

import cv2  # type: ignore[reportMissingImports]
import huggingface_hub  # pyright: ignore[reportMissingImports]
import imageio  # type: ignore[reportMissingImports]
import numpy as np
import requests
from artifact_utils.video_utils import dict_to_video_url_artifact  # type: ignore[reportMissingImports]
from griptape.artifacts.video_url_artifact import VideoUrlArtifact
from safetensors.torch import load_file  # type: ignore[reportMissingImports]

# static_ffmpeg is dynamically installed by the library loader at runtime
# into the library's own virtual environment, but not available during type checking
from static_ffmpeg import run  # type: ignore[import-untyped]

from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import AsyncResult, ControlNode
from griptape_nodes.exe_types.param_components.huggingface.huggingface_repo_file_parameter import (
    HuggingFaceRepoFileParameter,  # type: ignore[reportMissingImports]
)
from griptape_nodes.exe_types.param_components.log_parameter import LogParameter
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
from openpose_nodes_library.model import util  # type: ignore[reportMissingImports]
from openpose_nodes_library.model.body import Body  # type: ignore[reportMissingImports]
from openpose_nodes_library.model.hand import Hand  # type: ignore[reportMissingImports]

logger = logging.getLogger("openpose")


def calculate_processing_size(original_height: int, original_width: int, max_dim: int | None) -> tuple[int, int, float]:
    """Calculate processing dimensions based on max_dim constraint."""
    if max_dim is None:
        return original_height, original_width, 1.0

    # Find the longer dimension
    longer_dim = max(original_height, original_width)

    # If already smaller than max_dim, don't scale
    if longer_dim <= max_dim:
        return original_height, original_width, 1.0

    # Calculate scale factor to make longest dimension = max_dim
    scale_factor = max_dim / longer_dim
    new_height = int(original_height * scale_factor)
    new_width = int(original_width * scale_factor)

    return new_height, new_width, scale_factor


def scale_keypoints_back(keypoints: np.ndarray | None, scale_factor: float) -> np.ndarray | None:
    """Scale keypoints back to original resolution."""
    if keypoints is None or len(keypoints) == 0 or scale_factor == 1.0:
        return keypoints

    scaled = keypoints.copy()
    scaled[:, 0] = keypoints[:, 0] / scale_factor  # x coordinates
    scaled[:, 1] = keypoints[:, 1] / scale_factor  # y coordinates
    return scaled


def scale_pose_results_back(
    candidate: np.ndarray | None, subset: np.ndarray | None, scale_factor: float
) -> tuple[np.ndarray | None, np.ndarray | None]:
    """Scale body pose results back to original resolution."""
    if scale_factor == 1.0:
        return candidate, subset

    if candidate is not None and len(candidate) > 0:
        scaled_candidate = candidate.copy()
        scaled_candidate[:, 0] = candidate[:, 0] / scale_factor  # x coordinates
        scaled_candidate[:, 1] = candidate[:, 1] / scale_factor  # y coordinates
        return scaled_candidate, subset

    return candidate, subset


def process_frame(  # noqa: PLR0913
    frame: Any,
    body_estimation: Any,
    hand_estimation: Any,
    model_type: str,
    max_dim: int | None = None,
    *,
    black_background: bool = False,
) -> Any:
    """Process a single frame and return annotated result."""
    # Calculate processing dimensions
    proc_height, proc_width, scale_factor = calculate_processing_size(frame.shape[0], frame.shape[1], max_dim)

    # Resize frame for processing if needed
    if scale_factor != 1.0:
        processing_frame = cv2.resize(frame, (proc_width, proc_height), interpolation=cv2.INTER_LINEAR)
    else:
        processing_frame = frame

    # Create canvas - either original frame or black background
    if black_background:
        canvas = np.zeros_like(frame)  # Black background with same dimensions
    else:
        canvas = copy.deepcopy(frame)  # Original frame

    if model_type == "hand":
        # Hand-only detection
        peaks = hand_estimation(processing_frame)
        # Scale keypoints back to original resolution
        scaled_peaks = scale_keypoints_back(peaks, scale_factor)
        canvas = util.draw_handpose(canvas, [scaled_peaks])
    else:
        # Body pose detection only
        candidate, subset = body_estimation(processing_frame)
        # Scale results back to original resolution
        scaled_candidate, scaled_subset = scale_pose_results_back(candidate, subset, scale_factor)
        if scaled_candidate is not None and scaled_subset is not None:
            canvas = util.draw_bodypose(canvas, scaled_candidate, scaled_subset, model_type)

    return canvas


class OpenPoseVideoDetection(ControlNode):
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._huggingface_repo_parameter = HuggingFaceRepoFileParameter(
            self,
            repo_files=[
                ("dylanholmes/openpose-safetensors", "body25.safetensors"),
                ("dylanholmes/openpose-safetensors", "coco.safetensors"),
            ],
        )
        self.log_params = LogParameter(self)

        self._huggingface_repo_parameter.add_input_parameters()
        self.add_parameter(
            Parameter(
                name="input_video",
                input_types=["VideoUrlArtifact"],
                type="VideoUrlArtifact",
                tooltip="Input video for pose detection",
            )
        )
        self.add_parameter(
            Parameter(
                name="max_dim",
                input_types=["int"],
                type="int",
                tooltip="Maximum dimension for processing (preserves aspect ratio)",
                default_value=256,
            )
        )
        self.add_parameter(
            Parameter(
                name="max_frames",
                input_types=["int"],
                type="int",
                tooltip="Maximum number of frames to process (default: all frames)",
                default_value=None,
            )
        )
        self.add_parameter(
            Parameter(
                name="black_background",
                input_types=["bool"],
                type="bool",
                tooltip="Draw poses on black background instead of original video",
                default_value=False,
            )
        )
        self.add_parameter(
            Parameter(
                name="no_audio",
                input_types=["bool"],
                type="bool",
                tooltip="Remove audio from output video",
                default_value=False,
            )
        )
        self.add_parameter(
            Parameter(
                name="output_video",
                output_type="VideoUrlArtifact",
                tooltip="Video with pose detection results",
                allowed_modes={ParameterMode.OUTPUT},
            )
        )
        self.log_params.add_output_parameters()

        # Internal state
        self._model = None
        self._model_type = None
        self._repo_id = None
        self._revision = None
        self._model_file = None

    def validate_before_node_run(self) -> list[Exception] | None:
        errors = self._huggingface_repo_parameter.validate_before_node_run()

        if not self.get_parameter_value("input_video"):
            if errors is None:
                errors = []
            errors.append(Exception("No input video provided"))

        return errors or None

    def get_input_video_path(self) -> Path:
        input_video_artifact = self.get_parameter_value("input_video")
        if input_video_artifact is None:
            logger.exception("No input video specified")
            msg = "No input video specified"
            raise ValueError(msg)

        if isinstance(input_video_artifact, dict):
            input_video_artifact = dict_to_video_url_artifact(input_video_artifact)

        # Download video from URL to temporary file
        response = requests.get(input_video_artifact.value, timeout=30)
        # Use mkstemp for safe temporary file creation
        fd, temp_path = tempfile.mkstemp(suffix=".mp4")
        os.close(fd)  # Close the file descriptor immediately
        try:
            with Path(temp_path).open("wb") as f:
                f.write(response.content)
        except Exception:
            # Clean up on failure
            Path(temp_path).unlink(missing_ok=True)
            raise
        return Path(temp_path)

    def publish_preview_placeholder_video(self) -> None:
        # For now, just set None - could create a placeholder video later
        pass

    def publish_output_video(self, video_path: Path) -> None:
        filename = f"{uuid.uuid4()}{video_path.suffix}"
        url = GriptapeNodes.StaticFilesManager().save_static_file(video_path.read_bytes(), filename)
        self.parameter_output_values["output_video"] = VideoUrlArtifact(url)

    def get_openpose_model(self) -> tuple[Body | Hand, str]:
        repo_id, revision = self._huggingface_repo_parameter.get_repo_revision()
        model_file = self._huggingface_repo_parameter.get_repo_filename()

        # Download the model file from HuggingFace
        model_path = huggingface_hub.hf_hub_download(
            repo_id=repo_id,
            revision=revision,
            filename=model_file,
            local_files_only=True,
        )

        # Extract model type from filename
        if "body25" in model_file:
            model_type = "body25"
        elif "coco" in model_file:
            model_type = "coco"
        elif "face" in model_file:
            model_type = "face"
        elif "hand" in model_file:
            model_type = "hand"
        else:
            model_type = "body25"  # Default fallback

        # Load model using safetensors
        state_dict = load_file(model_path)

        if model_type == "hand":
            self._model = Hand(state_dict)
        else:
            self._model = Body(state_dict, model_type)

        self._model_type = model_type
        self._repo_id = repo_id
        self._revision = revision
        self._model_file = model_file

        return self._model, model_type

    def process(self) -> AsyncResult | None:
        yield lambda: self._process()

    def _process(self) -> AsyncResult | None:  # noqa: C901, PLR0912, PLR0915
        self.log_params.clear_logs()
        self.log_params.append_to_logs("Starting OpenPose video detection...\n")

        input_video_path = self.get_input_video_path()
        max_dim = self.get_parameter_value("max_dim")
        max_frames = self.get_parameter_value("max_frames")
        black_background = self.get_parameter_value("black_background") or False
        no_audio = self.get_parameter_value("no_audio") or False

        # Immediately set a preview placeholder
        self.publish_preview_placeholder_video()

        # Get OpenPose model
        with self.log_params.append_profile_to_logs("Loading OpenPose model"):
            openpose_model, model_type = self.get_openpose_model()
            self.log_params.append_to_logs(f"Loaded {model_type} model\n")

        # Ensure cleanup of input video temp file
        try:
            # Determine which estimation objects to use
            if model_type == "hand":
                hand_estimation = openpose_model
                body_estimation = None
            else:
                body_estimation = openpose_model
                hand_estimation = None

            # Open video
            cap = cv2.VideoCapture(str(input_video_path))
            if not cap.isOpened():
                msg = f"Could not open video '{input_video_path}'"
                raise ValueError(msg)

            # Get video properties
            fps = int(cap.get(cv2.CAP_PROP_FPS))
            width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

            # Calculate codec-compatible dimensions (multiple of 16)
            compatible_width = ((width + 15) // 16) * 16
            compatible_height = ((height + 15) // 16) * 16

            # Apply frame limit if specified
            if max_frames:
                frames_to_process = min(max_frames, total_frames)
            else:
                frames_to_process = total_frames

            self.log_params.append_to_logs(f"Video properties: {width}x{height}, {fps} FPS\n")
            self.log_params.append_to_logs(f"Processing {frames_to_process}/{total_frames} frames\n")
            if max_dim:
                self.log_params.append_to_logs(f"Max processing dimension: {max_dim}\n")

            # Collect processed frames
            processed_frames = []
            frame_count = 0

            try:
                with self.log_params.append_profile_to_logs("Processing video frames"):
                    while frame_count < frames_to_process:
                        ret, frame = cap.read()
                        if not ret:
                            break

                        # Process frame
                        processed_frame = process_frame(
                            frame,
                            body_estimation,
                            hand_estimation,
                            model_type,
                            max_dim,
                            black_background=black_background,
                        )

                        # Resize to codec-compatible dimensions if needed
                        if compatible_width != width or compatible_height != height:
                            processed_frame = cv2.resize(
                                processed_frame, (compatible_width, compatible_height), interpolation=cv2.INTER_LINEAR
                            )

                        # Convert BGR to RGB for imageio (OpenCV uses BGR, imageio expects RGB)
                        processed_frame_rgb = cv2.cvtColor(processed_frame, cv2.COLOR_BGR2RGB)
                        processed_frames.append(processed_frame_rgb)

                        frame_count += 1

                        # Log progress every 10% of frames
                        if frame_count % max(1, frames_to_process // 10) == 0:
                            progress = (frame_count / frames_to_process) * 100
                            self.log_params.append_to_logs(
                                f"Progress: {frame_count}/{frames_to_process} frames ({progress:.1f}%)\n"
                            )

            except Exception as e:
                logger.error("Error processing video: %s", e)
                raise
            finally:
                cap.release()

            # Create output file path using safe temporary file creation
            fd, output_path_str = tempfile.mkstemp(suffix=".mp4")
            output_path = Path(output_path_str)
            # Close the file descriptor since we'll write to it later
            os.close(fd)

            # Write video using imageio
            output_path_created = None
            try:
                output_path_created = output_path
                with self.log_params.append_profile_to_logs("Writing output video"):
                    if no_audio:
                        # Simple video without audio
                        self.log_params.append_to_logs("Writing video without audio...\n")
                        imageio.mimsave(str(output_path), processed_frames, fps=fps)
                        self.log_params.append_to_logs("Video saved without audio\n")
                    else:
                        # Write video and preserve audio using ffmpeg with explicit stream mapping
                        self.log_params.append_to_logs("Writing video with audio preservation...\n")
                        temp_video_path = output_path.with_suffix(".temp.mp4")
                        imageio.mimsave(str(temp_video_path), processed_frames, fps=fps)

                        # Use ffmpeg with explicit stream mapping
                        try:
                            # Get ffmpeg executable path from static-ffmpeg dependency
                            ffmpeg_path, _ = run.get_or_fetch_platform_executables_else_raise()

                            subprocess.run(  # noqa: S603
                                [
                                    ffmpeg_path,
                                    "-y",
                                    "-loglevel",
                                    "error",
                                    "-i",
                                    str(temp_video_path),  # Input 0: processed video (no audio)
                                    "-i",
                                    str(input_video_path),  # Input 1: original video (with audio)
                                    "-map",
                                    "0:v:0",  # Take video from input 0
                                    "-map",
                                    "1:a:0",  # Take audio from input 1
                                    "-c:v",
                                    "copy",  # Copy video stream as-is
                                    "-c:a",
                                    "copy",  # Copy audio stream as-is
                                    "-shortest",  # End when shortest stream ends
                                    str(output_path),
                                ],
                                check=True,
                                capture_output=True,
                                text=True,
                            )

                            # Clean up temp file
                            temp_video_path.unlink()
                            self.log_params.append_to_logs("Video saved with original audio\n")

                        except subprocess.CalledProcessError:
                            # ffmpeg failed, keep video without audio
                            if temp_video_path.exists():
                                temp_video_path.rename(output_path)
                            self.log_params.append_to_logs(
                                "Video saved without audio (ffmpeg failed - original may not have audio)\n"
                            )

                        except FileNotFoundError:
                            # Fallback to video without audio when ffmpeg is unavailable
                            if temp_video_path.exists():
                                temp_video_path.rename(output_path)
                            self.log_params.append_to_logs("Video saved without audio (ffmpeg not available)\n")

            except Exception as e:
                logger.error("Error writing video: %s", e)
                # Clean up output file on error
                if output_path_created and output_path_created.exists():
                    output_path_created.unlink(missing_ok=True)
                raise

            self.log_params.append_to_logs("Video processing completed successfully!\n")
            self.publish_output_video(output_path)

        finally:
            # Clean up input video temp file
            if input_video_path.exists():
                input_video_path.unlink(missing_ok=True)
