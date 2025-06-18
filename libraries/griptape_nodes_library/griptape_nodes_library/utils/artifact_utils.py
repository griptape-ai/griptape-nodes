import hashlib
import logging
from datetime import UTC, datetime
from typing import Any

from griptape.artifacts import BaseArtifact

logger = logging.getLogger(__name__)


def add_common_metadata(artifact: BaseArtifact, content_bytes: bytes | None = None) -> None:
    """Add universal metadata to any artifact.

    Args:
        artifact: The artifact to add metadata to
        content_bytes: Optional bytes content for hash/size calculation
    """
    logger.info("Starting add_common_metadata")
    metadata: dict[str, str | int] = {
        "created_at": datetime.now(UTC).isoformat(),
    }

    if content_bytes is not None:
        metadata.update(
            {
                "content_hash": hashlib.sha256(content_bytes).hexdigest(),
                "size_bytes": len(content_bytes),
            }
        )

    logger.info("Common metadata to add: %s", metadata)
    artifact.meta.update(metadata)
    logger.info("Updated metadata after adding common: %s", artifact.meta)


def set_artifact_properties(artifact: BaseArtifact, properties: dict[str, Any]) -> None:
    """Set type-specific properties for an artifact.

    Args:
        artifact: The artifact to set properties on
        properties: Dictionary of properties to set
    """
    logger.info("Starting set_artifact_properties")
    logger.info("Current metadata: %s", artifact.meta)
    logger.info("Properties to set: %s", properties)

    if "properties" not in artifact.meta:
        artifact.meta["properties"] = {}
        logger.info("Created new properties dict in metadata")

    artifact.meta["properties"].update(properties)
    logger.info("Updated metadata: %s", artifact.meta)


def set_artifact_tags(artifact: BaseArtifact, tags: dict[str, Any]) -> None:
    """Set tags/rich metadata for an artifact.

    Args:
        artifact: The artifact to set tags on
        tags: Dictionary of tags to set
    """
    if "tags" not in artifact.meta:
        artifact.meta["tags"] = {}

    artifact.meta["tags"].update(tags)


def get_artifact_property(artifact: BaseArtifact, key: str, default: Any = None) -> Any:
    """Get a property value from an artifact's metadata.

    Args:
        artifact: The artifact to get property from
        key: The property key to retrieve
        default: Default value if property doesn't exist

    Returns:
        The property value or default
    """
    return artifact.meta.get("properties", {}).get(key, default)


def get_artifact_tag(artifact: BaseArtifact, key: str, default: Any = None) -> Any:
    """Get a tag value from an artifact's metadata.

    Args:
        artifact: The artifact to get tag from
        key: The tag key to retrieve
        default: Default value if tag doesn't exist

    Returns:
        The tag value or default
    """
    return artifact.meta.get("tags", {}).get(key, default)


def has_metadata_type(artifact: BaseArtifact, artifact_type: str) -> bool:
    """Check if an artifact has a specific type in its properties.

    Args:
        artifact: The artifact to check
        artifact_type: The type to check for (e.g., 'image', 'audio', 'video')

    Returns:
        True if the artifact has the specified type
    """
    return get_artifact_property(artifact, "type") == artifact_type


def calculate_content_hash(content_bytes: bytes) -> str:
    """Calculate SHA256 hash of content bytes.

    Args:
        content_bytes: The content to hash

    Returns:
        Hex string of the SHA256 hash
    """
    return hashlib.sha256(content_bytes).hexdigest()


def get_artifact_size(artifact: BaseArtifact) -> int | None:
    """Get the size in bytes of an artifact from its metadata.

    Args:
        artifact: The artifact to get size for

    Returns:
        Size in bytes or None if not available
    """
    return artifact.meta.get("size_bytes")


def get_artifact_created_at(artifact: BaseArtifact) -> str | None:
    """Get the creation timestamp of an artifact from its metadata.

    Args:
        artifact: The artifact to get timestamp for

    Returns:
        ISO format timestamp string or None if not available
    """
    return artifact.meta.get("created_at")
