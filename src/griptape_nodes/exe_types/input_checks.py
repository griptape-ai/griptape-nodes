"""Checks a node runs on its media inputs before a run, against a provider's documented limits.

A request a provider is certain to reject still costs the artist an upload and a wait, and sometimes
credits. These helpers let a node refuse it first, from what it can read locally.

- **Combined checks** (`image_errors`, `video_errors`, `audio_errors`) run every image, video or
  audio check a provider documents in one call, reading the input once. Most nodes need only these.
- **Readers** (`local_size_bytes`, `local_image_info`, `local_video_probe`, `local_audio_probe`)
  read a media input's properties from data already on this machine. `local_video_probe` reads a
  video's container, codec, frame size, durations and frame rates in one ffprobe run, and
  `local_audio_probe` an audio input's container, codec and durations. None of them makes a network
  call or downloads a tool: the video and audio readers use ffprobe only if it is already
  installed. They return None when the value is a remote URL, can't be found or parsed, or when the
  tool to read it is missing or too slow.
- **Checks** (`check_count`, `check_size`, `check_dimensions`, `check_aspect_ratio_range`,
  `check_aspect_ratio_exact`, `check_mime_type`, `check_video_codec`, `check_audio_codec`,
  `check_duration`, `check_frame_rate`) compare one value with a limit and return a `NodeError`
  ready to append to `validate_before_node_run`'s list, or None when the value is within the limit
  or unknown.

A limit is enforced only where it can be read cheaply; anything else is left for the provider.

```python
from griptape_nodes.exe_types.input_checks import image_errors, input_subject


def validate_before_node_run(self) -> list[Exception] | None:
    exceptions = super().validate_before_node_run() or []
    for position, image in enumerate(self.get_parameter_list_value("reference_images"), start=1):
        exceptions.extend(
            image_errors(
                image,
                subject=input_subject("reference images", noun="image", position=position),
                allowed_mime_types=("image/jpeg", "image/png"),
                maximum_bytes=MAX_BYTES,
                docs_url=LIMITS_URL,
            )
        )
    return exceptions or None
```
"""

from __future__ import annotations

import base64
import binascii
import json
import logging
import math
import re
import shutil
import subprocess
import sys
import time
from contextlib import contextmanager
from contextvars import ContextVar
from io import BytesIO
from pathlib import Path
from typing import TYPE_CHECKING, Any, NamedTuple

from PIL import Image, UnidentifiedImageError
from pillow_heif import register_heif_opener
from static_ffmpeg import run as static_ffmpeg_run

from griptape_nodes.exe_types.node_error import NodeError, NodeErrorLink
from griptape_nodes.files.file import File, FileLoadError
from griptape_nodes.files.path_utils import is_url
from griptape_nodes.utils.media_values import MediaKind, coerce_media_url_or_data_uri

if TYPE_CHECKING:
    from collections.abc import Iterator, Sequence

logger = logging.getLogger("griptape_nodes")

# Teaches Pillow to read HEIC and HEIF headers, the format phones save photos in, so they can be
# checked like any other image instead of skipped.
register_heif_opener()

__all__ = [
    "AudioProbe",
    "ImageInfo",
    "VideoProbe",
    "audio_errors",
    "check_aspect_ratio_exact",
    "check_aspect_ratio_range",
    "check_audio_codec",
    "check_count",
    "check_dimensions",
    "check_duration",
    "check_frame_rate",
    "check_mime_type",
    "check_size",
    "check_video_codec",
    "image_errors",
    "input_check_budget",
    "input_subject",
    "local_audio_probe",
    "local_image_info",
    "local_size_bytes",
    "local_video_probe",
    "video_errors",
]

BYTES_PER_MB = 1024 * 1024


LIMITS_LINK_LABEL = "Provider limits"

# How far past a frame-rate limit still passes, as a fraction of the limit. Providers write limits
# like "24-60fps"; NTSC footage at 23.976 or 59.94 fps is within 0.1% of those.
FRAME_RATE_TOLERANCE = 0.01

# Validation runs on the engine's event loop, so every probe blocks it. A local probe takes tens of
# milliseconds; one that takes longer than this is abandoned and the checks that need it (container,
# codec, frame size, duration, frame rate) are skipped.
FFPROBE_TIMEOUT_SECONDS = 2

# How long after a node's validation starts it may still probe video and audio inputs. The engine
# opens one `input_check_budget` around each node's `validate_before_node_run`; once this much time
# has passed, the remaining inputs are skipped rather than probed, so one node's slow probes can't
# add up.
# It counts all of the validation's time, not only probing. The cap is per node: when the engine
# starts several nodes in one pass, each can block for this long.
VALIDATION_PROBE_BUDGET_SECONDS = 5

# When the current validation run's probe budget runs out, as a `time.monotonic()` reading, or None
# outside a run, where each probe is limited only by FFPROBE_TIMEOUT_SECONDS.
_probe_deadline: ContextVar[float | None] = ContextVar("input_check_probe_deadline", default=None)

# EXIF Orientation tag (0x0112) values that display an image rotated a quarter turn.
_EXIF_ORIENTATION_TAG = 0x0112
_QUARTER_TURN_ORIENTATIONS = frozenset({5, 6, 7, 8})

_QUARTER_TURN_DEGREES = 90
_HALF_TURN_DEGREES = 180


class ImageInfo(NamedTuple):
    """An image's or video frame's pixel size, and an image's MIME type read from its header."""

    width: int
    height: int
    mime_type: str | None


def input_subject(parameter: str, *, noun: str, position: int | None = None) -> str:
    """The start of a message naming one input, such as "Image 2 in 'reference images'".

    Args:
        parameter: The parameter's name as the UI shows it.
        noun: What the input is, such as "image" or "video".
        position: The input's 1-based position in a list parameter, or None for a single input.
    """
    if position is None:
        return f"The {noun} in '{parameter}'"
    return f"{noun.capitalize()} {position} in '{parameter}'"


def local_size_bytes(value: Any, *, kind: MediaKind) -> int | None:
    """The size in bytes of a media input, or None if it can't be read locally.

    A data URI is measured from its base64 length. A path, a macro path, or a localhost static file
    URL is measured on disk. A remote URL returns None rather than being fetched.
    """
    location = coerce_media_url_or_data_uri(value, kind=kind)
    if not location:
        return None
    if location.startswith("data:"):
        payload = "".join(location.split(",", 1)[-1].split())
        return len(payload) * 3 // 4 - payload[-2:].count("=")
    path = _local_path(location)
    if path is None:
        return None
    try:
        return path.stat().st_size
    except OSError:
        return None


def local_image_info(value: Any) -> ImageInfo | None:
    """The pixel size and MIME type of an image input, or None if it can't be read locally.

    Reads only the image header (Pillow reads a WebP or AVIF file in full, without decoding it), and
    reports the size as displayed, so a phone photo stored landscape with an EXIF rotation reads as
    portrait. Returns None for a remote URL, for a format Pillow can't open (a RAW camera file, say), and for an
    image over Pillow's decompression-bomb limit (about 179 megapixels), which Pillow refuses to open
    without decoding anything. The checks that use it then skip, rather than reject a valid image or
    override a process-wide Pillow setting.
    """
    location = coerce_media_url_or_data_uri(value, kind="image")
    if not location:
        return None
    source = _image_source(location)
    if source is None:
        return None
    try:
        with Image.open(source) as image:
            image_format = image.format
            width = image.width
            height = image.height
            orientation = _exif_orientation(image)
    # Pillow re-raises NotImplementedError from a format plugin that recognises a file but can't decode
    # it, such as a DDS texture in an unsupported DXGI format. Its AVIF plugin passes on libavif's
    # RuntimeError for a damaged file.
    except (
        OSError,
        UnidentifiedImageError,
        Image.DecompressionBombError,
        ValueError,
        NotImplementedError,
        RuntimeError,
    ) as e:
        logger.debug("Could not read image header for a pre-run input check, skipping it: %s", e)
        return None
    # Phones store a portrait shot landscape with an EXIF orientation of 5 to 8, which displays it a
    # quarter turn round; report the size as displayed, as the video reader does.
    if orientation in _QUARTER_TURN_ORIENTATIONS:
        width, height = height, width
    # Phone and camera JPEGs with Multi-Picture extensions open as MPO; they are JPEG streams.
    if image_format == "MPO":
        mime_type = "image/jpeg"
    else:
        mime_type = Image.MIME.get(image_format or "")
    # Pillow registers no MIME type for some formats it reads, such as DDS and QOI. Name one after
    # its format so a format check can still refuse it, rather than skipping a format it has read.
    if mime_type is None and image_format:
        mime_type = f"image/{image_format.lower()}"
    return ImageInfo(width=width, height=height, mime_type=mime_type)


def _exif_orientation(image: Image.Image) -> int | None:
    """The EXIF Orientation tag of an image Pillow reports at its stored size, read from its header.

    None if it has none, if it can't be read, or if Pillow already reports the displayed size: its
    TIFF plugin applies the orientation itself, so applying it again would turn the image back.
    Pillow's PNG plugin decodes every pixel to look for an eXIf chunk after the image data, so a PNG
    is read only when its header already held one. An eXIf chunk after the data is rare, and such a
    PNG keeps its stored size.
    """
    if image.format == "TIFF":
        return None
    if image.format == "PNG" and "exif" not in image.info:
        return None
    try:
        orientation = image.getexif().get(_EXIF_ORIENTATION_TAG)
    except (OSError, ValueError, SyntaxError) as e:
        logger.debug("Could not read an image's EXIF orientation for a pre-run input check: %s", e)
        return None
    if isinstance(orientation, int):
        return orientation
    return None


class VideoProbe(NamedTuple):
    """A video's displayed frame size, duration and frame rate, read with one ffprobe run.

    `seconds` is the video stream's duration, falling back to the container's. The container's
    duration covers every stream, so a longer audio track can make it longer than the video;
    `container_seconds` keeps it so a minimum can be checked against the longer of the two.
    `fps` is the average frame rate and `nominal_fps` the stream's declared one; they differ only
    for a variable-frame-rate clip, so each frame-rate bound is checked against the easier of them.
    `mime_type` is the container, such as "video/mp4" or "video/quicktime", read from the file rather
    than its name, and `codec` the video stream's, as ffprobe names it, such as "h264" or "hevc".
    Each part is None when ffprobe didn't report it.
    """

    info: ImageInfo | None
    seconds: float | None
    fps: float | None = None
    container_seconds: float | None = None
    nominal_fps: float | None = None
    mime_type: str | None = None
    codec: str | None = None

    @property
    def shortest_seconds(self) -> float | None:
        """The shorter of the stream and container durations, or None if ffprobe reported neither.

        Providers don't say which of the two they measure, so a maximum is checked against this one.
        """
        return min(self._durations(), default=None)

    @property
    def longest_seconds(self) -> float | None:
        """The longer of the stream and container durations, or None if ffprobe reported neither.

        A minimum is checked against this one.
        """
        return max(self._durations(), default=None)

    def _durations(self) -> list[float]:
        return [s for s in (self.seconds, self.container_seconds) if s is not None]


# video_errors' default for `probe`, told apart by identity from a None the caller passes for a video
# it couldn't read, so that video isn't probed a second time.
_PROBE_NOT_GIVEN = VideoProbe(info=None, seconds=None)


@contextmanager
def input_check_budget(seconds: float = VALIDATION_PROBE_BUDGET_SECONDS) -> Iterator[None]:
    """Stop the video and audio probes inside this block once `seconds` have passed since it opened.

    The engine opens one around each node's `validate_before_node_run`, so a node checking several
    video or audio inputs probes for at most `seconds` in all. The time counts from when the block opens, so it
    includes any other checks the node runs first. Inside it, each probe gets the smaller of
    `FFPROBE_TIMEOUT_SECONDS` and the time left, and a probe that would start with no time left is
    skipped. Opened inside another budget, it can shorten the time left but never
    extend it.
    """
    deadline = time.monotonic() + seconds
    # Nested inside another budget, this one can only end sooner, so the engine's cap always holds.
    outer = _probe_deadline.get()
    if outer is not None and outer < deadline:
        deadline = outer
    token = _probe_deadline.set(deadline)
    try:
        yield
    finally:
        _probe_deadline.reset(token)


def local_video_probe(value: Any) -> VideoProbe | None:
    """A video input's container, codec, frame size, duration and frame rate, or None if unreadable here.

    One ffprobe run reads them all, so a node checking several on the same clip waits on at most
    one `FFPROBE_TIMEOUT_SECONDS`, and the values come from the same read of the file. Inside an
    `input_check_budget`, the probe also stops when the budget does.
    Probes only a file on this machine, with an ffprobe that is already installed; see
    `_run_ffprobe`.
    """
    data = _run_ffprobe(value, ["-show_format", "-select_streams", "v:0", "-show_streams"], kind="video")
    if data is None:
        return None
    stream_seconds = _seconds(_first_stream(data).get("duration"))
    container_seconds = _seconds(data.get("format", {}).get("duration"))
    seconds = stream_seconds
    if seconds is None:
        seconds = container_seconds
    return VideoProbe(
        info=_frame_size(data),
        seconds=seconds,
        fps=_frame_rate(data),
        container_seconds=container_seconds,
        nominal_fps=_nominal_frame_rate(data),
        mime_type=_video_mime_type(data),
        codec=_video_codec(data),
    )


class AudioProbe(NamedTuple):
    """An audio input's container, codec and duration, read with one ffprobe run.

    `mime_type` is the container, such as "audio/mpeg" or "audio/wav", read from the file rather than
    its name. `codec` is the first audio stream's codec as ffprobe names it, such as "mp3", "aac" or
    "pcm_s16le", and `profile` its profile where it has one, such as "LC" for AAC-LC. `seconds` is the
    audio stream's duration, falling back to the file's; `container_seconds` keeps the file's, which a
    longer video track can stretch. Each part is None when ffprobe didn't report it.
    """

    mime_type: str | None
    codec: str | None
    profile: str | None
    seconds: float | None
    container_seconds: float | None = None

    @property
    def shortest_seconds(self) -> float | None:
        """The shorter of the stream and container durations; a maximum is checked against this one."""
        return min(self._durations(), default=None)

    @property
    def longest_seconds(self) -> float | None:
        """The longer of the stream and container durations; a minimum is checked against this one."""
        return max(self._durations(), default=None)

    def _durations(self) -> list[float]:
        return [s for s in (self.seconds, self.container_seconds) if s is not None]


def local_audio_probe(value: Any) -> AudioProbe | None:
    """The container, codec and duration of an audio input, or None if it can't be read locally.

    Reads the first audio stream, so an audio track inside a video file is read too. Probes only a
    file on this machine, with an ffprobe that is already installed, under the same time limits as
    `local_video_probe`; see `_run_ffprobe`.
    """
    data = _run_ffprobe(value, ["-show_format", "-select_streams", "a:0", "-show_streams"], kind="audio")
    if data is None:
        return None
    stream = _first_stream(data)
    if not stream:
        return None
    stream_seconds = _seconds(stream.get("duration"))
    container_seconds = _seconds(data.get("format", {}).get("duration"))
    seconds = stream_seconds
    if seconds is None:
        seconds = container_seconds
    return AudioProbe(
        mime_type=_audio_mime_type(data),
        codec=_stream_text(stream, "codec_name"),
        profile=_stream_text(stream, "profile"),
        seconds=seconds,
        container_seconds=container_seconds,
    )


def check_count(
    count: int, *, maximum: int, parameter: str, noun: str = "items", docs_url: str | None = None
) -> NodeError | None:
    """An error when more inputs are connected than the provider accepts.

    Args:
        count: How many inputs are connected.
        maximum: The most the provider accepts.
        parameter: The parameter's name as the UI shows it.
        noun: The plural of what is counted, such as "images".
        docs_url: The provider's page documenting the limit.
    """
    if count <= maximum:
        return None
    return _error(
        f"{count} {noun} are connected to '{parameter}' and the limit is {maximum}. Remove {count - maximum}.",
        docs_url,
    )


def check_size(  # noqa: PLR0913
    size_bytes: int | None,
    *,
    maximum_bytes: int,
    subject: str,
    fix: str = "Use a smaller file.",
    strict: bool = False,
    docs_url: str | None = None,
) -> NodeError | None:
    """An error when an input file is larger than the provider accepts.

    Args:
        size_bytes: The file's size, from `local_size_bytes`. None skips the check.
        maximum_bytes: The largest file the provider accepts, or with `strict`, the size every file
            must be under.
        subject: The input, from `input_subject`.
        fix: What the artist can do about it.
        strict: For a provider that writes "less than 30 MB": a file of exactly `maximum_bytes` is
            refused too.
        docs_url: The provider's page documenting the limit.
    """
    if size_bytes is None:
        return None
    if strict and size_bytes >= maximum_bytes:
        limit = _format_limit(maximum_bytes / BYTES_PER_MB)
        # A file at exactly the limit is the one a strict limit adds; printed past it, it would round
        # onto the allowed side and read as smaller than the limit.
        if size_bytes == maximum_bytes:
            shown = f"exactly {limit}"
        else:
            shown = _format_past(size_bytes / BYTES_PER_MB, maximum_bytes / BYTES_PER_MB, 1)
        return _error(f"{subject} is {shown} MB and it must be under {limit} MB. {fix}", docs_url)
    if size_bytes <= maximum_bytes:
        return None
    return _error(
        f"{subject} is {_format_past(size_bytes / BYTES_PER_MB, maximum_bytes / BYTES_PER_MB, 1)} MB and the limit "
        f"is {_format_limit(maximum_bytes / BYTES_PER_MB)} MB. {fix}",
        docs_url,
    )


def check_dimensions(  # noqa: PLR0913
    info: ImageInfo | None,
    *,
    subject: str,
    min_side: int | None = None,
    max_side: int | None = None,
    min_megapixels: float | None = None,
    max_megapixels: float | None = None,
    docs_url: str | None = None,
) -> NodeError | None:
    """An error when an image or video frame's pixel size is outside what the provider accepts.

    Args:
        info: The pixel size, from `local_image_info` or a `local_video_probe` result's `info`. None skips
            the check.
        subject: The input, from `input_subject`.
        min_side: The fewest pixels accepted for the width and for the height.
        max_side: The most pixels accepted for the width and for the height.
        min_megapixels: The fewest pixels accepted in total, in millions.
        max_megapixels: The most pixels accepted in total, in millions.
        docs_url: The provider's page documenting the limit.
    """
    if info is None:
        return None
    size = f"{info.width}x{info.height}"
    if min_side is not None and min(info.width, info.height) < min_side:
        return _error(
            f"{subject} is {size} and each side must be at least {min_side} pixels. Use a larger one.", docs_url
        )
    if max_side is not None and max(info.width, info.height) > max_side:
        return _error(
            f"{subject} is {size} and each side must be at most {max_side} pixels. Resize it smaller.", docs_url
        )
    megapixels = info.width * info.height / 1_000_000
    if min_megapixels is not None and megapixels < min_megapixels:
        return _error(
            f"{subject} is {size} ({_format_past(megapixels, min_megapixels, 1)} megapixels) and the minimum is "
            f"{_format_limit(min_megapixels, round_up=True)} megapixels. Use a larger one.",
            docs_url,
        )
    if max_megapixels is not None and megapixels > max_megapixels:
        return _error(
            f"{subject} is {size} ({_format_past(megapixels, max_megapixels, 1)} megapixels) and the limit is "
            f"{_format_limit(max_megapixels)} megapixels. Resize it smaller.",
            docs_url,
        )
    return None


def check_aspect_ratio_range(
    info: ImageInfo | None, *, subject: str, widest: str, tallest: str, docs_url: str | None = None
) -> NodeError | None:
    """An error when an image or video frame is wider or taller than the provider accepts.

    Args:
        info: The pixel size, from `local_image_info` or a `local_video_probe` result's `info`. None skips
            the check.
        subject: The input, from `input_subject`.
        widest: The widest ratio accepted, as the provider writes it, such as "3:1".
        tallest: The tallest ratio accepted, such as "1:3".
        docs_url: The provider's page documenting the limit.

    Raises:
        ValueError: If `widest` or `tallest` isn't a ratio such as "16:9".
    """
    widest_ratio = _parse_ratio(widest)
    tallest_ratio = _parse_ratio(tallest)
    if info is None or info.height == 0:
        return None
    ratio = info.width / info.height
    if tallest_ratio <= ratio <= widest_ratio:
        return None
    if ratio > widest_ratio:
        shape = "wide"
    else:
        shape = "tall"
    return _error(
        f"{subject} is {info.width}x{info.height}, which is too {shape}. The aspect ratio must be between "
        f"{tallest} and {widest}. Crop it.",
        docs_url,
    )


def check_aspect_ratio_exact(
    info: ImageInfo | None, *, subject: str, ratios: Sequence[str], docs_url: str | None = None
) -> NodeError | None:
    """An error when an image or video frame isn't one of the exact aspect ratios the provider accepts.

    For a provider that takes only certain shapes, such as "16:9 or 9:16", rather than a range. A
    frame matches a ratio when either side is within a pixel of what the ratio makes it from the other,
    so a size rounded to whole pixels, such as 854x480 for 16:9 or 406x720 for 9:16, still matches.

    Args:
        info: The pixel size, from `local_image_info` or a `local_video_probe` result's `info`. None skips
            the check.
        subject: The input, from `input_subject`.
        ratios: The ratios accepted, as the provider writes them, such as ("16:9", "9:16").
        docs_url: The provider's page documenting the limit.

    Raises:
        ValueError: If `ratios` is empty or one of them isn't a ratio such as "16:9".
        TypeError: If `ratios` is a single string rather than a sequence of ratios.
    """
    _require_valid_exact_ratios(ratios)
    if info is None or info.height == 0:
        return None
    for name in ratios:
        ratio = _parse_ratio(name)
        # Allow a pixel of rounding on whichever side was derived from the other.
        if abs(info.width / ratio - info.height) <= 1 or abs(info.height * ratio - info.width) <= 1:
            return None
    return _error(
        f"{subject} is {info.width}x{info.height}, and its aspect ratio must be {_join_or(list(ratios))}. Crop it.",
        docs_url,
    )


def check_mime_type(
    mime_type: str | None, *, subject: str, allowed: Sequence[str], docs_url: str | None = None
) -> NodeError | None:
    """An error when an input's format isn't one the provider accepts.

    Args:
        mime_type: The input's MIME type, such as from `local_image_info`. None skips the check.
        subject: The input, from `input_subject`.
        allowed: The MIME types the provider accepts, such as ("image/jpeg", "image/png").
        docs_url: The provider's page documenting the limit.

    Raises:
        TypeError: If `allowed` is a single string rather than a sequence of MIME types.
    """
    _require_mime_type_sequence(allowed)
    return _mime_type_error(mime_type, subject=subject, allowed=allowed, docs_url=docs_url)


def _mime_type_error(
    mime_type: str | None,
    *,
    subject: str,
    allowed: Sequence[str],
    docs_url: str | None,
    also_matching: Sequence[str] = (),
) -> NodeError | None:
    """`check_mime_type`, with `also_matching` names that widen the match but aren't listed in the message."""
    if mime_type is None or not allowed or _is_allowed(mime_type, (*allowed, *also_matching)):
        return None
    # Names that differ but read the same, such as audio/wav and audio/x-wav, are listed once.
    formats = _join_or(list(dict.fromkeys(_format_name(name) for name in allowed)))
    current = _format_name(mime_type)
    return _error(f"{subject} is in {current} format. Convert it to {formats}.", docs_url)


def check_video_codec(
    codec: str | None, *, subject: str, allowed: Sequence[str], docs_url: str | None = None
) -> NodeError | None:
    """An error when a video's codec isn't one the provider accepts.

    Args:
        codec: The video stream's codec as ffprobe names it, from `local_video_probe`, such as "h264".
            None skips the check.
        subject: The input, from `input_subject`.
        allowed: The codecs the provider accepts, such as ("h264", "hevc"). They may be written as
            ffprobe names them or as providers do ("H.264", "HEVC", "AVC"); case doesn't matter.
        docs_url: The provider's page documenting the limit.

    Raises:
        TypeError: If `allowed` is a single string rather than a sequence of codecs.
    """
    return _codec_error(codec, kind="a video", example="h264", subject=subject, allowed=allowed, docs_url=docs_url)


def check_audio_codec(
    codec: str | None, *, subject: str, allowed: Sequence[str], docs_url: str | None = None
) -> NodeError | None:
    """An error when an audio input's codec isn't one the provider accepts.

    Args:
        codec: The audio stream's codec as ffprobe names it, from `local_audio_probe`, such as "mp3".
            None skips the check.
        subject: The input, from `input_subject`.
        allowed: The codecs the provider accepts, such as ("mp3", "aac"). They may be written as ffprobe
            names them or as providers do ("MP3", "AAC-LC"); case doesn't matter. A profile such as
            AAC-LC matches its codec, as the profile isn't checked.
        docs_url: The provider's page documenting the limit.

    Raises:
        TypeError: If `allowed` is a single string rather than a sequence of codecs.
    """
    return _codec_error(codec, kind="an audio", example="mp3", subject=subject, allowed=allowed, docs_url=docs_url)


def check_duration(  # noqa: PLR0913
    seconds: float | None,
    *,
    subject: str,
    minimum: float | None = None,
    maximum: float | None = None,
    fix: str | None = None,
    docs_url: str | None = None,
) -> NodeError | None:
    """An error when an audio or video input is shorter or longer than the provider accepts.

    Args:
        seconds: The input's duration. For a video, pass a `local_video_probe` result's
            `shortest_seconds` for a maximum or `longest_seconds` for a minimum, the readings
            `video_errors` uses. None skips the check.
        subject: The input, from `input_subject`.
        minimum: The shortest input accepted, in seconds.
        maximum: The longest input accepted, in seconds.
        fix: What the artist can do about it. Defaults to trimming or using a longer clip.
        docs_url: The provider's page documenting the limit.
    """
    if seconds is None:
        return None
    if maximum is not None and seconds > maximum:
        next_step = fix or "Use a Trim Video node to shorten it."
        return _error(
            f"{subject} is {_format_past(seconds, maximum, 2)} seconds long and the limit is {_format_limit(maximum)}. {next_step}",
            docs_url,
        )
    if minimum is not None and seconds < minimum:
        next_step = fix or "Use a longer clip."
        return _error(
            f"{subject} is {_format_past(seconds, minimum, 2)} seconds long and the minimum is {_format_limit(minimum, round_up=True)}. {next_step}",
            docs_url,
        )
    return None


def check_frame_rate(  # noqa: PLR0913
    fps: float | None,
    *,
    subject: str,
    minimum: float | None = None,
    maximum: float | None = None,
    tolerance: float = FRAME_RATE_TOLERANCE,
    docs_url: str | None = None,
) -> NodeError | None:
    """An error when a video's frame rate is outside what the provider accepts.

    Args:
        fps: The frame rate, from `local_video_probe`. None skips the check.
        subject: The input, from `input_subject`.
        minimum: The lowest frame rate accepted.
        maximum: The highest frame rate accepted.
        tolerance: How far past a limit, as a fraction of it, still passes. The default lets NTSC
            footage at 23.976 fps through a "24 fps" minimum and 59.94 fps through a "60 fps" one.
        docs_url: The provider's page documenting the limit.
    """
    if fps is None:
        return None
    if minimum is not None and fps < minimum * (1 - tolerance):
        return _error(
            f"{subject} is {_format_past(fps, minimum, 0)} fps and the minimum is "
            f"{_format_limit(minimum, round_up=True)} fps. Re-export it at a higher frame rate.",
            docs_url,
        )
    if maximum is not None and fps > maximum * (1 + tolerance):
        return _error(
            f"{subject} is {_format_past(fps, maximum, 0)} fps and the maximum is {_format_limit(maximum)} fps. "
            "Re-export it at a lower frame rate.",
            docs_url,
        )
    return None


def image_errors(  # noqa: PLR0913
    image: Any,
    *,
    subject: str,
    allowed_mime_types: Sequence[str] = (),
    maximum_bytes: int | None = None,
    strict_maximum_bytes: bool = False,
    min_side: int | None = None,
    max_side: int | None = None,
    min_megapixels: float | None = None,
    max_megapixels: float | None = None,
    widest: str | None = None,
    tallest: str | None = None,
    exact_aspect_ratios: Sequence[str] = (),
    docs_url: str | None = None,
) -> list[NodeError]:
    """Every provider image limit an image input breaks, in one call.

    Reads the image once and runs only the checks whose limits are given: the format when
    `allowed_mime_types` is set, the file size with `maximum_bytes`, the sides and area with
    `min_side`, `max_side`, `min_megapixels` or `max_megapixels`, the aspect ratio when both
    `widest` and `tallest` are set, and the exact shape with `exact_aspect_ratios`. Like the checks
    it runs, it skips anything it can't read locally.

    Args:
        image: The image input.
        subject: The input, from `input_subject`.
        allowed_mime_types: The formats the provider accepts, such as ("image/jpeg", "image/png").
        maximum_bytes: The largest file the provider accepts.
        strict_maximum_bytes: For a provider that writes "less than": a file of exactly
            `maximum_bytes` is refused too.
        min_side: The fewest pixels accepted for the width and for the height.
        max_side: The most pixels accepted for the width and for the height.
        min_megapixels: The fewest pixels accepted in total, in millions.
        max_megapixels: The most pixels accepted in total, in millions.
        widest: The widest aspect ratio accepted, as the provider writes it, such as "2.5:1".
        tallest: The tallest aspect ratio accepted, such as "1:2.5". Pass both bounds or neither.
        exact_aspect_ratios: For a provider that takes only certain shapes rather than a range, those
            ratios, such as ("16:9", "9:16"). See `check_aspect_ratio_exact`.
        docs_url: The provider's page documenting the limits.

    Raises:
        ValueError: If only one of `widest` and `tallest` is given, or one isn't a ratio such as "16:9".
        TypeError: If `allowed_mime_types` is a single string.
    """
    _require_mime_type_sequence(allowed_mime_types)
    _require_valid_aspect_ratio_bounds(widest, tallest)
    if exact_aspect_ratios:
        _require_valid_exact_ratios(exact_aspect_ratios)
    # Reduce the input to one string once, and hand that to both readers.
    location = coerce_media_url_or_data_uri(image, kind="image")
    info = local_image_info(location)
    errors: list[NodeError | None] = []
    if allowed_mime_types:
        mime_type = None
        if info is not None:
            mime_type = info.mime_type
        errors.append(check_mime_type(mime_type, subject=subject, allowed=allowed_mime_types, docs_url=docs_url))
    if maximum_bytes is not None:
        errors.append(
            check_size(
                local_size_bytes(location, kind="image"),
                maximum_bytes=maximum_bytes,
                subject=subject,
                strict=strict_maximum_bytes,
                docs_url=docs_url,
            )
        )
    errors.extend(
        _frame_errors(
            info,
            subject=subject,
            min_side=min_side,
            max_side=max_side,
            min_megapixels=min_megapixels,
            max_megapixels=max_megapixels,
            widest=widest,
            tallest=tallest,
            exact_aspect_ratios=exact_aspect_ratios,
            docs_url=docs_url,
        )
    )
    return [error for error in errors if error]


def video_errors(  # noqa: PLR0913
    video: Any,
    *,
    subject: str,
    maximum_bytes: int | None = None,
    strict_maximum_bytes: bool = False,
    min_seconds: float | None = None,
    max_seconds: float | None = None,
    min_side: int | None = None,
    max_side: int | None = None,
    min_megapixels: float | None = None,
    max_megapixels: float | None = None,
    widest: str | None = None,
    tallest: str | None = None,
    exact_aspect_ratios: Sequence[str] = (),
    min_fps: float | None = None,
    max_fps: float | None = None,
    allowed_mime_types: Sequence[str] = (),
    allowed_codecs: Sequence[str] = (),
    duration_fix: str | None = None,
    docs_url: str | None = None,
    probe: VideoProbe | None = _PROBE_NOT_GIVEN,
) -> list[NodeError]:
    """Every provider video limit a video input breaks, in one call.

    Probes the video once, with `local_video_probe`, and runs only the checks whose limits are
    given: the file size with `maximum_bytes`, the duration with `min_seconds` or `max_seconds`,
    the displayed frame's sides and area with `min_side`, `max_side`, `min_megapixels` or
    `max_megapixels`, the aspect ratio when both `widest` and `tallest` are set, the exact shape with
    `exact_aspect_ratios`, the frame rate with `min_fps` or `max_fps`, the container with
    `allowed_mime_types`, and the codec with `allowed_codecs`. Like the checks it runs, it skips
    anything it can't read locally.

    Args:
        video: The video input.
        subject: The input, from `input_subject`.
        maximum_bytes: The largest file the provider accepts.
        strict_maximum_bytes: For a provider that writes "less than": a file of exactly
            `maximum_bytes` is refused too.
        min_seconds: The shortest clip accepted.
        max_seconds: The longest clip accepted.
        min_side: The fewest pixels accepted for the width and for the height.
        max_side: The most pixels accepted for the width and for the height.
        min_megapixels: The fewest pixels accepted in total, in millions.
        max_megapixels: The most pixels accepted in total, in millions.
        widest: The widest aspect ratio accepted, as the provider writes it, such as "2.5:1".
        tallest: The tallest aspect ratio accepted, such as "1:2.5". Pass both bounds or neither.
        exact_aspect_ratios: For a provider that takes only certain shapes rather than a range, those
            ratios, such as ("16:9", "9:16"). See `check_aspect_ratio_exact`.
        min_fps: The lowest frame rate accepted.
        max_fps: The highest frame rate accepted.
        allowed_mime_types: The containers the provider accepts, such as ("video/mp4", "video/quicktime").
            The container is read from the file, so a MOV renamed to .mp4 is still a MOV.
        allowed_codecs: The video codecs the provider accepts, as ffprobe names them, such as
            ("h264", "hevc").
        duration_fix: What the artist can do about a clip of the wrong length. Defaults to
            `check_duration`'s.
        docs_url: The provider's page documenting the limits.
        probe: The video's `local_video_probe` result, when the node has already read it for a check
            of its own, such as a total duration across several videos; None for a video it
            couldn't read. Left out, the video is probed here.

    Raises:
        ValueError: If only one of `widest` and `tallest` is given, or one isn't a ratio such as "16:9".
        TypeError: If `allowed_mime_types` or `allowed_codecs` is a single string.
    """
    _require_valid_aspect_ratio_bounds(widest, tallest)
    if exact_aspect_ratios:
        _require_valid_exact_ratios(exact_aspect_ratios)
    _require_mime_type_sequence(allowed_mime_types)
    errors: list[NodeError | None] = []
    if maximum_bytes is not None:
        errors.append(
            check_size(
                local_size_bytes(video, kind="video"),
                maximum_bytes=maximum_bytes,
                subject=subject,
                strict=strict_maximum_bytes,
                docs_url=docs_url,
            )
        )
    needs_frame = (
        min_side is not None
        or max_side is not None
        or min_megapixels is not None
        or max_megapixels is not None
        or (widest is not None and tallest is not None)
        or bool(exact_aspect_ratios)
    )
    needs_fps = min_fps is not None or max_fps is not None
    needs_encoding = bool(allowed_mime_types) or bool(allowed_codecs)
    if min_seconds is None and max_seconds is None and not needs_frame and not needs_fps and not needs_encoding:
        return [error for error in errors if error]
    if probe is _PROBE_NOT_GIVEN:
        probe = local_video_probe(video)
    info = None
    if probe is not None:
        info = probe.info
    errors.extend(
        _encoding_errors(
            probe,
            subject=subject,
            allowed_mime_types=allowed_mime_types,
            allowed_codecs=allowed_codecs,
            docs_url=docs_url,
        )
    )
    errors.extend(
        _duration_errors(
            probe,
            subject=subject,
            min_seconds=min_seconds,
            max_seconds=max_seconds,
            fix=duration_fix,
            docs_url=docs_url,
        )
    )
    errors.extend(
        _frame_errors(
            info,
            subject=subject,
            min_side=min_side,
            max_side=max_side,
            min_megapixels=min_megapixels,
            max_megapixels=max_megapixels,
            widest=widest,
            tallest=tallest,
            exact_aspect_ratios=exact_aspect_ratios,
            docs_url=docs_url,
        )
    )
    # A variable-frame-rate clip's average and declared rates differ, and providers don't say which
    # they mean, so each bound uses the rate it's easier to meet, as the duration checks do.
    rates = _frame_rates(probe)
    if max_fps is not None:
        errors.append(check_frame_rate(min(rates, default=None), subject=subject, maximum=max_fps, docs_url=docs_url))
    if min_fps is not None:
        errors.append(check_frame_rate(max(rates, default=None), subject=subject, minimum=min_fps, docs_url=docs_url))
    return [error for error in errors if error]


def audio_errors(  # noqa: PLR0913
    audio: Any,
    *,
    subject: str,
    allowed_mime_types: Sequence[str] = (),
    allowed_codecs: Sequence[str] = (),
    maximum_bytes: int | None = None,
    strict_maximum_bytes: bool = False,
    min_seconds: float | None = None,
    max_seconds: float | None = None,
    duration_fix: str | None = None,
    docs_url: str | None = None,
) -> list[NodeError]:
    """Every provider audio limit an audio input breaks, in one call.

    Probes the audio once, with `local_audio_probe`, and runs only the checks whose limits are given:
    the container with `allowed_mime_types`, the codec with `allowed_codecs`, the file size with
    `maximum_bytes`, and the duration with `min_seconds` or `max_seconds`. Like the checks it runs,
    it skips anything it can't read locally.

    Args:
        audio: The audio input.
        subject: The input, from `input_subject`.
        allowed_mime_types: The containers the provider accepts, such as ("audio/mpeg", "audio/wav").
            The container is read from the file, so an MP3 renamed to .wav is still an MP3.
        allowed_codecs: The audio codecs the provider accepts, as ffprobe names them, such as
            ("mp3", "aac"). A WAV's codec is a PCM one, such as "pcm_s16le".
        maximum_bytes: The largest file the provider accepts.
        strict_maximum_bytes: For a provider that writes "less than": a file of exactly
            `maximum_bytes` is refused too.
        min_seconds: The shortest clip accepted.
        max_seconds: The longest clip accepted.
        duration_fix: What the artist can do about a clip of the wrong length. Defaults to trimming it
            in an audio editor, or using a longer clip.
        docs_url: The provider's page documenting the limits.

    Raises:
        TypeError: If `allowed_mime_types` or `allowed_codecs` is a single string.
    """
    _require_mime_type_sequence(allowed_mime_types)
    errors: list[NodeError | None] = []
    if maximum_bytes is not None:
        errors.append(
            check_size(
                local_size_bytes(audio, kind="audio"),
                maximum_bytes=maximum_bytes,
                subject=subject,
                strict=strict_maximum_bytes,
                docs_url=docs_url,
            )
        )
    needs_probe = bool(allowed_mime_types) or bool(allowed_codecs) or min_seconds is not None or max_seconds is not None
    if not needs_probe:
        return [error for error in errors if error]
    probe = local_audio_probe(audio)
    mime_type = None
    codec = None
    if probe is not None:
        mime_type = probe.mime_type
        codec = probe.codec
    if allowed_mime_types:
        errors.append(
            _mime_type_error(
                mime_type,
                subject=subject,
                allowed=allowed_mime_types,
                docs_url=docs_url,
                also_matching=_audio_readings_of(allowed_mime_types),
            )
        )
    if allowed_codecs:
        errors.append(check_audio_codec(codec, subject=subject, allowed=allowed_codecs, docs_url=docs_url))
    errors.extend(
        _duration_errors(
            probe,
            subject=subject,
            min_seconds=min_seconds,
            max_seconds=max_seconds,
            fix=duration_fix,
            docs_url=docs_url,
            too_long_fix="Trim it in an audio editor.",
        )
    )
    return [error for error in errors if error]


def _codec_error(  # noqa: PLR0913
    codec: str | None, *, kind: str, example: str, subject: str, allowed: Sequence[str], docs_url: str | None
) -> NodeError | None:
    """`check_video_codec` and `check_audio_codec`: `kind` and `example` only shape the TypeError."""
    if isinstance(allowed, str):
        msg = (
            f"Attempted to check {kind} codec. Failed because the allowed codecs were one string; "
            f"pass a tuple such as ('{example}',)."
        )
        raise TypeError(msg)
    # An empty list is no limit, as the combined checks treat it.
    if codec is None or not allowed:
        return None
    # A codec matches however a provider writes it ("H.264", "AVC", "h264"), so a refusal never asks
    # for the input's own codec. Names that read the same are listed once.
    if any(_codec_matches(codec, name) for name in allowed):
        return None
    shown = _codec_name(codec)
    # Last guard: a refusal that would list the input's own codec, under any spelling not matched
    # above, would contradict itself, so the codec is let through instead.
    if any(_squash(_codec_name(name)) == _squash(shown) for name in allowed):
        return None
    codecs = _join_or(list(dict.fromkeys(_codec_name(name) for name in allowed)))
    return _error(f"{subject} is encoded as {shown}. Re-encode it as {codecs}.", docs_url)


def _audio_readings_of(allowed: Sequence[str]) -> tuple[str, ...]:
    """The extra names an audio check matches for the video containers a provider lists.

    A video file's audio reads under its container's audio name (an MP4's as audio/mp4, an MKV's as
    audio/x-matroska), and a provider listing the video container takes that file. The names widen
    the match only; a refusal lists just the names the provider wrote.
    """
    readings = (_VIDEO_TO_AUDIO_CONTAINER.get(_canonical_mime_type(name)) for name in allowed)
    return tuple(reading for reading in readings if reading is not None)


def _encoding_errors(
    probe: VideoProbe | None,
    *,
    subject: str,
    allowed_mime_types: Sequence[str],
    allowed_codecs: Sequence[str],
    docs_url: str | None,
) -> list[NodeError | None]:
    """`video_errors`' container and codec checks, for those whose limits are given."""
    mime_type = None
    codec = None
    if probe is not None:
        mime_type = probe.mime_type
        codec = probe.codec
    errors: list[NodeError | None] = []
    if allowed_mime_types:
        errors.append(check_mime_type(mime_type, subject=subject, allowed=allowed_mime_types, docs_url=docs_url))
    if allowed_codecs:
        errors.append(check_video_codec(codec, subject=subject, allowed=allowed_codecs, docs_url=docs_url))
    return errors


def _frame_errors(  # noqa: PLR0913
    info: ImageInfo | None,
    *,
    subject: str,
    min_side: int | None,
    max_side: int | None,
    min_megapixels: float | None,
    max_megapixels: float | None,
    widest: str | None,
    tallest: str | None,
    exact_aspect_ratios: Sequence[str],
    docs_url: str | None,
) -> list[NodeError | None]:
    """The pixel-size and shape checks `image_errors` and `video_errors` share, for those whose limits are given."""
    errors: list[NodeError | None] = []
    if min_side is not None or max_side is not None or min_megapixels is not None or max_megapixels is not None:
        errors.append(
            check_dimensions(
                info,
                subject=subject,
                min_side=min_side,
                max_side=max_side,
                min_megapixels=min_megapixels,
                max_megapixels=max_megapixels,
                docs_url=docs_url,
            )
        )
    if widest is not None and tallest is not None:
        errors.append(
            check_aspect_ratio_range(info, subject=subject, widest=widest, tallest=tallest, docs_url=docs_url)
        )
    if exact_aspect_ratios:
        errors.append(check_aspect_ratio_exact(info, subject=subject, ratios=exact_aspect_ratios, docs_url=docs_url))
    return errors


def _duration_errors(  # noqa: PLR0913
    probe: VideoProbe | AudioProbe | None,
    *,
    subject: str,
    min_seconds: float | None,
    max_seconds: float | None,
    fix: str | None,
    docs_url: str | None,
    too_long_fix: str | None = None,
) -> list[NodeError | None]:
    """`video_errors`' and `audio_errors`' duration checks.

    `fix` is the node's own advice for both bounds. Without it, `too_long_fix` replaces
    `check_duration`'s default for a clip over the maximum, which suggests a video trim node.

    Providers don't say whether they measure the video stream or the whole container, so each bound
    uses the reading it's easier to meet: the shorter for a maximum, the longer for a minimum.
    """
    shortest = None
    longest = None
    if probe is not None:
        shortest = probe.shortest_seconds
        longest = probe.longest_seconds
    errors: list[NodeError | None] = []
    if max_seconds is not None:
        maximum_fix = fix
        if maximum_fix is None:
            maximum_fix = too_long_fix
        errors.append(
            check_duration(shortest, subject=subject, maximum=max_seconds, fix=maximum_fix, docs_url=docs_url)
        )
    if min_seconds is not None:
        errors.append(check_duration(longest, subject=subject, minimum=min_seconds, fix=fix, docs_url=docs_url))
    return errors


def _frame_rates(probe: VideoProbe | None) -> list[float]:
    """A probe's average and declared frame rates, leaving out the ones it doesn't have."""
    if probe is None:
        return []
    return [rate for rate in (probe.fps, probe.nominal_fps) if rate is not None]


def _is_allowed(mime_type: str, allowed: Sequence[str]) -> bool:
    """Whether a MIME type is one the provider accepts, under any name the provider writes it as.

    Providers and Python's `mimetypes` give some formats other names than the readers return, such
    as "audio/mp3" for "audio/mpeg" or "image/heic" for "image/heif", so both sides are compared by
    their usual name.
    """
    canonical = _canonical_mime_type(mime_type)
    shown = _format_name(mime_type)
    # A name that reads the same as the input's in a message also matches, so a refusal can never
    # name the input's format among the ones it asks for.
    return any(_canonical_mime_type(name) == canonical or _format_name(name) == shown for name in allowed)


def _canonical_mime_type(mime_type: str) -> str:
    """A MIME type's usual name, so its other names, and any capitalisation of them, compare equal to it."""
    # Parameters such as "; codecs=opus" name a codec, which `allowed_codecs` checks, not a format.
    folded = mime_type.split(";", 1)[0].strip().lower()
    return _MIME_ALIASES.get(folded, folded)


def _require_mime_type_sequence(allowed: Sequence[str]) -> None:
    """Raise when `allowed` is one string: it would match by substring and list its letters."""
    if isinstance(allowed, str):
        msg = (
            "Attempted to check a format. Failed because the allowed formats were one string; "
            "pass a tuple such as ('image/png',)."
        )
        raise TypeError(msg)


def _require_valid_exact_ratios(ratios: Sequence[str]) -> None:
    """Raise when `ratios` can't be checked: one string, empty, or holding something that isn't a ratio."""
    if isinstance(ratios, str):
        msg = (
            "Attempted to check an exact aspect ratio. Failed because the ratios were one string; "
            "pass a tuple such as ('16:9', '9:16')."
        )
        raise TypeError(msg)
    if not ratios:
        msg = "Attempted to check an exact aspect ratio. Failed because no ratios were given."
        raise ValueError(msg)
    for name in ratios:
        _parse_ratio(name)


def _require_valid_aspect_ratio_bounds(widest: str | None, tallest: str | None) -> None:
    """Raise when the aspect-ratio bounds can't be checked: only one is given, or one isn't a ratio.

    Runs before anything is read, so a bad bound fails on every call, not only once an input can be read.
    """
    if (widest is None) != (tallest is None):
        msg = "Attempted to check an aspect ratio. Failed because only one of widest and tallest was given; pass both."
        raise ValueError(msg)
    for bound in (widest, tallest):
        if bound is not None:
            _parse_ratio(bound)


def _error(message: str, docs_url: str | None) -> NodeError:
    if not docs_url:
        return NodeError(message, links=None)
    return NodeError(message, links=[NodeErrorLink(label=LIMITS_LINK_LABEL, url=docs_url)])


def _image_source(location: str) -> BytesIO | Path | None:
    """What Pillow should open for an image location: a data URI's bytes or a file on this machine."""
    if not location.startswith("data:"):
        return _local_path(location)
    payload = location.split(",", 1)[-1]
    try:
        return BytesIO(base64.b64decode(payload, validate=False))
    except (binascii.Error, ValueError) as e:
        logger.debug("Could not read image header for a pre-run input check, skipping it: %s", e)
        return None


def _run_ffprobe(value: Any, args: list[str], *, kind: MediaKind) -> dict[str, Any] | None:  # noqa: PLR0911
    """The JSON ffprobe prints for a video or audio input on this machine, or None.

    Only a file on this machine is probed: a remote URL would make ffprobe download it, and a data
    URI is too large to pass on its command line. ffprobe is used only if it is already installed
    (see `_installed_ffprobe`), never fetched, and is given `FFPROBE_TIMEOUT_SECONDS` to answer, or
    what's left of the current `input_check_budget` if that's less.
    """
    location = coerce_media_url_or_data_uri(value, kind=kind)
    if not location or location.startswith("data:"):
        return None
    path = _local_path(location)
    if path is None:
        return None
    ffprobe = _installed_ffprobe()
    if ffprobe is None:
        logger.debug("ffprobe is not installed, skipping a pre-run %s check", kind)
        return None
    timeout = _probe_timeout()
    if timeout is None:
        logger.debug("This validation run's probe budget is spent, skipping a pre-run %s check", kind)
        return None
    cmd = [ffprobe, "-v", "error", "-print_format", "json", *args, str(path)]
    try:
        result = subprocess.run(  # noqa: S603
            cmd,
            capture_output=True,
            # ffprobe writes UTF-8 whatever the locale; the default would decode it with Windows' code
            # page and fail on a non-Latin file name, which it echoes back.
            encoding="utf-8",
            errors="replace",
            check=True,
            timeout=timeout,
        )
    except (subprocess.SubprocessError, OSError, ValueError) as e:
        logger.debug("Could not probe a %s for a pre-run input check, skipping it: %s", kind, e)
        return None
    try:
        data = json.loads(result.stdout)
    except ValueError as e:
        logger.debug("Could not probe a %s for a pre-run input check, skipping it: %s", kind, e)
        return None
    if not isinstance(data, dict):
        return None
    _record_matroska_doctype(data, path)
    return data


def _record_matroska_doctype(data: dict[str, Any], path: Path) -> None:
    """Add a Matroska file's DocType ("webm" or "matroska") to ffprobe's JSON, which doesn't report it.

    ffprobe names MKV and WebM with one demuxer. The file's header says which it is, and that's more
    reliable than guessing from a codec, as WebM and MKV can carry the same ones.
    """
    format_info = data.get("format")
    if not isinstance(format_info, dict) or not str(format_info.get("format_name", "")).startswith("matroska"):
        return
    try:
        with path.open("rb") as file:
            header = file.read(_MATROSKA_HEADER_BYTES)
    except OSError:
        return
    doctype = _matroska_doctype(header)
    if doctype is not None:
        format_info[_DOCTYPE_KEY] = doctype


def _matroska_doctype(header: bytes) -> str | None:
    """The DocType in a Matroska file's EBML header, or None if it isn't found there."""
    start = header.find(_EBML_DOCTYPE_ID)
    if start < 0 or start + len(_EBML_DOCTYPE_ID) >= len(header):
        return None
    size_byte = header[start + len(_EBML_DOCTYPE_ID)]
    # A one-byte EBML size has its top bit set; the DocType is short enough to always use one.
    if not size_byte & 0x80:
        return None
    end = start + len(_EBML_DOCTYPE_ID) + 1 + (size_byte & 0x7F)
    if end > len(header):
        return None
    return header[start + len(_EBML_DOCTYPE_ID) + 1 : end].decode("ascii", errors="replace")


def _probe_timeout() -> float | None:
    """How long the next probe may take, or None when the current budget leaves no time for one."""
    deadline = _probe_deadline.get()
    if deadline is None:
        return FFPROBE_TIMEOUT_SECONDS
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        return None
    return min(FFPROBE_TIMEOUT_SECONDS, remaining)


def _installed_ffprobe() -> str | None:
    """The path to an ffprobe that is already installed, or None.

    Prefers the static-ffmpeg copy the engine uses elsewhere, but only once its download has
    finished (it writes `installed.crumb` last); asking static-ffmpeg for the path would download it
    otherwise. Falls back to an ffprobe on PATH.

    `get_platform_dir()` reads static-ffmpeg's `SELF_DIR` each time it is called, and the engine
    redirects `SELF_DIR` at boot (`utils/ffmpeg_cache.py`), so this looks in the directory the
    engine downloads ffmpeg to.
    """
    try:
        platform_dir = Path(static_ffmpeg_run.get_platform_dir())
    except OSError:
        return shutil.which("ffprobe")
    if not (platform_dir / "installed.crumb").is_file():
        return shutil.which("ffprobe")
    if sys.platform == "win32":
        exe = platform_dir / "ffprobe.exe"
    else:
        exe = platform_dir / "ffprobe"
    if not exe.is_file():
        return shutil.which("ffprobe")
    return str(exe)


def _local_path(location: str) -> Path | None:
    """The file on this machine a location names, or None for a remote URL or an unresolvable path."""
    try:
        resolved = File(location).resolve()
    except (FileLoadError, OSError, ValueError):
        return None
    if is_url(resolved):
        return None
    path = Path(resolved)
    # A name longer than the OS allows raises rather than reading as missing.
    try:
        is_file = path.is_file()
    except (OSError, ValueError):
        return None
    if not is_file:
        return None
    return path


def _first_stream(data: dict[str, Any]) -> dict[str, Any]:
    """The first stream ffprobe selected, or an empty dict when there is none."""
    streams = data.get("streams")
    if not streams:
        return {}
    return streams[0]


def _stream_text(stream: dict[str, Any], key: str) -> str | None:
    """A text field of an ffprobe stream, or None when it's missing or ffprobe's "unknown"."""
    value = stream.get(key)
    if not isinstance(value, str) or not value or value == "unknown":
        return None
    return value


def _audio_mime_type(data: dict[str, Any]) -> str | None:
    """An audio input's container as a MIME type, read from ffprobe's JSON, or None if it isn't named here.

    ffprobe names MP4 and M4A with one demuxer, so an MP4 reads as audio/mp4 here, the audio in it
    being what an audio check looks at.
    """
    format_info = data.get("format")
    if not isinstance(format_info, dict):
        return None
    demuxer = format_info.get("format_name")
    if not isinstance(demuxer, str):
        return None
    if demuxer.startswith("mov,"):
        return _iso_audio_mime_type(format_info.get("tags", {}).get("major_brand"))
    if demuxer.startswith("matroska"):
        return _matroska_audio_mime_type(format_info, _stream_text(_first_stream(data), "codec_name"))
    return _AUDIO_DEMUXER_MIME_TYPES.get(demuxer)


def _iso_audio_mime_type(brand: Any) -> str:
    """An ISO media file's container for an audio check.

    A MOV stays a MOV, a 3GP reads as 3GP audio, and the rest reads as M4A.
    """
    match _iso_media_mime_type(brand):
        case "video/quicktime":
            return "video/quicktime"
        case "video/3gpp":
            return "audio/3gpp"
        case "video/3gpp2":
            return "audio/3gpp2"
        case _:
            return "audio/mp4"


def _matroska_audio_mime_type(format_info: dict[str, Any], codec: str | None) -> str:
    """A Matroska file's container for an audio check: WebM or MKA, by the file's DocType."""
    if _is_webm(format_info, codec, _WEBM_AUDIO_CODECS):
        return "audio/webm"
    return "audio/x-matroska"


def _video_codec(data: dict[str, Any]) -> str | None:
    """The first video stream's codec in ffprobe's JSON, such as "h264", or None."""
    codec = _first_stream(data).get("codec_name")
    if isinstance(codec, str) and codec:
        return codec
    return None


def _video_mime_type(data: dict[str, Any]) -> str | None:
    """A video's container as a MIME type, read from ffprobe's JSON, or None if it's one not named here.

    ffprobe names MP4, MOV and 3GP with one demuxer ("mov,mp4,m4a,3gp,3g2,mj2"), and MKV and WebM with
    another, so the file's brand tells MP4 from MOV, and its DocType WebM from MKV.
    """
    format_info = data.get("format")
    if not isinstance(format_info, dict):
        return None
    demuxer = format_info.get("format_name")
    if not isinstance(demuxer, str):
        return None
    if demuxer.startswith("mov,"):
        brand = format_info.get("tags", {}).get("major_brand")
        return _iso_media_mime_type(brand)
    if demuxer.startswith("matroska"):
        if _is_webm(format_info, _video_codec(data), _WEBM_VIDEO_CODECS):
            return "video/webm"
        return "video/x-matroska"
    return _DEMUXER_MIME_TYPES.get(demuxer)


def _is_webm(format_info: dict[str, Any], codec: str | None, webm_codecs: frozenset[str]) -> bool:
    """Whether a Matroska file is WebM: by the DocType in its header, or by its codec when that's unread."""
    doctype = format_info.get(_DOCTYPE_KEY)
    if doctype is not None:
        return doctype == "webm"
    return codec in webm_codecs


def _iso_media_mime_type(brand: Any) -> str:
    """The MIME type an ISO media file's major brand names.

    A file with no brand is old QuickTime, so it reads as MOV, like one branded "qt".
    """
    if not isinstance(brand, str):
        return "video/quicktime"
    brand = brand.strip().lower()
    if brand in {"", "qt"}:
        return "video/quicktime"
    if brand.startswith("3gp"):
        return "video/3gpp"
    if brand.startswith("3g2"):
        return "video/3gpp2"
    return "video/mp4"


def _frame_size(data: dict[str, Any]) -> ImageInfo | None:
    """The displayed frame size in ffprobe's JSON for the first video stream, or None."""
    streams = data.get("streams")
    if not streams:
        return None
    stream = streams[0]
    try:
        width, height = int(stream["width"]), int(stream["height"])
    except (KeyError, TypeError, ValueError):
        return None
    # ffprobe reports 0x0 when it can't work out the frame size; that's unread, not tiny.
    if width <= 0 or height <= 0:
        return None
    if _is_quarter_turn(stream):
        return ImageInfo(width=height, height=width, mime_type=None)
    return ImageInfo(width=width, height=height, mime_type=None)


def _is_quarter_turn(stream: dict[str, Any]) -> bool:
    """Whether a video stream is displayed rotated by 90 degrees, so its width and height swap.

    The display matrix in `side_data_list` wins over the older `rotate` tag.
    """
    rotation = stream.get("tags", {}).get("rotate")
    for side_data in stream.get("side_data_list", []):
        rotation = side_data.get("rotation", rotation)
    if rotation is None:
        return False
    try:
        degrees = abs(int(float(rotation)))
    except (TypeError, ValueError):
        return False
    return degrees % _HALF_TURN_DEGREES == _QUARTER_TURN_DEGREES


def _nominal_frame_rate(data: dict[str, Any]) -> float | None:
    """The first video stream's declared frame rate (`r_frame_rate`) in ffprobe's JSON, or None."""
    streams = data.get("streams")
    if not streams:
        return None
    return _positive_fraction(streams[0].get("r_frame_rate", ""))


def _frame_rate(data: dict[str, Any]) -> float | None:
    """The first video stream's playback frame rate in ffprobe's JSON, or None.

    FFmpeg's avformat.h documents `r_frame_rate` as the lowest rate at which all timestamps can be
    represented exactly and notes it is "just a guess". `avg_frame_rate` is the actual average
    playback rate and is preferred. Falls back to `r_frame_rate` when the average is unset ("0/0"),
    then to `nb_frames` / `duration`.
    """
    streams = data.get("streams")
    if not streams:
        return None
    stream = streams[0]

    average = _positive_fraction(stream.get("avg_frame_rate", ""))
    if average is not None:
        return average

    declared = _positive_fraction(stream.get("r_frame_rate", ""))
    if declared is not None:
        return declared

    frames = _whole_number(stream.get("nb_frames"))
    duration = _seconds(stream.get("duration"))
    if frames is None or frames <= 0 or duration is None or duration <= 0:
        return None
    return frames / duration


def _positive_fraction(text: str) -> float | None:
    """An ffprobe rate such as "30/1" or "30000/1001" as a number, or None when it isn't above 0.

    ffprobe writes "0/0" for a rate it doesn't know.
    """
    if not text or text == "0/0":
        return None
    parts = text.split("/")
    if len(parts) != 2:  # noqa: PLR2004
        return None
    try:
        numerator = float(parts[0])
        denominator = float(parts[1])
    except ValueError:
        return None
    if denominator == 0:
        return None
    rate = numerator / denominator
    if not rate > 0:
        return None
    return rate


def _whole_number(value: Any) -> int | None:
    """An ffprobe count field such as `nb_frames` as an int, or None when it's missing or not one."""
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _seconds(value: Any) -> float | None:
    """An ffprobe duration field as seconds, or None when it's missing or not a number."""
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _format_limit(limit: float, *, round_up: bool = False) -> str:
    """A limit as messages show it: up to 6 significant figures, rounded toward the allowed side.

    A maximum rounds down and a minimum rounds up (`round_up`), so a value past the limit can always
    be printed past the shown limit too.
    """
    text = f"{limit:g}"
    shown = float(text)
    if shown == limit or limit <= 0 or (shown > limit) == round_up:
        return text
    scale = 10 ** max(6 - len(str(int(limit))), 0)
    if round_up:
        rounded = math.ceil(limit * scale)
    else:
        rounded = math.floor(limit * scale)
    return f"{rounded / scale:g}"


def _format_past(value: float, limit: float, decimals: int) -> str:
    """`value` printed past `limit`: to `decimals` places, or more where fewer would not be.

    More places are used when fewer would read as equal to `limit` as `_format_limit` shows it, or
    on its other side. A file of 200,000,001 bytes against a 200,000,000-byte limit (shown as "190.734 MB") must not
    be reported as "190.735 MB" either way round.
    """
    over = value > limit
    shown_limit = float(_format_limit(limit, round_up=not over))
    for places in range(decimals, decimals + 9):
        text = f"{value:.{places}f}"
        rounded = float(text)
        if rounded != shown_limit and (rounded > shown_limit) == over:
            return text
    return repr(value)


# Other names providers and `mimetypes` use for a format, mapped to the one the readers return.
# HEIC and HEIF share one container, which Pillow names HEIF.
_MIME_ALIASES = {
    "image/heic": "image/heif",
    "image/jpg": "image/jpeg",
    "image/pjpeg": "image/jpeg",
    "video/mov": "video/quicktime",
    "video/matroska": "video/x-matroska",
    "video/mkv": "video/x-matroska",
    "audio/matroska": "audio/x-matroska",
    "audio/mka": "audio/x-matroska",
    "audio/mpeg3": "audio/mpeg",
    "audio/x-mpeg-3": "audio/mpeg",
    "video/avi": "video/x-msvideo",
    "video/msvideo": "video/x-msvideo",
    "video/wmv": "video/x-ms-wmv",
    "video/mpg": "video/mpeg",
    "audio/mp3": "audio/mpeg",
    "audio/x-mpeg": "audio/mpeg",
    "audio/x-wav": "audio/wav",
    "audio/wave": "audio/wav",
    "audio/vnd.wave": "audio/wav",
    "audio/x-m4a": "audio/mp4",
    "audio/m4a": "audio/mp4",
    "audio/x-flac": "audio/flac",
    "audio/x-aiff": "audio/aiff",
    "audio/x-aac": "audio/aac",
    "audio/x-ogg": "audio/ogg",
    # A .opus file is Ogg. Listing only audio/opus then also accepts Ogg Vorbis, which refuses less.
    "audio/opus": "audio/ogg",
    "audio/aif": "audio/aiff",
    "audio/x-aif": "audio/aiff",
    "audio/mp4a-latm": "audio/mp4",
    "audio/x-mp4": "audio/mp4",
}

# A Matroska file's EBML header holds its DocType within its first few dozen bytes.
_EBML_DOCTYPE_ID = b"\x42\x82"
_MATROSKA_HEADER_BYTES = 64
# Where _run_ffprobe records a Matroska file's DocType in ffprobe's format JSON.
_DOCTYPE_KEY = "griptape_doctype"

# Video and audio codecs a WebM file may carry, used when a Matroska file's DocType can't be read.
_WEBM_VIDEO_CODECS = frozenset({"vp8", "vp9", "av1"})
_WEBM_AUDIO_CODECS = frozenset({"opus", "vorbis"})

# The audio reading of a video container, for an audio check of a video file's audio track.
_VIDEO_TO_AUDIO_CONTAINER = {
    "video/mp4": "audio/mp4",
    "video/x-matroska": "audio/x-matroska",
    "video/webm": "audio/webm",
    "video/3gpp": "audio/3gpp",
    "video/3gpp2": "audio/3gpp2",
}

# ffprobe demuxer names for audio containers that name one format each.
_AUDIO_DEMUXER_MIME_TYPES = {
    "mp3": "audio/mpeg",
    "wav": "audio/wav",
    "flac": "audio/flac",
    "ogg": "audio/ogg",
    "aac": "audio/aac",
    "aiff": "audio/aiff",
    "w64": "audio/wav",
}

# ffprobe demuxer names for containers that name one format each.
_DEMUXER_MIME_TYPES = {
    "avi": "video/x-msvideo",
    "flv": "video/x-flv",
    "mpegts": "video/mp2t",
    "mpeg": "video/mpeg",
    "asf": "video/x-ms-wmv",
    "gif": "image/gif",
}

# Formats whose MIME subtype isn't the name an artist knows them by.
_FORMAT_NAMES = {
    "image/vnd.adobe.photoshop": "PSD",
    "image/x-portable-anymap": "PPM",
    "application/postscript": "EPS",
    "video/quicktime": "MOV",
    "video/x-matroska": "MKV",
    "video/x-msvideo": "AVI",
    "video/avi": "AVI",
    "video/msvideo": "AVI",
    "video/mov": "MOV",
    "video/matroska": "MKV",
    "video/mkv": "MKV",
    "audio/matroska": "MKA",
    "audio/mka": "MKA",
    "audio/mpeg3": "MP3",
    "audio/x-mpeg-3": "MP3",
    "image/jpg": "JPEG",
    "image/pjpeg": "JPEG",
    "video/mpg": "MPEG",
    "video/wmv": "WMV",
    "audio/x-ogg": "OGG",
    "audio/opus": "Opus",
    "audio/aif": "AIFF",
    "audio/x-aif": "AIFF",
    "audio/mp4a-latm": "M4A",
    "audio/x-mp4": "M4A",
    "audio/x-matroska": "MKA",
    "audio/3gpp": "3GP",
    "audio/3gpp2": "3G2",
    "video/webm": "WebM",
    "video/3gpp": "3GP",
    "video/3gpp2": "3G2",
    "video/mp2t": "MPEG-TS",
    "video/x-ms-wmv": "WMV",
    "audio/mpeg": "MP3",
    "audio/mp4": "M4A",
    "audio/wav": "WAV",
    "audio/x-wav": "WAV",
    "audio/wave": "WAV",
    "audio/vnd.wave": "WAV",
    "audio/mp3": "MP3",
    "audio/x-mpeg": "MP3",
    "audio/x-m4a": "M4A",
    "audio/m4a": "M4A",
    "audio/ogg": "OGG",
    "audio/webm": "WebM",
    "audio/aiff": "AIFF",
}


# Other ways providers write a codec, mapped to ffprobe's name. Profiles such as AAC-LC are matched
# as their codec; the checks don't read a profile, which refuses less.
_CODEC_ALIASES = {
    "avc": "h264",
    "h264": "h264",
    "x264": "h264",
    "mpeg4avc": "h264",
    "mpeg4part10": "h264",
    "hevc": "hevc",
    "h265": "hevc",
    "x265": "hevc",
    "aaclc": "aac",
    "heaac": "aac",
    "heaacv2": "aac",
    "mpeg4aac": "aac",
    "mpeg4": "mpeg4",
    "mpeg4part2": "mpeg4",
    "mpeg2": "mpeg2video",
    "mp2": "mp2",
    "ac3": "ac3",
    "dolbydigital": "ac3",
    "eac3": "eac3",
    "dolbydigitalplus": "eac3",
    "mjpeg": "mjpeg",
    "motionjpeg": "mjpeg",
    "applelossless": "alac",
    "mpeg1audiolayer3": "mp3",
    "mpeg1audiolayeriii": "mp3",
    "mpegaudiolayer3": "mp3",
    "mpeg1layer3": "mp3",
    "mpeglayer3": "mp3",
    "dnxhr": "dnxhd",
    "pcm16": "pcm_s16le",
    "pcmu": "pcm_mulaw",
    "pcma": "pcm_alaw",
    "mpegaudiolayeriii": "mp3",
    "mpeg2audiolayeriii": "mp3",
    "mpeg1layeriii": "mp3",
    "amr": "amr_nb",
    "amrnb": "amr_nb",
    "amrwb": "amr_wb",
    "speexwithheaderbyte": "speex",
    "g711ulaw": "pcm_mulaw",
    "g711mulaw": "pcm_mulaw",
    "g711alaw": "pcm_alaw",
    "mulaw": "pcm_mulaw",
    "ulaw": "pcm_mulaw",
    "alaw": "pcm_alaw",
}

# Words a provider writes for PCM without naming a bit depth or byte order. "PCM" and "WAV" accept any
# PCM codec; the "linear" ones exclude companded PCM (G.711 mu-law and A-law), which isn't linear.
_GENERIC_PCM_WORDS = frozenset({"pcm", "wav", "wave", "uncompressed"})
_LINEAR_PCM_WORDS = frozenset({"lpcm", "linearpcm", "linear16", "linear32", "l16"})
# ffprobe's prefixes for linear PCM: signed, unsigned and float samples.
_LINEAR_PCM_PREFIXES = ("pcm_s", "pcm_u", "pcm_f")
_LINEAR_PCM_PHRASE = re.compile(r"linear[\s_-]*pcm", re.IGNORECASE)
_BIT_DEPTH = re.compile(r"\b(?:8|16|24|32)[\s-]*bits?\b", re.IGNORECASE)

# What `_codecs_named` records for a generic PCM word, and for a linear-PCM one.
_PCM = "pcm"
_LINEAR_PCM = "linear pcm"

# What separates the words of a codec name a provider writes, such as "AAC LC" or "H.264/AVC".
_CODEC_WORD_SPLIT = re.compile(r"[\s/,()_]+")
_NON_ALPHANUMERIC = re.compile(r"[^a-z0-9]")
# What separates the codecs of a list a provider writes in one string.
_CODEC_LIST_SPLIT = re.compile(r",|;|\s+(?:or|and)\s+", re.IGNORECASE)

# ffprobe's codec names that aren't the name an artist knows a codec by.
_CODEC_NAMES = {
    "h264": "H.264",
    "hevc": "H.265",
    "av1": "AV1",
    "vp8": "VP8",
    "vp9": "VP9",
    "prores": "ProRes",
    "mpeg4": "MPEG-4",
    "mpeg2video": "MPEG-2",
    "mjpeg": "Motion JPEG",
    "dnxhd": "DNxHD",
    "mp3": "MP3",
    "aac": "AAC",
    "ac3": "AC-3",
    "eac3": "E-AC-3",
    "flac": "FLAC",
    "opus": "Opus",
    "vorbis": "Vorbis",
    "alac": "ALAC",
    "pcm_s16le": "16-bit PCM (little-endian)",
    "pcm_s24le": "24-bit PCM (little-endian)",
    "pcm_s32le": "32-bit PCM (little-endian)",
    "pcm_f32le": "32-bit float PCM (little-endian)",
    "pcm_s16be": "16-bit PCM (big-endian)",
    "pcm_s24be": "24-bit PCM (big-endian)",
    "pcm_s32be": "32-bit PCM (big-endian)",
    "pcm_f32be": "32-bit float PCM (big-endian)",
    "pcm_u8": "8-bit PCM",
    "pcm_mulaw": "G.711 μ-law",
    "amr_nb": "AMR-NB",
    "amr_wb": "AMR-WB",
    "speex": "Speex",
    "h263": "H.263",
    "pcm_alaw": "G.711 A-law",
}


def _codec_matches(codec: str, written: str) -> bool:
    """Whether a codec name a provider wrote accepts the input's codec, from ffprobe.

    Names are compared without case or punctuation, and a long name accepts every codec it mentions,
    so "AAC LC", "H.264 (MPEG-4 AVC)", "Dolby Digital (AC-3)" and "Apple ProRes" accept the codec they
    name. "MPEG-4" alone means MPEG-4 Part 2, but next to H.264 or HEVC it only qualifies that codec,
    so it accepts nothing on its own there. Any PCM word ("PCM", "16-bit PCM", "WAV") accepts any PCM
    codec, whatever its bit depth or byte order.
    """
    canonical = _canonical_codec(codec)
    named = _codecs_named(written)
    if canonical.startswith("pcm_") and _PCM in named:
        return True
    if canonical.startswith(_LINEAR_PCM_PREFIXES) and _LINEAR_PCM in named:
        return True
    return canonical in named


def _codecs_named(written: str) -> set[str]:
    """The codecs a name a provider wrote mentions, by their ffprobe names; `_PCM` for any PCM word.

    A list in one string ("H.264, MPEG-4 Part 2", "H.264 or H.263") is read piece by piece, so each
    piece names its own codec and "MPEG-4" in one piece isn't taken as a qualifier of H.264 in another.
    """
    pieces = [piece for piece in _CODEC_LIST_SPLIT.split(written) if piece.strip()]
    if len(pieces) > 1:
        return set().union(*(_codecs_named_in_one(piece) for piece in pieces))
    return _codecs_named_in_one(written)


def _codecs_named_in_one(written: str) -> set[str]:
    """`_codecs_named` for one codec name, not a list."""
    whole = _canonical_codec(written)
    if _is_known_codec(whole):
        return {whole}
    # "G.711" alone names both its laws.
    if _squash(written) == "g711":
        return {"pcm_mulaw", "pcm_alaw"}
    named = set()
    # "Linear PCM" is one phrase; split, its word "PCM" would read as any PCM, companded included.
    if _LINEAR_PCM_PHRASE.search(written):
        named.add(_LINEAR_PCM)
        written = _LINEAR_PCM_PHRASE.sub(" ", written)
    named |= _codecs_named_by_words(written)
    # "MPEG-4" beside H.264 or HEVC names its family, as in "H.264 (MPEG-4 AVC)", not MPEG-4 Part 2.
    if named & {"h264", "hevc"}:
        named.discard("mpeg4")
    # A name that says linear PCM or gives a bit depth ("Linear PCM (WAV)", "16-bit PCM") means linear
    # PCM, so a generic PCM word beside it doesn't widen it to companded PCM.
    if _PCM in named and (_LINEAR_PCM in named or _BIT_DEPTH.search(written)):
        named.discard(_PCM)
        named.add(_LINEAR_PCM)
    return named


def _codecs_named_by_words(written: str) -> set[str]:
    """The codecs the words of one codec name name, with `_PCM` and `_LINEAR_PCM` for PCM words."""
    named = set()
    for word in _CODEC_WORD_SPLIT.split(written.lower()):
        if not word:
            continue
        squashed = _squash(word)
        if squashed in _GENERIC_PCM_WORDS:
            named.add(_PCM)
            continue
        if squashed in _LINEAR_PCM_WORDS:
            named.add(_LINEAR_PCM)
            continue
        candidate = _canonical_codec(word)
        if _is_known_codec(candidate):
            named.add(candidate)
        elif "-" in word:
            # A hyphenated word that isn't one codec ("ogg-opus", as Deepgram and AWS write it) is
            # read part by part. Whole names such as "AC-3" and "AAC-LC" matched above first.
            named |= _codecs_named_by_hyphenated_parts(word.split("-"))
    return named


def _codecs_named_by_hyphenated_parts(parts: list[str]) -> set[str]:
    """The codecs the parts of a hyphenated word name.

    Two adjacent parts are joined first when together they name a codec, so Azure's "amr-wb-16000hz"
    names AMR-WB, not AMR-NB.
    """
    parts = [part for part in parts if part]
    named: set[str] = set()
    index = 0
    while index < len(parts):
        if index + 1 < len(parts):
            pair = parts[index] + parts[index + 1]
            if _is_known_codec(_canonical_codec(pair)):
                named |= _codecs_named_by_words(pair)
                index += 2
                continue
        named |= _codecs_named_by_words(parts[index])
        index += 1
    return named


def _is_known_codec(canonical: str) -> bool:
    """Whether a canonical codec name is one this module knows by name."""
    return canonical in _CODEC_NAMES or canonical in _CODEC_ALIASES.values()


def _canonical_codec(name: str) -> str:
    """A codec's ffprobe name, however it's written: "H.264", "AVC" and "h264" all give "h264"."""
    squashed = _squash(name)
    known = _CODEC_ALIASES.get(squashed)
    if known is not None:
        return known
    for ffprobe_name, shown in _CODEC_NAMES.items():
        if _squash(shown) == squashed or _squash(ffprobe_name) == squashed:
            return ffprobe_name
    return name.strip().lower()


def _squash(name: str) -> str:
    """A name without case, spaces or punctuation, so "AC-3", "ac3" and "AC 3" compare equal.

    The micro sign and Greek mu read as "mu", so "μ-law" squashes to "mulaw" rather than "law".
    """
    return _NON_ALPHANUMERIC.sub("", name.lower().replace("μ", "mu").replace("µ", "mu"))


def _codec_name(codec: str) -> str:
    """A codec as a message shows it: ffprobe's "hevc", or "HEVC" as a provider writes it, reads "H.265"."""
    known = _CODEC_NAMES.get(_canonical_codec(codec))
    if known:
        return known
    # ffprobe writes codecs in lowercase ASCII ("vp9"); a name a provider wrote ("Apple ProRes",
    # "μ-law") keeps its case.
    if codec == codec.lower() and codec.isascii():
        return codec.upper()
    return codec


def _format_name(mime_type: str) -> str:
    """A MIME type's format as a message shows it: "image/x-icon" reads "ICON"."""
    folded = mime_type.split(";", 1)[0].strip().lower()
    known = _FORMAT_NAMES.get(folded)
    if known:
        return known
    return folded.split("/", 1)[-1].removeprefix("x-").removeprefix("vnd.").upper()


def _parse_ratio(name: str) -> float:
    """A ratio written the way providers write it, such as "16:9", as width over height.

    Raises:
        ValueError: If `name` isn't two positive numbers joined by a colon.
    """
    width, separator, height = name.partition(":")
    msg = f"Attempted to check an aspect ratio. Failed because {name!r} is not a ratio such as '16:9'."
    if not separator:
        raise ValueError(msg)
    try:
        width_value = float(width)
        height_value = float(height)
    except ValueError as e:
        raise ValueError(msg) from e
    if not (math.isfinite(width_value) and math.isfinite(height_value)):
        raise ValueError(msg)
    if not width_value > 0 or not height_value > 0:
        raise ValueError(msg)
    return width_value / height_value


def _join_or(names: Sequence[str]) -> str:
    if len(names) <= 1:
        return "".join(names)
    return f"{', '.join(names[:-1])} or {names[-1]}"
