"""Tests for `griptape_nodes.common.sequences` via the public `ScanSequencesRequest`.

The public entry point is the bus request, not the (now module-private)
`_scan_sequences` function. Each test dispatches via `GriptapeNodes.ahandle_request(...)`
and asserts on the typed result payload.

Filesystem listings are stubbed by patching `GriptapeNodes.handle_request` so the
inner `ListDirectoryRequest` returns canned filenames; this leaves the real
`OSManager.on_scan_sequences_request` handler in place to exercise the full
async dispatch path.
"""

# ruff: noqa: PLR2004

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from griptape_nodes.common.sequences import MissingItemPolicy
from griptape_nodes.retained_mode.events.os_events import (
    FileIOFailureReason,
    FileSystemEntry,
    ListDirectoryRequest,
    ListDirectoryResultFailure,
    ListDirectoryResultSuccess,
    ScanSequencesRequest,
    ScanSequencesResultFailure,
    ScanSequencesResultSuccess,
    SequenceScanFailureReason,
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


async def _scan(
    directory: str,
    pattern: str,
    *,
    policy: MissingItemPolicy = MissingItemPolicy.SPLIT,
    start_number: int | None = None,
    end_number: int | None = None,
) -> ScanSequencesResultSuccess | ScanSequencesResultFailure:
    """Dispatch a ScanSequencesRequest and narrow the result type for assertions."""
    result = await GriptapeNodes.ahandle_request(
        ScanSequencesRequest(
            directory=directory,
            pattern=pattern,
            policy=policy,
            start_number=start_number,
            end_number=end_number,
        )
    )
    assert isinstance(result, (ScanSequencesResultSuccess, ScanSequencesResultFailure)), (
        f"unexpected result type: {type(result).__name__}"
    )
    return result


# --- Basic scanning -----------------------------------------------------


class TestBasicScanning:
    @pytest.mark.asyncio
    async def test_contiguous_sequence_split(self) -> None:
        """SPLIT on a contiguous sequence yields one sub-sequence."""
        directory = "/work/in"
        filenames = [f"render.{n:04d}.png" for n in [1, 2, 3, 4, 5]]
        with patch.object(GriptapeNodes, "handle_request", side_effect=_stub_listing(directory, filenames)):
            result = await _scan(directory, "render.####.png", policy=MissingItemPolicy.SPLIT)
        assert isinstance(result, ScanSequencesResultSuccess)
        assert result.has_entries is True
        seqs = result.sequences
        assert len(seqs) == 1
        assert seqs[0].first == 1
        assert seqs[0].last == 5
        assert [e.number for e in seqs[0].entries] == [1, 2, 3, 4, 5]
        assert [e.padded_number for e in seqs[0].entries] == ["0001", "0002", "0003", "0004", "0005"]

    @pytest.mark.asyncio
    async def test_no_files_returns_empty_success(self) -> None:
        """An empty directory yields a success with no sequences and `has_entries=False`."""
        with patch.object(GriptapeNodes, "handle_request", side_effect=_stub_listing("/work/in", [])):
            result = await _scan("/work/in", "render.####.png")
        assert isinstance(result, ScanSequencesResultSuccess)
        assert result.sequences == []
        assert result.has_entries is False

    @pytest.mark.asyncio
    async def test_directory_listing_failure_returns_empty_success(self) -> None:
        """A failed listing is currently swallowed by `_scan_sequences` and surfaces as an empty success.

        TODO: a future iteration may have the handler dispatch its own
        `ListDirectoryRequest` first and surface OS-layer failures via
        `FileIOFailureReason` instead of folding them into empty success.
        """
        # Stub always returns failure
        with patch.object(GriptapeNodes, "handle_request", side_effect=_stub_listing("/other", [])):
            result = await _scan("/work/in", "render.####.png")
        assert isinstance(result, ScanSequencesResultSuccess)
        assert result.sequences == []
        assert result.has_entries is False

    @pytest.mark.asyncio
    async def test_unrelated_files_filtered_out(self) -> None:
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
            result = await _scan(directory, "render.####.png", policy=MissingItemPolicy.SPLIT)
        assert isinstance(result, ScanSequencesResultSuccess)
        seqs = result.sequences
        assert len(seqs) == 1
        assert [e.number for e in seqs[0].entries] == [1, 2]


# --- Policy semantics ---------------------------------------------------


class TestSplitPolicy:
    @pytest.mark.asyncio
    async def test_three_runs(self) -> None:
        """Numbers 1-2, 4, 6-7 split into three sub-sequences."""
        directory = "/work/in"
        filenames = [f"render.{n:04d}.png" for n in [1, 2, 4, 6, 7]]
        with patch.object(GriptapeNodes, "handle_request", side_effect=_stub_listing(directory, filenames)):
            result = await _scan(directory, "render.####.png", policy=MissingItemPolicy.SPLIT)
        assert isinstance(result, ScanSequencesResultSuccess)
        seqs = result.sequences
        assert len(seqs) == 3
        assert (seqs[0].first, seqs[0].last) == (1, 2)
        assert (seqs[1].first, seqs[1].last) == (4, 4)
        assert (seqs[2].first, seqs[2].last) == (6, 7)

    @pytest.mark.asyncio
    async def test_split_records_discovered_range_on_each(self) -> None:
        """All sub-sequences carry the same discovered_first/discovered_last."""
        directory = "/work/in"
        filenames = [f"render.{n:04d}.png" for n in [1, 2, 4, 6, 7]]
        with patch.object(GriptapeNodes, "handle_request", side_effect=_stub_listing(directory, filenames)):
            result = await _scan(directory, "render.####.png", policy=MissingItemPolicy.SPLIT)
        assert isinstance(result, ScanSequencesResultSuccess)
        for s in result.sequences:
            assert s.discovered_first == 1
            assert s.discovered_last == 7


class TestSkipPolicy:
    @pytest.mark.asyncio
    async def test_skip_omits_gaps(self) -> None:
        """SKIP yields one sequence with only present numbers; gaps absent from entries."""
        directory = "/work/in"
        filenames = [f"render.{n:04d}.png" for n in [1, 2, 4, 6, 7]]
        with patch.object(GriptapeNodes, "handle_request", side_effect=_stub_listing(directory, filenames)):
            result = await _scan(directory, "render.####.png", policy=MissingItemPolicy.SKIP)
        assert isinstance(result, ScanSequencesResultSuccess)
        seqs = result.sequences
        assert len(seqs) == 1
        assert [e.number for e in seqs[0].entries] == [1, 2, 4, 6, 7]
        assert seqs[0].missing_numbers == {3, 5}


class TestFillNearestPolicy:
    @pytest.mark.asyncio
    async def test_fill_nearest_backward_first(self) -> None:
        """FILL_NEAREST fills gaps with the backward-first present number."""
        directory = "/work/in"
        filenames = [f"render.{n:04d}.png" for n in [1, 2, 4, 6, 7]]
        with patch.object(GriptapeNodes, "handle_request", side_effect=_stub_listing(directory, filenames)):
            result = await _scan(directory, "render.####.png", policy=MissingItemPolicy.FILL_NEAREST)
        assert isinstance(result, ScanSequencesResultSuccess)
        s = result.sequences[0]
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
    @pytest.mark.asyncio
    async def test_abort_surfaces_failure_at_first_gap(self) -> None:
        """ABORT surfaces a ScanSequencesResultFailure with the offending number."""
        directory = "/work/in"
        filenames = [f"render.{n:04d}.png" for n in [1, 2, 4, 5]]
        with patch.object(GriptapeNodes, "handle_request", side_effect=_stub_listing(directory, filenames)):
            result = await _scan(directory, "render.####.png", policy=MissingItemPolicy.ABORT)
        assert isinstance(result, ScanSequencesResultFailure)
        assert result.failure_reason is SequenceScanFailureReason.ABORTED_AT_GAP
        assert result.missing_item_number == 3

    @pytest.mark.asyncio
    async def test_abort_succeeds_when_dense(self) -> None:
        """ABORT returns one Sequence with all entries when there are no gaps."""
        directory = "/work/in"
        filenames = [f"render.{n:04d}.png" for n in [1, 2, 3]]
        with patch.object(GriptapeNodes, "handle_request", side_effect=_stub_listing(directory, filenames)):
            result = await _scan(directory, "render.####.png", policy=MissingItemPolicy.ABORT)
        assert isinstance(result, ScanSequencesResultSuccess)
        seqs = result.sequences
        assert len(seqs) == 1
        assert [e.number for e in seqs[0].entries] == [1, 2, 3]


# --- Negative numbers ---------------------------------------------------


class TestNegativeNumbers:
    @pytest.mark.asyncio
    async def test_negatives_with_different_padding_filter_out_silently(self) -> None:
        """Negative numbers at a different padding width are filtered by the padding match.

        When `-0005.png` has 5 total chars (sign + 4 digits), fileseq groups
        it as a width-5 sequence — separate from the positive width-4 numbers.
        Our zfill filter discards it before we ever see the negative.
        """
        directory = "/work/in"
        filenames = ["render.-0005.png", "render.0001.png", "render.0002.png"]
        with patch.object(GriptapeNodes, "handle_request", side_effect=_stub_listing(directory, filenames)):
            result = await _scan(directory, "render.####.png", policy=MissingItemPolicy.SPLIT)
        assert isinstance(result, ScanSequencesResultSuccess)
        seqs = result.sequences
        assert len(seqs) == 1
        assert [e.number for e in seqs[0].entries] == [1, 2]
        # Negatives never entered our loop; the counter sees zero.
        assert seqs[0].dropped_negative_number_count == 0

    @pytest.mark.asyncio
    async def test_negatives_with_matching_padding_dropped_with_counter(self) -> None:
        """When padding matches, negatives DO enter the loop and get filtered out."""
        directory = "/work/in"
        # Width-5 pattern: `-0005` and `00005` both have 5 digits in their slot.
        filenames = ["render.-0005.png", "render.00005.png", "render.00010.png"]
        with patch.object(GriptapeNodes, "handle_request", side_effect=_stub_listing(directory, filenames)):
            result = await _scan(directory, "render.#####.png", policy=MissingItemPolicy.SPLIT)
        assert isinstance(result, ScanSequencesResultSuccess)
        seqs = result.sequences
        # The negative is dropped; positives 5 and 10 are in the same sequence
        # under SPLIT but they aren't contiguous, so they split into two runs.
        assert len(seqs) == 2
        assert {e.number for s in seqs for e in s.entries} == {5, 10}
        # The counter should have noted the dropped negative on every produced sequence.
        assert all(s.dropped_negative_number_count == 1 for s in seqs)


# --- Subset clipping ----------------------------------------------------


class TestSubsetClipping:
    @pytest.mark.asyncio
    async def test_start_only(self) -> None:
        directory = "/work/in"
        filenames = [f"render.{n:04d}.png" for n in [1, 2, 3, 4, 5]]
        with patch.object(GriptapeNodes, "handle_request", side_effect=_stub_listing(directory, filenames)):
            result = await _scan(directory, "render.####.png", policy=MissingItemPolicy.SPLIT, start_number=3)
        assert isinstance(result, ScanSequencesResultSuccess)
        seqs = result.sequences
        assert len(seqs) == 1
        assert [e.number for e in seqs[0].entries] == [3, 4, 5]
        assert seqs[0].discovered_first == 1
        assert seqs[0].first == 3

    @pytest.mark.asyncio
    async def test_end_only(self) -> None:
        directory = "/work/in"
        filenames = [f"render.{n:04d}.png" for n in [1, 2, 3, 4, 5]]
        with patch.object(GriptapeNodes, "handle_request", side_effect=_stub_listing(directory, filenames)):
            result = await _scan(directory, "render.####.png", policy=MissingItemPolicy.SPLIT, end_number=3)
        assert isinstance(result, ScanSequencesResultSuccess)
        seqs = result.sequences
        assert len(seqs) == 1
        assert [e.number for e in seqs[0].entries] == [1, 2, 3]
        assert seqs[0].discovered_last == 5
        assert seqs[0].last == 3

    @pytest.mark.asyncio
    async def test_start_and_end(self) -> None:
        directory = "/work/in"
        filenames = [f"render.{n:04d}.png" for n in [1, 2, 3, 4, 5]]
        with patch.object(GriptapeNodes, "handle_request", side_effect=_stub_listing(directory, filenames)):
            result = await _scan(
                directory, "render.####.png", policy=MissingItemPolicy.SPLIT, start_number=2, end_number=4
            )
        assert isinstance(result, ScanSequencesResultSuccess)
        seqs = result.sequences
        assert len(seqs) == 1
        assert [e.number for e in seqs[0].entries] == [2, 3, 4]

    @pytest.mark.asyncio
    async def test_subset_outside_discovered_range_yields_empty_success(self) -> None:
        directory = "/work/in"
        filenames = [f"render.{n:04d}.png" for n in [1, 2, 3]]
        with patch.object(GriptapeNodes, "handle_request", side_effect=_stub_listing(directory, filenames)):
            result = await _scan(
                directory, "render.####.png", policy=MissingItemPolicy.SPLIT, start_number=10, end_number=20
            )
        assert isinstance(result, ScanSequencesResultSuccess)
        assert result.sequences == []
        assert result.has_entries is False

    @pytest.mark.asyncio
    async def test_negative_start_rejected(self) -> None:
        result = await _scan("/work/in", "render.####.png", start_number=-1)
        assert isinstance(result, ScanSequencesResultFailure)
        assert result.failure_reason is SequenceScanFailureReason.INVALID_BOUNDS

    @pytest.mark.asyncio
    async def test_inverted_bounds_rejected(self) -> None:
        result = await _scan("/work/in", "render.####.png", start_number=10, end_number=5)
        assert isinstance(result, ScanSequencesResultFailure)
        assert result.failure_reason is SequenceScanFailureReason.INVALID_BOUNDS


# --- Pattern variants ---------------------------------------------------


class TestPatternVariants:
    @pytest.mark.asyncio
    async def test_printf_pattern(self) -> None:
        """%04d works the same as ####."""
        directory = "/work/in"
        filenames = [f"render.{n:04d}.png" for n in [1, 2, 3]]
        with patch.object(GriptapeNodes, "handle_request", side_effect=_stub_listing(directory, filenames)):
            result = await _scan(directory, "render.%04d.png", policy=MissingItemPolicy.SPLIT)
        assert isinstance(result, ScanSequencesResultSuccess)
        seqs = result.sequences
        assert len(seqs) == 1
        assert [e.number for e in seqs[0].entries] == [1, 2, 3]

    @pytest.mark.asyncio
    async def test_mismatched_padding_returns_empty_success(self) -> None:
        """Disk has 3-digit numbers; user declared #### (4 digits). No match — empty success."""
        directory = "/work/in"
        filenames = [f"render.{n:03d}.png" for n in [1, 2, 3]]
        with patch.object(GriptapeNodes, "handle_request", side_effect=_stub_listing(directory, filenames)):
            result = await _scan(directory, "render.####.png", policy=MissingItemPolicy.SPLIT)
        assert isinstance(result, ScanSequencesResultSuccess)
        assert result.sequences == []
        assert result.has_entries is False

    @pytest.mark.asyncio
    async def test_unpadded_printf_round_trip(self) -> None:
        """`%d` matches an unpadded directory and yields bare integer padded_numbers.

        fileseq treats `%d` as zfill=1 (same as a single `#`). The Sequence's
        canonical `pattern` preserves the user's input form (`%d`, not `#`).
        """
        directory = "/work/in"
        filenames = ["render.5.png", "render.42.png", "render.123.png"]
        with patch.object(GriptapeNodes, "handle_request", side_effect=_stub_listing(directory, filenames)):
            result = await _scan(directory, "render.%d.png", policy=MissingItemPolicy.SPLIT)
        assert isinstance(result, ScanSequencesResultSuccess)
        seqs = result.sequences
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
    """Multi-token templates surface as INVALID_TEMPLATE failures."""

    @pytest.mark.asyncio
    async def test_multi_token_dot_separator(self) -> None:
        """`render.##.##.exr` — fileseq accepts this and silently misparses."""
        result = await _scan("/work/in", "render.##.##.exr")
        assert isinstance(result, ScanSequencesResultFailure)
        assert result.failure_reason is SequenceScanFailureReason.INVALID_TEMPLATE
        assert "2 sequence tokens" in str(result.result_details or "")

    @pytest.mark.asyncio
    async def test_multi_token_underscore_separator(self) -> None:
        """`render.####_v####.exr` — two distinct hash tokens."""
        result = await _scan("/work/in", "render.####_v####.exr")
        assert isinstance(result, ScanSequencesResultFailure)
        assert result.failure_reason is SequenceScanFailureReason.INVALID_TEMPLATE
        assert "2 sequence tokens" in str(result.result_details or "")

    @pytest.mark.asyncio
    async def test_multi_token_mixed_syntax(self) -> None:
        """A printf token AND a hash token in the same template."""
        result = await _scan("/work/in", "foo_%04d_bar_####.exr")
        assert isinstance(result, ScanSequencesResultFailure)
        assert result.failure_reason is SequenceScanFailureReason.INVALID_TEMPLATE
        assert "2 sequence tokens" in str(result.result_details or "")

    @pytest.mark.asyncio
    async def test_zero_token_pattern_left_to_fileseq(self) -> None:
        """A pattern with no token returns empty success.

        fileseq itself accepts non-sequence patterns silently; either way, no
        result-set means a successful scan with `has_entries=False`.
        """
        directory = "/work/in"
        with patch.object(GriptapeNodes, "handle_request", side_effect=_stub_listing(directory, [])):
            result = await _scan(directory, "photo.png")
        assert isinstance(result, ScanSequencesResultSuccess)
        assert result.sequences == []
        assert result.has_entries is False

    @pytest.mark.asyncio
    async def test_single_token_passes(self) -> None:
        """Sanity: a normal single-token pattern survives the validator."""
        directory = "/work/in"
        filenames = [f"render.{n:04d}.png" for n in [1, 2, 3]]
        with patch.object(GriptapeNodes, "handle_request", side_effect=_stub_listing(directory, filenames)):
            result = await _scan(directory, "render.####.png")
        assert isinstance(result, ScanSequencesResultSuccess)
        assert len(result.sequences) == 1
