"""Data shapes for the sequences module.

Three concepts:
    - `MissingFramePolicy`: how to fill gaps inside a sequence's range.
    - `Sequence`: one contiguous-or-gap-aware sequence with metadata.
    - `SequenceEntry`: one frame inside a Sequence (frame number + path or marker).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING, NamedTuple

if TYPE_CHECKING:
    from pathlib import Path


class MissingFramePolicy(StrEnum):
    """How to handle gaps inside a sequence's frame range.

    The choice changes the *shape* of `scan_sequences` output:

    - `SPLIT`: returns multiple Sequences, each contiguous (no gaps inside any).
    - All others: returns exactly one Sequence whose entries span the full
      [first, last] range, with policy applied to fill missing frames.
    """

    SPLIT = "split"  # Sparse sequence becomes N contiguous sub-sequences.
    ERROR = "error"  # Single sequence with only the present frames; gaps absent.
    NEAREST = "nearest"  # Dense sequence; gaps point at the backward-first neighbor.
    BLACK = "black"  # Dense sequence; gaps hold a BLACK MissingFrameMarker.
    CHECKERBOARD = "checkerboard"  # Dense sequence; gaps hold a CHECKERBOARD marker.


@dataclass(frozen=True)
class MissingFrameMarker:
    """Sentinel returned for a missing frame under BLACK/CHECKERBOARD.

    Image-generating callers (e.g. node-level renderers) interpret the marker
    and synthesize the appropriate frame. This module does not produce images.
    """

    policy: MissingFramePolicy
    frame: int
    frame_string: str


class MissingFrameError(Exception):
    """Raised when a sequence is queried for an unrepresented frame.

    Currently unused at scan time (ERROR policy just produces a sparse Sequence
    rather than raising). Reserved for future query APIs on Sequence.
    """

    def __init__(self, frame: int) -> None:
        super().__init__(f"Frame {frame} is missing from the sequence")
        self.frame = frame


class SequenceEntry(NamedTuple):
    """One frame entry in a Sequence.

    Attributes:
        frame: The integer frame index (e.g. 5).
        frame_string: The zero-padded form matching the sequence's declared
            width (e.g. "0005" for frame 5 in a `####` sequence). For
            unpadded `%d` patterns this is just the bare integer as a string.
        path: The on-disk file path, OR a MissingFrameMarker for synthesized
            slots under BLACK/CHECKERBOARD policy.
    """

    frame: int
    frame_string: str
    path: Path | MissingFrameMarker


@dataclass
class Sequence:
    """A scanned sequence of frames plus metadata.

    Attributes:
        entries: List of SequenceEntry objects, one per frame inside the
            active range (after subset clipping). The exact contents depend
            on policy:
                - SPLIT: contiguous range; no markers.
                - ERROR: only frames that exist on disk; markers never appear.
                - NEAREST: dense; missing frames carry the nearest existing
                  frame's path.
                - BLACK / CHECKERBOARD: dense; missing frames carry markers.
        first: Lowest frame number in the active range (post-subset).
        last: Highest frame number in the active range (post-subset).
        discovered_first: Lowest frame number actually found on disk before
            subset clipping.
        discovered_last: Highest frame number actually found on disk before
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
    policy: MissingFramePolicy
    dropped_negative_frame_count: int = 0
    # Frames present on disk inside [first, last]. Useful when the policy
    # densified gaps — callers can still find out what was actually there.
    present_frames: set[int] = field(default_factory=set)

    @property
    def missing_frames(self) -> set[int]:
        """Frame numbers between `first` and `last` that aren't on disk.

        Computed from `present_frames`. Always present regardless of policy
        (e.g. the SPLIT policy would have an empty set since each sub-sequence
        is contiguous; NEAREST/BLACK/CHECKERBOARD show the gaps that got
        filled).
        """
        return {f for f in range(self.first, self.last + 1) if f not in self.present_frames}
