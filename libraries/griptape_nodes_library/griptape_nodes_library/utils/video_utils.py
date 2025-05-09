import base64
import uuid

from griptape.artifacts import UrlArtifact


class VideoUrlArtifact(UrlArtifact):
    pass


def dict_to_video_url_artifact(video_dict: dict, video_format: str | None = None) -> VideoUrlArtifact:
    """Convert a dictionary representation of an image to an ImageArtifact."""
    from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

    # Get the base64 encoded string
    value = video_dict["value"]
    if video_dict["type"] == "VideoUrlArtifact":
        return VideoUrlArtifact(value)

    # If the base64 string has a prefix like "data:image/png;base64,", remove it
    if "base64," in value:
        value = value.split("base64,")[1]

    # Decode the base64 string to bytes
    video_bytes = base64.b64decode(value)

    # Determine the format from the MIME type if not specified
    if video_format is None:
        if "type" in video_dict:
            # Extract format from MIME type (e.g., 'image/png' -> 'png')
            mime_format = video_dict["type"].split("/")[1] if "/" in video_dict["type"] else None
            video_format = mime_format
        else:
            video_format = "mp4"

    url = GriptapeNodes.StaticFilesManager().save_static_file(video_bytes, f"{uuid.uuid4()}.{video_format}")

    return VideoUrlArtifact(url)
