"""Image artifact provider."""

from griptape_nodes.retained_mode.managers.default_artifact_providers.base_artifact_provider import (
    BaseArtifactProvider,
)


class ImageArtifactProvider(BaseArtifactProvider):
    """Provider for image artifacts."""

    @property
    def friendly_name(self) -> str:
        return "Image"

    @property
    def supported_formats(self) -> set[str]:
        return {"png", "jpg", "jpeg", "gif", "bmp", "webp", "tiff", "tif"}

    @property
    def preview_formats(self) -> set[str]:
        return {"webp", "jpg", "png"}
