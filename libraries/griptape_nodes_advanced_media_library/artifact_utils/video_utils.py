import base64
import tempfile
import uuid
from pathlib import Path
from typing import Any

from griptape.artifacts.video_url_artifact import VideoUrlArtifact

# Constants for magic numbers
RGB_CHANNELS = 3
DIMENSIONS_3D = 3
VIDEO_DIMENSIONS_4D = 4


def detect_video_format(video: Any | dict) -> str | None:
    """Detect the video format from the video data.

    Args:
        video: Video data as dict, artifact, or other format

    Returns:
        The detected format (e.g., 'mp4', 'avi', 'mov') or None if not detected.
    """
    if isinstance(video, dict):
        # Check for MIME type in dictionary
        if "type" in video and "/" in video["type"]:
            # e.g. "video/mp4" -> "mp4"
            return video["type"].split("/")[1]
    elif hasattr(video, "meta") and video.meta:
        # Check for format information in artifact metadata
        if "format" in video.meta:
            return video.meta["format"]
        if "content_type" in video.meta and "/" in video.meta["content_type"]:
            return video.meta["content_type"].split("/")[1]
    elif hasattr(video, "value") and isinstance(video.value, str):
        # For URL artifacts, try to extract extension from URL
        url = video.value
        if "." in url:
            # Extract extension from URL (e.g., "video.mp4" -> "mp4")
            extension = url.split(".")[-1].split("?")[0]  # Remove query params
            # Common video extensions
            if extension.lower() in ["mp4", "avi", "mov", "mkv", "flv", "wmv", "webm", "m4v"]:
                return extension.lower()

    return None


def dict_to_video_url_artifact(video_dict: dict, video_format: str | None = None) -> VideoUrlArtifact:
    """Convert a dictionary representation of video to a VideoUrlArtifact."""
    from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

    value = video_dict["value"]

    # If it already is a VideoUrlArtifact, just wrap and return
    if video_dict.get("type") == "VideoUrlArtifact":
        return VideoUrlArtifact(value)

    # Remove any data URL prefix
    if "base64," in value:
        value = value.split("base64,")[1]

    # Decode the base64 payload
    video_bytes = base64.b64decode(value)

    # Infer format/extension if not explicitly provided
    if video_format is None:
        if "type" in video_dict and "/" in video_dict["type"]:
            # e.g. "video/mp4" -> "mp4"
            video_format = video_dict["type"].split("/")[1]
        else:
            video_format = "mp4"

    # Save to static file server
    filename = f"{uuid.uuid4()}.{video_format}"
    url = GriptapeNodes.StaticFilesManager().save_static_file(video_bytes, filename)

    return VideoUrlArtifact(url)


def frames_to_video_artifact(frames: list[Any], fps: int = 30, video_format: str = "mp4") -> VideoUrlArtifact:  # noqa: PLR0912
    """Convert a list of frames (PIL Images or numpy arrays) to a VideoUrlArtifact.

    Args:
        frames: List of frame images (PIL.Image objects or numpy arrays)
        fps: Frames per second for the output video
        video_format: Output video format (default: mp4)

    Returns:
        VideoUrlArtifact containing the generated video
    """
    import cv2  # type: ignore[reportMissingImports]
    import numpy as np
    from PIL import Image

    from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

    if not frames:
        msg = "frames list cannot be empty"
        raise ValueError(msg)

    # Create temporary file for video
    with tempfile.NamedTemporaryFile(suffix=f".{video_format}", delete=False) as temp_file:
        temp_video_path = temp_file.name

    try:
        # Convert first frame to get dimensions
        first_frame = frames[0]
        if isinstance(first_frame, Image.Image):
            first_frame_np = np.array(first_frame)
        elif isinstance(first_frame, np.ndarray):
            first_frame_np = first_frame
        else:
            msg = f"Unsupported frame type: {type(first_frame)}"
            raise TypeError(msg)

        # Ensure RGB format (OpenCV uses BGR)
        if len(first_frame_np.shape) == DIMENSIONS_3D and first_frame_np.shape[2] == RGB_CHANNELS:
            height, width, _ = first_frame_np.shape
        else:
            msg = "Frames must be RGB images"
            raise ValueError(msg)

        # Define codec and create VideoWriter
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        out = cv2.VideoWriter(temp_video_path, fourcc, fps, (width, height))

        # Process each frame
        for frame in frames:
            if isinstance(frame, Image.Image):
                frame_np = np.array(frame)
            elif isinstance(frame, np.ndarray):
                frame_np = frame
            else:
                msg = f"Unsupported frame type: {type(frame)}"
                raise TypeError(msg)

            # Convert RGB to BGR for OpenCV
            if len(frame_np.shape) == DIMENSIONS_3D and frame_np.shape[2] == RGB_CHANNELS:
                frame_bgr = cv2.cvtColor(frame_np, cv2.COLOR_RGB2BGR)
            else:
                msg = "All frames must be RGB images"
                raise ValueError(msg)

            out.write(frame_bgr)

        # Release the video writer
        out.release()

        # Read the video file and save to static files
        video_bytes = Path(temp_video_path).read_bytes()

        filename = f"{uuid.uuid4()}.{video_format}"
        url = GriptapeNodes.StaticFilesManager().save_static_file(video_bytes, filename)

        return VideoUrlArtifact(url)

    finally:
        # Clean up temporary file
        temp_path = Path(temp_video_path)
        if temp_path.exists():
            temp_path.unlink()


def numpy_video_to_video_artifact(video_np: Any, fps: int = 30, video_format: str = "mp4") -> VideoUrlArtifact:
    """Convert a numpy video array to a VideoUrlArtifact.

    Args:
        video_np: Numpy array with shape (frames, height, width, channels)
        fps: Frames per second for the output video
        video_format: Output video format (default: mp4)

    Returns:
        VideoUrlArtifact containing the generated video
    """
    import numpy as np

    if not isinstance(video_np, np.ndarray):
        msg = "video_np must be a numpy array"
        raise TypeError(msg)

    if len(video_np.shape) != VIDEO_DIMENSIONS_4D:
        msg = "video_np must have shape (frames, height, width, channels)"
        raise ValueError(msg)

    # Convert numpy array to list of frames
    frames = [video_np[i] for i in range(video_np.shape[0])]

    return frames_to_video_artifact(frames, fps=fps, video_format=video_format)
