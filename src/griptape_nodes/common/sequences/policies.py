"""Gap-handling policy logic for sequences.

Pure functions that take a `fileseq.FileSequence` plus the present-frame map
and produce a list of `Sequence` objects shaped according to the chosen
policy. No I/O, no fileseq state mutation — just transformation.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from griptape_nodes.common.sequences.models import (
    MissingFrameMarker,
    MissingFramePolicy,
    Sequence,
    SequenceEntry,
)

if TYPE_CHECKING:
    from pathlib import Path

    from fileseq.filesequence import FileSequence


@dataclass(frozen=True)
class PolicyContext:
    """Bundle of inputs for `apply_policy`.

    Groups the unchanging context (range, discovered range, fileseq object,
    drop count) so callers and helpers can pass one object instead of nine
    keyword arguments.
    """

    fseq: FileSequence
    present_frames: dict[int, Path]
    directory: str
    policy: MissingFramePolicy
    first: int
    last: int
    discovered_first: int
    discovered_last: int
    dropped_negative_frame_count: int


def apply_policy(context: PolicyContext) -> list[Sequence]:
    """Build the final list of Sequences according to `context.policy`.

    `context.present_frames` maps each present frame integer to its on-disk
    Path. Frames may sit inside or outside [first, last]; only those inside
    the active range are surfaced. SPLIT returns multiple sequences (one per
    contiguous run). All other policies return exactly one sequence.

    `context.fseq` is used only to read its formatting metadata (basename,
    padding, extension, zfill); it is not mutated.
    """
    if context.policy is MissingFramePolicy.SPLIT:
        return _apply_split(context)
    return [_apply_single(context)]


def _apply_split(context: PolicyContext) -> list[Sequence]:
    """SPLIT: emit one Sequence per contiguous run of present frames in [first, last]."""
    in_range_frames = sorted(f for f in context.present_frames if context.first <= f <= context.last)
    if not in_range_frames:
        return []

    runs = _contiguous_runs(in_range_frames)
    return [_build_split_sequence(run, context) for run in runs]


def _build_split_sequence(run: list[int], context: PolicyContext) -> Sequence:
    """Build one Sequence from a contiguous run of present frames."""
    entries = [_present_entry(context.fseq, frame, context.present_frames[frame]) for frame in run]
    return Sequence(
        entries=entries,
        first=run[0],
        last=run[-1],
        discovered_first=context.discovered_first,
        discovered_last=context.discovered_last,
        padding=context.fseq.zfill(),
        pattern=_canonical_pattern(context.fseq),
        directory=context.directory,
        policy=MissingFramePolicy.SPLIT,
        dropped_negative_frame_count=context.dropped_negative_frame_count,
        present_frames=set(run),
    )


def _apply_single(context: PolicyContext) -> Sequence:
    """ERROR / NEAREST / BLACK / CHECKERBOARD: emit one Sequence over [first, last]."""
    in_range_present = {f: p for f, p in context.present_frames.items() if context.first <= f <= context.last}
    entries: list[SequenceEntry] = []
    for frame in range(context.first, context.last + 1):
        if frame in in_range_present:
            entries.append(_present_entry(context.fseq, frame, in_range_present[frame]))
            continue
        gap_entry = _gap_entry(frame, context.policy, context.fseq, in_range_present)
        if gap_entry is not None:
            entries.append(gap_entry)

    return Sequence(
        entries=entries,
        first=context.first,
        last=context.last,
        discovered_first=context.discovered_first,
        discovered_last=context.discovered_last,
        padding=context.fseq.zfill(),
        pattern=_canonical_pattern(context.fseq),
        directory=context.directory,
        policy=context.policy,
        dropped_negative_frame_count=context.dropped_negative_frame_count,
        present_frames=set(in_range_present.keys()),
    )


def _gap_entry(
    frame: int,
    policy: MissingFramePolicy,
    fseq: FileSequence,
    in_range_present: dict[int, Path],
) -> SequenceEntry | None:
    """Build the SequenceEntry for a missing frame, or None to omit it.

    None is returned for the ERROR policy (which drops gaps from `entries`)
    and for NEAREST when there's no neighbor at all (empty in-range present
    set).
    """
    match policy:
        case MissingFramePolicy.ERROR:
            return None
        case MissingFramePolicy.NEAREST:
            neighbor_path = _nearest_path(frame, in_range_present)
            if neighbor_path is None:
                return None
            return SequenceEntry(
                frame=frame,
                frame_string=_format_frame(fseq, frame),
                path=neighbor_path,
            )
        case MissingFramePolicy.BLACK | MissingFramePolicy.CHECKERBOARD:
            marker = MissingFrameMarker(
                policy=policy,
                frame=frame,
                frame_string=_format_frame(fseq, frame),
            )
            return SequenceEntry(frame=frame, frame_string=marker.frame_string, path=marker)
        case _:
            msg = f"Unknown missing-frame policy: {policy}"
            raise ValueError(msg)


def _contiguous_runs(sorted_frames: list[int]) -> list[list[int]]:
    """Group an already-sorted frame list into contiguous integer runs."""
    if not sorted_frames:
        return []
    runs: list[list[int]] = [[sorted_frames[0]]]
    for frame in sorted_frames[1:]:
        if frame == runs[-1][-1] + 1:
            runs[-1].append(frame)
        else:
            runs.append([frame])
    return runs


def _nearest_path(frame: int, present: dict[int, Path]) -> Path | None:
    """Find the nearest present frame's path. Backward-first, then forward.

    Per the spec: when a missing frame needs a NEAREST fill, we prefer the
    closest *earlier* present frame. Only if no earlier frame exists do we
    look forward. Returns None only if `present` is empty.
    """
    if not present:
        return None
    earlier = max((f for f in present if f < frame), default=None)
    if earlier is not None:
        return present[earlier]
    later = min((f for f in present if f > frame), default=None)
    if later is not None:
        return present[later]
    return None


def _present_entry(fseq: FileSequence, frame: int, path: Path) -> SequenceEntry:
    """Build a SequenceEntry for a present-on-disk frame."""
    return SequenceEntry(frame=frame, frame_string=_format_frame(fseq, frame), path=path)


def _format_frame(fseq: FileSequence, frame: int) -> str:
    """Render a frame integer with the sequence's declared zero-padding.

    `fseq.frame(N)` returns the full filename (basename + padded frame +
    extension). We want just the padded number (e.g. "0005" for frame 5
    against `####`), so we compute it directly from `zfill()`.
    """
    width = fseq.zfill()
    if width <= 0:
        return str(frame)
    if frame < 0:
        return f"-{abs(frame):0{width}d}"
    return f"{frame:0{width}d}"


def _canonical_pattern(fseq: FileSequence) -> str:
    """Reconstruct the basename + padding + extension form (no frame range)."""
    return f"{fseq.basename()}{fseq.padding()}{fseq.extension()}"
