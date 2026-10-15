"""Tests for collect_metadata_for_write and prepare_content_for_write on ImageArtifactProvider and ArtifactManager."""

import logging
from unittest.mock import MagicMock, patch

import pytest

from griptape_nodes.retained_mode.engine import Engine
from griptape_nodes.retained_mode.events.artifact_events import RegisterArtifactProviderRequest
from griptape_nodes.retained_mode.managers.artifact_providers.audio.audio_artifact_provider import (
    AudioArtifactProvider,
)
from griptape_nodes.retained_mode.managers.artifact_providers.image.image_artifact_provider import (
    ImageArtifactProvider,
)
from griptape_nodes.retained_mode.managers.artifact_providers.provider_registry import ProviderRegistry

_MODULE = "griptape_nodes.retained_mode.managers.artifact_providers.image.image_artifact_provider"
COLLECT_PATH = f"{_MODULE}.collect_workflow_metadata"
IMAGE_OPEN_PATH = f"{_MODULE}.Image.open"
DRIVER_REGISTRY_PATH = f"{_MODULE}.ImageMetadataDriverRegistry.get_driver_for_format"


@pytest.fixture
def registry() -> ProviderRegistry:
    """Provide a bare ProviderRegistry."""
    return ProviderRegistry()


@pytest.fixture
def image_provider(registry: ProviderRegistry) -> ImageArtifactProvider:
    """Provide an ImageArtifactProvider backed by a bare registry."""
    return ImageArtifactProvider(registry=registry)


class TestBaseArtifactProviderDefaults:
    """A provider that overrides neither hook embeds nothing and leaves the bytes alone."""

    def test_collects_no_metadata(self, registry: ProviderRegistry) -> None:
        assert AudioArtifactProvider(registry=registry).collect_metadata_for_write("clip.mp3") == {}

    def test_returns_data_unchanged(self, registry: ProviderRegistry) -> None:
        data = b"audio bytes"

        result = AudioArtifactProvider(registry=registry).prepare_content_for_write(data, "clip.mp3", {"k": "v"})

        assert result is data


class TestImageArtifactProviderCollectMetadataForWrite:
    """Tests for ImageArtifactProvider.collect_metadata_for_write."""

    def test_collects_workflow_metadata_for_png(self, image_provider: ImageArtifactProvider) -> None:
        metadata = {"gtn_saved_at": "2024-01-01T00:00:00+00:00"}

        with patch(COLLECT_PATH, return_value=metadata):
            result = image_provider.collect_metadata_for_write("image.png")

        assert result == metadata

    def test_skips_collecting_for_formats_without_metadata(self, image_provider: ImageArtifactProvider) -> None:
        with patch(COLLECT_PATH) as mock_collect:
            result = image_provider.collect_metadata_for_write("image.jpg")

        mock_collect.assert_not_called()
        assert result == {}

    def test_returns_empty_and_warns_when_collecting_fails(
        self, image_provider: ImageArtifactProvider, caplog: pytest.LogCaptureFixture
    ) -> None:
        with patch(COLLECT_PATH, side_effect=RuntimeError("collect failed")), caplog.at_level(logging.WARNING):
            result = image_provider.collect_metadata_for_write("image.png")

        assert result == {}
        assert any("Attempted to collect workflow metadata" in record.message for record in caplog.records)


class TestImageArtifactProviderPrepareContentForWrite:
    """Tests for ImageArtifactProvider.prepare_content_for_write."""

    def test_injects_the_given_metadata_via_driver(self, image_provider: ImageArtifactProvider) -> None:
        original_bytes = b"fake png bytes"
        injected_bytes = b"fake png bytes with metadata"
        metadata = {"gtn_saved_at": "2024-01-01T00:00:00+00:00"}

        mock_image = MagicMock()
        mock_image.format = "PNG"
        mock_driver = MagicMock()
        mock_driver.inject_metadata.return_value = injected_bytes

        with (
            patch(COLLECT_PATH) as mock_collect,
            patch(IMAGE_OPEN_PATH, return_value=mock_image),
            patch(DRIVER_REGISTRY_PATH, return_value=mock_driver),
        ):
            result = image_provider.prepare_content_for_write(original_bytes, "image.png", metadata)

        assert result == injected_bytes
        mock_driver.inject_metadata.assert_called_once_with(mock_image, metadata)
        # It runs on a worker thread, so it must not read engine state itself.
        mock_collect.assert_not_called()

    def test_returns_data_unchanged_without_metadata(self, image_provider: ImageArtifactProvider) -> None:
        with patch(IMAGE_OPEN_PATH) as mock_open:
            result = image_provider.prepare_content_for_write(b"fake png bytes", "image.png", {})

        assert result == b"fake png bytes"
        mock_open.assert_not_called()

    def test_returns_empty_data_unchanged(self, image_provider: ImageArtifactProvider) -> None:
        result = image_provider.prepare_content_for_write(b"", "image.png", {"gtn_saved_at": "x"})

        assert result == b""


class TestArtifactManagerPrepareContentForWrite:
    """Tests for ArtifactManager.prepare_content_for_write."""

    def test_returns_data_unchanged_for_unknown_extension(self, engine: Engine) -> None:
        """Test that data is returned unchanged when no provider handles the extension."""
        artifact_manager = engine.artifact_manager
        data = b"some binary data"

        result = artifact_manager.prepare_content_for_write(data, "archive.xyz_unknown", {"k": "v"})

        assert result is data

    def test_returns_data_unchanged_for_empty_extension(self, engine: Engine) -> None:
        """Test that data is returned unchanged when filename has no extension."""
        artifact_manager = engine.artifact_manager
        data = b"some binary data"

        result = artifact_manager.prepare_content_for_write(data, "no_extension_file", {"k": "v"})

        assert result is data

    def test_dispatches_to_provider_for_known_extension(self, engine: Engine) -> None:
        """Test that both halves dispatch to the image provider for .png files."""
        artifact_manager = engine.artifact_manager
        artifact_manager.on_handle_register_artifact_provider_request(
            RegisterArtifactProviderRequest(provider_class=ImageArtifactProvider)
        )
        original_bytes = b"fake png bytes"
        processed_bytes = b"fake png bytes with metadata"
        metadata = {"gtn_saved_at": "2024-01-01T00:00:00+00:00"}

        mock_image = MagicMock()
        mock_image.format = "PNG"
        mock_driver = MagicMock()
        mock_driver.inject_metadata.return_value = processed_bytes

        with (
            patch(COLLECT_PATH, return_value=metadata),
            patch(IMAGE_OPEN_PATH, return_value=mock_image),
            patch(DRIVER_REGISTRY_PATH, return_value=mock_driver),
        ):
            collected = artifact_manager.collect_metadata_for_write("output.png")
            result = artifact_manager.prepare_content_for_write(original_bytes, "output.png", collected)

        assert result == processed_bytes
        mock_driver.inject_metadata.assert_called_once_with(mock_image, metadata)
