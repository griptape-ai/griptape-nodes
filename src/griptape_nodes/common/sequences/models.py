"""Data shapes for the sequences module.

Four concepts:
    - `MissingItemPolicy`: how to fill gaps inside a sequence's range.
    - `NoTokenBehavior`: what to do when the input has no sequence token at all.
    - `Sequence`: one contiguous-or-gap-aware sequence with metadata.
    - `SequenceEntry`: one item inside a Sequence (number + path).
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field, computed_field


class MissingItemPolicy(StrEnum):
    """How to handle gaps inside a sequence's number range.

    The choice changes the *shape* (or even the success) of `scan_sequences` output:

    - `ABORT`: raise `MissingItemError` on the first missing slot in `[first..last]`.
    - `SPLIT`: returns multiple Sequences, each contiguous (no gaps inside any).
    - `SKIP`: one Sequence with only the present items; gaps absent from `entries`.
    - `FILL_NEAREST`: one Sequence whose entries span the full [first, last] range,
      with each missing slot's path pointing at the nearest present neighbor.
    """

    ABORT = "abort"  # Raise MissingItemError on the first gap.
    SPLIT = "split"  # Sparse sequence becomes N contiguous sub-sequences.
    SKIP = "skip"  # Single sequence with only the present items; gaps absent.
    FILL_NEAREST = "fill_nearest"  # Dense sequence; gaps point at the backward-first neighbor.


class NoTokenBehavior(StrEnum):
    """What to do when the caller's path has no sequence token (`####`, `%04d`, etc.).

    A path with zero tokens is ambiguous: the artist may have typed the
    literal name of one specific file (`render.0002.png`), or they may have
    meant to scan the surrounding sequence and forgotten the token, or they
    may have a workflow that should fail loud if the token is missing. This
    enum picks which interpretation the scanner uses.

    - `SINGLE_FILE` *(default)*: Treat the whole filename as a literal. The
      result is a 1-item Sequence (`first=last=1, padding=0`) when the file
      exists, an empty result when it doesn't. Sibling files in the same
      directory are ignored.
    - `EXPLORE_SEQUENCE`: Let fileseq parse digits in the filename as an
      implicit sequence token. `render.0002.png` is treated as one frame of
      a `render.####.png` sequence; the scan walks every matching sibling
      and the result reflects the entire on-disk run. Useful when a
      downstream tool gave you one filename but you want the whole take.
    - `REJECT`: Fail with `INVALID_TEMPLATE` and tell the artist the path
      needs an explicit token. Strict mode for workflows that must not
      silently widen the artist's intent.
    """

    SINGLE_FILE = "single_file"
    EXPLORE_SEQUENCE = "explore_sequence"
    REJECT = "reject"


class MissingItemError(Exception):
    """Raised by `MissingItemPolicy.ABORT` on the first missing slot inside the active range.

    Attributes:
        number: The slot number that triggered the abort.
    """

    def __init__(self, number: int) -> None:
        super().__init__(f"Sequence has a gap at item {number}.")
        self.number = number


class InvalidSubsetBoundsError(ValueError):
    """Raised when `scan_sequences`'s `start` / `end` bounds are unusable.

    Subclasses `ValueError` so existing `except ValueError` clauses keep working,
    but lets request handlers and other callers discriminate this failure mode
    from invalid-template errors via `except InvalidSubsetBoundsError`.
    """


class InvalidTemplateError(ValueError):
    """Raised when a template string can't be parsed as a single-token fileseq pattern.

    Subclasses `ValueError` so existing `except ValueError` clauses keep working,
    but lets request handlers and other callers discriminate this failure mode
    from invalid-bounds errors via `except InvalidTemplateError`.
    """


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
                - SKIP: only items that exist on disk.
                - FILL_NEAREST: dense; missing items carry the nearest existing
                  item's path.
            (ABORT never returns a Sequence — it raises on the first gap.)
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
