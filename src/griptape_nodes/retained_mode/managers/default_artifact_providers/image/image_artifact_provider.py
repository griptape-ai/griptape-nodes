"""Image artifact provider."""

from griptape_nodes.retained_mode.managers.default_artifact_providers.base_artifact_provider import (
    BaseArtifactProvider,
)


class ImageArtifactProvider(BaseArtifactProvider):
    """Provider for image artifacts.

    Instance attributes may hold heavyweight image processing dependencies
    (e.g., PIL/Pillow) that are loaded lazily when the provider is instantiated.
    """

    def __init__(self) -> None:
        """Initialize with default preview generators."""
        super().__init__()

        # Do lazy imports here to only instantiate when the provider gets rezzed up.
        from griptape_nodes.retained_mode.managers.default_artifact_providers.image.preview_generators import (
            DefaultImagePreviewGenerator,
        )

        # Register default generator
        self.register_preview_generator(DefaultImagePreviewGenerator)

    @classmethod
    def get_friendly_name(cls) -> str:
        return "Image"

    @classmethod
    def get_supported_formats(cls) -> set[str]:
        return {"png", "jpg", "jpeg", "gif", "bmp", "webp", "tiff", "tif", "tga"}

    @classmethod
    def get_preview_formats(cls) -> set[str]:
        return {"webp", "jpg", "png"}
