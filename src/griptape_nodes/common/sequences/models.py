"""Data shapes for the sequences module.

Three concepts:
    - `MissingItemPolicy`: how to fill gaps inside a sequence's range.
    - `Sequence`: one contiguous-or-gap-aware sequence with metadata.
    - `SequenceEntry`: one item inside a Sequence (number + path).
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field, computed_field


class MissingItemPolicy(StrEnum):
    """How to handle gaps inside a sequence's number range.

    The choice changes the *shape* of `scan_sequences` output:

    - `SPLIT`: returns multiple Sequences, each contiguous (no gaps inside any).
    - `ERROR`: one Sequence with only the present items; gaps absent from `entries`.
    - `NEAREST`: one Sequence whose entries span the full [first, last] range,
      with each missing slot's path pointing at the nearest present neighbor.
    """

    SPLIT = "split"  # Sparse sequence becomes N contiguous sub-sequences.
    ERROR = "error"  # Single sequence with only the present items; gaps absent.
    NEAREST = "nearest"  # Dense sequence; gaps point at the backward-first neighbor.


class SequenceEntry(BaseModel):
    """One entry in a Sequence.

    Attributes:
        number: The integer key (e.g. 5).
        padded_number: The zero-padded form matching the sequence's declared
            width (e.g. "0005" for number 5 in a `####` sequence). For
            unpadded `%d` patterns this is just the bare integer as a string.
        path: Absolute on-disk file path as a string (platform-neutral payload).
            Under NEAREST, gap entries carry the nearest present neighbor's
            path; the entry's `number` still records the slot the entry
            represents — cross-check against `Sequence.present_numbers` to
            tell present from filled.
    """

    number: int
    padded_number: str
    path: str


class Sequence(BaseModel):
    """A scanned sequence of items plus metadata.

    Attributes:
        entries: List of SequenceEntry objects, one per item inside the
            active range (after subset clipping). The exact contents depend
            on policy:
                - SPLIT: contiguous range; no gaps inside this Sequence.
                - ERROR: only items that exist on disk.
                - NEAREST: dense; missing items carry the nearest existing
                  item's path.
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
        present_numbers: Numbers present on disk inside [first, last].
            Useful when the policy densified gaps — callers can still find
            out what was actually there.
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
    present_numbers: set[int] = Field(default_factory=set)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def missing_numbers(self) -> set[int]:
        """Numbers between `first` and `last` that aren't on disk.

        Computed from `present_numbers`. Always present regardless of policy
        (e.g. the SPLIT policy would have an empty set since each sub-sequence
        is contiguous; NEAREST shows the gaps that got filled).
        """
        return {n for n in range(self.first, self.last + 1) if n not in self.present_numbers}
