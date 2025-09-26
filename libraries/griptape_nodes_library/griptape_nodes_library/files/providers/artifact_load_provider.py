from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from griptape_nodes.exe_types.core_types import Parameter


class ArtifactLoadProvider(ABC):
    """Abstract base class for artifact load providers.

    Each provider handles loading and processing of a specific artifact type
    (image, video, audio, text) with their own additional parameters and
    validation logic.
    """

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Human-readable name of this provider (e.g., 'Image', 'Video')."""

    @property
    @abstractmethod
    def artifact_type(self) -> str:
        """The artifact type this provider produces (e.g., 'ImageUrlArtifact')."""

    @property
    @abstractmethod
    def supported_extensions(self) -> set[str]:
        """Set of file extensions this provider supports (e.g., {'.png', '.jpg'})."""

    @property
    @abstractmethod
    def url_content_type_prefix(self) -> str:
        """Content-type prefix for URL validation (e.g., 'image/', 'video/')."""

    @property
    @abstractmethod
    def default_extension(self) -> str:
        """Default extension to use when generating filenames (e.g., 'png')."""

    @abstractmethod
    def can_handle_file(self, file_path: Path) -> bool:
        """Check if this provider can handle the given file path.

        Args:
            file_path: Path to the file to check

        Returns:
            True if this provider can handle the file, False otherwise
        """

    @abstractmethod
    def can_handle_url(self, url: str) -> bool:
        """Check if this provider can handle content from the given URL.

        Args:
            url: URL to check

        Returns:
            True if this provider can handle the URL content, False otherwise
        """

    @abstractmethod
    def get_additional_parameters(self) -> list[Parameter]:
        """Get provider-specific parameters to add to the node.

        Returns:
            List of additional parameters this provider needs
        """

    @abstractmethod
    def create_artifact_from_dict(self, artifact_dict: dict[str, Any]) -> Any:
        """Convert a dictionary to the appropriate artifact type.

        Args:
            artifact_dict: Dictionary containing artifact data

        Returns:
            Artifact object of the appropriate type
        """

    @abstractmethod
    def create_artifact_from_url(self, url: str) -> Any:
        """Create an artifact from a URL.

        Args:
            url: URL to create artifact from

        Returns:
            Artifact object of the appropriate type
        """

    @abstractmethod
    def validate_artifact_loadable(self, artifact: Any) -> None:
        """Validate that the artifact can actually be loaded/processed.

        Args:
            artifact: The artifact to validate

        Raises:
            RuntimeError: If the artifact cannot be loaded
        """

    @abstractmethod
    def extract_url_from_artifact(self, artifact_value: Any) -> str | None:
        """Extract URL from an artifact parameter value.

        Args:
            artifact_value: The artifact value (dict, artifact object, or string)

        Returns:
            The extracted URL or None if no value is present
        """

    @abstractmethod
    def process_additional_parameters(self, node: Any, artifact: Any) -> None:
        """Process provider-specific parameters after artifact is loaded.

        This is called after the main artifact is loaded and allows providers
        to update their additional parameters (e.g., extract mask for images).

        Args:
            node: The LoadFile node instance
            artifact: The loaded artifact
        """

    def get_priority_score(self, _file_path: Path) -> int:
        """Get priority score for handling this file (higher = more preferred).

        Used for disambiguation when multiple providers can handle the same file.
        Default implementation returns 0 (neutral priority).

        Args:
            _file_path: Path to the file (unused in base implementation)

        Returns:
            Priority score (higher numbers indicate higher priority)
        """
        return 0
