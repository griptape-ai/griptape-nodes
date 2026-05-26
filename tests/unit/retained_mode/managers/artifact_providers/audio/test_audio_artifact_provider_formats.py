"""Tests for the format/detection API on AudioArtifactProvider."""

import pytest

from griptape_nodes.retained_mode.managers.artifact_providers.audio.audio_artifact_provider import (
    AudioArtifactProvider,
)
from griptape_nodes.retained_mode.managers.artifact_providers.provider_registry import ProviderRegistry


@pytest.fixture
def audio_provider() -> AudioArtifactProvider:
    """Provide an AudioArtifactProvider backed by a bare registry."""
    return AudioArtifactProvider(registry=ProviderRegistry())


class TestNormalizeFormat:
    def test_lowercased(self) -> None:
        assert AudioArtifactProvider.normalize_format("MP3") == "mp3"

    def test_leading_dot_stripped(self) -> None:
        assert AudioArtifactProvider.normalize_format(".wav") == "wav"

    def test_mpeg_alias_to_mp3_extension(self) -> None:
        assert AudioArtifactProvider.extension_for_format("mpeg") == "mp3"

    def test_unknown_format_raises(self) -> None:
        with pytest.raises(ValueError, match="Unsupported audio format"):
            AudioArtifactProvider.normalize_format("xyz")


class TestExtensionForFormat:
    def test_mp3_request(self) -> None:
        assert AudioArtifactProvider.extension_for_format("mp3") == "mp3"

    def test_invalid_format_raises(self) -> None:
        with pytest.raises(ValueError, match="Unsupported audio format"):
            AudioArtifactProvider.extension_for_format("xyz")


class TestDetectFormat:
    def test_mp3_id3(self, audio_provider: AudioArtifactProvider) -> None:
        assert audio_provider.detect_format(b"ID3" + b"\x00" * 16) == "mp3"

    def test_mp3_frame_sync(self, audio_provider: AudioArtifactProvider) -> None:
        assert audio_provider.detect_format(b"\xff\xfb" + b"\x00" * 16) == "mp3"

    def test_wav(self, audio_provider: AudioArtifactProvider) -> None:
        head = b"RIFF\x00\x00\x00\x00WAVE" + b"\x00" * 16
        assert audio_provider.detect_format(head) == "wav"

    def test_flac(self, audio_provider: AudioArtifactProvider) -> None:
        assert audio_provider.detect_format(b"fLaC" + b"\x00" * 16) == "flac"

    def test_ogg(self, audio_provider: AudioArtifactProvider) -> None:
        assert audio_provider.detect_format(b"OggS" + b"\x00" * 16) == "ogg"

    def test_opus_in_ogg(self, audio_provider: AudioArtifactProvider) -> None:
        head = b"OggS" + b"\x00" * 8 + b"OpusHead" + b"\x00" * 16
        assert audio_provider.detect_format(head) == "opus"

    def test_garbage(self, audio_provider: AudioArtifactProvider) -> None:
        assert audio_provider.detect_format(b"not an audio file") is None


class TestExtensionMapping:
    def test_extensions_have_no_dots(self) -> None:
        for ext in AudioArtifactProvider.get_format_to_extension().values():
            assert not ext.startswith(".")
