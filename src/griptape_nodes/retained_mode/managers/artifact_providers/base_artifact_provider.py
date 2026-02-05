"""Base abstract class for artifact providers."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any, NamedTuple

if TYPE_CHECKING:
    from griptape_nodes.retained_mode.managers.artifact_providers.base_artifact_preview_generator import (
        BaseArtifactPreviewGenerator,
    )
    from griptape_nodes.retained_mode.managers.artifact_providers.provider_registry import ProviderRegistry


class ProviderValue(NamedTuple):
    """Metadata for a generator parameter.

    Attributes:
        default_value: Default value if parameter not provided
        required: Whether parameter must be provided
        json_schema_type: JSON Schema type (e.g., 'integer', 'string', 'number', 'boolean')
        description: Human-readable description of the parameter
    """

    default_value: Any
    required: bool
    json_schema_type: str = "string"
    description: str = ""


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
    def get_default_generators(cls) -> list[type[BaseArtifactPreviewGenerator]]:
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
    def get_preview_format_config_key(cls) -> str:
        """Get the config key for the user's selected preview format.

        Returns:
            Config key (e.g., 'artifacts.image.preview_generation.preview_format')
        """
        return f"{cls.get_config_key_prefix()}.preview_format"

    @classmethod
    def get_preview_generator_config_key(cls) -> str:
        """Get the config key for the user's selected preview generator.

        Returns:
            Config key (e.g., 'artifacts.image.preview_generation.preview_generator')
        """
        return f"{cls.get_config_key_prefix()}.preview_generator"

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
        generator_class = self._registry.get_preview_generator_by_name(self.__class__, preview_generator_friendly_name)
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
        await generator.generate_preview()

    def register_preview_generator_with_config(
        self, preview_generator_class: type[BaseArtifactPreviewGenerator]
    ) -> None:
        """Register a preview generator and its config settings.

        This is the provider's responsibility - it knows about its generators.

        Args:
            preview_generator_class: The preview generator class to register
        """
        from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

        # Register with registry
        self._registry.register_preview_generator_with_provider(self.__class__, preview_generator_class)

        # Register config settings (access config manager via singleton)
        config_schema = BaseArtifactProvider.get_preview_generator_config_schema(
            self.__class__, preview_generator_class
        )
        for key, default_value in config_schema.items():
            GriptapeNodes.ConfigManager().set_config_value(key, default_value)

    @classmethod
    def get_preview_generator_config_schema(
        cls, provider_class: type[BaseArtifactProvider], generator_class: type[BaseArtifactPreviewGenerator]
    ) -> dict:
        """Generate config schema for a preview generator without requiring provider instantiation.

        Args:
            provider_class: The provider class this generator belongs to
            generator_class: The generator class to generate config schema for

        Returns:
            Dictionary mapping config keys to default values for generator parameters
        """
        key_prefix = generator_class.get_config_key_prefix(provider_class.get_friendly_name())

        parameters = generator_class.get_parameters()
        config = {}
        for param_name, provider_value in parameters.items():
            config[f"{key_prefix}.{param_name}"] = provider_value.default_value

        return config
