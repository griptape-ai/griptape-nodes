"""Base abstract class for artifact providers."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any, NamedTuple

if TYPE_CHECKING:
    from griptape_nodes.retained_mode.managers.artifact_providers.base_artifact_preview_generator import (
        BaseArtifactPreviewGenerator,
    )


class ProviderValue(NamedTuple):
    """Metadata for a generator parameter.

    Attributes:
        default_value: Default value if parameter not provided
        required: Whether parameter must be provided
    """

    default_value: Any
    required: bool


class BaseArtifactProvider(ABC):
    """Abstract base class for artifact type providers.

    Providers define how to handle specific artifact types (images, video, audio)
    including supported formats and preview generation capabilities.

    Metadata is defined as class methods for zero-cost introspection without instantiation.
    Instance attributes may hold heavyweight dependencies (e.g., PIL, ffmpeg) loaded lazily.
    """

    def __init__(self) -> None:
        """Initialize provider with empty preview generator registry."""
        self._preview_generator_classes: list[type[BaseArtifactPreviewGenerator]] = []
        self._friendly_name_to_preview_generator_class: dict[str, type[BaseArtifactPreviewGenerator]] = {}

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

    async def generate_preview(
        self,
        preview_generator_friendly_name: str,
        source_file_location: str,
        preview_format: str,
        destination_preview_file_location: str,
        params: dict[str, Any],
    ) -> None:
        """Generate a preview using the specified preview generator.

        This method handles the complete preview generation flow:
        1. Verifies the generator is registered
        2. Validates all required parameters are provided
        3. Verifies the preview format is supported
        4. Instantiates and executes the generator

        Args:
            preview_generator_friendly_name: Friendly name of registered generator to use
            source_file_location: Path to the source artifact file
            preview_format: Target preview format
            destination_preview_file_location: Path where the preview should be saved
            params: Generator-specific parameters

        Raises:
            ValueError: If generator not registered, missing required params, or unsupported format
            Exception: If generator instantiation or execution fails
        """
        # FAILURE CASE: Generator not registered
        generator_class = self._get_preview_generator_by_name(preview_generator_friendly_name)
        if generator_class is None:
            msg = f"Preview generator '{preview_generator_friendly_name}' not registered with this provider"
            raise ValueError(msg)

        # Get generator metadata
        generator_params = generator_class.get_parameters()
        supported_formats = generator_class.get_supported_preview_formats()

        # FAILURE CASE: Validate required parameters are provided
        missing_params = []
        for param_name, param_value in generator_params.items():
            if param_value.required and param_name not in params:
                missing_params.append(param_name)

        if missing_params:
            msg = f"Missing required parameters: {', '.join(missing_params)}"
            raise ValueError(msg)

        # FAILURE CASE: Verify preview format is supported
        if preview_format not in supported_formats:
            msg = (
                f"Preview format '{preview_format}' not supported by generator "
                f"(supported: {', '.join(sorted(supported_formats))})"
            )
            raise ValueError(msg)

        # FAILURE CASE: Instantiate generator
        generator = generator_class(source_file_location, preview_format, destination_preview_file_location, params)

        # FAILURE CASE: Execute generator
        await generator()

    def register_preview_generator(self, preview_generator_class: type[BaseArtifactPreviewGenerator]) -> None:
        """Register a preview generator with this provider.

        Args:
            preview_generator_class: The preview generator class to register

        Raises:
            ValueError: If generator with same name or class already registered
        """
        friendly_name = preview_generator_class.get_friendly_name()
        friendly_name_lower = friendly_name.lower()

        if friendly_name_lower in self._friendly_name_to_preview_generator_class:
            msg = f"Preview generator with friendly name '{friendly_name}' already registered"
            raise ValueError(msg)

        if preview_generator_class in self._preview_generator_classes:
            msg = f"Preview generator class {preview_generator_class.__name__} already registered"
            raise ValueError(msg)

        self._preview_generator_classes.append(preview_generator_class)
        self._friendly_name_to_preview_generator_class[friendly_name_lower] = preview_generator_class

    def get_registered_preview_generators(self) -> list[str]:
        """Get friendly names of all registered preview generators.

        Returns:
            List of friendly names
        """
        return [gen.get_friendly_name() for gen in self._preview_generator_classes]

    def _get_preview_generator_by_name(self, friendly_name: str) -> type[BaseArtifactPreviewGenerator] | None:
        """Get preview generator class by friendly name (case-insensitive).

        Args:
            friendly_name: The friendly name to look up

        Returns:
            The preview generator class, or None if not found
        """
        return self._friendly_name_to_preview_generator_class.get(friendly_name.lower())
