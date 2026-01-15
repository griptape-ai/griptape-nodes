import os
import tempfile
from pathlib import Path
from urllib.parse import unquote, urlparse

import cv2  # type: ignore[reportMissingImports]
import requests
from griptape.artifacts.video_url_artifact import VideoUrlArtifact
from requests.exceptions import RequestException


def download_video_to_temp_file(video_url_artifact: VideoUrlArtifact) -> Path:
    """Download a video from a VideoUrlArtifact to a temporary file.

    Args:
        video_url_artifact: The VideoUrlArtifact containing the video URL

    Returns:
        Path to the temporary file containing the downloaded video.
        The caller is responsible for cleaning up this file.

    Raises:
        ValueError: If video download fails with descriptive error message
    """
    url = video_url_artifact.value

    # Extract suffix from URL, defaulting to .mp4
    parsed_url = urlparse(url)
    url_path = Path(unquote(parsed_url.path))
    suffix = url_path.suffix or ".mp4"

    fd, temp_path_str = tempfile.mkstemp(suffix=suffix)
    os.close(fd)
    temp_path = Path(temp_path_str)

    try:
        response = requests.get(url, stream=True, timeout=300)
        response.raise_for_status()
        with temp_path.open("wb") as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
    except (RequestException, ConnectionError, TimeoutError) as err:
        temp_path.unlink(missing_ok=True)
        details = f"Failed to download video at '{url}'.\nError: {err}"
        raise ValueError(details) from err
    except Exception:
        temp_path.unlink(missing_ok=True)
        raise

    return temp_path


def get_video_fps(video_path: Path, default_fps: float = 30.0) -> float:
    """Get the FPS (frames per second) of a video file using OpenCV.

    Args:
        video_path: Path to the video file
        default_fps: Default FPS to return if unable to determine from video

    Returns:
        The video's FPS, or default_fps if unable to determine
    """
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        return default_fps

    try:
        fps = cap.get(cv2.CAP_PROP_FPS)
        if fps <= 0:
            return default_fps
        return fps
    finally:
        cap.release()
