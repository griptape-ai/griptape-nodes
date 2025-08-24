import base64
import re
import uuid
from typing import Any
from urllib.parse import urlparse

from griptape_nodes_library.video.video_url_artifact import VideoUrlArtifact

RATE_TOLERANCE = 0.1
NOMINAL_30FPS = 30
NOMINAL_60FPS = 60
DROP_FRAMES_30FPS = 2
DROP_FRAMES_60FPS = 4
ACTUAL_RATE_30FPS = 30000 / 1001
ACTUAL_RATE_60FPS = 60000 / 1001


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


def to_video_artifact(video: Any | dict) -> Any:
    """Convert a video or a dictionary to a VideoArtifact."""
    if isinstance(video, dict):
        return dict_to_video_url_artifact(video)
    return video


def validate_url(url: str) -> bool:
    """Validate that the URL is safe for ffmpeg processing."""
    try:
        parsed = urlparse(url)
        return bool(parsed.scheme in ("http", "https", "file") and parsed.netloc)
    except Exception:
        return False


def smpte_to_seconds(tc: str, rate: float, *, drop_frame: bool | None = None) -> float:
    """Convert SMPTE timecode to seconds."""
    if not re.match(r"^\d{2}:\d{2}:\d{2}[:;]\d{2}$", tc):
        error_msg = f"Bad SMPTE format: {tc!r}"
        raise ValueError(error_msg)
    sep = ";" if ";" in tc else ":"
    hh, mm, ss, ff = map(int, re.split(r"[:;]", tc))
    is_df = (sep == ";") if drop_frame is None else bool(drop_frame)

    # Non-drop: straightforward
    if not is_df:
        return (hh * 3600) + (mm * 60) + ss + (ff / rate)

    # Drop-frame: only valid for 29.97 and 59.94
    nominal = (
        NOMINAL_30FPS
        if abs(rate - 29.97) < RATE_TOLERANCE
        else NOMINAL_60FPS
        if abs(rate - 59.94) < RATE_TOLERANCE
        else None
    )
    if nominal is None:
        # Fallback (treat as non-drop rather than guessing)
        return (hh * 3600) + (mm * 60) + ss + (ff / rate)

    drop_per_min = DROP_FRAMES_30FPS if nominal == NOMINAL_30FPS else DROP_FRAMES_60FPS
    total_minutes = hh * 60 + mm
    # Drop every minute except every 10th minute
    dropped = drop_per_min * (total_minutes - total_minutes // 10)
    frame_number = (hh * 3600 + mm * 60 + ss) * nominal + ff - dropped
    actual_rate = ACTUAL_RATE_30FPS if nominal == NOMINAL_30FPS else ACTUAL_RATE_60FPS
    return frame_number / actual_rate


def seconds_to_ts(sec: float) -> str:
    """Return HH:MM:SS.mmm for ffmpeg."""
    sec = max(sec, 0)
    whole = int(sec)
    ms = round((sec - whole) * 1000)
    h = whole // 3600
    m = (whole % 3600) // 60
    s = whole % 60
    return f"{h:02d}:{m:02d}:{s:02d}.{ms:03d}"


def sanitize_filename(name: str) -> str:
    """Sanitize filename by removing invalid characters and replacing spaces with underscores."""
    name = re.sub(r"[^\w\s\-.]+", "_", name.strip())
    name = re.sub(r"\s+", "_", name)
    return name or "segment"
