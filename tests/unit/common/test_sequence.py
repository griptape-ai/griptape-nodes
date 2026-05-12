"""Tests for SequenceTemplate / Sequence / missing-frame handling.

Scan tests stub GriptapeNodes.handle_request to return synthetic directory
listings. The boundary is intentional — filesystem-level behavior lives in
OSManager's own tests; here we verify the sequence layer's segment-split,
regex-match, and collection logic.
"""

# ruff: noqa: PLR2004

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from griptape_nodes.common.macro_parser import ParsedMacro
from griptape_nodes.common.macro_parser.sequence import (
    MissingFrameError,
    MissingFrameMarker,
    MissingFramePolicy,
    Sequence,
    SequenceFrame,
    SequenceTemplate,
    SequenceTemplateError,
)
from griptape_nodes.retained_mode.events.os_events import (
    FileSystemEntry,
    ListDirectoryRequest,
    ListDirectoryResultFailure,
    ListDirectoryResultSuccess,
)
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes


@pytest.fixture
def mock_secrets() -> Any:
    """SecretsManager double that reports no env vars present."""
    mock = MagicMock()
    mock.get_secret.return_value = None
    return mock


def _make_entry(name: str, parent: str, *, is_dir: bool) -> FileSystemEntry:
    """Build a FileSystemEntry the handler would produce for a real listing."""
    absolute = str(Path(parent) / name)
    return FileSystemEntry(
        name=name,
        path=absolute,
        is_dir=is_dir,
        absolute_path=absolute,
    )


def _stub_listings(listings: dict[str, list[FileSystemEntry]]) -> Any:
    """Build a handle_request side_effect that returns canned directory contents.

    `listings` maps normalized directory paths to the entries that would be
    returned when that directory is listed. Missing directories return a
    listing-failure (matching OSManager's behavior on nonexistent dirs).

    Mirrors the real handler's behavior of filtering by `request.pattern`
    using `Path.match` — without that filter, scan tests can't distinguish
    which directory was queried from which filename within it.
    """

    def handle_request(request: object) -> object:
        if isinstance(request, ListDirectoryRequest):
            directory = request.directory_path or ""
            if directory not in listings:
                from griptape_nodes.retained_mode.events.os_events import FileIOFailureReason

                return ListDirectoryResultFailure(
                    failure_reason=FileIOFailureReason.FILE_NOT_FOUND,
                    result_details=f"{directory} not present in stub",
                )
            entries = list(listings[directory])
            if request.pattern is not None:
                entries = [e for e in entries if Path(e.path).match(request.pattern)]
            return ListDirectoryResultSuccess(
                entries=entries,
                current_path=directory,
                is_workspace_path=False,
                result_details="stub",
            )
        msg = f"Unexpected request type in stub: {type(request).__name__}"
        raise AssertionError(msg)

    return handle_request


class TestSequenceTemplateConstruction:
    def test_requires_sequence_token(self) -> None:
        """SequenceTemplate rejects macros without a sequence token."""
        with pytest.raises(SequenceTemplateError, match="no sequence token"):
            SequenceTemplate(ParsedMacro("{outputs}/photo.jpg"))

    def test_accepts_hash_template(self) -> None:
        """Templates with `####` construct successfully."""
        st = SequenceTemplate(ParsedMacro("render.####.exr"))
        assert st.macro.is_sequence is True

    def test_accepts_printf_template(self) -> None:
        """Templates with `%04d` construct successfully."""
        st = SequenceTemplate(ParsedMacro("render.%04d.exr"))
        assert st.macro.is_sequence is True


class TestExtractFrameFromEntry:
    """The string-op matcher that replaces the regex: extract frame from an entry name."""

    def _token(self, width: int) -> Any:
        from griptape_nodes.common.macro_parser.segments import ParsedSequenceToken, SequenceTokenSyntax

        return ParsedSequenceToken(width=width, original_syntax=SequenceTokenSyntax.HASH)

    def test_basic_match(self) -> None:
        """Prefix + padded digits + suffix extracts the frame int."""
        from griptape_nodes.common.macro_parser.sequence import _extract_frame_from_entry

        assert _extract_frame_from_entry("render.0042.exr", "render.", self._token(4), ".exr") == 42

    def test_width_minimum_rejects_underwidth(self) -> None:
        """Declared width 4 rejects 3-digit middles."""
        from griptape_nodes.common.macro_parser.sequence import _extract_frame_from_entry

        assert _extract_frame_from_entry("render.123.exr", "render.", self._token(4), ".exr") is None

    def test_width_minimum_accepts_overflow(self) -> None:
        """Declared width 4 accepts 5-digit middles (overflow allowed)."""
        from griptape_nodes.common.macro_parser.sequence import _extract_frame_from_entry

        assert _extract_frame_from_entry("render.12345.exr", "render.", self._token(4), ".exr") == 12345

    def test_negative_frame(self) -> None:
        """Leading `-` is treated as sign, extra to padding width."""
        from griptape_nodes.common.macro_parser.sequence import _extract_frame_from_entry

        assert _extract_frame_from_entry("render.-0005.exr", "render.", self._token(4), ".exr") == -5

    def test_prefix_mismatch_returns_none(self) -> None:
        from griptape_nodes.common.macro_parser.sequence import _extract_frame_from_entry

        assert _extract_frame_from_entry("other.0005.exr", "render.", self._token(4), ".exr") is None

    def test_suffix_mismatch_returns_none(self) -> None:
        from griptape_nodes.common.macro_parser.sequence import _extract_frame_from_entry

        assert _extract_frame_from_entry("render.0005.png", "render.", self._token(4), ".exr") is None

    def test_non_digit_middle_returns_none(self) -> None:
        """Prefix/suffix match but middle has non-digit characters."""
        from griptape_nodes.common.macro_parser.sequence import _extract_frame_from_entry

        assert _extract_frame_from_entry("render.abcd.exr", "render.", self._token(4), ".exr") is None

    def test_empty_prefix_and_suffix(self) -> None:
        """Token-only component (e.g. directory name `####`) matches bare digits."""
        from griptape_nodes.common.macro_parser.sequence import _extract_frame_from_entry

        assert _extract_frame_from_entry("0042", "", self._token(4), "") == 42

    def test_width_1_accepts_any_non_empty_integer(self) -> None:
        """Width 1 (single `#`) degrades to min-width-1 — any non-empty digit run."""
        from griptape_nodes.common.macro_parser.sequence import _extract_frame_from_entry

        token = self._token(1)
        assert _extract_frame_from_entry("frame_5.png", "frame_", token, ".png") == 5
        assert _extract_frame_from_entry("frame_12345.png", "frame_", token, ".png") == 12345


class TestRenderFrame:
    def test_render_frame_pads_to_declared_width(self, mock_secrets: Any) -> None:
        """Frame is padded to declared width with the variables substituted."""
        st = SequenceTemplate(ParsedMacro("{outputs}/render.####.exr"))
        path = st.render_frame(5, {"outputs": "/workspace/out"}, mock_secrets)
        assert path == "/workspace/out/render.0005.exr"

    def test_render_frame_overflow(self, mock_secrets: Any) -> None:
        """Frames exceeding declared width render at natural width."""
        st = SequenceTemplate(ParsedMacro("render.####.exr"))
        assert st.render_frame(12345, {}, mock_secrets) == "render.12345.exr"

    def test_render_frame_negative(self, mock_secrets: Any) -> None:
        """Negative frames prepend sign in addition to padding."""
        st = SequenceTemplate(ParsedMacro("render.####.exr"))
        assert st.render_frame(-5, {}, mock_secrets) == "render.-0005.exr"

    def test_render_frame_unpadded_printf(self, mock_secrets: Any) -> None:
        """`%d` renders at natural width (no padding)."""
        st = SequenceTemplate(ParsedMacro("render.%d.exr"))
        assert st.render_frame(5, {}, mock_secrets) == "render.5.exr"
        assert st.render_frame(12345, {}, mock_secrets) == "render.12345.exr"


class TestScanMissingVariables:
    def test_scan_raises_when_variables_unresolved(self, mock_secrets: Any) -> None:
        """Scan refuses when a required variable isn't supplied."""
        from griptape_nodes.common.macro_parser.exceptions import MacroResolutionError

        st = SequenceTemplate(ParsedMacro("{outputs}/render.####.exr"))
        with pytest.raises(MacroResolutionError, match="not supplied"):
            st.scan({}, mock_secrets)


class TestScanTokenInFinalComponent:
    """Sequence token in the filename — the common case."""

    def test_scan_finds_all_frames(self, mock_secrets: Any) -> None:
        directory = "/workspace/out"
        entries = [_make_entry(f"render.{n:04d}.exr", directory, is_dir=False) for n in [1, 2, 4, 6, 7]]
        listings = {directory: entries}

        st = SequenceTemplate(ParsedMacro("{outputs}/render.####.exr"))
        with patch.object(GriptapeNodes, "handle_request", side_effect=_stub_listings(listings)):
            seq = st.scan({"outputs": directory}, mock_secrets)

        assert [f for f, _ in seq.frames] == [1, 2, 4, 6, 7]

    def test_scan_sorts_numerically_not_lexically(self, mock_secrets: Any) -> None:
        directory = "/workspace/out"
        entries = [_make_entry(f"render.{n:04d}.exr", directory, is_dir=False) for n in [2, 10]]
        st = SequenceTemplate(ParsedMacro("{outputs}/render.####.exr"))
        with patch.object(GriptapeNodes, "handle_request", side_effect=_stub_listings({directory: entries})):
            seq = st.scan({"outputs": directory}, mock_secrets)
        assert [f for f, _ in seq.frames] == [2, 10]

    def test_scan_computes_missing(self, mock_secrets: Any) -> None:
        directory = "/workspace/out"
        entries = [_make_entry(f"render.{n:04d}.exr", directory, is_dir=False) for n in [1, 2, 4, 7]]
        st = SequenceTemplate(ParsedMacro("{outputs}/render.####.exr"))
        with patch.object(GriptapeNodes, "handle_request", side_effect=_stub_listings({directory: entries})):
            seq = st.scan({"outputs": directory}, mock_secrets)
        assert seq.missing == {3, 5, 6}

    def test_scan_empty_directory(self, mock_secrets: Any) -> None:
        directory = "/workspace/out"
        st = SequenceTemplate(ParsedMacro("{outputs}/render.####.exr"))
        with patch.object(GriptapeNodes, "handle_request", side_effect=_stub_listings({directory: []})):
            seq = st.scan({"outputs": directory}, mock_secrets)
        assert seq.frames == []
        assert seq.missing == set()

    def test_scan_respects_minimum_width(self, mock_secrets: Any) -> None:
        """`####` matches 4+ digits on the regex stage (glob is `*`, permissive)."""
        directory = "/workspace/out"
        entries = [
            _make_entry("render.0001.exr", directory, is_dir=False),
            _make_entry("render.123.exr", directory, is_dir=False),  # 3 digits, under minimum
            _make_entry("render.12345.exr", directory, is_dir=False),  # 5 digits, over minimum
        ]
        st = SequenceTemplate(ParsedMacro("{outputs}/render.####.exr"))
        with patch.object(GriptapeNodes, "handle_request", side_effect=_stub_listings({directory: entries})):
            seq = st.scan({"outputs": directory}, mock_secrets)
        assert [f for f, _ in seq.frames] == [1, 12345]

    def test_scan_matches_negative_frames(self, mock_secrets: Any) -> None:
        directory = "/workspace/out"
        entries = [
            _make_entry("render.-0005.exr", directory, is_dir=False),
            _make_entry("render.0001.exr", directory, is_dir=False),
        ]
        st = SequenceTemplate(ParsedMacro("{outputs}/render.####.exr"))
        with patch.object(GriptapeNodes, "handle_request", side_effect=_stub_listings({directory: entries})):
            seq = st.scan({"outputs": directory}, mock_secrets)
        assert [f for f, _ in seq.frames] == [-5, 1]

    def test_scan_duplicate_frames_first_lex_wins(self, mock_secrets: Any, caplog: pytest.LogCaptureFixture) -> None:
        """Duplicate frames: lexicographically-first filename keeps the slot, others shadow."""
        directory = "/workspace/out"
        entries = [
            _make_entry("render.001.png", directory, is_dir=False),
            _make_entry("render.01.png", directory, is_dir=False),
            _make_entry("render.1.png", directory, is_dir=False),
        ]
        st = SequenceTemplate(ParsedMacro("{outputs}/render.#.png"))
        with (
            caplog.at_level(logging.WARNING),
            patch.object(GriptapeNodes, "handle_request", side_effect=_stub_listings({directory: entries})),
        ):
            seq = st.scan({"outputs": directory}, mock_secrets)
        assert dict(seq.frames)[1].name == "render.001.png"
        shadowed = sorted(p.name for p in seq.shadowed_files[1])
        assert shadowed == ["render.01.png", "render.1.png"]
        assert any("duplicate" in rec.message for rec in caplog.records)


class TestScanTokenInDirectoryComponent:
    """Sequence token IS a directory name (no suffix after it)."""

    def test_scan_finds_frame_directories(self, mock_secrets: Any) -> None:
        directory = "/workspace/out"
        entries = [_make_entry(f"{n:04d}", directory, is_dir=True) for n in [1, 2, 4]]
        st = SequenceTemplate(ParsedMacro("{outputs}/####"))
        with patch.object(GriptapeNodes, "handle_request", side_effect=_stub_listings({directory: entries})):
            seq = st.scan({"outputs": directory}, mock_secrets)
        assert [f for f, _ in seq.frames] == [1, 2, 4]


class TestScanTokenInDirectoryWithSuffix:
    """Sequence token in a mid-path directory component with a suffix file."""

    def test_scan_verifies_suffix_file_exists(self, mock_secrets: Any) -> None:
        """Each matching directory is probed for the suffix file."""
        directory = "/workspace/out"
        # Directories named by frame:
        dir_entries = [_make_entry(f"{n:04d}", directory, is_dir=True) for n in [1, 2, 3]]
        # Frame 1 and 3 contain beauty.exr, frame 2 does NOT.
        listings: dict[str, list[FileSystemEntry]] = {
            directory: dir_entries,
            "/workspace/out/0001": [_make_entry("beauty.exr", "/workspace/out/0001", is_dir=False)],
            "/workspace/out/0002": [_make_entry("other.exr", "/workspace/out/0002", is_dir=False)],
            "/workspace/out/0003": [_make_entry("beauty.exr", "/workspace/out/0003", is_dir=False)],
        }
        st = SequenceTemplate(ParsedMacro("{outputs}/####/beauty.exr"))
        with patch.object(GriptapeNodes, "handle_request", side_effect=_stub_listings(listings)):
            seq = st.scan({"outputs": directory}, mock_secrets)

        # Frame 2 should be missing because beauty.exr isn't there.
        assert [f for f, _ in seq.frames] == [1, 3]
        assert seq.frames[0][1] == Path("/workspace/out/0001/beauty.exr")
        assert seq.frames[1][1] == Path("/workspace/out/0003/beauty.exr")

    def test_scan_embedded_token_in_directory_name(self, mock_secrets: Any) -> None:
        """Token inside a directory name (e.g. `v_####_final`) works via regex."""
        directory = "/workspace/out"
        dir_entries = [
            _make_entry("v_0001_final", directory, is_dir=True),
            _make_entry("v_0002_final", directory, is_dir=True),
            _make_entry("v_stale", directory, is_dir=True),  # doesn't match pattern
        ]
        listings: dict[str, list[FileSystemEntry]] = {
            directory: dir_entries,
            "/workspace/out/v_0001_final": [_make_entry("beauty.exr", "/workspace/out/v_0001_final", is_dir=False)],
            "/workspace/out/v_0002_final": [_make_entry("beauty.exr", "/workspace/out/v_0002_final", is_dir=False)],
        }
        st = SequenceTemplate(ParsedMacro("{outputs}/v_####_final/beauty.exr"))
        with patch.object(GriptapeNodes, "handle_request", side_effect=_stub_listings(listings)):
            seq = st.scan({"outputs": directory}, mock_secrets)
        assert [f for f, _ in seq.frames] == [1, 2]


class TestMissingFramePolicy:
    def _build_sequence(self, policy: MissingFramePolicy) -> Sequence:
        """Build a Sequence with frames 1, 2, 4, 6, 7 directly (skip scan stubbing)."""
        frames = [SequenceFrame(frame=n, path=Path(f"/workspace/out/render.{n:04d}.exr")) for n in [1, 2, 4, 6, 7]]
        return Sequence(frames=frames, first=1, last=7, policy=policy)

    def test_error_policy_raises(self) -> None:
        seq = self._build_sequence(MissingFramePolicy.ERROR)
        with pytest.raises(MissingFrameError) as exc_info:
            seq.get(3)
        assert exc_info.value.frame == 3

    def test_error_policy_present_frame_returns_path(self) -> None:
        seq = self._build_sequence(MissingFramePolicy.ERROR)
        path = seq.get(4)
        assert isinstance(path, Path)
        assert path.name == "render.0004.exr"

    def test_nearest_policy_mid_gap_prefers_lower(self) -> None:
        """Missing frame 3: tie between 2 and 4, lower wins."""
        seq = self._build_sequence(MissingFramePolicy.NEAREST)
        path = seq.get(3)
        assert isinstance(path, Path)
        assert path.name == "render.0002.exr"

    def test_nearest_policy_before_first(self) -> None:
        seq = self._build_sequence(MissingFramePolicy.NEAREST)
        path = seq.get(-50)
        assert isinstance(path, Path)
        assert path.name == "render.0001.exr"

    def test_nearest_policy_after_last(self) -> None:
        seq = self._build_sequence(MissingFramePolicy.NEAREST)
        path = seq.get(999)
        assert isinstance(path, Path)
        assert path.name == "render.0007.exr"

    def test_black_policy_returns_marker(self) -> None:
        seq = self._build_sequence(MissingFramePolicy.BLACK)
        result = seq.get(3)
        assert isinstance(result, MissingFrameMarker)
        assert result.policy is MissingFramePolicy.BLACK
        assert result.frame == 3

    def test_checkerboard_policy_returns_marker(self) -> None:
        seq = self._build_sequence(MissingFramePolicy.CHECKERBOARD)
        result = seq.get(5)
        assert isinstance(result, MissingFrameMarker)
        assert result.policy is MissingFramePolicy.CHECKERBOARD
        assert result.frame == 5


class TestIterDense:
    def test_iter_dense_yields_entry_per_frame(self) -> None:
        """`iter_dense` yields one entry for each frame in [first, last]."""
        frames = [SequenceFrame(frame=n, path=Path(f"/workspace/out/render.{n:04d}.exr")) for n in [1, 2, 4]]
        seq = Sequence(frames=frames, first=1, last=4, policy=MissingFramePolicy.BLACK)
        dense = list(seq.iter_dense())
        assert [d.frame for d in dense] == [1, 2, 3, 4]
        assert isinstance(dense[2].value, MissingFrameMarker)
        assert isinstance(dense[0].value, Path)
