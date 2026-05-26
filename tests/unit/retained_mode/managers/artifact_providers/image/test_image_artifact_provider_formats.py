"""Tests for the format/detection API on ImageArtifactProvider."""

from io import BytesIO

import pytest
from PIL import Image

from griptape_nodes.retained_mode.managers.artifact_providers.image.image_artifact_provider import (
    ImageArtifactProvider,
)
from griptape_nodes.retained_mode.managers.artifact_providers.provider_registry import ProviderRegistry


def _png_bytes() -> bytes:
    buf = BytesIO()
    Image.new("RGB", (1, 1), (0, 0, 0)).save(buf, format="PNG")
    return buf.getvalue()


def _jpeg_bytes() -> bytes:
    buf = BytesIO()
    Image.new("RGB", (1, 1), (0, 0, 0)).save(buf, format="JPEG")
    return buf.getvalue()


def _webp_bytes() -> bytes:
    buf = BytesIO()
    Image.new("RGB", (1, 1), (0, 0, 0)).save(buf, format="WEBP")
    return buf.getvalue()


@pytest.fixture
def image_provider() -> ImageArtifactProvider:
    """Provide an ImageArtifactProvider backed by a bare registry."""
    return ImageArtifactProvider(registry=ProviderRegistry())


class TestNormalizeFormat:
    def test_jpg_normalizes_to_jpeg(self) -> None:
        assert ImageArtifactProvider.normalize_format("jpg") == "JPEG"

    def test_jpeg_uppercased(self) -> None:
        assert ImageArtifactProvider.normalize_format("jpeg") == "JPEG"

    def test_png_uppercased(self) -> None:
        assert ImageArtifactProvider.normalize_format("png") == "PNG"

    def test_leading_dot_stripped(self) -> None:
        assert ImageArtifactProvider.normalize_format(".png") == "PNG"

    def test_unknown_format_raises(self) -> None:
        with pytest.raises(ValueError, match="Unsupported image format"):
            ImageArtifactProvider.normalize_format("xyz")

    def test_pil_format_without_extension_mapping_raises(self) -> None:
        # EPS is a valid PIL format but intentionally not in _FORMAT_TO_EXTENSION.
        with pytest.raises(ValueError, match="Unsupported image format"):
            ImageArtifactProvider.normalize_format("eps")


class TestExtensionForFormat:
    def test_jpeg_request_yields_jpg_extension(self) -> None:
        assert ImageArtifactProvider.extension_for_format("jpeg") == "jpg"

    def test_png_request_yields_png_extension(self) -> None:
        assert ImageArtifactProvider.extension_for_format("png") == "png"

    def test_invalid_format_raises(self) -> None:
        with pytest.raises(ValueError, match="Unsupported image format"):
            ImageArtifactProvider.extension_for_format("xyz")


class TestDetectFormat:
    def test_png(self, image_provider: ImageArtifactProvider) -> None:
        assert image_provider.detect_format(_png_bytes()) == "PNG"

    def test_jpeg(self, image_provider: ImageArtifactProvider) -> None:
        assert image_provider.detect_format(_jpeg_bytes()) == "JPEG"

    def test_webp(self, image_provider: ImageArtifactProvider) -> None:
        assert image_provider.detect_format(_webp_bytes()) == "WEBP"

    def test_garbage(self, image_provider: ImageArtifactProvider) -> None:
        assert image_provider.detect_format(b"not an image") is None


class TestExtensionMapping:
    def test_extensions_have_no_dots(self) -> None:
        for ext in ImageArtifactProvider.get_format_to_extension().values():
            assert not ext.startswith(".")

    def test_jpeg_maps_to_jpg(self) -> None:
        assert ImageArtifactProvider.get_format_to_extension()["JPEG"] == "jpg"
