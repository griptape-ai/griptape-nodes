"""Tests for `griptape_nodes.common.sequences`.

Filesystem listings are stubbed via `GriptapeNodes.handle_request` so the
tests don't depend on real on-disk state. fileseq's parsing/math is exercised
indirectly through `scan_sequences`.
"""

# ruff: noqa: PLR2004

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from griptape_nodes.common.sequences import (
    MissingItemError,
    MissingItemPolicy,
    scan_sequences,
)
from griptape_nodes.retained_mode.events.os_events import (
    FileIOFailureReason,
    FileSystemEntry,
    ListDirectoryRequest,
    ListDirectoryResultFailure,
    ListDirectoryResultSuccess,
)
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes


def _stub_listing(directory: str, filenames: list[str]) -> Any:
    """Return a `handle_request` side_effect that lists `directory` with `filenames`.

    Any directory other than `directory` returns a listing failure. Any
    request type other than ListDirectoryRequest raises (no other request
    types should be hit by this code path).
    """

    def handle_request(request: object) -> object:
        if isinstance(request, ListDirectoryRequest):
            if request.directory_path == directory:
                entries = [
                    FileSystemEntry(name=name, path=str(Path(directory) / name), is_dir=False) for name in filenames
                ]
                return ListDirectoryResultSuccess(
                    entries=entries,
                    current_path=directory,
                    is_workspace_path=False,
                    result_details="ok",
                )
            return ListDirectoryResultFailure(
                failure_reason=FileIOFailureReason.FILE_NOT_FOUND,
                result_details=f"{request.directory_path} not stubbed",
            )
        msg = f"Unexpected request: {type(request).__name__}"
        raise AssertionError(msg)

    return handle_request


# --- Basic scanning -----------------------------------------------------


class TestBasicScanning:
    def test_contiguous_sequence_split(self) -> None:
        """SPLIT on a contiguous sequence yields one sub-sequence."""
        directory = "/work/in"
        filenames = [f"render.{n:04d}.png" for n in [1, 2, 3, 4, 5]]
        with patch.object(GriptapeNodes, "handle_request", side_effect=_stub_listing(directory, filenames)):
            seqs = scan_sequences(directory, "render.####.png", policy=MissingItemPolicy.SPLIT)
        assert len(seqs) == 1
        assert seqs[0].first == 1
        assert seqs[0].last == 5
        assert [e.number for e in seqs[0].entries] == [1, 2, 3, 4, 5]
        assert [e.padded_number for e in seqs[0].entries] == ["0001", "0002", "0003", "0004", "0005"]

    def test_no_files_returns_empty(self) -> None:
        """An empty directory yields an empty list."""
        with patch.object(GriptapeNodes, "handle_request", side_effect=_stub_listing("/work/in", [])):
            seqs = scan_sequences("/work/in", "render.####.png")
        assert seqs == []

    def test_directory_listing_failure_returns_empty(self) -> None:
        """A failed listing yields an empty list (no exception)."""
        # Stub always returns failure
        with patch.object(GriptapeNodes, "handle_request", side_effect=_stub_listing("/other", [])):
            seqs = scan_sequences("/work/in", "render.####.png")
        assert seqs == []

    def test_unrelated_files_filtered_out(self) -> None:
        """Files not matching basename/extension are ignored."""
        directory = "/work/in"
        filenames = [
            "render.0001.png",
            "render.0002.png",
            "comp.0001.png",  # different basename
            "render.0001.exr",  # different extension
            "notes.txt",  # totally unrelated
        ]
        with patch.object(GriptapeNodes, "handle_request", side_effect=_stub_listing(directory, filenames)):
            seqs = scan_sequences(directory, "render.####.png", policy=MissingItemPolicy.SPLIT)
        assert len(seqs) == 1
        assert [e.number for e in seqs[0].entries] == [1, 2]


# --- Policy semantics ---------------------------------------------------


class TestSplitPolicy:
    def test_three_runs(self) -> None:
        """Numbers 1-2, 4, 6-7 split into three sub-sequences."""
        directory = "/work/in"
        filenames = [f"render.{n:04d}.png" for n in [1, 2, 4, 6, 7]]
        with patch.object(GriptapeNodes, "handle_request", side_effect=_stub_listing(directory, filenames)):
            seqs = scan_sequences(directory, "render.####.png", policy=MissingItemPolicy.SPLIT)
        assert len(seqs) == 3
        assert (seqs[0].first, seqs[0].last) == (1, 2)
        assert (seqs[1].first, seqs[1].last) == (4, 4)
        assert (seqs[2].first, seqs[2].last) == (6, 7)

    def test_split_records_discovered_range_on_each(self) -> None:
        """All sub-sequences carry the same discovered_first/discovered_last."""
        directory = "/work/in"
        filenames = [f"render.{n:04d}.png" for n in [1, 2, 4, 6, 7]]
        with patch.object(GriptapeNodes, "handle_request", side_effect=_stub_listing(directory, filenames)):
            seqs = scan_sequences(directory, "render.####.png", policy=MissingItemPolicy.SPLIT)
        for s in seqs:
            assert s.discovered_first == 1
            assert s.discovered_last == 7


class TestSkipPolicy:
    def test_skip_omits_gaps(self) -> None:
        """SKIP yields one sequence with only present numbers; gaps absent from entries."""
        directory = "/work/in"
        filenames = [f"render.{n:04d}.png" for n in [1, 2, 4, 6, 7]]
        with patch.object(GriptapeNodes, "handle_request", side_effect=_stub_listing(directory, filenames)):
            seqs = scan_sequences(directory, "render.####.png", policy=MissingItemPolicy.SKIP)
        assert len(seqs) == 1
        assert [e.number for e in seqs[0].entries] == [1, 2, 4, 6, 7]
        assert seqs[0].missing_numbers == {3, 5}


class TestFillNearestPolicy:
    def test_fill_nearest_backward_first(self) -> None:
        """FILL_NEAREST fills gaps with the backward-first present number."""
        directory = "/work/in"
        filenames = [f"render.{n:04d}.png" for n in [1, 2, 4, 6, 7]]
        with patch.object(GriptapeNodes, "handle_request", side_effect=_stub_listing(directory, filenames)):
            seqs = scan_sequences(directory, "render.####.png", policy=MissingItemPolicy.FILL_NEAREST)
        s = seqs[0]
        # Gap at 3 -> backward to 2
        entry_3 = next(e for e in s.entries if e.number == 3)
        assert Path(entry_3.path).name == "render.0002.png"
        # Gap at 5 -> backward to 4
        entry_5 = next(e for e in s.entries if e.number == 5)
        assert Path(entry_5.path).name == "render.0004.png"

    # Note: forward-fall is unreachable through scan_sequences with a single
    # subset clip — `active_first` is always clamped up to `discovered_first`,
    # so there's always at least one earlier present number for any in-range
    # gap. Forward-fall remains in the policy code as a defensive fallback
    # for direct callers of `apply_policy`, but isn't exercised here.


class TestAbortPolicy:
    def test_abort_raises_at_first_gap(self) -> None:
        """ABORT raises MissingItemError on the first missing slot."""
        directory = "/work/in"
        filenames = [f"render.{n:04d}.png" for n in [1, 2, 4, 5]]
        with (
            patch.object(GriptapeNodes, "handle_request", side_effect=_stub_listing(directory, filenames)),
            pytest.raises(MissingItemError) as exc_info,
        ):
            scan_sequences(directory, "render.####.png", policy=MissingItemPolicy.ABORT)
        assert exc_info.value.number == 3

    def test_abort_succeeds_when_dense(self) -> None:
        """ABORT returns one Sequence with all entries when there are no gaps."""
        directory = "/work/in"
        filenames = [f"render.{n:04d}.png" for n in [1, 2, 3]]
        with patch.object(GriptapeNodes, "handle_request", side_effect=_stub_listing(directory, filenames)):
            seqs = scan_sequences(directory, "render.####.png", policy=MissingItemPolicy.ABORT)
        assert len(seqs) == 1
        assert [e.number for e in seqs[0].entries] == [1, 2, 3]


# --- Negative numbers ---------------------------------------------------


class TestNegativeNumbers:
    def test_negatives_with_different_padding_filter_out_silently(self) -> None:
        """Negative numbers at a different padding width are filtered by the padding match.

        When `-0005.png` has 5 total chars (sign + 4 digits), fileseq groups
        it as a width-5 sequence — separate from the positive width-4 numbers.
        Our zfill filter discards it before we ever see the negative.
        """
        directory = "/work/in"
        filenames = ["render.-0005.png", "render.0001.png", "render.0002.png"]
        with patch.object(GriptapeNodes, "handle_request", side_effect=_stub_listing(directory, filenames)):
            seqs = scan_sequences(directory, "render.####.png", policy=MissingItemPolicy.SPLIT)
        assert len(seqs) == 1
        assert [e.number for e in seqs[0].entries] == [1, 2]
        # Negatives never entered our loop; the counter sees zero.
        assert seqs[0].dropped_negative_number_count == 0

    def test_negatives_with_matching_padding_dropped_with_counter(self) -> None:
        """When padding matches, negatives DO enter the loop and get filtered out."""
        directory = "/work/in"
        # Width-5 pattern: `-0005` and `00005` both have 5 digits in their slot.
        filenames = ["render.-0005.png", "render.00005.png", "render.00010.png"]
        with patch.object(GriptapeNodes, "handle_request", side_effect=_stub_listing(directory, filenames)):
            seqs = scan_sequences(directory, "render.#####.png", policy=MissingItemPolicy.SPLIT)
        # The negative is dropped; positives 5 and 10 are in the same sequence
        # under SPLIT but they aren't contiguous, so they split into two runs.
        assert len(seqs) == 2
        assert {e.number for s in seqs for e in s.entries} == {5, 10}
        # The counter should have noted the dropped negative on every produced sequence.
        assert all(s.dropped_negative_number_count == 1 for s in seqs)


# --- Subset clipping ----------------------------------------------------


class TestSubsetClipping:
    def test_start_only(self) -> None:
        directory = "/work/in"
        filenames = [f"render.{n:04d}.png" for n in [1, 2, 3, 4, 5]]
        with patch.object(GriptapeNodes, "handle_request", side_effect=_stub_listing(directory, filenames)):
            seqs = scan_sequences(directory, "render.####.png", policy=MissingItemPolicy.SPLIT, start=3)
        assert len(seqs) == 1
        assert [e.number for e in seqs[0].entries] == [3, 4, 5]
        assert seqs[0].discovered_first == 1
        assert seqs[0].first == 3

    def test_end_only(self) -> None:
        directory = "/work/in"
        filenames = [f"render.{n:04d}.png" for n in [1, 2, 3, 4, 5]]
        with patch.object(GriptapeNodes, "handle_request", side_effect=_stub_listing(directory, filenames)):
            seqs = scan_sequences(directory, "render.####.png", policy=MissingItemPolicy.SPLIT, end=3)
        assert len(seqs) == 1
        assert [e.number for e in seqs[0].entries] == [1, 2, 3]
        assert seqs[0].discovered_last == 5
        assert seqs[0].last == 3

    def test_start_and_end(self) -> None:
        directory = "/work/in"
        filenames = [f"render.{n:04d}.png" for n in [1, 2, 3, 4, 5]]
        with patch.object(GriptapeNodes, "handle_request", side_effect=_stub_listing(directory, filenames)):
            seqs = scan_sequences(directory, "render.####.png", policy=MissingItemPolicy.SPLIT, start=2, end=4)
        assert len(seqs) == 1
        assert [e.number for e in seqs[0].entries] == [2, 3, 4]

    def test_subset_outside_discovered_range_yields_empty(self) -> None:
        directory = "/work/in"
        filenames = [f"render.{n:04d}.png" for n in [1, 2, 3]]
        with patch.object(GriptapeNodes, "handle_request", side_effect=_stub_listing(directory, filenames)):
            seqs = scan_sequences(directory, "render.####.png", policy=MissingItemPolicy.SPLIT, start=10, end=20)
        assert seqs == []

    def test_negative_start_rejected(self) -> None:
        with pytest.raises(ValueError, match=">= 0"):
            scan_sequences("/work/in", "render.####.png", start=-1)

    def test_inverted_bounds_rejected(self) -> None:
        with pytest.raises(ValueError, match=">= `start`"):
            scan_sequences("/work/in", "render.####.png", start=10, end=5)


# --- Pattern variants ---------------------------------------------------


class TestPatternVariants:
    def test_printf_pattern(self) -> None:
        """%04d works the same as ####."""
        directory = "/work/in"
        filenames = [f"render.{n:04d}.png" for n in [1, 2, 3]]
        with patch.object(GriptapeNodes, "handle_request", side_effect=_stub_listing(directory, filenames)):
            seqs = scan_sequences(directory, "render.%04d.png", policy=MissingItemPolicy.SPLIT)
        assert len(seqs) == 1
        assert [e.number for e in seqs[0].entries] == [1, 2, 3]

    def test_mismatched_padding_returns_empty(self) -> None:
        """Disk has 3-digit numbers; user declared #### (4 digits). No match."""
        directory = "/work/in"
        filenames = [f"render.{n:03d}.png" for n in [1, 2, 3]]
        with patch.object(GriptapeNodes, "handle_request", side_effect=_stub_listing(directory, filenames)):
            seqs = scan_sequences(directory, "render.####.png", policy=MissingItemPolicy.SPLIT)
        assert seqs == []

    def test_unpadded_printf_round_trip(self) -> None:
        """`%d` matches an unpadded directory and yields bare integer padded_numbers.

        fileseq treats `%d` as zfill=1 (same as a single `#`). The Sequence's
        canonical `pattern` preserves the user's input form (`%d`, not `#`).
        """
        directory = "/work/in"
        filenames = ["render.5.png", "render.42.png", "render.123.png"]
        with patch.object(GriptapeNodes, "handle_request", side_effect=_stub_listing(directory, filenames)):
            seqs = scan_sequences(directory, "render.%d.png", policy=MissingItemPolicy.SPLIT)
        # 5, 42, 123 aren't contiguous, so SPLIT yields three sequences.
        assert len(seqs) == 3
        all_entries = [e for s in seqs for e in s.entries]
        assert [e.number for e in all_entries] == [5, 42, 123]
        assert [e.padded_number for e in all_entries] == ["5", "42", "123"]
        for s in seqs:
            assert s.padding == 1
            assert s.pattern == "render.%d.png"


# --- Pattern validation -------------------------------------------------


class TestPatternValidation:
    """Multi-token templates raise before any work happens."""

    def test_multi_token_dot_separator(self) -> None:
        """`render.##.##.exr` — fileseq accepts this and silently misparses."""
        with pytest.raises(ValueError, match="2 sequence tokens"):
            scan_sequences("/work/in", "render.##.##.exr")

    def test_multi_token_underscore_separator(self) -> None:
        """`render.####_v####.exr` — two distinct hash tokens."""
        with pytest.raises(ValueError, match="2 sequence tokens"):
            scan_sequences("/work/in", "render.####_v####.exr")

    def test_multi_token_mixed_syntax(self) -> None:
        """A printf token AND a hash token in the same template."""
        with pytest.raises(ValueError, match="2 sequence tokens"):
            scan_sequences("/work/in", "foo_%04d_bar_####.exr")

    def test_zero_token_pattern_left_to_fileseq(self) -> None:
        """A pattern with no token doesn't raise our error.

        fileseq itself will report an empty result (or its own error) for a
        non-sequence pattern; we don't second-guess that here.
        """
        directory = "/work/in"
        with patch.object(GriptapeNodes, "handle_request", side_effect=_stub_listing(directory, [])):
            # Should NOT raise from our validator. fileseq's FileSequence may
            # accept it silently; either way, no result-set means empty.
            seqs = scan_sequences(directory, "photo.png")
        assert seqs == []

    def test_single_token_passes(self) -> None:
        """Sanity: a normal single-token pattern survives the validator."""
        directory = "/work/in"
        filenames = [f"render.{n:04d}.png" for n in [1, 2, 3]]
        with patch.object(GriptapeNodes, "handle_request", side_effect=_stub_listing(directory, filenames)):
            seqs = scan_sequences(directory, "render.####.png")
        assert len(seqs) == 1
