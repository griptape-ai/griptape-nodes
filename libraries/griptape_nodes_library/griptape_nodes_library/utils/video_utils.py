import base64
import uuid
from typing import Any

from griptape_nodes_library.video.video_url_artifact import VideoUrlArtifact


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
    from griptape_nodes_library.video.video_url_artifact import VideoUrlArtifact

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
