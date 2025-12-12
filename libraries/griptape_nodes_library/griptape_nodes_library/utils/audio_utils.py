import base64
import uuid
from typing import Any

from griptape.artifacts.audio_url_artifact import AudioUrlArtifact

from griptape_nodes.utils import is_url

DEFAULT_DOWNLOAD_TIMEOUT = 30.0
DOWNLOAD_CHUNK_SIZE = 8192

# Supported audio file extensions (with leading dots)
SUPPORTED_AUDIO_EXTENSIONS = {".mp3", ".wav", ".ogg", ".flac", ".m4a", ".aac", ".wma", ".opus", ".webm"}


def detect_audio_format(audio: Any | dict) -> str | None:
    """Detect the audio format from the audio data.

    Args:
        audio: Audio data as dict, artifact, or other format

    Returns:
        The detected format (e.g., 'mp3', 'wav', 'ogg') or None if not detected.
    """
    # Handle DownloadedAudioArtifact from SaveAudio
    if hasattr(audio, "detected_format") and hasattr(audio, "value") and isinstance(audio.value, bytes):  # type: ignore[attr-defined]
        return audio.detected_format  # type: ignore[attr-defined]

    if isinstance(audio, dict):
        # Check for MIME type in dictionary
        if "type" in audio and "/" in audio["type"]:
            # e.g. "audio/mp3" -> "mp3"
            return audio["type"].split("/")[1]
    elif hasattr(audio, "meta") and audio.meta:
        # Check for format information in artifact metadata
        if "format" in audio.meta:
            return audio.meta["format"]
        if "content_type" in audio.meta and "/" in audio.meta["content_type"]:
            return audio.meta["content_type"].split("/")[1]
    elif hasattr(audio, "value") and isinstance(audio.value, str):
        # For URL artifacts, try to extract extension from URL
        url = audio.value
        if "." in url:
            # Extract extension from URL (e.g., "audio.mp3" -> "mp3")
            extension = url.split(".")[-1].split("?")[0]  # Remove query params
            if f".{extension.lower()}" in SUPPORTED_AUDIO_EXTENSIONS:
                return extension.lower()

    return None


def dict_to_audio_url_artifact(audio_dict: dict, audio_format: str | None = None) -> AudioUrlArtifact:
    """Convert a dictionary representation of audio to an AudioUrlArtifact."""
    from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

    value = audio_dict["value"]

    # If it already is an AudioUrlArtifact, just wrap and return
    if audio_dict.get("type") == "AudioUrlArtifact":
        return AudioUrlArtifact(value)

    # Remove any data URL prefix
    if "base64," in value:
        value = value.split("base64,")[1]

    # Decode the base64 payload
    audio_bytes = base64.b64decode(value)

    # Infer format/extension if not explicitly provided
    if audio_format is None:
        if "type" in audio_dict and "/" in audio_dict["type"]:
            # e.g. "audio/mpeg" -> "mpeg"
            audio_format = audio_dict["type"].split("/")[1]
        else:
            audio_format = "mp3"

    # Save to static file server
    filename = f"{uuid.uuid4()}.{audio_format}"
    url = GriptapeNodes.FileManager().write_file(audio_bytes, filename)

    return AudioUrlArtifact(url)


def to_audio_artifact(audio: Any | dict) -> Any:
    """Convert audio or a dictionary to an AudioUrlArtifact."""
    if isinstance(audio, dict):
        return dict_to_audio_url_artifact(audio)
    return audio


def is_audio_url_artifact(obj: Any) -> bool:
    """Check if object is any kind of AudioUrlArtifact (regardless of library).

    This handles AudioUrlArtifacts from various libraries that follow
    the AudioUrlArtifact pattern.

    Args:
        obj: Object to check

    Returns:
        True if object appears to be an AudioUrlArtifact
    """
    if not obj:
        return False

    # Must have both 'value' attribute and class name containing 'AudioUrlArtifact'
    return hasattr(obj, "value") and hasattr(obj, "__class__") and "AudioUrlArtifact" in obj.__class__.__name__


def is_downloadable_audio_url(obj: Any) -> bool:
    """Check if object contains a URL that needs downloading.

    Args:
        obj: Object to check (string, AudioUrlArtifact, etc.)

    Returns:
        True if object contains an http/https/file URI that needs downloading
    """
    # Direct URL string
    if isinstance(obj, str) and is_url(obj):
        return True

    # Any AudioUrlArtifact-like object with downloadable URL
    if is_audio_url_artifact(obj) and hasattr(obj, "value"):
        value = obj.value  # type: ignore[attr-defined]
        if isinstance(value, str):
            return is_url(value)

    return False


def extract_url_from_audio_object(obj: Any) -> str | None:
    """Extract URL from audio object if it contains one.

    Args:
        obj: Audio object (string, AudioUrlArtifact, etc.)

    Returns:
        URL string if found, None otherwise
    """
    if isinstance(obj, str):
        return obj

    if is_audio_url_artifact(obj) and hasattr(obj, "value"):
        value = obj.value  # type: ignore[attr-defined]
        if isinstance(value, str):
            return value

    return None
