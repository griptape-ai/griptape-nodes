"""Helpers for writing artifact bytes to disk with a truthful filename extension.

Many generation nodes write provider bytes straight through to a user-controlled
filename without checking that the extension matches the actual byte format. The
result is files like a JPEG named ``foo.png`` that strict consumers (Nuke,
ffmpeg with strict mode, codec validators) reject.

The policy implemented here is "extension follows bytes":

* If a node has an ``output_format`` parameter, that parameter is the source of
  truth. The on-disk filename suffix is forced to match it.
* Otherwise, the format is sniffed from the bytes and the suffix is forced to
  match what the bytes actually are.
* Validates against a media-type allowlist; raises ``ValueError`` otherwise.

No re-encoding is done; we only correct the filename suffix.
"""

from __future__ import annotations

import logging
from io import BytesIO
from pathlib import Path

from PIL import Image

from griptape_nodes.exe_types.param_components.project_file_parameter import ProjectFileParameter
from griptape_nodes.files.file import File, FileDestination, FileDestinationProvider
from griptape_nodes.files.project_file import ProjectFileDestination
from griptape_nodes.retained_mode.events.connection_events import (
    ListConnectionsForNodeRequest,
    ListConnectionsForNodeResultSuccess,
)
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

logger = logging.getLogger("griptape_nodes")


# ---------------------------------------------------------------------------
# Format -> on-disk extension mappings (no leading dot)
# ---------------------------------------------------------------------------

IMAGE_FORMAT_TO_EXTENSION: dict[str, str] = {
    "JPEG": "jpg",
    "PNG": "png",
    "WEBP": "webp",
    "GIF": "gif",
    "BMP": "bmp",
    "TIFF": "tiff",
    "ICO": "ico",
}

VIDEO_FORMAT_TO_EXTENSION: dict[str, str] = {
    "mp4": "mp4",
    "webm": "webm",
    "mov": "mov",
    "mkv": "mkv",
    "avi": "avi",
    "m4v": "m4v",
    "gif": "gif",
}

AUDIO_FORMAT_TO_EXTENSION: dict[str, str] = {
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


# ---------------------------------------------------------------------------
# Format normalization
# ---------------------------------------------------------------------------


def _normalize_image_format(fmt: str) -> str:
    """Canonicalize ``'jpg' -> 'JPEG'``, ``'png' -> 'PNG'``, etc.

    Raises:
        ValueError: if the format has no on-disk extension mapping.
    """
    canon = fmt.upper().lstrip(".")
    if canon == "JPG":
        canon = "JPEG"
    if canon not in IMAGE_FORMAT_TO_EXTENSION:
        msg = f"Unsupported image format: '{fmt}'. Supported: {', '.join(sorted(IMAGE_FORMAT_TO_EXTENSION))}"
        raise ValueError(msg)
    return canon


def _normalize_video_format(fmt: str) -> str:
    canon = fmt.lower().lstrip(".")
    if canon not in VIDEO_FORMAT_TO_EXTENSION:
        msg = f"Unsupported video format: '{fmt}'. Supported: {', '.join(sorted(VIDEO_FORMAT_TO_EXTENSION))}"
        raise ValueError(msg)
    return canon


def _normalize_audio_format(fmt: str) -> str:
    canon = fmt.lower().lstrip(".")
    if canon not in AUDIO_FORMAT_TO_EXTENSION:
        msg = f"Unsupported audio format: '{fmt}'. Supported: {', '.join(sorted(AUDIO_FORMAT_TO_EXTENSION))}"
        raise ValueError(msg)
    return canon


# ---------------------------------------------------------------------------
# Byte-sniffing fallbacks (used when no requested_format is provided)
# ---------------------------------------------------------------------------


def _sniff_image_format(image_bytes: bytes) -> str | None:
    """Return canonical PIL format string ('PNG', 'JPEG', ...) or None."""
    try:
        with Image.open(BytesIO(image_bytes)) as img:
            if img.format:
                return img.format.upper()
    except Exception:
        logger.debug("PIL could not identify image format from bytes", exc_info=True)
    return None


def _sniff_video_format(video_bytes: bytes) -> str | None:
    """Magic-byte sniff for common video container formats."""
    if len(video_bytes) < 12:
        return None
    head = video_bytes[:12]
    # ISO BMFF (mp4/mov/m4v): bytes 4-8 are "ftyp"
    if head[4:8] == b"ftyp":
        major_brand = head[8:12]
        if major_brand in (b"qt  ",):
            return "mov"
        if major_brand in (b"M4V ", b"M4VH", b"M4VP"):
            return "m4v"
        # Most others (isom, mp42, avc1, dash, ...) -> mp4
        return "mp4"
    # Matroska/WebM: 1A 45 DF A3 (EBML header)
    if head[:4] == b"\x1aE\xdf\xa3":
        # Could be mkv or webm; default to mp4-flavored guess fails. Use webm
        # as the more common web-delivered output, falling back to mkv if the
        # bytes contain "matroska" later. Cheap heuristic:
        if b"webm" in video_bytes[:256]:
            return "webm"
        return "mkv"
    # AVI: "RIFF" .... "AVI "
    if head[:4] == b"RIFF" and head[8:12] == b"AVI ":
        return "avi"
    # GIF: "GIF87a" / "GIF89a"
    if head[:6] in (b"GIF87a", b"GIF89a"):
        return "gif"
    return None


def _sniff_audio_format(audio_bytes: bytes) -> str | None:
    """Magic-byte sniff for common audio container/codec formats."""
    if len(audio_bytes) < 12:
        return None
    head = audio_bytes[:12]
    # ID3v2-tagged MP3
    if head[:3] == b"ID3":
        return "mp3"
    # MPEG audio frame sync (0xFFE0+ pattern; common MP3 starts FF FB / FF F3 / FF F2)
    if head[0] == 0xFF and (head[1] & 0xE0) == 0xE0:
        return "mp3"
    # WAV: "RIFF" .... "WAVE"
    if head[:4] == b"RIFF" and head[8:12] == b"WAVE":
        return "wav"
    # FLAC
    if head[:4] == b"fLaC":
        return "flac"
    # OGG
    if head[:4] == b"OggS":
        # Could be ogg-vorbis or opus; we treat both as .ogg unless opus is
        # detected in the first page.
        if b"OpusHead" in audio_bytes[:128]:
            return "opus"
        return "ogg"
    # ISO BMFF (m4a/aac in mp4 container)
    if head[4:8] == b"ftyp":
        major_brand = head[8:12]
        if major_brand in (b"M4A ", b"M4B ", b"mp42", b"isom"):
            return "m4a"
        return "m4a"
    # Matroska/WebM audio
    if head[:4] == b"\x1aE\xdf\xa3":
        return "webm"
    # ADTS AAC: 0xFFF0 / 0xFFF1 / 0xFFF8 / 0xFFF9
    if head[0] == 0xFF and (head[1] & 0xF0) == 0xF0 and head[1] != 0xFB and head[1] != 0xF3 and head[1] != 0xF2:
        return "aac"
    return None


# ---------------------------------------------------------------------------
# Suffix correction
# ---------------------------------------------------------------------------


def _force_suffix(filename: str, target_extension: str) -> tuple[str, bool]:
    """Return ``(new_filename, suffix_was_changed)``.

    Preserves stem, parent dirs, and any leading directory component the user
    supplied. Only the extension is adjusted.
    """
    path = Path(filename)
    current = path.suffix.lstrip(".").lower()
    target = target_extension.lower()
    # Treat .jpeg and .jpg as equivalent for the change detection.
    if {current, target} == {"jpg", "jpeg"}:
        return filename, False
    if current == target:
        return filename, False
    new_path = path.with_suffix(f".{target_extension}")
    return str(new_path), True


# ---------------------------------------------------------------------------
# Destination construction (handles upstream FileDestinationProvider)
# ---------------------------------------------------------------------------


def _upstream_provider_destination(output_file_param: ProjectFileParameter) -> FileDestination | None:
    """If ``output_file_param`` has an upstream FileDestinationProvider connected, return its destination.

    Mirrors the upstream-provider lookup in ``ProjectFileParameter.build_file``.
    """
    node = output_file_param._node  # noqa: SLF001
    name = output_file_param._name  # noqa: SLF001
    result = GriptapeNodes.handle_request(ListConnectionsForNodeRequest(node_name=node.name))
    if not isinstance(result, ListConnectionsForNodeResultSuccess):
        return None
    for conn in result.incoming_connections:
        if conn.target_parameter_name != name:
            continue
        source_node = GriptapeNodes.ObjectManager().attempt_get_object_by_name(conn.source_node_name)
        if isinstance(source_node, FileDestinationProvider):
            file_dest = source_node.file_destination
            if file_dest is None:
                msg = (
                    f"Attempted to build file destination for {node.name}.{name}. "
                    f"Failed because upstream node '{conn.source_node_name}' provides a "
                    f"FileDestination but returned None (likely missing a filename)."
                )
                raise ValueError(msg)
            return file_dest
    return None


def _build_corrected_destination(
    output_file_param: ProjectFileParameter,
    target_extension: str,
    *,
    log_label: str,
    extra_vars: dict[str, str | int],
) -> FileDestination:
    """Build a FileDestination with the filename suffix forced to ``target_extension``.

    If an upstream FileDestinationProvider is connected, it is honored as-is and
    the suffix correction is not applied (the user's upstream wiring wins).
    Otherwise, builds a ``ProjectFileDestination`` from the (possibly suffix-
    corrected) filename string, mirroring ``ProjectFileParameter.build_file``.
    """
    upstream = _upstream_provider_destination(output_file_param)
    if upstream is not None:
        # User explicitly wired a FileOutputSettings (or other provider). The
        # provider's filename is not ours to override; we just write through.
        return upstream

    node = output_file_param._node  # noqa: SLF001
    name = output_file_param._name  # noqa: SLF001
    default_filename = output_file_param._default_filename  # noqa: SLF001
    situation_name = output_file_param._situation_name  # noqa: SLF001

    value = node.get_parameter_value(name)
    user_filename = value if isinstance(value, str) and value else default_filename

    corrected_filename, changed = _force_suffix(user_filename, target_extension)
    if changed:
        logger.warning(
            "%s: '%s' renamed to '%s' so the on-disk extension matches the actual file format.",
            log_label,
            user_filename,
            corrected_filename,
        )

    vars_for_macro: dict[str, str | int] = {**extra_vars}
    if "node_name" not in vars_for_macro:
        vars_for_macro["node_name"] = node.name

    return ProjectFileDestination.from_situation(corrected_filename, situation_name, **vars_for_macro)


# ---------------------------------------------------------------------------
# Public API: image
# ---------------------------------------------------------------------------


def _resolve_image_extension(image_bytes: bytes, requested_format: str | None) -> str:
    if requested_format:
        canonical = _normalize_image_format(requested_format)
        return IMAGE_FORMAT_TO_EXTENSION[canonical]
    sniffed = _sniff_image_format(image_bytes)
    if sniffed is None:
        msg = "Could not determine image format from bytes; pass requested_format explicitly."
        raise ValueError(msg)
    canonical = _normalize_image_format(sniffed)
    return IMAGE_FORMAT_TO_EXTENSION[canonical]


def write_image_bytes(
    output_file_param: ProjectFileParameter,
    image_bytes: bytes,
    *,
    requested_format: str | None = None,
    log_label: str | None = None,
    **extra_vars: str | int,
) -> File:
    """Write ``image_bytes`` to disk; force filename suffix to match the format.

    If ``requested_format`` is given (e.g. ``'jpeg'``, ``'png'``), it overrides
    any sniffed format. Otherwise the format is detected from the bytes via PIL.
    """
    target_extension = _resolve_image_extension(image_bytes, requested_format)
    label = log_label or output_file_param._node.name  # noqa: SLF001
    dest = _build_corrected_destination(output_file_param, target_extension, log_label=label, extra_vars=extra_vars)
    return dest.write_bytes(image_bytes)


async def awrite_image_bytes(
    output_file_param: ProjectFileParameter,
    image_bytes: bytes,
    *,
    requested_format: str | None = None,
    log_label: str | None = None,
    **extra_vars: str | int,
) -> File:
    """Async sibling of ``write_image_bytes``."""
    target_extension = _resolve_image_extension(image_bytes, requested_format)
    label = log_label or output_file_param._node.name  # noqa: SLF001
    dest = _build_corrected_destination(output_file_param, target_extension, log_label=label, extra_vars=extra_vars)
    return await dest.awrite_bytes(image_bytes)


# ---------------------------------------------------------------------------
# Public API: video
# ---------------------------------------------------------------------------


def _resolve_video_extension(video_bytes: bytes, requested_format: str | None) -> str:
    if requested_format:
        canonical = _normalize_video_format(requested_format)
        return VIDEO_FORMAT_TO_EXTENSION[canonical]
    sniffed = _sniff_video_format(video_bytes)
    if sniffed is None:
        msg = "Could not determine video format from bytes; pass requested_format explicitly."
        raise ValueError(msg)
    canonical = _normalize_video_format(sniffed)
    return VIDEO_FORMAT_TO_EXTENSION[canonical]


def write_video_bytes(
    output_file_param: ProjectFileParameter,
    video_bytes: bytes,
    *,
    requested_format: str | None = None,
    log_label: str | None = None,
    **extra_vars: str | int,
) -> File:
    target_extension = _resolve_video_extension(video_bytes, requested_format)
    label = log_label or output_file_param._node.name  # noqa: SLF001
    dest = _build_corrected_destination(output_file_param, target_extension, log_label=label, extra_vars=extra_vars)
    return dest.write_bytes(video_bytes)


async def awrite_video_bytes(
    output_file_param: ProjectFileParameter,
    video_bytes: bytes,
    *,
    requested_format: str | None = None,
    log_label: str | None = None,
    **extra_vars: str | int,
) -> File:
    target_extension = _resolve_video_extension(video_bytes, requested_format)
    label = log_label or output_file_param._node.name  # noqa: SLF001
    dest = _build_corrected_destination(output_file_param, target_extension, log_label=label, extra_vars=extra_vars)
    return await dest.awrite_bytes(video_bytes)


# ---------------------------------------------------------------------------
# Public API: audio
# ---------------------------------------------------------------------------


def _resolve_audio_extension(audio_bytes: bytes, requested_format: str | None) -> str:
    if requested_format:
        canonical = _normalize_audio_format(requested_format)
        return AUDIO_FORMAT_TO_EXTENSION[canonical]
    sniffed = _sniff_audio_format(audio_bytes)
    if sniffed is None:
        msg = "Could not determine audio format from bytes; pass requested_format explicitly."
        raise ValueError(msg)
    canonical = _normalize_audio_format(sniffed)
    return AUDIO_FORMAT_TO_EXTENSION[canonical]


def write_audio_bytes(
    output_file_param: ProjectFileParameter,
    audio_bytes: bytes,
    *,
    requested_format: str | None = None,
    log_label: str | None = None,
    **extra_vars: str | int,
) -> File:
    target_extension = _resolve_audio_extension(audio_bytes, requested_format)
    label = log_label or output_file_param._node.name  # noqa: SLF001
    dest = _build_corrected_destination(output_file_param, target_extension, log_label=label, extra_vars=extra_vars)
    return dest.write_bytes(audio_bytes)


async def awrite_audio_bytes(
    output_file_param: ProjectFileParameter,
    audio_bytes: bytes,
    *,
    requested_format: str | None = None,
    log_label: str | None = None,
    **extra_vars: str | int,
) -> File:
    target_extension = _resolve_audio_extension(audio_bytes, requested_format)
    label = log_label or output_file_param._node.name  # noqa: SLF001
    dest = _build_corrected_destination(output_file_param, target_extension, log_label=label, extra_vars=extra_vars)
    return await dest.awrite_bytes(audio_bytes)
