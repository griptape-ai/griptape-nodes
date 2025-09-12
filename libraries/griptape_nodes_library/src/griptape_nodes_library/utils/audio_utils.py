import base64
import uuid

from griptape_nodes_library.audio.audio_url_artifact import AudioUrlArtifact


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
    url = GriptapeNodes.StaticFilesManager().save_static_file(audio_bytes, filename)

    return AudioUrlArtifact(url)
