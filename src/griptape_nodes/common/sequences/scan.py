"""Directory scanning for sequences.

Module-private worker behind `ScanSequencesRequest`. Takes a directory + a
fileseq pattern (either as a string like `render.####.exr` or a pre-constructed
`FileSequence`), lists the directory via `ListDirectoryRequest`, hands the
filenames to `fileseq.findSequencesInList`, applies subset clipping and the
chosen missing-item policy, and returns a list of `Sequence` objects.

All filesystem I/O is routed through the engine's request bus — this module
never calls `os.scandir`, `os.walk`, or `pathlib.Path.glob` directly.
fileseq's filesystem-touching helpers (`findSequencesOnDisk`,
`findSequenceOnDisk`) are not used.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import NamedTuple

from fileseq.constants import PAD_STYLE_HASH1
from fileseq.filesequence import FileSequence

from griptape_nodes.common.sequences.models import (
    InvalidSubsetBoundsError,
    InvalidTemplateError,
    MissingItemPolicy,
    Sequence,
)
from griptape_nodes.common.sequences.policies import PolicyContext, apply_policy
from griptape_nodes.retained_mode.events.os_events import (
    ListDirectoryRequest,
    ListDirectoryResultSuccess,
)
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

logger = logging.getLogger("griptape_nodes")

# Mandatory pad style: each `#` = 1 zero, matching Nuke. fileseq's default
# (HASH4) treats each `#` as 4 zeros, which would silently break templates.
PAD_STYLE = PAD_STYLE_HASH1


@dataclass(frozen=True)
class _PresentNumbers:
    """Map of item numbers to their on-disk paths, plus the dropped count."""

    by_number: dict[int, Path]
    dropped_negatives: int


class _ActiveRange(NamedTuple):
    """The [first, last] bounds after subset clipping is applied."""

    first: int
    last: int


def _scan_sequences(
    directory: str,
    pattern: str | FileSequence,
    *,
    policy: MissingItemPolicy = MissingItemPolicy.SPLIT,
    start: int | None = None,
    end: int | None = None,
) -> list[Sequence]:
    """Find sequences matching `pattern` inside `directory`.

    Module-private. The public entry point is `ScanSequencesRequest` on the
    engine's event bus; that request's handler invokes this function via
    `asyncio.to_thread()` so neither the directory listing nor fileseq parsing
    blocks the event loop.

    Args:
        directory: Absolute directory path to scan. Listed via
            `ListDirectoryRequest` (no direct filesystem access).
        pattern: Either a fileseq pattern string (e.g. "render.####.exr") or
            a pre-constructed `FileSequence` whose basename + padding +
            extension act as the filter. Sequence tokens are interpreted in
            HASH1 mode regardless of pattern syntax.
        policy: How to handle gaps within the matched range. SPLIT yields one
            Sequence per contiguous run; the others yield exactly one
            Sequence with policy-driven gap fills (or omissions for SKIP, or
            a `MissingItemError` for ABORT).
        start: Optional lower bound (inclusive) for the active subset. Items
            below this are dropped from output. Must be >= 0 if supplied.
        end: Optional upper bound (inclusive) for the active subset. Items
            above this are dropped from output. Must be >= start if both
            supplied.

    Returns:
        List of `Sequence` objects. Empty if the directory listing fails, the
        directory contains no files matching the pattern, or the active
        subset is empty.

    Raises:
        InvalidSubsetBoundsError: If `start` < 0 or `end` < `start`.
        InvalidTemplateError: If `pattern` contains more than one sequence token.
        MissingItemError: If `policy` is ABORT and a gap is found inside the
            active range.

    Negative numbers on disk are filtered out before policy is applied;
    `Sequence.dropped_negative_number_count` records how many were skipped.
    """
    _validate_subset_bounds(start, end)
    target = _coerce_target_pattern(pattern)

    relevant = _list_pattern_matching_filenames(directory, target)
    if not relevant:
        return []

    present = _collect_present_numbers(directory, target, relevant)
    if not present.by_number:
        return []

    discovered_first = min(present.by_number)
    discovered_last = max(present.by_number)
    active = _compute_active_range(start, end, discovered_first, discovered_last)
    if active.first > active.last:
        return []

    return apply_policy(
        PolicyContext(
            fseq=target,
            present_numbers=present.by_number,
            directory=directory,
            policy=policy,
            first=active.first,
            last=active.last,
            discovered_first=discovered_first,
            discovered_last=discovered_last,
            dropped_negative_number_count=present.dropped_negatives,
        )
    )


def _validate_subset_bounds(start: int | None, end: int | None) -> None:
    """Reject negative start values and end < start ranges before any work."""
    if start is not None and start < 0:
        msg = f"Attempted to validate sequence subset bounds with start={start}. Failed because start must be >= 0."
        raise InvalidSubsetBoundsError(msg)
    if start is not None and end is not None and end < start:
        msg = (
            f"Attempted to validate sequence subset bounds with start={start}, end={end}. "
            f"Failed because end must be >= start."
        )
        raise InvalidSubsetBoundsError(msg)


def _coerce_target_pattern(pattern: str | FileSequence) -> FileSequence:
    """Construct a FileSequence (in HASH1 mode) from the caller's pattern.

    For string inputs, also rejects multi-token templates up-front. fileseq's
    own behavior here is uneven: it raises on some forms (`v##_f####.exr`)
    but silently accepts others (`render.##.##.exr` parses as a single
    `##.##` padding) — neither produces what the user meant. Catching it
    here gives a clear error before any work is done.
    """
    if isinstance(pattern, FileSequence):
        return pattern
    token_count = _count_sequence_tokens(pattern)
    if token_count > 1:
        msg = (
            f"Attempted to parse fileseq template {pattern!r}. "
            f"Failed because it contains {token_count} sequence tokens; only one is supported. "
            f"Multi-token templates like 'v##_f####.exr' are not handled correctly by fileseq."
        )
        raise InvalidTemplateError(msg)
    return FileSequence(pattern, pad_style=PAD_STYLE)


# Recognized sequence-token forms, in fileseq's HASH1 idiom:
# - hash runs: `#`, `##`, `####`, ...
# - printf:    `%d`, `%4d`, `%04d`
# - at runs:   `@`, `@@`, ... (Houdini/RV)
# - $F tokens: `$F`, `$F4` (Houdini variable form)
_TOKEN_PATTERN = re.compile(r"#+|%0?\d*d|@+|\$F\d*")


def _count_sequence_tokens(pattern: str) -> int:
    """Return the number of sequence tokens in `pattern`.

    Used to reject multi-token templates before they reach fileseq.
    """
    return len(_TOKEN_PATTERN.findall(pattern))


def _list_pattern_matching_filenames(directory: str, target: FileSequence) -> list[str]:
    """List `directory` and keep only files whose name matches the target shape.

    Filters by basename prefix and extension suffix before fileseq sees the
    list — avoids polluting fileseq's grouping with unrelated files (which
    would produce noise sequences).
    """
    filenames = _list_directory_filenames(directory)
    if not filenames:
        return []
    target_basename = target.basename()
    target_extension = target.extension()
    return [name for name in filenames if name.startswith(target_basename) and name.endswith(target_extension)]


def _collect_present_numbers(
    directory: str,
    target: FileSequence,
    relevant_filenames: list[str],
) -> _PresentNumbers:
    """Run fileseq inference on `relevant_filenames` and collect number->path entries.

    Drops negatives, filters to sequences whose padding matches `target`, and
    reconstructs absolute paths via fileseq's frame-rendering.
    """
    inferred = FileSequence.findSequencesInList(relevant_filenames, pad_style=PAD_STYLE)
    matching = [s for s in inferred if s.zfill() == target.zfill()]
    if not matching:
        return _PresentNumbers(by_number={}, dropped_negatives=0)

    present: dict[int, Path] = {}
    dropped = 0
    for seq in matching:
        frame_set = seq.frameSet()
        if frame_set is None:
            continue
        for number in frame_set:
            # Subframes (Decimal/float) aren't enabled (allow_subframes is
            # False by default) so this is always an int in practice;
            # narrow the type for pyright.
            if not isinstance(number, int):
                continue
            if number < 0:
                dropped += 1
                continue
            present[number] = Path(directory) / seq.frame(number)

    if dropped:
        logger.warning(
            "scan_sequences: dropped %d negative number(s) from %r",
            dropped,
            f"{target.basename()}{target.padding()}{target.extension()}",
        )
    return _PresentNumbers(by_number=present, dropped_negatives=dropped)


def _compute_active_range(
    start: int | None,
    end: int | None,
    discovered_first: int,
    discovered_last: int,
) -> _ActiveRange:
    """Clip the discovered range to the optional [start, end] subset bounds."""
    if start is None:
        active_first = discovered_first
    else:
        active_first = max(start, discovered_first)
    if end is None:
        active_last = discovered_last
    else:
        active_last = min(end, discovered_last)
    return _ActiveRange(first=active_first, last=active_last)


def _list_directory_filenames(directory: str) -> list[str]:
    """List `directory` via ListDirectoryRequest, returning bare filenames.

    Returns an empty list on any listing failure. Suppresses client toasts
    via `broadcast_result=False` since "directory not found" is a normal
    outcome of a user-supplied template.
    """
    result = GriptapeNodes.handle_request(
        ListDirectoryRequest(
            directory_path=directory,
            workspace_only=False,
            show_hidden=False,
            include_size=False,
            include_modified_time=False,
            include_mime_type=False,
            include_absolute_path=False,
            broadcast_result=False,
        )
    )
    if not isinstance(result, ListDirectoryResultSuccess):
        return []
    # Skip directories — we want files only.
    return [entry.name for entry in result.entries if not entry.is_dir]
