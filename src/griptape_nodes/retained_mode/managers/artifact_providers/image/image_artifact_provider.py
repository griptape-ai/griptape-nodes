"""Image artifact provider."""

from __future__ import annotations

from typing import TYPE_CHECKING

from griptape_nodes.retained_mode.managers.artifact_providers.base_artifact_provider import (
    BaseArtifactProvider,
)

if TYPE_CHECKING:
    from griptape_nodes.retained_mode.managers.artifact_providers.base_artifact_preview_generator import (
        BaseArtifactPreviewGenerator,
    )
    from griptape_nodes.retained_mode.managers.artifact_providers.provider_registry import ProviderRegistry


class ImageArtifactProvider(BaseArtifactProvider):
    """Provider for image artifacts.

    Instance attributes may hold heavyweight image processing dependencies
    (e.g., PIL/Pillow) that are loaded lazily when the provider is instantiated.
    """

    def __init__(self, registry: ProviderRegistry) -> None:
        """Initialize with default preview generators.

        Args:
            registry: The ProviderRegistry that manages this provider
        """
        super().__init__(registry)

        # Do lazy imports here to only instantiate when the provider gets rezzed up.
        from griptape_nodes.retained_mode.managers.artifact_providers.image.preview_generators import (
            PILRoundedPreviewGenerator,
            PILThumbnailGenerator,
        )

        # Register default generators with config
        self.register_preview_generator_with_config(PILThumbnailGenerator)
        self.register_preview_generator_with_config(PILRoundedPreviewGenerator)

    @classmethod
    def get_friendly_name(cls) -> str:
        return "Image"

    @classmethod
    def get_supported_formats(cls) -> set[str]:
        return {"png", "jpg", "jpeg", "gif", "bmp", "webp", "tiff", "tif", "tga"}

    @classmethod
    def get_preview_formats(cls) -> set[str]:
        return {"webp", "jpg", "png"}

    @classmethod
    def get_default_preview_generator(cls) -> str:
        return "Standard Thumbnail Generation"

    @classmethod
    def get_default_preview_format(cls) -> str:
        return "png"

    @classmethod
    def get_default_generators(cls) -> list[type[BaseArtifactPreviewGenerator]]:
        """Get default preview generator classes."""
        from griptape_nodes.retained_mode.managers.artifact_providers.image.preview_generators import (
            PILRoundedPreviewGenerator,
            PILThumbnailGenerator,
        )

        return [PILThumbnailGenerator, PILRoundedPreviewGenerator]
