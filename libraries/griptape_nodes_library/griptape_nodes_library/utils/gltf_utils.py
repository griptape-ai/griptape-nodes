import base64
import uuid

from griptape_nodes_library.three_d.gltf_artifact import GLTFUrlArtifact


def dict_to_gltf_url_artifact(gltf_dict: dict, gltf_format: str | None = None) -> GLTFUrlArtifact:
    """Convert a dictionary representation of a GLTF file to a GLTFArtifact."""
    from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

    # Get the base64 encoded string
    value = gltf_dict["value"]
    if gltf_dict["type"] == "GLTFUrlArtifact":
        return GLTFUrlArtifact(value)

    # If the base64 string has a prefix like "data:model/gltf-binary;base64,", remove it
    if "base64," in value:
        value = value.split("base64,")[1]

    # Decode the base64 string to bytes
    gltf_bytes = base64.b64decode(value)

    # Determine the format from the MIME type if not specified
    if gltf_format is None:
        if "type" in gltf_dict:
            # Extract format from MIME type (e.g., 'model/gltf-binary' -> 'glb')
            mime_format = gltf_dict["type"].split("/")[1] if "/" in gltf_dict["type"] else None
            gltf_format = mime_format
        else:
            gltf_format = "glb"

    url = GriptapeNodes.StaticFilesManager().save_static_file(gltf_bytes, f"{uuid.uuid4()}.{gltf_format}")

    return GLTFUrlArtifact(url)
