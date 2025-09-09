from typing import Any

from griptape.artifacts import BaseArtifact
from griptape.artifacts.url_artifact import UrlArtifact


class ThreeDArtifact(BaseArtifact):
    """A ThreeD file artifact."""

    def __init__(self, value: bytes, meta: dict[str, Any] | None = None) -> None:
        super().__init__(value=value, meta=meta or {})

    def to_text(self) -> str:
        """Convert the ThreeD file to text representation."""
        return f"ThreeD file with {len(self.value)} bytes"


class ThreeDUrlArtifact(UrlArtifact):
    """A ThreeD file URL artifact."""

    def __init__(self, value: str, meta: dict[str, Any] | None = None) -> None:
        super().__init__(value=value, meta=meta or {})

    def to_text(self) -> str:
        """Convert the ThreeD URL to text representation."""
        return f"ThreeD file URL: {self.value}"
