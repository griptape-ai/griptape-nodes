import base64
import uuid

from griptape_nodes_library.three_d.three_d_artifact import ThreeDUrlArtifact


def dict_to_three_d_url_artifact(three_d_dict: dict, three_d_format: str | None = None) -> ThreeDUrlArtifact:
    """Convert a dictionary representation of a 3D file to a ThreeDArtifact."""
    from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

    # Get the base64 encoded string
    value = three_d_dict["value"]
    if three_d_dict["type"] == "ThreeDUrlArtifact":
        return ThreeDUrlArtifact(value)

    # If the base64 string has a prefix like "data:model/gltf-binary;base64,", remove it
    if "base64," in value:
        value = value.split("base64,")[1]

    # Decode the base64 string to bytes
    three_d_bytes = base64.b64decode(value)

    # Determine the format from the MIME type if not specified
    if three_d_format is None:
        if "type" in three_d_dict:
            # Extract format from MIME type (e.g., 'model/gltf-binary' -> 'glb')
            mime_format = three_d_dict["type"].split("/")[1] if "/" in three_d_dict["type"] else None
            three_d_format = mime_format
        else:
            three_d_format = "glb"

    url = GriptapeNodes.StaticFilesManager().save_static_file(three_d_bytes, f"{uuid.uuid4()}.{three_d_format}")

    return ThreeDUrlArtifact(url)
