"""Data shapes for the sequences module.

Three concepts:
    - `MissingItemPolicy`: how to fill gaps inside a sequence's range.
    - `Sequence`: one contiguous-or-gap-aware sequence with metadata.
    - `SequenceEntry`: one item inside a Sequence (number + path or marker).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING, NamedTuple

if TYPE_CHECKING:
    from pathlib import Path


class MissingItemPolicy(StrEnum):
    """How to handle gaps inside a sequence's number range.

    The choice changes the *shape* of `scan_sequences` output:

    - `SPLIT`: returns multiple Sequences, each contiguous (no gaps inside any).
    - All others: returns exactly one Sequence whose entries span the full
      [first, last] range, with policy applied to fill missing items.
    """

    SPLIT = "split"  # Sparse sequence becomes N contiguous sub-sequences.
    ERROR = "error"  # Single sequence with only the present items; gaps absent.
    NEAREST = "nearest"  # Dense sequence; gaps point at the backward-first neighbor.
    BLACK = "black"  # Dense sequence; gaps hold a BLACK MissingItemMarker.
    CHECKERBOARD = "checkerboard"  # Dense sequence; gaps hold a CHECKERBOARD marker.


@dataclass(frozen=True)
class MissingItemMarker:
    """Sentinel returned for a missing item under BLACK/CHECKERBOARD.

    Image-generating callers (e.g. node-level renderers) interpret the marker
    and synthesize the appropriate item. This module does not produce images.
    """

    policy: MissingItemPolicy
    number: int
    padded_number: str


class MissingItemError(Exception):
    """Raised when a sequence is queried for an unrepresented item.

    Currently unused at scan time (ERROR policy just produces a sparse Sequence
    rather than raising). Reserved for future query APIs on Sequence.
    """

    def __init__(self, number: int) -> None:
        super().__init__(f"Item {number} is missing from the sequence")
        self.number = number


class SequenceEntry(NamedTuple):
    """One entry in a Sequence.

    Attributes:
        number: The integer key (e.g. 5).
        padded_number: The zero-padded form matching the sequence's declared
            width (e.g. "0005" for number 5 in a `####` sequence). For
            unpadded `%d` patterns this is just the bare integer as a string.
        path: The on-disk file path, OR a MissingItemMarker for synthesized
            slots under BLACK/CHECKERBOARD policy.
    """

    number: int
    padded_number: str
    path: Path | MissingItemMarker


@dataclass
class Sequence:
    """A scanned sequence of items plus metadata.

    Attributes:
        entries: List of SequenceEntry objects, one per item inside the
            active range (after subset clipping). The exact contents depend
            on policy:
                - SPLIT: contiguous range; no markers.
                - ERROR: only items that exist on disk; markers never appear.
                - NEAREST: dense; missing items carry the nearest existing
                  item's path.
                - BLACK / CHECKERBOARD: dense; missing items carry markers.
        first: Lowest number in the active range (post-subset).
        last: Highest number in the active range (post-subset).
        discovered_first: Lowest number actually found on disk before
            subset clipping.
        discovered_last: Highest number actually found on disk before
            subset clipping.
        padding: The fileseq zfill width (e.g. 4 for `####`, 0 for `%d`).
        pattern: The canonical fileseq pattern (e.g. "render.####.exr").
        directory: Absolute directory the sequence was scanned from.
        policy: The policy applied during scan.
    """

    entries: list[SequenceEntry]
    first: int
    last: int
    discovered_first: int
    discovered_last: int
    padding: int
    pattern: str
    directory: str
    policy: MissingItemPolicy
    dropped_negative_number_count: int = 0
    # Numbers present on disk inside [first, last]. Useful when the policy
    # densified gaps — callers can still find out what was actually there.
    present_numbers: set[int] = field(default_factory=set)

    @property
    def missing_numbers(self) -> set[int]:
        """Numbers between `first` and `last` that aren't on disk.

        Computed from `present_numbers`. Always present regardless of policy
        (e.g. the SPLIT policy would have an empty set since each sub-sequence
        is contiguous; NEAREST/BLACK/CHECKERBOARD show the gaps that got
        filled).
        """
        return {n for n in range(self.first, self.last + 1) if n not in self.present_numbers}
