from typing import Any

from griptape.artifacts import BaseArtifact
from griptape.artifacts.url_artifact import UrlArtifact


class GLTFArtifact(BaseArtifact):
    """A GLTF file artifact."""

    def __init__(self, value: bytes, meta: dict[str, Any] | None = None) -> None:
        super().__init__(value=value, meta=meta or {})

    def to_text(self) -> str:
        """Convert the GLTF file to text representation."""
        return f"GLTF file with {len(self.value)} bytes"


class GLTFUrlArtifact(UrlArtifact):
    """A GLTF file URL artifact."""

    def __init__(self, value: str, meta: dict[str, Any] | None = None) -> None:
        super().__init__(value=value, meta=meta or {})

    def to_text(self) -> str:
        """Convert the GLTF URL to text representation."""
        return f"GLTF file URL: {self.value}"
