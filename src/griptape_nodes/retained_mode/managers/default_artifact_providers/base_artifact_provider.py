"""Base abstract class for artifact providers."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any, NamedTuple

if TYPE_CHECKING:
    from griptape_nodes.retained_mode.managers.default_artifact_providers.base_artifact_preview_generator import (
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


class PreviewGenerationResult(NamedTuple):
    """Result of preview generation operation.

    Attributes:
        success: Whether the preview generation succeeded
        message: Success message or error details
    """

    success: bool
    message: str


class PreviewGeneratorRegistrationResult(NamedTuple):
    """Result of preview generator registration operation.

    Attributes:
        success: Whether the registration succeeded
        message: Success message or error details
    """

    success: bool
    message: str


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

    async def generate_preview(
        self,
        preview_generator_friendly_name: str,
        source_file_location: str,
        preview_format: str,
        destination_preview_file_location: str,
        params: dict[str, Any],
    ) -> PreviewGenerationResult:
        """Generate a preview using the specified preview generator.

        This method handles the complete preview generation flow:
        1. Verifies the generator is registered
        2. Validates all required parameters are provided
        3. Verifies the preview format is supported
        4. Instantiates and executes the generator
        5. Returns the result

        Args:
            preview_generator_friendly_name: Friendly name of registered generator to use
            source_file_location: Path to the source artifact file
            preview_format: Target preview format
            destination_preview_file_location: Path where the preview should be saved
            params: Generator-specific parameters

        Returns:
            PreviewGenerationResult with success status and message
        """
        # FAILURE CASE: Generator not registered
        generator_class = self._get_preview_generator_by_name(preview_generator_friendly_name)
        if generator_class is None:
            return PreviewGenerationResult(
                success=False,
                message=f"Preview generator '{preview_generator_friendly_name}' not registered with this provider",
            )

        # Get generator metadata
        generator_params = generator_class.get_parameters()
        supported_formats = generator_class.get_supported_preview_formats()

        # FAILURE CASE: Validate required parameters are provided
        missing_params = []
        for param_name, param_value in generator_params.items():
            if param_value.required and param_name not in params:
                missing_params.append(param_name)

        if missing_params:
            return PreviewGenerationResult(
                success=False,
                message=f"Missing required parameters: {', '.join(missing_params)}",
            )

        # FAILURE CASE: Verify preview format is supported
        if preview_format not in supported_formats:
            return PreviewGenerationResult(
                success=False,
                message=f"Preview format '{preview_format}' not supported by generator "
                f"(supported: {', '.join(sorted(supported_formats))})",
            )

        # FAILURE CASE: Instantiate generator
        try:
            generator = generator_class(source_file_location, preview_format, destination_preview_file_location, params)
        except Exception as e:
            return PreviewGenerationResult(
                success=False,
                message=f"Failed to instantiate preview generator: {e}",
            )

        # FAILURE CASE: Execute generator
        try:
            await generator()
        except Exception as e:
            return PreviewGenerationResult(
                success=False,
                message=f"Preview generation failed: {e}",
            )

        # SUCCESS PATH: Preview generated successfully
        return PreviewGenerationResult(
            success=True,
            message="Preview generated successfully",
        )

    def register_preview_generator(
        self, preview_generator_class: type[BaseArtifactPreviewGenerator]
    ) -> PreviewGeneratorRegistrationResult:
        """Register a preview generator with this provider.

        Args:
            preview_generator_class: The preview generator class to register

        Returns:
            PreviewGeneratorRegistrationResult with success status and message
        """
        friendly_name = preview_generator_class.get_friendly_name()
        friendly_name_lower = friendly_name.lower()

        if friendly_name_lower in self._friendly_name_to_preview_generator_class:
            return PreviewGeneratorRegistrationResult(
                success=False,
                message=f"Preview generator with friendly name '{friendly_name}' already registered",
            )

        if preview_generator_class in self._preview_generator_classes:
            return PreviewGeneratorRegistrationResult(
                success=False,
                message=f"Preview generator class {preview_generator_class.__name__} already registered",
            )

        self._preview_generator_classes.append(preview_generator_class)
        self._friendly_name_to_preview_generator_class[friendly_name_lower] = preview_generator_class

        return PreviewGeneratorRegistrationResult(
            success=True, message=f"Preview generator '{friendly_name}' registered successfully"
        )

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
