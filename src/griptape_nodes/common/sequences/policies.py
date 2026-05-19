"""Gap-handling policy logic for sequences.

Pure functions that take a `fileseq.FileSequence` plus the present-numbers
map and produce a list of `Sequence` objects shaped according to the chosen
policy. No I/O, no fileseq state mutation — just transformation.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from griptape_nodes.common.sequences.models import (
    MissingItemPolicy,
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
    present_numbers: dict[int, Path]
    directory: str
    policy: MissingItemPolicy
    first: int
    last: int
    discovered_first: int
    discovered_last: int
    dropped_negative_number_count: int


def apply_policy(context: PolicyContext) -> list[Sequence]:
    """Build the final list of Sequences according to `context.policy`.

    `context.present_numbers` maps each present integer key to its on-disk
    Path. Numbers may sit inside or outside [first, last]; only those inside
    the active range are surfaced. SPLIT returns multiple sequences (one per
    contiguous run). All other policies return exactly one sequence.

    `context.fseq` is used only to read its formatting metadata (basename,
    padding, extension, zfill); it is not mutated.
    """
    if context.policy is MissingItemPolicy.SPLIT:
        return _apply_split(context)
    return [_apply_single(context)]


def _apply_split(context: PolicyContext) -> list[Sequence]:
    """SPLIT: emit one Sequence per contiguous run of present numbers in [first, last]."""
    in_range_numbers = sorted(n for n in context.present_numbers if context.first <= n <= context.last)
    if not in_range_numbers:
        return []

    runs = _contiguous_runs(in_range_numbers)
    return [_build_split_sequence(run, context) for run in runs]


def _build_split_sequence(run: list[int], context: PolicyContext) -> Sequence:
    """Build one Sequence from a contiguous run of present numbers."""
    entries = [_present_entry(context.fseq, number, context.present_numbers[number]) for number in run]
    return Sequence(
        entries=entries,
        first=run[0],
        last=run[-1],
        discovered_first=context.discovered_first,
        discovered_last=context.discovered_last,
        padding=context.fseq.zfill(),
        pattern=_canonical_pattern(context.fseq),
        directory=context.directory,
        policy=MissingItemPolicy.SPLIT,
        dropped_negative_number_count=context.dropped_negative_number_count,
        present_numbers=set(run),
    )


def _apply_single(context: PolicyContext) -> Sequence:
    """ERROR / NEAREST: emit one Sequence over [first, last]."""
    in_range_present = {n: p for n, p in context.present_numbers.items() if context.first <= n <= context.last}
    entries: list[SequenceEntry] = []
    for number in range(context.first, context.last + 1):
        if number in in_range_present:
            entries.append(_present_entry(context.fseq, number, in_range_present[number]))
            continue
        gap_entry = _gap_entry(number, context.policy, context.fseq, in_range_present)
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
        dropped_negative_number_count=context.dropped_negative_number_count,
        present_numbers=set(in_range_present.keys()),
    )


def _gap_entry(
    number: int,
    policy: MissingItemPolicy,
    fseq: FileSequence,
    in_range_present: dict[int, Path],
) -> SequenceEntry | None:
    """Build the SequenceEntry for a missing item, or None to omit it.

    None is returned for the ERROR policy (which drops gaps from `entries`)
    and for NEAREST when there's no neighbor at all (empty in-range present
    set).
    """
    match policy:
        case MissingItemPolicy.ERROR:
            return None
        case MissingItemPolicy.NEAREST:
            neighbor_path = _nearest_path(number, in_range_present)
            if neighbor_path is None:
                return None
            return SequenceEntry(
                number=number,
                padded_number=_format_number(fseq, number),
                path=neighbor_path,
            )
        case _:
            msg = f"Unknown missing-item policy: {policy}"
            raise ValueError(msg)


def _contiguous_runs(sorted_numbers: list[int]) -> list[list[int]]:
    """Group an already-sorted number list into contiguous integer runs."""
    if not sorted_numbers:
        return []
    runs: list[list[int]] = [[sorted_numbers[0]]]
    for number in sorted_numbers[1:]:
        if number == runs[-1][-1] + 1:
            runs[-1].append(number)
        else:
            runs.append([number])
    return runs


def _nearest_path(number: int, present: dict[int, Path]) -> Path | None:
    """Find the nearest present number's path. Backward-first, then forward.

    Per the spec: when a missing item needs a NEAREST fill, we prefer the
    closest *earlier* present number. Only if no earlier number exists do we
    look forward. Returns None only if `present` is empty.
    """
    if not present:
        return None
    earlier = max((n for n in present if n < number), default=None)
    if earlier is not None:
        return present[earlier]
    later = min((n for n in present if n > number), default=None)
    if later is not None:
        return present[later]
    return None


def _present_entry(fseq: FileSequence, number: int, path: Path) -> SequenceEntry:
    """Build a SequenceEntry for a present-on-disk item."""
    return SequenceEntry(number=number, padded_number=_format_number(fseq, number), path=path)


def _format_number(fseq: FileSequence, number: int) -> str:
    """Render an integer key with the sequence's declared zero-padding.

    `fseq.frame(N)` returns the full filename (basename + padded number +
    extension). We want just the padded number (e.g. "0005" for number 5
    against `####`), so we compute it directly from `zfill()`.
    """
    width = fseq.zfill()
    if width <= 0:
        return str(number)
    if number < 0:
        return f"-{abs(number):0{width}d}"
    return f"{number:0{width}d}"


def _canonical_pattern(fseq: FileSequence) -> str:
    """Reconstruct the basename + padding + extension form (no number range)."""
    return f"{fseq.basename()}{fseq.padding()}{fseq.extension()}"
