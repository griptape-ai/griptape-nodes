"""Integration tests for ``ArtifactManager._resolve_target_extension``.

Caller-supplied ``requested_format`` wins over byte sniffing; otherwise the
provider's ``detect_format`` is consulted; unknown bytes with no caller hint
raise ``ValueError``.
"""

from io import BytesIO

import pytest
from PIL import Image

from griptape_nodes.retained_mode.events.artifact_events import RegisterArtifactProviderRequest
from griptape_nodes.retained_mode.events.base_events import RequestPayload, ResultPayload
from griptape_nodes.retained_mode.events.config_events import SetConfigValueRequest, SetConfigValueResultSuccess
from griptape_nodes.retained_mode.managers.artifact_manager import ArtifactManager
from griptape_nodes.retained_mode.managers.artifact_providers import (
    ImageArtifactProvider,
    VideoArtifactProvider,
)
from griptape_nodes.retained_mode.managers.artifact_providers.audio.audio_artifact_provider import (
    AudioArtifactProvider,
)


@pytest.fixture(autouse=True)
def mock_config_writes(monkeypatch: pytest.MonkeyPatch) -> None:
    """Prevent provider registration from writing to real user config files."""
    from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

    original_handle_request = GriptapeNodes.handle_request

    def selective_mock(request: RequestPayload) -> ResultPayload:
        if isinstance(request, SetConfigValueRequest):
            return SetConfigValueResultSuccess(result_details="Mocked config write")
        return original_handle_request(request)

    monkeypatch.setattr(
        "griptape_nodes.retained_mode.managers.artifact_manager.GriptapeNodes.handle_request", selective_mock
    )


def _png_bytes() -> bytes:
    buf = BytesIO()
    Image.new("RGB", (1, 1), (0, 0, 0)).save(buf, format="PNG")
    return buf.getvalue()


def _jpeg_bytes() -> bytes:
    buf = BytesIO()
    Image.new("RGB", (1, 1), (0, 0, 0)).save(buf, format="JPEG")
    return buf.getvalue()


@pytest.fixture
def manager() -> ArtifactManager:
    """An ArtifactManager with Image, Video, and Audio providers registered."""
    mgr = ArtifactManager()
    for provider_class in (ImageArtifactProvider, VideoArtifactProvider, AudioArtifactProvider):
        mgr.on_handle_register_artifact_provider_request(RegisterArtifactProviderRequest(provider_class=provider_class))
    return mgr


class TestResolveImageExtension:
    def test_requested_format_wins_over_bytes(self, manager: ArtifactManager) -> None:
        # Bytes are JPEG but caller asked for PNG. Caller wins.
        assert manager._resolve_target_extension("Image", _jpeg_bytes(), requested_format="png") == "png"

    def test_jpeg_request_yields_jpg_extension(self, manager: ArtifactManager) -> None:
        assert manager._resolve_target_extension("Image", _jpeg_bytes(), requested_format="jpeg") == "jpg"

    def test_sniff_when_no_request(self, manager: ArtifactManager) -> None:
        assert manager._resolve_target_extension("Image", _png_bytes(), requested_format=None) == "png"
        assert manager._resolve_target_extension("Image", _jpeg_bytes(), requested_format=None) == "jpg"

    def test_unknown_bytes_with_no_request_raises(self, manager: ArtifactManager) -> None:
        with pytest.raises(ValueError, match="Could not determine image format"):
            manager._resolve_target_extension("Image", b"garbage", requested_format=None)

    def test_invalid_requested_format_raises(self, manager: ArtifactManager) -> None:
        with pytest.raises(ValueError, match="Unsupported image format"):
            manager._resolve_target_extension("Image", _png_bytes(), requested_format="xyz")


class TestResolveVideoExtension:
    def test_requested_format_wins(self, manager: ArtifactManager) -> None:
        head = b"\x00\x00\x00\x18ftypisom" + b"\x00" * 16
        assert manager._resolve_target_extension("Video", head, requested_format="webm") == "webm"

    def test_sniff_when_no_request(self, manager: ArtifactManager) -> None:
        head = b"\x00\x00\x00\x18ftypisom" + b"\x00" * 16
        assert manager._resolve_target_extension("Video", head, requested_format=None) == "mp4"

    def test_unknown_bytes_with_no_request_raises(self, manager: ArtifactManager) -> None:
        with pytest.raises(ValueError, match="Could not determine video format"):
            manager._resolve_target_extension("Video", b"garbage", requested_format=None)


class TestResolveAudioExtension:
    def test_requested_format_wins(self, manager: ArtifactManager) -> None:
        head = b"RIFF\x00\x00\x00\x00WAVE" + b"\x00" * 16
        assert manager._resolve_target_extension("Audio", head, requested_format="mp3") == "mp3"

    def test_sniff_when_no_request(self, manager: ArtifactManager) -> None:
        assert manager._resolve_target_extension("Audio", b"ID3" + b"\x00" * 16, requested_format=None) == "mp3"

    def test_unknown_bytes_with_no_request_raises(self, manager: ArtifactManager) -> None:
        with pytest.raises(ValueError, match="Could not determine audio format"):
            manager._resolve_target_extension("Audio", b"garbage", requested_format=None)


class TestResolveUnknownProvider:
    def test_unregistered_friendly_name_raises(self, manager: ArtifactManager) -> None:
        with pytest.raises(ValueError, match="No artifact provider registered with friendly name"):
            manager._resolve_target_extension("Bogus", b"\x00", requested_format=None)
