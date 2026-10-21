"""Checks a node runs on its media inputs before a run, against a provider's documented limits.

A request a provider is certain to reject still costs the artist an upload and a wait, and sometimes
credits. These helpers let a node refuse it first, from what it can read locally.

- **Combined checks** (`image_errors`, `video_errors`) run every image or video check a provider
  documents in one call, reading the input once. Most nodes need only these.
- **Readers** (`local_size_bytes`, `local_image_info`, `local_video_probe`) read a media input's
  properties from data already on this machine. `local_video_probe` reads a video's frame size,
  durations and frame rates in one ffprobe run. None of them makes a network call or downloads a
  tool: the video reader uses ffprobe only if it is already installed. They return None when the value is a remote URL, can't be found or parsed,
  or when the tool to read it is missing or too slow.
- **Checks** (`check_count`, `check_size`, `check_dimensions`, `check_aspect_ratio_range`,
  `check_mime_type`, `check_duration`, `check_frame_rate`) compare one value with a limit and
  return a `NodeError` ready to append to `validate_before_node_run`'s list, or None when the value
  is within the limit or unknown.

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
from static_ffmpeg import run as static_ffmpeg_run

from griptape_nodes.exe_types.node_error import NodeError, NodeErrorLink
from griptape_nodes.files.file import File, FileLoadError
from griptape_nodes.files.path_utils import is_url
from griptape_nodes.utils.media_values import MediaKind, coerce_media_url_or_data_uri

if TYPE_CHECKING:
    from collections.abc import Iterator, Sequence

logger = logging.getLogger("griptape_nodes")

__all__ = [
    "ImageInfo",
    "VideoProbe",
    "check_aspect_ratio_range",
    "check_count",
    "check_dimensions",
    "check_duration",
    "check_frame_rate",
    "check_mime_type",
    "check_size",
    "image_errors",
    "input_check_budget",
    "input_subject",
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
# milliseconds; one that takes longer than this is abandoned and the checks that need it (frame
# size, duration, frame rate) are skipped.
FFPROBE_TIMEOUT_SECONDS = 2

# The most one validation run spends probing videos, across all of a node's inputs. The engine
# opens one `input_check_budget` around each node's `validate_before_node_run`; once it's spent,
# the remaining videos are skipped rather than probed, so several slow probes can't add up.
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
    portrait. Returns None for a remote URL, for a format Pillow can't open (HEIC, say), and for an
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
    # it, such as a DDS texture in an unsupported DXGI format.
    except (
        OSError,
        UnidentifiedImageError,
        Image.DecompressionBombError,
        ValueError,
        NotImplementedError,
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
    Each part is None when ffprobe didn't report it.
    """

    info: ImageInfo | None
    seconds: float | None
    fps: float | None = None
    container_seconds: float | None = None
    nominal_fps: float | None = None

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
    """Cap the time the video probes inside this block spend, together, at `seconds`.

    The engine opens one around each node's `validate_before_node_run`, so a node checking several
    videos blocks the event loop for at most `seconds` in all. Inside it, each probe gets the
    smaller of `FFPROBE_TIMEOUT_SECONDS` and the time left, and a probe that would start with no
    time left is skipped. Opened inside another budget, it can shorten the time left but never
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
    """The frame size, duration and frame rate of a video input, or None if it can't be read locally.

    One ffprobe run reads all three, so a node checking several on the same clip waits on at most
    one `FFPROBE_TIMEOUT_SECONDS`, and the values come from the same read of the file. Inside an
    `input_check_budget`, the probe also stops when the budget does.
    Probes only a file on this machine, with an ffprobe that is already installed; see
    `_probe_local_video`.
    """
    data = _probe_local_video(value, ["-show_format", "-select_streams", "v:0", "-show_streams"])
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


def check_size(
    size_bytes: int | None,
    *,
    maximum_bytes: int,
    subject: str,
    fix: str = "Use a smaller file.",
    docs_url: str | None = None,
) -> NodeError | None:
    """An error when an input file is larger than the provider accepts.

    Args:
        size_bytes: The file's size, from `local_size_bytes`. None skips the check.
        maximum_bytes: The largest file the provider accepts.
        subject: The input, from `input_subject`.
        fix: What the artist can do about it.
        docs_url: The provider's page documenting the limit.
    """
    if size_bytes is None or size_bytes <= maximum_bytes:
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
    """
    if info is None or info.height == 0:
        return None
    ratio = info.width / info.height
    if _parse_ratio(tallest) <= ratio <= _parse_ratio(widest):
        return None
    if ratio > _parse_ratio(widest):
        shape = "wide"
    else:
        shape = "tall"
    return _error(
        f"{subject} is {info.width}x{info.height}, which is too {shape}. The aspect ratio must be between "
        f"{tallest} and {widest}. Crop it.",
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
    """
    if mime_type is None or mime_type in allowed:
        return None
    formats = _join_or([_format_name(name) for name in allowed])
    current = _format_name(mime_type)
    return _error(f"{subject} is in {current} format. Convert it to {formats}.", docs_url)


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
    min_side: int | None = None,
    max_side: int | None = None,
    min_megapixels: float | None = None,
    max_megapixels: float | None = None,
    widest: str | None = None,
    tallest: str | None = None,
    docs_url: str | None = None,
) -> list[NodeError]:
    """Every provider image limit an image input breaks, in one call.

    Reads the image once and runs only the checks whose limits are given: the format when
    `allowed_mime_types` is set, the file size with `maximum_bytes`, the sides and area with
    `min_side`, `max_side`, `min_megapixels` or `max_megapixels`, and the aspect ratio when both
    `widest` and `tallest` are set. Like the checks it runs, it skips anything it can't read locally.

    Args:
        image: The image input.
        subject: The input, from `input_subject`.
        allowed_mime_types: The formats the provider accepts, such as ("image/jpeg", "image/png").
        maximum_bytes: The largest file the provider accepts.
        min_side: The fewest pixels accepted for the width and for the height.
        max_side: The most pixels accepted for the width and for the height.
        min_megapixels: The fewest pixels accepted in total, in millions.
        max_megapixels: The most pixels accepted in total, in millions.
        widest: The widest aspect ratio accepted, as the provider writes it, such as "2.5:1".
        tallest: The tallest aspect ratio accepted, such as "1:2.5". Pass both bounds or neither.
        docs_url: The provider's page documenting the limits.

    Raises:
        ValueError: If only one of `widest` and `tallest` is given, which would check nothing.
    """
    _require_both_aspect_ratio_bounds(widest, tallest)
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
                docs_url=docs_url,
            )
        )
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
    return [error for error in errors if error]


def video_errors(  # noqa: PLR0913
    video: Any,
    *,
    subject: str,
    maximum_bytes: int | None = None,
    min_seconds: float | None = None,
    max_seconds: float | None = None,
    min_side: int | None = None,
    max_side: int | None = None,
    min_megapixels: float | None = None,
    max_megapixels: float | None = None,
    widest: str | None = None,
    tallest: str | None = None,
    min_fps: float | None = None,
    max_fps: float | None = None,
    duration_fix: str | None = None,
    docs_url: str | None = None,
    probe: VideoProbe | None = _PROBE_NOT_GIVEN,
) -> list[NodeError]:
    """Every provider video limit a video input breaks, in one call.

    Probes the video once, with `local_video_probe`, and runs only the checks whose limits are
    given: the file size with `maximum_bytes`, the duration with `min_seconds` or `max_seconds`,
    the displayed frame's sides and area with `min_side`, `max_side`, `min_megapixels` or
    `max_megapixels`, the aspect ratio when both `widest` and `tallest` are set, and the frame rate
    with `min_fps` or `max_fps`. Like the checks it runs, it skips anything it can't read locally.

    Args:
        video: The video input.
        subject: The input, from `input_subject`.
        maximum_bytes: The largest file the provider accepts.
        min_seconds: The shortest clip accepted.
        max_seconds: The longest clip accepted.
        min_side: The fewest pixels accepted for the width and for the height.
        max_side: The most pixels accepted for the width and for the height.
        min_megapixels: The fewest pixels accepted in total, in millions.
        max_megapixels: The most pixels accepted in total, in millions.
        widest: The widest aspect ratio accepted, as the provider writes it, such as "2.5:1".
        tallest: The tallest aspect ratio accepted, such as "1:2.5". Pass both bounds or neither.
        min_fps: The lowest frame rate accepted.
        max_fps: The highest frame rate accepted.
        duration_fix: What the artist can do about a clip of the wrong length. Defaults to
            `check_duration`'s.
        docs_url: The provider's page documenting the limits.
        probe: The video's `local_video_probe` result, when the node has already read it for a check
            of its own, such as a total duration across several videos; None for a video it
            couldn't read. Left out, the video is probed here.

    Raises:
        ValueError: If only one of `widest` and `tallest` is given, which would check nothing.
    """
    _require_both_aspect_ratio_bounds(widest, tallest)
    errors: list[NodeError | None] = []
    if maximum_bytes is not None:
        errors.append(
            check_size(
                local_size_bytes(video, kind="video"), maximum_bytes=maximum_bytes, subject=subject, docs_url=docs_url
            )
        )
    needs_frame = (
        min_side is not None
        or max_side is not None
        or min_megapixels is not None
        or max_megapixels is not None
        or (widest is not None and tallest is not None)
    )
    needs_fps = min_fps is not None or max_fps is not None
    if min_seconds is None and max_seconds is None and not needs_frame and not needs_fps:
        return [error for error in errors if error]
    if probe is _PROBE_NOT_GIVEN:
        probe = local_video_probe(video)
    info = None
    if probe is not None:
        info = probe.info
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
    # A variable-frame-rate clip's average and declared rates differ, and providers don't say which
    # they mean, so each bound uses the rate it's easier to meet, as the duration checks do.
    rates = _frame_rates(probe)
    if max_fps is not None:
        errors.append(check_frame_rate(min(rates, default=None), subject=subject, maximum=max_fps, docs_url=docs_url))
    if min_fps is not None:
        errors.append(check_frame_rate(max(rates, default=None), subject=subject, minimum=min_fps, docs_url=docs_url))
    return [error for error in errors if error]


def _duration_errors(  # noqa: PLR0913
    probe: VideoProbe | None,
    *,
    subject: str,
    min_seconds: float | None,
    max_seconds: float | None,
    fix: str | None,
    docs_url: str | None,
) -> list[NodeError | None]:
    """`video_errors`' duration checks.

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
        errors.append(check_duration(shortest, subject=subject, maximum=max_seconds, fix=fix, docs_url=docs_url))
    if min_seconds is not None:
        errors.append(check_duration(longest, subject=subject, minimum=min_seconds, fix=fix, docs_url=docs_url))
    return errors


def _frame_rates(probe: VideoProbe | None) -> list[float]:
    """A probe's average and declared frame rates, leaving out the ones it doesn't have."""
    if probe is None:
        return []
    return [rate for rate in (probe.fps, probe.nominal_fps) if rate is not None]


def _require_both_aspect_ratio_bounds(widest: str | None, tallest: str | None) -> None:
    """Raise when only one aspect-ratio bound is given, which `check_aspect_ratio_range` can't check."""
    if (widest is None) == (tallest is None):
        return
    msg = "Attempted to check an aspect ratio. Failed because only one of widest and tallest was given; pass both."
    raise ValueError(msg)


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


def _probe_local_video(value: Any, args: list[str]) -> dict[str, Any] | None:  # noqa: PLR0911
    """The JSON ffprobe prints for a video input on this machine, or None.

    Only a file on this machine is probed: a remote URL would make ffprobe download it, and a data
    URI is too large to pass on its command line. ffprobe is used only if it is already installed
    (see `_installed_ffprobe`), never fetched, and is given `FFPROBE_TIMEOUT_SECONDS` to answer, or
    what's left of the current `input_check_budget` if that's less.
    """
    location = coerce_media_url_or_data_uri(value, kind="video")
    if not location or location.startswith("data:"):
        return None
    path = _local_path(location)
    if path is None:
        return None
    ffprobe = _installed_ffprobe()
    if ffprobe is None:
        logger.debug("ffprobe is not installed, skipping a pre-run video check")
        return None
    timeout = _probe_timeout()
    if timeout is None:
        logger.debug("This validation run's probe budget is spent, skipping a pre-run video check")
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
        logger.debug("Could not probe a video for a pre-run input check, skipping it: %s", e)
        return None
    try:
        data = json.loads(result.stdout)
    except ValueError as e:
        logger.debug("Could not probe a video for a pre-run input check, skipping it: %s", e)
        return None
    if not isinstance(data, dict):
        return None
    return data


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
    """The first video stream in ffprobe's JSON, or an empty dict when there is none."""
    streams = data.get("streams")
    if not streams:
        return {}
    return streams[0]


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


# Formats whose MIME subtype isn't the name an artist knows them by.
_FORMAT_NAMES = {
    "image/vnd.adobe.photoshop": "PSD",
    "image/x-portable-anymap": "PPM",
    "application/postscript": "EPS",
    "video/quicktime": "MOV",
    "video/x-matroska": "MKV",
    "video/x-msvideo": "AVI",
}


def _format_name(mime_type: str) -> str:
    """A MIME type's format as a message shows it: "image/x-icon" reads "ICON"."""
    known = _FORMAT_NAMES.get(mime_type)
    if known:
        return known
    return mime_type.split("/", 1)[-1].removeprefix("x-").removeprefix("vnd.").upper()


def _parse_ratio(name: str) -> float:
    width, height = name.split(":", 1)
    return float(width) / float(height)


def _join_or(names: Sequence[str]) -> str:
    if len(names) <= 1:
        return "".join(names)
    return f"{', '.join(names[:-1])} or {names[-1]}"
