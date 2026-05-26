"""Audio artifact provider."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, ClassVar

from griptape_nodes.retained_mode.managers.artifact_providers.base_artifact_provider import (
    BaseArtifactMetadata,
    BaseArtifactProvider,
)

if TYPE_CHECKING:
    from griptape_nodes.retained_mode.managers.artifact_providers.base_artifact_preview_generator import (
        BaseArtifactPreviewGenerator,
    )

logger = logging.getLogger("griptape_nodes")


# Magic-byte sniffing constants
_MIN_HEADER_BYTES = 12
_BYTE_FF = 0xFF
_MPEG_FRAME_SYNC_MASK = 0xE0
_MPEG_FRAME_SYNC_VALUE = 0xE0
_ADTS_SYNC_MASK = 0xF0
_ADTS_SYNC_VALUE = 0xF0
_MP3_LAYER_FB = 0xFB
_MP3_LAYER_F3 = 0xF3
_MP3_LAYER_F2 = 0xF2


class AudioArtifactMetadata(BaseArtifactMetadata):
    """Metadata extracted from an audio source file."""


class AudioArtifactProvider(BaseArtifactProvider):
    """Provider for audio artifacts.

    Currently exposes the format/extension and byte-sniffing surface needed by
    the artifact-write API. Preview generation and metadata extraction are not
    yet implemented; the provider returns sensible empty defaults.
    """

    # Maps canonical audio format -> on-disk file extension (no leading dot).
    # Several keys map to the same extension on purpose ('mpeg' is the long form
    # of 'mp3' for some providers; 'pcm'/'ulaw'/'alaw' are raw PCM variants we
    # accept verbatim from the caller).
    _FORMAT_TO_EXTENSION: ClassVar[dict[str, str]] = {
        "mp3": "mp3",
        "wav": "wav",
        "flac": "flac",
        "aac": "aac",
        "m4a": "m4a",
        "ogg": "ogg",
        "opus": "opus",
        "webm": "webm",
        "mpeg": "mp3",
        "pcm": "pcm",
        "ulaw": "ulaw",
        "alaw": "alaw",
    }

    @classmethod
    def get_friendly_name(cls) -> str:
        return "Audio"

    @classmethod
    def get_supported_formats(cls) -> set[str]:
        return {"mp3", "wav", "flac", "aac", "m4a", "ogg", "opus", "webm", "pcm", "ulaw", "alaw"}

    @classmethod
    def get_format_to_extension(cls) -> dict[str, str]:
        return cls._FORMAT_TO_EXTENSION

    @classmethod
    def get_preview_formats(cls) -> set[str]:
        return set()

    @classmethod
    def get_default_preview_generator(cls) -> str:
        return ""

    @classmethod
    def get_default_preview_format(cls) -> str:
        return ""

    @classmethod
    def get_default_preview_generators(cls) -> list[type[BaseArtifactPreviewGenerator]]:
        return []

    @classmethod
    def get_artifact_metadata(cls, source_path: str) -> AudioArtifactMetadata | None:  # noqa: ARG003
        return None

    def detect_format(self, data: bytes) -> str | None:  # noqa: C901, PLR0911
        """Magic-byte sniff for common audio container/codec formats."""
        if len(data) < _MIN_HEADER_BYTES:
            return None
        head = data[:_MIN_HEADER_BYTES]
        # ID3v2-tagged MP3
        if head[:3] == b"ID3":
            return "mp3"
        # MPEG audio frame sync (0xFFE0+ pattern; common MP3 starts FF FB / FF F3 / FF F2)
        if head[0] == _BYTE_FF and (head[1] & _MPEG_FRAME_SYNC_MASK) == _MPEG_FRAME_SYNC_VALUE:
            return "mp3"
        # WAV: "RIFF" .... "WAVE"
        if head[:4] == b"RIFF" and head[8:12] == b"WAVE":
            return "wav"
        # FLAC
        if head[:4] == b"fLaC":
            return "flac"
        # OGG
        if head[:4] == b"OggS":
            if b"OpusHead" in data[:128]:
                return "opus"
            return "ogg"
        # ISO BMFF (m4a/aac in mp4 container)
        if head[4:8] == b"ftyp":
            return "m4a"
        # Matroska/WebM audio
        if head[:4] == b"\x1aE\xdf\xa3":
            return "webm"
        # ADTS AAC: 0xFFF0 / 0xFFF1 / 0xFFF8 / 0xFFF9
        if (
            head[0] == _BYTE_FF
            and (head[1] & _ADTS_SYNC_MASK) == _ADTS_SYNC_VALUE
            and head[1] not in (_MP3_LAYER_FB, _MP3_LAYER_F3, _MP3_LAYER_F2)
        ):
            return "aac"
        return None
