import base64
import re
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx
from griptape.artifacts.video_url_artifact import VideoUrlArtifact

DEFAULT_DOWNLOAD_TIMEOUT = 30.0
DOWNLOAD_CHUNK_SIZE = 8192

RATE_TOLERANCE = 0.1
NOMINAL_30FPS = 30
NOMINAL_60FPS = 60

# Drop-frame constants for NTSC timecode
# NTSC uses 29.97 fps (not exactly 30) due to color subcarrier requirements
# To keep timecode in sync with real time, drop-frame timecode drops 2 frames per minute
# (except every 10th minute) for 29.97 fps, and 4 frames per minute for 59.94 fps
# This ensures timecode matches wall clock time over long durations
DROP_FRAMES_30FPS = 2  # Frames dropped per minute for 29.97 fps NTSC
DROP_FRAMES_60FPS = 4  # Frames dropped per minute for 59.94 fps NTSC

# Actual NTSC frame rates (precise values)
ACTUAL_RATE_30FPS = 30000 / 1001  # ≈ 29.97 fps (NTSC)
ACTUAL_RATE_60FPS = 60000 / 1001  # ≈ 59.94 fps (NTSC)


def detect_video_format(video: Any | dict) -> str | None:
    """Detect the video format from the video data.

    Args:
        video: Video data as dict, artifact, or other format

    Returns:
        The detected format (e.g., 'mp4', 'avi', 'mov') or None if not detected.
    """
    # Handle DownloadedVideoArtifact from SaveVideo
    if hasattr(video, "detected_format") and hasattr(video, "value") and isinstance(video.value, bytes):  # type: ignore[attr-defined]
        return video.detected_format  # type: ignore[attr-defined]

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
    from griptape.artifacts import VideoUrlArtifact

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


def to_video_artifact(video: Any | dict) -> Any:
    """Convert a video or a dictionary to a VideoArtifact."""
    if isinstance(video, dict):
        return dict_to_video_url_artifact(video)
    return video


def is_video_url_artifact(obj: Any) -> bool:
    """Check if object is any kind of VideoUrlArtifact (regardless of library).

    This handles VideoUrlArtifacts from:
    - griptape_nodes_library.video.video_url_artifact
    - griptape_nodes.node_libraries.runwayml_library.image_to_video
    - Any other library that follows the VideoUrlArtifact pattern

    Args:
        obj: Object to check

    Returns:
        True if object appears to be a VideoUrlArtifact
    """
    if not obj:
        return False

    # Must have both 'value' attribute and class name containing 'VideoUrlArtifact'
    return hasattr(obj, "value") and hasattr(obj, "__class__") and "VideoUrlArtifact" in obj.__class__.__name__


def is_downloadable_video_url(obj: Any) -> bool:
    """Check if object contains a URL that needs downloading.

    Args:
        obj: Object to check (string, VideoUrlArtifact, etc.)

    Returns:
        True if object contains an http/https URL that needs downloading
    """
    # Direct URL string
    if isinstance(obj, str) and obj.startswith(("http://", "https://")):
        return True

    # Any VideoUrlArtifact-like object with downloadable URL
    if is_video_url_artifact(obj) and hasattr(obj, "value"):
        value = obj.value  # type: ignore[attr-defined]
        if isinstance(value, str):
            return value.startswith(("http://", "https://"))

    return False


def extract_url_from_video_object(obj: Any) -> str | None:
    """Extract URL from video object if it contains one.

    Args:
        obj: Video object (string, VideoUrlArtifact, etc.)

    Returns:
        URL string if found, None otherwise
    """
    if isinstance(obj, str):
        return obj

    if is_video_url_artifact(obj) and hasattr(obj, "value"):
        value = obj.value  # type: ignore[attr-defined]
        if isinstance(value, str):
            return value

    return None


def validate_url(url: str) -> bool:
    """Validate that the URL is safe for ffmpeg processing."""
    try:
        parsed = urlparse(url)
        return bool(parsed.scheme in ("http", "https", "file") and parsed.netloc)
    except Exception:
        return False


def smpte_to_seconds(tc: str, rate: float, *, drop_frame: bool | None = None) -> float:
    """Convert SMPTE timecode to seconds.

    Drop-frame timecode is used for NTSC video (29.97/59.94 fps) to keep timecode
    synchronized with real time. It drops frames at specific intervals to compensate
    for the slight difference between nominal and actual frame rates.

    Examples:
    - Non-drop: "01:23:45:12" (standard timecode)
    - Drop-frame: "01:23:45;12" (NTSC drop-frame timecode)
    """
    if not re.match(r"^\d{2}:\d{2}:\d{2}[:;]\d{2}$", tc):
        error_msg = f"Bad SMPTE format: {tc!r}"
        raise ValueError(error_msg)
    sep = ";" if ";" in tc else ":"
    hh, mm, ss, ff = map(int, re.split(r"[:;]", tc))
    is_df = (sep == ";") if drop_frame is None else bool(drop_frame)

    # Non-drop: straightforward calculation
    if not is_df:
        return (hh * 3600) + (mm * 60) + ss + (ff / rate)

    # Drop-frame: only valid for NTSC rates (29.97 and 59.94 fps)
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


@dataclass
class VideoDownloadResult:
    """Result of video download operation."""

    temp_file_path: Path
    detected_format: str | None = None


async def download_video_to_temp_file(url: str) -> VideoDownloadResult:
    """Download video from URL to temporary file using async httpx streaming.

    Args:
        url: The video URL to download

    Returns:
        VideoDownloadResult with path to temp file and detected format

    Raises:
        ValueError: If URL is invalid or download fails
    """
    # Validate URL first using existing function
    if not validate_url(url):
        error_details = f"Invalid or unsafe URL: {url}"
        raise ValueError(error_details)

    # Create temp file with generic extension initially
    with tempfile.NamedTemporaryFile(suffix=".video", delete=False) as temp_file:
        temp_path = Path(temp_file.name)

    try:
        async with httpx.AsyncClient(timeout=DEFAULT_DOWNLOAD_TIMEOUT) as client, client.stream("GET", url) as response:
            response.raise_for_status()

            # Use sync file operations for writing chunks - this is appropriate for streaming
            with temp_path.open("wb") as f:  # noqa: ASYNC230
                async for chunk in response.aiter_bytes(chunk_size=DOWNLOAD_CHUNK_SIZE):
                    f.write(chunk)

        # Detect format from URL or use default
        detected_format = detect_video_format({"value": url})

        return VideoDownloadResult(temp_file_path=temp_path, detected_format=detected_format)

    except Exception as e:
        # Cleanup on failure
        if temp_path.exists():
            temp_path.unlink()
        error_details = f"Failed to download video from {url}: {e}"
        raise ValueError(error_details) from e
