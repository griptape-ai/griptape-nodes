"""Base abstract class for artifact providers."""

from abc import ABC, abstractmethod


class BaseArtifactProvider(ABC):
    """Abstract base class for artifact type providers.

    Providers define how to handle specific artifact types (images, video, audio)
    including supported formats and preview generation capabilities.

    Metadata is defined as class methods for zero-cost introspection without instantiation.
    """

    @classmethod
    @abstractmethod
    def get_friendly_name(cls) -> str:
        """Human-readable name for this artifact type.

        Returns:
            The friendly name for this provider (e.g., 'Image', 'Video', 'Audio')
        """
        ...

    @classmethod
    @abstractmethod
    def get_supported_formats(cls) -> set[str]:
        """File extensions this provider handles.

        Returns:
            Set of lowercase file extensions WITHOUT leading dots (e.g., {'png', 'jpg'})
        """
        ...

    @classmethod
    @abstractmethod
    def get_preview_formats(cls) -> set[str]:
        """Preview formats this provider can generate.

        Returns:
            Set of lowercase preview format extensions WITHOUT leading dots (e.g., {'webp', 'jpg'})
        """
        ...
