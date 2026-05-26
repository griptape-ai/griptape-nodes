"""Tests for the format/detection API on VideoArtifactProvider."""

import pytest

from griptape_nodes.retained_mode.managers.artifact_providers.provider_registry import ProviderRegistry
from griptape_nodes.retained_mode.managers.artifact_providers.video.video_artifact_provider import (
    VideoArtifactProvider,
)


@pytest.fixture
def video_provider() -> VideoArtifactProvider:
    """Provide a VideoArtifactProvider backed by a bare registry."""
    return VideoArtifactProvider(registry=ProviderRegistry())


class TestNormalizeFormat:
    def test_lowercased(self) -> None:
        assert VideoArtifactProvider.normalize_format("MP4") == "mp4"

    def test_leading_dot_stripped(self) -> None:
        assert VideoArtifactProvider.normalize_format(".mov") == "mov"

    def test_unknown_format_raises(self) -> None:
        with pytest.raises(ValueError, match="Unsupported video format"):
            VideoArtifactProvider.normalize_format("xyz")


class TestExtensionForFormat:
    def test_mp4_request(self) -> None:
        assert VideoArtifactProvider.extension_for_format("mp4") == "mp4"

    def test_invalid_format_raises(self) -> None:
        with pytest.raises(ValueError, match="Unsupported video format"):
            VideoArtifactProvider.extension_for_format("xyz")


class TestDetectFormat:
    def test_mp4(self, video_provider: VideoArtifactProvider) -> None:
        head = b"\x00\x00\x00\x18ftypisom"
        assert video_provider.detect_format(head + b"\x00" * 16) == "mp4"

    def test_mov(self, video_provider: VideoArtifactProvider) -> None:
        head = b"\x00\x00\x00\x18ftypqt  "
        assert video_provider.detect_format(head + b"\x00" * 16) == "mov"

    def test_webm(self, video_provider: VideoArtifactProvider) -> None:
        head = b"\x1aE\xdf\xa3" + b"\x00" * 8 + b"webm" + b"\x00" * 16
        assert video_provider.detect_format(head) == "webm"

    def test_avi(self, video_provider: VideoArtifactProvider) -> None:
        head = b"RIFF\x00\x00\x00\x00AVI " + b"\x00" * 16
        assert video_provider.detect_format(head) == "avi"

    def test_gif(self, video_provider: VideoArtifactProvider) -> None:
        assert video_provider.detect_format(b"GIF89a" + b"\x00" * 16) == "gif"

    def test_garbage(self, video_provider: VideoArtifactProvider) -> None:
        assert video_provider.detect_format(b"not a video file") is None


class TestExtensionMapping:
    def test_extensions_have_no_dots(self) -> None:
        for ext in VideoArtifactProvider.get_format_to_extension().values():
            assert not ext.startswith(".")
