"""Base abstract class for artifact preview generators."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from griptape_nodes.retained_mode.managers.artifact_providers.base_artifact_provider import (
        ProviderValue,
    )


class BaseArtifactPreviewGenerator(ABC):
    """Abstract base class for preview generators.

    Preview generators perform the actual conversion work.
    They are passed to provider generate_preview methods.

    Metadata is defined as class methods for zero-cost introspection without instantiation.
    """

    def __init__(
        self,
        source_file_location: str,
        preview_format: str,
        destination_preview_file_location: str,
        _params: dict[str, Any],
    ) -> None:
        """Initialize the preview generator.

        Args:
            source_file_location: Path to the source artifact file
            preview_format: Target format for the preview (e.g., "png", "jpg", "webp")
            destination_preview_file_location: Path where the preview should be saved
            _params: Generator-specific parameters (concrete implementations validate internally)
        """
        self.source_file_location = source_file_location
        self.preview_format = preview_format
        self.destination_preview_file_location = destination_preview_file_location

    @classmethod
    @abstractmethod
    def get_friendly_name(cls) -> str:
        """Human-readable name for this generator.

        Returns:
            The friendly name for this generator (e.g., 'Pillow Dimension', 'FFmpeg Thumbnail')
        """
        ...

    @classmethod
    @abstractmethod
    def get_supported_source_formats(cls) -> set[str]:
        """Source formats this generator can process.

        Returns:
            Set of lowercase file extensions WITHOUT leading dots (e.g., {'png', 'jpg'})
        """
        ...

    @classmethod
    @abstractmethod
    def get_supported_preview_formats(cls) -> set[str]:
        """Preview formats this generator produces.

        Returns:
            Set of lowercase preview format extensions WITHOUT leading dots (e.g., {'webp', 'jpg'})
        """
        ...

    @classmethod
    @abstractmethod
    def get_parameters(cls) -> dict[str, ProviderValue]:
        """Get metadata about generator parameters.

        Returns:
            Dict mapping parameter names to their metadata (default value and required flag)

        Example:
            {
                "max_width": ProviderValue(default_value=800, required=False),
                "max_height": ProviderValue(default_value=600, required=False),
            }
        """
        ...

    @classmethod
    def get_config_key_prefix(cls, provider_friendly_name: str) -> str:
        """Get the config key prefix for this generator's parameters.

        Args:
            provider_friendly_name: The friendly name of the provider (e.g., 'Image')

        Returns:
            Config key prefix (e.g., 'artifacts.image.preview_generation.generators.standard_thumbnail_generation')
        """
        friendly_name = cls.get_friendly_name()
        generator_key = friendly_name.lower().replace(" ", "_")
        provider_key = provider_friendly_name.lower().replace(" ", "_")
        return f"artifacts.{provider_key}.preview_generation.generators.{generator_key}"

    @abstractmethod
    async def generate_preview(self) -> None:
        """Execute the preview generation.

        Raises:
            Exception: If preview generation fails
        """
        ...
