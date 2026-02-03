"""Image artifact provider."""

from griptape_nodes.retained_mode.managers.default_artifact_providers.base_artifact_provider import (
    BaseArtifactProvider,
)


class ImageArtifactProvider(BaseArtifactProvider):
    """Provider for image artifacts."""

    @classmethod
    def get_friendly_name(cls) -> str:
        return "Image"

    @classmethod
    def get_supported_formats(cls) -> set[str]:
        return {"png", "jpg", "jpeg", "gif", "bmp", "webp", "tiff", "tif"}

    @classmethod
    def get_preview_formats(cls) -> set[str]:
        return {"webp", "jpg", "png"}
