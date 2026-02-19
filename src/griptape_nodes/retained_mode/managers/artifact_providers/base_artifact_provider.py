"""Base abstract class for artifact providers."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from griptape_nodes.retained_mode.managers.artifact_providers.base_artifact_preview_generator import (
        BaseArtifactPreviewGenerator,
    )
    from griptape_nodes.retained_mode.managers.artifact_providers.provider_registry import ProviderRegistry


class BaseArtifactProvider(ABC):
    """Abstract base class for artifact type providers.

    Providers define how to handle specific artifact types (images, video, audio)
    including supported formats and preview generation capabilities.

    Metadata is defined as class methods for zero-cost introspection without instantiation.
    Instance attributes may hold heavyweight dependencies (e.g., PIL, ffmpeg) loaded lazily.
    """

    def __init__(self, registry: ProviderRegistry) -> None:
        """Initialize provider with registry reference.

        Args:
            registry: The ProviderRegistry that manages this provider
        """
        self._registry = registry

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

    @classmethod
    @abstractmethod
    def get_default_preview_generator(cls) -> str:
        """Default preview generator for this provider.

        Returns:
            Friendly name of the default preview generator
        """
        ...

    @classmethod
    @abstractmethod
    def get_default_preview_format(cls) -> str:
        """Default preview format for this provider.

        Returns:
            Default format extension WITHOUT leading dot (e.g., 'png', 'webp')
        """
        ...

    @classmethod
    @abstractmethod
    def get_default_preview_generators(cls) -> list[type[BaseArtifactPreviewGenerator]]:
        """Get default preview generator classes for this provider.

        Returns generator classes without requiring provider instantiation.
        This allows schema generation and registration without loading heavyweight dependencies.

        Returns:
            List of default preview generator classes
        """
        ...

    @classmethod
    def get_config_key_prefix(cls) -> str:
        """Get the config key prefix for this provider.

        Returns:
            Config key prefix (e.g., 'artifacts.image.preview_generation')
        """
        friendly_name = cls.get_friendly_name()
        provider_key = friendly_name.lower().replace(" ", "_")
        return f"artifacts.{provider_key}.preview_generation"

    @classmethod
    def get_preview_format_leaf_key(cls) -> str:
        """Get the leaf key for preview format config.

        Returns:
            The leaf key (e.g., 'preview_format')
        """
        return "preview_format"

    @classmethod
    def get_preview_generator_leaf_key(cls) -> str:
        """Get the leaf key for preview generator config.

        Returns:
            The leaf key (e.g., 'preview_generator')
        """
        return "preview_generator"

    @classmethod
    def get_preview_format_config_key(cls) -> str:
        """Get the config key for the user's selected preview format.

        Returns:
            Config key (e.g., 'artifacts.image.preview_generation.preview_format')
        """
        return f"{cls.get_config_key_prefix()}.{cls.get_preview_format_leaf_key()}"

    @classmethod
    def get_preview_generator_config_key(cls) -> str:
        """Get the config key for the user's selected preview generator.

        Returns:
            Config key (e.g., 'artifacts.image.preview_generation.preview_generator')
        """
        return f"{cls.get_config_key_prefix()}.{cls.get_preview_generator_leaf_key()}"

    async def attempt_generate_preview(  # noqa: PLR0913
        self,
        preview_generator_friendly_name: str,
        source_file_location: str,
        preview_format: str,
        destination_preview_directory: str,
        destination_preview_file_name: str,
        params: dict[str, Any],
    ) -> str | dict[str, str]:
        """Attempt to generate a preview using the specified preview generator.

        This method handles the complete preview generation flow:
        1. Verifies the generator is registered
        2. Validates all required parameters are provided
        3. Verifies the preview format is supported
        4. Instantiates and executes the generator

        Args:
            preview_generator_friendly_name: Friendly name of registered generator to use
            source_file_location: Path to the source artifact file
            preview_format: Target preview format
            destination_preview_directory: Directory where the preview should be saved
            destination_preview_file_name: Filename for the preview
            params: Generator-specific parameters

        Returns:
            Preview filename(s) generated by the generator.

        Raises:
            ValueError: If generator not registered, missing required params, or unsupported format
            Exception: If generator instantiation or execution fails
        """
        # FAILURE CASE: Generator not registered
        generator_class = self._registry.get_preview_generator_by_name(self.__class__, preview_generator_friendly_name)
        if generator_class is None:
            msg = f"Preview generator '{preview_generator_friendly_name}' not registered with this provider"
            raise ValueError(msg)

        # Get generator metadata
        supported_formats = generator_class.get_supported_preview_formats()

        # FAILURE CASE: Verify preview format is supported
        if preview_format not in supported_formats:
            msg = (
                f"Preview format '{preview_format}' not supported by generator "
                f"(supported: {', '.join(sorted(supported_formats))})"
            )
            raise ValueError(msg)

        # FAILURE CASE: Instantiate generator
        generator = generator_class(
            source_file_location, preview_format, destination_preview_directory, destination_preview_file_name, params
        )

        # FAILURE CASE: Execute generator and get result
        result = await generator.attempt_generate_preview()

        # FAILURE CASE: Validate result is not empty dict
        if isinstance(result, dict) and len(result) == 0:
            msg = "Generator returned empty dict - must return at least one file"
            raise ValueError(msg)

        return result
