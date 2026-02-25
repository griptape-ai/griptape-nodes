"""Image artifact provider."""

from __future__ import annotations

import logging
from io import BytesIO
from pathlib import Path
from typing import TYPE_CHECKING

from PIL import Image

from griptape_nodes.drivers.image_metadata.image_metadata_driver_registry import (
    ImageMetadataDriverRegistry,
)
from griptape_nodes.retained_mode.managers.artifact_providers.base_artifact_provider import (
    BaseArtifactProvider,
)
from griptape_nodes.retained_mode.managers.artifact_providers.image.metadata import collect_workflow_metadata

if TYPE_CHECKING:
    from griptape_nodes.retained_mode.managers.artifact_providers.base_artifact_preview_generator import (
        BaseArtifactPreviewGenerator,
    )
    from griptape_nodes.retained_mode.managers.artifact_providers.provider_registry import ProviderRegistry

logger = logging.getLogger("griptape_nodes")


class ImageArtifactProvider(BaseArtifactProvider):
    """Provider for image artifacts.

    Instance attributes may hold heavyweight image processing dependencies
    (e.g., PIL/Pillow) that are loaded lazily when the provider is instantiated.
    """

    def __init__(self, registry: ProviderRegistry) -> None:
        """Initialize the image artifact provider.

        Args:
            registry: The ProviderRegistry that manages this provider
        """
        super().__init__(registry)

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
        return "webp"

    @classmethod
    def get_default_preview_generators(cls) -> list[type[BaseArtifactPreviewGenerator]]:
        """Get default preview generator classes."""
        from griptape_nodes.retained_mode.managers.artifact_providers.image.preview_generators import (
            PILRoundedPreviewGenerator,
            PILThumbnailGenerator,
        )

        return [PILThumbnailGenerator, PILRoundedPreviewGenerator]

    @classmethod
    def get_metadata_formats(cls) -> set[str]:
        """File extensions that support automatic metadata injection.

        Returns:
            Set of lowercase file extensions WITHOUT leading dots
        """
        return {"png"}

    def prepare_content_for_write(self, data: bytes, file_name: str) -> bytes:  # noqa: PLR0911
        ext = Path(file_name).suffix.lstrip(".").lower()
        if ext not in self.get_metadata_formats():
            return data
        try:
            if not data:
                logger.warning("Cannot inject metadata: empty data")
                return data

            metadata = collect_workflow_metadata()
            if not metadata:
                return data

            pil_image = Image.open(BytesIO(data))

            if pil_image.format is None:
                logger.warning("Could not detect image format from data")
                return data

            driver = ImageMetadataDriverRegistry.get_driver_for_format(pil_image.format)
            if driver is None:
                logger.warning("No metadata driver found for format: %s", pil_image.format)
                return data

            return driver.inject_metadata(pil_image, metadata)
        except Exception as e:
            logger.warning("Failed to inject workflow metadata into %s: %s", file_name, e)
            return data
