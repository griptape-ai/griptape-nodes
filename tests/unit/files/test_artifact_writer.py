"""Tests for the artifact-write helpers.

These exercise the pure helper logic: format normalization, byte sniffing,
and filename-suffix correction. The full ``write_*_bytes`` entry points
require a running engine for ``ProjectFileDestination.from_situation`` and
are covered by integration tests / manual workflow runs instead.
"""

from io import BytesIO
from pathlib import Path

import pytest
from PIL import Image

from griptape_nodes.files.artifact_writer import (
    AUDIO_FORMAT_TO_EXTENSION,
    IMAGE_FORMAT_TO_EXTENSION,
    VIDEO_FORMAT_TO_EXTENSION,
    _force_suffix,
    _normalize_audio_format,
    _normalize_image_format,
    _normalize_video_format,
    _resolve_audio_extension,
    _resolve_image_extension,
    _resolve_video_extension,
    _sniff_audio_format,
    _sniff_image_format,
    _sniff_video_format,
)


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


class TestNormalizeImageFormat:
    def test_jpg_normalizes_to_jpeg(self) -> None:
        assert _normalize_image_format("jpg") == "JPEG"

    def test_jpeg_uppercased(self) -> None:
        assert _normalize_image_format("jpeg") == "JPEG"

    def test_png_uppercased(self) -> None:
        assert _normalize_image_format("png") == "PNG"

    def test_leading_dot_stripped(self) -> None:
        assert _normalize_image_format(".png") == "PNG"

    def test_unknown_format_raises(self) -> None:
        with pytest.raises(ValueError, match="Unsupported image format"):
            _normalize_image_format("xyz")

    def test_pil_format_without_extension_mapping_raises(self) -> None:
        # EPS is a valid PIL format but intentionally not in IMAGE_FORMAT_TO_EXTENSION.
        with pytest.raises(ValueError, match="Unsupported image format"):
            _normalize_image_format("eps")


class TestNormalizeVideoFormat:
    def test_lowercased(self) -> None:
        assert _normalize_video_format("MP4") == "mp4"

    def test_leading_dot_stripped(self) -> None:
        assert _normalize_video_format(".mov") == "mov"

    def test_unknown_format_raises(self) -> None:
        with pytest.raises(ValueError, match="Unsupported video format"):
            _normalize_video_format("xyz")


class TestNormalizeAudioFormat:
    def test_lowercased(self) -> None:
        assert _normalize_audio_format("MP3") == "mp3"

    def test_mpeg_alias_to_mp3_extension(self) -> None:
        assert AUDIO_FORMAT_TO_EXTENSION[_normalize_audio_format("mpeg")] == "mp3"

    def test_unknown_format_raises(self) -> None:
        with pytest.raises(ValueError, match="Unsupported audio format"):
            _normalize_audio_format("xyz")


class TestSniffImage:
    def test_png(self) -> None:
        assert _sniff_image_format(_png_bytes()) == "PNG"

    def test_jpeg(self) -> None:
        assert _sniff_image_format(_jpeg_bytes()) == "JPEG"

    def test_webp(self) -> None:
        assert _sniff_image_format(_webp_bytes()) == "WEBP"

    def test_garbage(self) -> None:
        assert _sniff_image_format(b"not an image") is None


class TestSniffVideo:
    def test_mp4(self) -> None:
        # Minimal mp4 header: 8 bytes prefix then "ftyp" + brand
        head = b"\x00\x00\x00\x18ftypisom"
        assert _sniff_video_format(head + b"\x00" * 16) == "mp4"

    def test_mov(self) -> None:
        head = b"\x00\x00\x00\x18ftypqt  "
        assert _sniff_video_format(head + b"\x00" * 16) == "mov"

    def test_webm(self) -> None:
        # EBML header + "webm" doctype later
        head = b"\x1aE\xdf\xa3" + b"\x00" * 8 + b"webm" + b"\x00" * 16
        assert _sniff_video_format(head) == "webm"

    def test_avi(self) -> None:
        head = b"RIFF\x00\x00\x00\x00AVI " + b"\x00" * 16
        assert _sniff_video_format(head) == "avi"

    def test_gif(self) -> None:
        assert _sniff_video_format(b"GIF89a" + b"\x00" * 16) == "gif"

    def test_garbage(self) -> None:
        assert _sniff_video_format(b"not a video file") is None


class TestSniffAudio:
    def test_mp3_id3(self) -> None:
        assert _sniff_audio_format(b"ID3" + b"\x00" * 16) == "mp3"

    def test_mp3_frame_sync(self) -> None:
        assert _sniff_audio_format(b"\xff\xfb" + b"\x00" * 16) == "mp3"

    def test_wav(self) -> None:
        head = b"RIFF\x00\x00\x00\x00WAVE" + b"\x00" * 16
        assert _sniff_audio_format(head) == "wav"

    def test_flac(self) -> None:
        assert _sniff_audio_format(b"fLaC" + b"\x00" * 16) == "flac"

    def test_ogg(self) -> None:
        assert _sniff_audio_format(b"OggS" + b"\x00" * 16) == "ogg"

    def test_opus_in_ogg(self) -> None:
        head = b"OggS" + b"\x00" * 8 + b"OpusHead" + b"\x00" * 16
        assert _sniff_audio_format(head) == "opus"

    def test_garbage(self) -> None:
        assert _sniff_audio_format(b"not an audio file") is None


class TestForceSuffix:
    def test_no_change_when_already_matching(self) -> None:
        assert _force_suffix("foo.png", "png") == ("foo.png", False)

    def test_change_when_extension_differs(self) -> None:
        assert _force_suffix("foo.png", "jpg") == ("foo.jpg", True)

    def test_jpg_jpeg_treated_as_equivalent(self) -> None:
        assert _force_suffix("foo.jpg", "jpeg") == ("foo.jpg", False)
        assert _force_suffix("foo.jpeg", "jpg") == ("foo.jpeg", False)

    def test_preserves_directory(self) -> None:
        new_filename, changed = _force_suffix("renders/foo.png", "jpg")
        assert changed is True
        assert Path(new_filename) == Path("renders/foo.jpg")

    def test_case_insensitive_match(self) -> None:
        assert _force_suffix("foo.PNG", "png") == ("foo.PNG", False)


class TestResolveImageExtension:
    def test_requested_format_wins_over_bytes(self) -> None:
        # Bytes are JPEG but caller asked for PNG -> we return png because the
        # caller is the source of truth (they asked the provider for png).
        assert _resolve_image_extension(_jpeg_bytes(), "png") == "png"

    def test_jpeg_request_yields_jpg_extension(self) -> None:
        assert _resolve_image_extension(_jpeg_bytes(), "jpeg") == "jpg"

    def test_sniff_when_no_request(self) -> None:
        assert _resolve_image_extension(_png_bytes(), None) == "png"
        assert _resolve_image_extension(_jpeg_bytes(), None) == "jpg"

    def test_unknown_bytes_with_no_request_raises(self) -> None:
        with pytest.raises(ValueError, match="Could not determine image format"):
            _resolve_image_extension(b"garbage", None)

    def test_invalid_requested_format_raises(self) -> None:
        with pytest.raises(ValueError, match="Unsupported image format"):
            _resolve_image_extension(_png_bytes(), "xyz")


class TestResolveVideoExtension:
    def test_requested_format_wins(self) -> None:
        # Bytes are mp4 but caller said webm -> trust caller.
        head = b"\x00\x00\x00\x18ftypisom" + b"\x00" * 16
        assert _resolve_video_extension(head, "webm") == "webm"

    def test_sniff_when_no_request(self) -> None:
        head = b"\x00\x00\x00\x18ftypisom" + b"\x00" * 16
        assert _resolve_video_extension(head, None) == "mp4"

    def test_unknown_bytes_with_no_request_raises(self) -> None:
        with pytest.raises(ValueError, match="Could not determine video format"):
            _resolve_video_extension(b"garbage", None)


class TestResolveAudioExtension:
    def test_requested_format_wins(self) -> None:
        # Bytes are wav but caller said mp3 -> trust caller.
        head = b"RIFF\x00\x00\x00\x00WAVE" + b"\x00" * 16
        assert _resolve_audio_extension(head, "mp3") == "mp3"

    def test_sniff_when_no_request(self) -> None:
        assert _resolve_audio_extension(b"ID3" + b"\x00" * 16, None) == "mp3"

    def test_unknown_bytes_with_no_request_raises(self) -> None:
        with pytest.raises(ValueError, match="Could not determine audio format"):
            _resolve_audio_extension(b"garbage", None)


class TestExtensionMappings:
    """Sanity checks on the format -> extension tables themselves."""

    def test_image_extensions_have_no_dots(self) -> None:
        for ext in IMAGE_FORMAT_TO_EXTENSION.values():
            assert not ext.startswith(".")

    def test_video_extensions_have_no_dots(self) -> None:
        for ext in VIDEO_FORMAT_TO_EXTENSION.values():
            assert not ext.startswith(".")

    def test_audio_extensions_have_no_dots(self) -> None:
        for ext in AUDIO_FORMAT_TO_EXTENSION.values():
            assert not ext.startswith(".")

    def test_jpeg_maps_to_jpg(self) -> None:
        assert IMAGE_FORMAT_TO_EXTENSION["JPEG"] == "jpg"
