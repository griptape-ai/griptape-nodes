import base64
import uuid


def dict_to_video_url_artifact(video_dict: dict, video_format: str | None = None) -> None:
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
