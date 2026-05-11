"""Nuke-style image-sequence support built on ParsedMacro.

This module provides read-side scanning and write-side frame rendering for
templates containing a Nuke-style sequence token (`####` or `%04d`).

Semantics are tethered to Nuke:
    - Scan (read): declared padding is a MINIMUM. `####` matches any integer
      with >= 4 digits. Directory iteration is sorted lexicographically;
      duplicate frame numbers resolve to the lexicographically-first file,
      with the others recorded on `Sequence.shadowed_files` and a warning
      logged.
    - Render (write): pads to declared width with overflow allowed; sign is
      extra to the padding for negative frames (see
      `ParsedSequenceToken.render_frame`).

The sequence token may appear anywhere in the resolved path — basename,
directory component, or embedded within a directory name (e.g. `v_####_final`).
All filesystem I/O is routed through `ListDirectoryRequest` so the macro
parser stays free of OS-specific path handling.

TODO: verify assumptions against Nuke source. Open questions dispatched to
the Nuke team:
    - Width on read: minimum-width (our assumption) or strict-width in some
      mode?
    - Duplicate-frame tie-break: lexicographic filename order (our assumption)
      or raw filesystem order?
    - NEAREST policy tie-break direction: lower frame (our assumption) or
      higher frame wins?
    - Sequence tokens in directory components: Nuke supports them; confirm
      nothing subtle about how Nuke walks the subtree.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING

from griptape_nodes.common.macro_parser.exceptions import MacroResolutionError, MacroResolutionFailureReason
from griptape_nodes.common.macro_parser.resolution import resolve_variable
from griptape_nodes.common.macro_parser.segments import (
    MacroVariables,
    ParsedSegment,
    ParsedSequenceToken,
    ParsedStaticValue,
    ParsedVariable,
)

if TYPE_CHECKING:
    from collections.abc import Iterator

    from griptape_nodes.common.macro_parser.core import ParsedMacro
    from griptape_nodes.retained_mode.managers.secrets_manager import SecretsManager


logger = logging.getLogger(__name__)


class MissingFramePolicy(StrEnum):
    """How `Sequence.get()` handles a requested frame that isn't on disk.

    Names mirror Nuke's `on_error` Read-node knob.
    """

    ERROR = "error"  # Raise MissingFrameError
    BLACK = "black"  # Return MissingFrameMarker(BLACK) — caller renders a black frame
    CHECKERBOARD = "checkerboard"  # Return MissingFrameMarker(CHECKERBOARD) — caller renders a checkerboard
    NEAREST = "nearest"  # Return the closest existing frame's path


class _EntryKind(StrEnum):
    """Filter for `_list_directory_entries`.

    When the sequence token is in a middle path component, the candidates
    must be directories (so we can descend). When the token is in the final
    path component, the candidates can be either files or directories
    (Nuke permits both; we let the filesystem decide).
    """

    FILES = "files"
    DIRECTORIES = "directories"
    EITHER = "either"


@dataclass(frozen=True)
class MissingFrameMarker:
    """Sentinel returned for a missing frame under a BLACK/CHECKERBOARD policy.

    Image-generating callers (e.g. node-level composite renderers) interpret
    the marker and synthesize the appropriate frame. This module does not
    produce images itself.
    """

    policy: MissingFramePolicy
    frame: int


class MissingFrameError(Exception):
    """Raised by `Sequence.get(frame)` under the ERROR policy when missing."""

    def __init__(self, frame: int) -> None:
        super().__init__(f"Frame {frame} is missing from the sequence")
        self.frame = frame


class SequenceTemplateError(Exception):
    """Raised when a SequenceTemplate cannot be constructed or scanned."""


@dataclass
class Sequence:
    """A scanned sequence of concrete per-frame files plus metadata.

    Attributes:
        frames: Sorted list of (frame_number, path) pairs. Sorted by frame
            number (not filename) so dense iteration is always in frame order.
        first: Lowest frame number present (or the explicit floor if set).
        last: Highest frame number present (or the explicit ceiling if set).
        shadowed_files: For each frame that had multiple candidate files on
            disk, the files that did not win the slot. Lexicographically-first
            file wins per Nuke parity.
        policy: How `.get()` handles a requested frame that is absent.
    """

    frames: list[tuple[int, Path]]
    first: int
    last: int
    shadowed_files: dict[int, list[Path]] = field(default_factory=dict)
    policy: MissingFramePolicy = MissingFramePolicy.ERROR

    @property
    def missing(self) -> set[int]:
        """Frame numbers between `first` and `last` that aren't on disk."""
        present = {frame for frame, _ in self.frames}
        return {f for f in range(self.first, self.last + 1) if f not in present}

    def get(self, frame: int) -> Path | MissingFrameMarker:
        """Return the path for `frame`, applying the missing-frame policy if absent.

        For present frames, returns the Path. For missing frames, the policy
        decides: ERROR raises, NEAREST returns the closest existing frame's
        path, BLACK/CHECKERBOARD return a MissingFrameMarker sentinel.
        """
        frame_to_path = dict(self.frames)
        if frame in frame_to_path:
            return frame_to_path[frame]

        match self.policy:
            case MissingFramePolicy.ERROR:
                raise MissingFrameError(frame)
            case MissingFramePolicy.NEAREST:
                return self._nearest_path(frame, frame_to_path)
            case MissingFramePolicy.BLACK | MissingFramePolicy.CHECKERBOARD:
                return MissingFrameMarker(policy=self.policy, frame=frame)
            case _:
                msg = f"Unknown missing-frame policy: {self.policy}"
                raise ValueError(msg)

    def iter_dense(self) -> Iterator[tuple[int, Path | MissingFrameMarker]]:
        """Yield (frame, path-or-marker) for every frame in [first, last].

        Uses `get()` internally, so the policy applies consistently.
        """
        for frame in range(self.first, self.last + 1):
            yield (frame, self.get(frame))

    def _nearest_path(self, frame: int, frame_to_path: dict[int, Path]) -> Path:
        """Return the path of the frame closest to `frame`.

        Ties resolve toward the lower frame number (TODO: verify vs Nuke).
        Assumes `frames` is non-empty; `scan()` returns an empty Sequence
        under the ERROR policy, in which case this path is unreachable.
        """
        if not frame_to_path:
            msg = "Cannot apply NEAREST policy to an empty sequence"
            raise MissingFrameError(frame) from ValueError(msg)
        nearest_frame = min(frame_to_path, key=lambda f: (abs(f - frame), f))
        return frame_to_path[nearest_frame]


@dataclass
class SequenceTemplate:
    """Wraps a ParsedMacro that contains a sequence token.

    Provides write-side frame rendering (`render_frame`) and read-side
    directory scanning (`scan`). A non-sequence macro raises on construction.
    """

    macro: ParsedMacro

    def __post_init__(self) -> None:
        if not self.macro.is_sequence:
            msg = f"Template '{self.macro.template}' has no sequence token (`####` or `%04d`)"
            raise SequenceTemplateError(msg)

    def render_frame(
        self,
        frame: int,
        variables: MacroVariables,
        secrets_manager: SecretsManager,
    ) -> str:
        """Render a concrete path for `frame`.

        Variables resolve normally; the sequence token is expanded to the
        frame integer with declared-width padding (overflow allowed).
        """
        parts: list[str] = []
        for segment in self.macro.segments:
            match segment:
                case ParsedStaticValue():
                    parts.append(segment.text)
                case ParsedVariable():
                    parts.append(_render_variable(segment, variables, secrets_manager))
                case ParsedSequenceToken():
                    parts.append(segment.render_frame(frame))
                case _:
                    msg = f"Unexpected segment type: {type(segment).__name__}"
                    raise TypeError(msg)
        return "".join(parts)

    def scan(
        self,
        variables: MacroVariables,
        secrets_manager: SecretsManager,
        policy: MissingFramePolicy = MissingFramePolicy.ERROR,
    ) -> Sequence:
        """Scan the filesystem for files matching this template.

        Resolves every variable (via `partial_resolve`), derives the
        directory-to-scan from the segments preceding the sequence token,
        and issues one or more `ListDirectoryRequest`s to enumerate
        candidates. All filesystem I/O flows through `OSManager` — this
        method never touches `pathlib` or `os` directly.

        Raises:
            SequenceTemplateError: if any non-sequence variable remains
                unresolved after `partial_resolve` (the scan cannot proceed
                without a fully-known directory prefix).
        """
        # Defer the resolve-and-scan orchestration to a private helper so
        # the public method stays a pure composition of small steps.
        resolved_segments = self._fully_resolve_non_sequence_segments(variables, secrets_manager)
        prefix_segments, token_component_segments, suffix_segments = _split_on_token_component(resolved_segments)

        directory_path = _normalize_directory_path(_segments_to_string(prefix_segments))
        token_component_glob = _segments_to_glob(token_component_segments)
        suffix_path = _segments_to_string(suffix_segments)

        # When there's a suffix, the token component names a directory we'll
        # descend into. When there's no suffix, it's the final path component
        # and can be either a file or a directory (Nuke supports both).
        entry_kind: _EntryKind = _EntryKind.DIRECTORIES if suffix_segments else _EntryKind.EITHER
        candidates = _list_directory_entries(
            directory_path=directory_path,
            pattern=token_component_glob,
            kind=entry_kind,
        )

        frames_by_number, shadowed_files = _collect_frames(
            candidates=candidates,
            token_component_segments=token_component_segments,
            suffix_path=suffix_path,
            template_display=self.macro.template,
        )

        if not frames_by_number:
            return Sequence(frames=[], first=0, last=-1, policy=policy)

        sorted_frames = sorted(frames_by_number.items())
        return Sequence(
            frames=sorted_frames,
            first=sorted_frames[0][0],
            last=sorted_frames[-1][0],
            shadowed_files=shadowed_files,
            policy=policy,
        )

    def _fully_resolve_non_sequence_segments(
        self,
        variables: MacroVariables,
        secrets_manager: SecretsManager,
    ) -> list[ParsedSegment]:
        """Resolve variable segments to static text; preserve the sequence token intact.

        Unlike `partial_resolve` — which converts sequence tokens to static
        text for the Nuke-passthrough case — scan needs the token preserved so
        the split/glob/regex stages can reason about its width and original
        syntax. Raises if any required variable is missing.
        """
        # First pass: collect all missing required variables up-front so the
        # error message lists every missing name at once (resolve_variable
        # raises on the first missing required var, which is less useful).
        missing = {
            seg.info.name
            for seg in self.macro.segments
            if isinstance(seg, ParsedVariable) and seg.info.is_required and seg.info.name not in variables
        }
        if missing:
            msg = (
                f"Cannot scan template '{self.macro.template}': required variables "
                f"not supplied: {', '.join(sorted(missing))}"
            )
            raise MacroResolutionError(
                msg,
                failure_reason=MacroResolutionFailureReason.MISSING_REQUIRED_VARIABLES,
                missing_variables=missing,
            )

        resolved: list[ParsedSegment] = []
        for segment in self.macro.segments:
            match segment:
                case ParsedStaticValue() | ParsedSequenceToken():
                    resolved.append(segment)
                case ParsedVariable():
                    text = resolve_variable(segment, variables, secrets_manager)
                    if text is None:
                        # Optional variable not supplied -> contribute nothing.
                        continue
                    resolved.append(ParsedStaticValue(text=text))
                case _:
                    msg = f"Unexpected segment type during scan resolution: {type(segment).__name__}"
                    raise TypeError(msg)
        return resolved


def _render_variable(
    variable: ParsedVariable,
    variables: MacroVariables,
    secrets_manager: SecretsManager,
) -> str:
    """Render a single variable segment to a string.

    Optional variables not supplied contribute the empty string.
    """
    resolved = resolve_variable(variable, variables, secrets_manager)
    if resolved is None:
        return ""
    return resolved


def _normalize_directory_path(directory: str) -> str:
    """Strip a trailing path separator so `ListDirectoryRequest` sees the dir itself.

    The split helper always leaves the trailing separator on the prefix string
    so the prefix round-trips cleanly; strip it at the OS boundary.
    """
    if directory.endswith(os.sep) and len(directory) > 1:
        return directory[: -len(os.sep)]
    return directory


def _split_on_token_component(
    segments: list[ParsedSegment],
) -> tuple[list[ParsedSegment], list[ParsedSegment], list[ParsedSegment]]:
    """Partition fully-resolved segments on the path component holding the sequence token.

    Returns:
        (prefix_segments, token_component_segments, suffix_segments)

        - `prefix_segments` resolve to a literal directory path ending in a
          separator (or empty for templates whose token is at position 0).
        - `token_component_segments` cover the full path component containing
          the sequence token — static text on either side of the token within
          that component is preserved (e.g. `render_####_v2`).
        - `suffix_segments` resolve to a literal sub-path starting with a
          separator (or empty when the token is in the final component).

    All static segments have path separators in them pre-split; we walk by
    character position across the resolved-segments string.
    """
    full_text = _segments_to_string(segments)
    token_index = _find_sequence_token_index(segments)

    # Compute the token's character offsets in the concatenated string so we
    # can find the enclosing path separators on either side.
    token_start = sum(len(_segment_rendered_text(seg)) for seg in segments[:token_index])
    token_rendered_length = len(_segment_rendered_text(segments[token_index]))
    token_end = token_start + token_rendered_length

    # Separator before the token defines where the prefix ends.
    # Everything up to and including that separator is the prefix.
    separator_before = full_text.rfind(os.sep, 0, token_start)
    if separator_before == -1:
        # Token is in the first path component. Prefix is empty (current dir).
        prefix_split_char = 0
    else:
        prefix_split_char = separator_before + 1  # include the separator in the prefix

    # Separator after the token defines where the suffix starts.
    # Everything from that separator onward is the suffix.
    separator_after = full_text.find(os.sep, token_end)
    if separator_after == -1:
        # Token is in the final path component.
        suffix_split_char = len(full_text)
    else:
        suffix_split_char = separator_after  # include the separator in the suffix

    return (
        _slice_segments(segments, 0, prefix_split_char),
        _slice_segments(segments, prefix_split_char, suffix_split_char),
        _slice_segments(segments, suffix_split_char, len(full_text)),
    )


def _find_sequence_token_index(segments: list[ParsedSegment]) -> int:
    """Return the index of the single sequence token in the segment list."""
    for i, seg in enumerate(segments):
        if isinstance(seg, ParsedSequenceToken):
            return i
    msg = "Segment list contains no sequence token (should be unreachable from SequenceTemplate)"
    raise SequenceTemplateError(msg)


def _slice_segments(segments: list[ParsedSegment], start_char: int, end_char: int) -> list[ParsedSegment]:
    """Slice the concatenated segment string by character offsets, preserving segment types.

    Splits static segments if a slice boundary falls mid-segment. Sequence
    tokens must fall entirely within a single slice — this invariant holds
    because splits happen on path separators and tokens can't contain them.
    """
    if start_char >= end_char:
        return []

    out: list[ParsedSegment] = []
    cursor = 0
    for segment in segments:
        seg_text = _segment_rendered_text(segment)
        seg_end = cursor + len(seg_text)

        # Entirely before the slice: skip.
        if seg_end <= start_char:
            cursor = seg_end
            continue
        # Entirely after the slice: done.
        if cursor >= end_char:
            break

        # Some or all of this segment is within the slice.
        local_start = max(0, start_char - cursor)
        local_end = min(len(seg_text), end_char - cursor)

        if isinstance(segment, ParsedStaticValue):
            out.append(ParsedStaticValue(text=seg_text[local_start:local_end]))
        else:
            # Sequence tokens are indivisible and must not be partially sliced.
            if local_start != 0 or local_end != len(seg_text):
                msg = f"Slice boundary fell inside a non-static segment: {type(segment).__name__}"
                raise SequenceTemplateError(msg)
            out.append(segment)

        cursor = seg_end

    return out


def _segment_rendered_text(segment: ParsedSegment) -> str:
    """Return the literal string a fully-resolved segment contributes to a path.

    Static segments contribute their text. Sequence tokens contribute their
    `to_literal()` form (`####` or `%04d`) — this is the width the static
    prefix scan expects, and the regex/glob stages handle interpretation.
    """
    if isinstance(segment, ParsedStaticValue):
        return segment.text
    if isinstance(segment, ParsedSequenceToken):
        return segment.to_literal()
    msg = f"Unexpected segment type at scan time: {type(segment).__name__}"
    raise SequenceTemplateError(msg)


def _segments_to_string(segments: list[ParsedSegment]) -> str:
    """Concatenate segments' rendered text (static + literal token form)."""
    return "".join(_segment_rendered_text(seg) for seg in segments)


def _segments_to_glob(segments: list[ParsedSegment]) -> str:
    """Build a coarse fnmatch-style glob from segments.

    Sequence tokens glob to `*` — permissive on width. The exact minimum-width
    check happens in the regex stage via `segments_to_regex`.
    """
    parts: list[str] = []
    for segment in segments:
        match segment:
            case ParsedStaticValue():
                parts.append(segment.text)
            case ParsedSequenceToken():
                parts.append("*")
            case _:
                msg = f"Unexpected segment type in glob stage: {type(segment).__name__}"
                raise SequenceTemplateError(msg)
    return "".join(parts)


def _list_directory_entries(
    directory_path: str,
    pattern: str,
    *,
    kind: _EntryKind,
) -> list[tuple[str, str]]:
    """Issue a ListDirectoryRequest and return (entry_name, absolute_path) pairs.

    Filters by `kind`: FILES, DIRECTORIES, or EITHER. All filesystem access
    flows through the OSManager handler, which takes care of Windows
    long-path prefixes, permission errors, hidden-file filtering, and the
    like.

    Returns an empty list on any failure (no sequence to produce). Callers
    can distinguish "no matches" from "listing failed" by checking whether
    the directory exists via their own means, but for the scan use case the
    two cases collapse: either way we have no frames.
    """
    # Imports are local to avoid a module-level cycle: griptape_nodes ->
    # os_manager -> macro_parser, and the sequence module would close the
    # loop. The cycle only exists at import time; runtime usage is fine.
    from griptape_nodes.retained_mode.events.os_events import (
        ListDirectoryRequest,
        ListDirectoryResultSuccess,
    )
    from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

    result = GriptapeNodes.handle_request(
        ListDirectoryRequest(
            directory_path=directory_path,
            pattern=pattern,
            workspace_only=False,
            show_hidden=False,
            include_size=False,
            include_modified_time=False,
            include_mime_type=False,
            include_absolute_path=True,
        )
    )
    if not isinstance(result, ListDirectoryResultSuccess):
        return []

    entries: list[tuple[str, str]] = []
    for entry in result.entries:
        match kind:
            case _EntryKind.FILES:
                if entry.is_dir:
                    continue
            case _EntryKind.DIRECTORIES:
                if not entry.is_dir:
                    continue
            case _EntryKind.EITHER:
                pass
        entries.append((entry.name, entry.absolute_path or entry.path))
    # Sort lexicographically by filename for deterministic duplicate-frame
    # tie-breaking across platforms.
    entries.sort(key=lambda e: e[0])
    return entries


def _collect_frames(
    candidates: list[tuple[str, str]],
    token_component_segments: list[ParsedSegment],
    suffix_path: str,
    template_display: str,
) -> tuple[dict[int, Path], dict[int, list[Path]]]:
    """Match candidates, verify suffix existence if any, collect frames.

    For each candidate entry name matching the token component, extracts the
    frame integer. When `suffix_path` is non-empty, the final file lives at
    `<candidate>/<suffix>`; that file's existence is verified via another
    ListDirectoryRequest on the candidate directory.
    """
    prefix_str, token, suffix_str = _decompose_token_component(token_component_segments)

    frames_by_number: dict[int, Path] = {}
    shadowed_files: dict[int, list[Path]] = {}

    for entry_name, absolute_path in candidates:
        frame = _extract_frame_from_entry(entry_name, prefix_str, token, suffix_str)
        if frame is None:
            continue

        final_path = _verified_final_path(absolute_path, suffix_path)
        if final_path is None:
            continue

        if frame in frames_by_number:
            shadowed_files.setdefault(frame, []).append(final_path)
            logger.warning(
                "Sequence scan of '%s': frame %d has duplicate file '%s'; keeping '%s' (lexicographically first).",
                template_display,
                frame,
                final_path,
                frames_by_number[frame],
            )
            continue
        frames_by_number[frame] = final_path

    return frames_by_number, shadowed_files


def _decompose_token_component(
    segments: list[ParsedSegment],
) -> tuple[str, ParsedSequenceToken, str]:
    """Split a token-component segment list into (prefix_str, token, suffix_str).

    The token component is guaranteed by `_split_on_token_component` to have
    the shape [ParsedStaticValue?, ParsedSequenceToken, ParsedStaticValue?] —
    one token in the middle with at most one static segment on each side.
    Raises if the list violates that invariant.
    """
    prefix_str = ""
    suffix_str = ""
    token: ParsedSequenceToken | None = None
    for segment in segments:
        match segment:
            case ParsedStaticValue():
                if token is None:
                    prefix_str += segment.text
                else:
                    suffix_str += segment.text
            case ParsedSequenceToken():
                if token is not None:
                    msg = "Token component contains multiple sequence tokens (should be unreachable)"
                    raise SequenceTemplateError(msg)
                token = segment
            case _:
                msg = f"Token component contains unexpected segment: {type(segment).__name__}"
                raise SequenceTemplateError(msg)
    if token is None:
        msg = "Token component contains no sequence token (should be unreachable)"
        raise SequenceTemplateError(msg)
    return prefix_str, token, suffix_str


def _extract_frame_from_entry(
    entry_name: str,
    prefix_str: str,
    token: ParsedSequenceToken,
    suffix_str: str,
) -> int | None:
    """Match `entry_name` against a decomposed token component; return frame or None.

    Uses Nuke read semantics: the digits between prefix and suffix must be at
    least `max(token.width, 1)` wide. Accepts a leading `-` for negative
    frames (sign is extra to padding). No pattern language — four string
    operations: startswith, endswith, slice, isdigit.
    """
    if not entry_name.startswith(prefix_str):
        return None
    if not entry_name.endswith(suffix_str):
        return None

    # Guard the slice: prefix and suffix must not overlap.
    if len(prefix_str) + len(suffix_str) > len(entry_name):
        return None

    middle = (
        entry_name[len(prefix_str) : len(entry_name) - len(suffix_str)] if suffix_str else entry_name[len(prefix_str) :]
    )

    sign = ""
    digits = middle
    if digits.startswith("-"):
        sign, digits = "-", digits[1:]

    if not digits or not digits.isdigit():
        return None
    if len(digits) < max(token.width, 1):  # Nuke minimum-width read semantics
        return None

    return int(sign + digits)


def _verified_final_path(candidate_absolute_path: str, suffix_path: str) -> Path | None:
    """Return the full path for a candidate if its suffix file exists on disk.

    When `suffix_path` is empty, the candidate IS the final path (file case).
    When `suffix_path` is non-empty, the candidate is a directory whose
    `suffix_path` descendant must exist — verified via another
    ListDirectoryRequest so we never touch the filesystem directly.
    """
    if not suffix_path:
        return Path(candidate_absolute_path)

    # Suffix starts with a separator; strip it before joining.
    relative_suffix = suffix_path.lstrip(os.sep)
    expected_path = Path(candidate_absolute_path) / relative_suffix

    # To confirm existence without touching the filesystem directly, list the
    # parent of the expected file and look for a matching entry name.
    parent = expected_path.parent
    filename = expected_path.name
    existing = _list_directory_entries(
        directory_path=str(parent),
        pattern=filename,
        kind=_EntryKind.FILES,
    )
    if not existing:
        return None
    return expected_path
