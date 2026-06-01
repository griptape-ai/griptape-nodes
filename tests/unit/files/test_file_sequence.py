"""Unit tests for FileSequence and FileSequenceDestination."""

from pathlib import Path
from unittest.mock import patch

import pytest

from griptape_nodes.common.macro_parser import ParsedMacro
from griptape_nodes.common.sequences import MissingItemPolicy, Sequence, SequenceEntry
from griptape_nodes.files.file_sequence import (
    FileSequence,
    FileSequenceDestination,
    FileSequenceError,
    build_versioned_sequence_destination,
    entry_macro_to_hash_pattern,
    hash_pattern_to_entry_macro,
)
from griptape_nodes.retained_mode.events.os_events import (
    ExistingFilePolicy,
    ScanSequencesRequest,
    ScanSequencesResultFailure,
    ScanSequencesResultSuccess,
    SequenceScanFailureReason,
)
from griptape_nodes.retained_mode.events.project_events import (
    GetPathForMacroResultFailure,
    GetPathForMacroResultSuccess,
    MacroPath,
    PathResolutionFailureReason,
)

HANDLE_REQUEST_PATH = "griptape_nodes.files.file_sequence.GriptapeNodes.handle_request"


class TestHashPatternConversion:
    """Tests for hash_pattern_to_entry_macro and entry_macro_to_hash_pattern (pure functions)."""

    def test_hash_to_entry_macro_four_hashes(self) -> None:
        assert hash_pattern_to_entry_macro("####") == "{entry:04}"

    def test_hash_to_entry_macro_two_hashes(self) -> None:
        assert hash_pattern_to_entry_macro("##") == "{entry:02}"

    def test_hash_to_entry_macro_six_hashes(self) -> None:
        assert hash_pattern_to_entry_macro("######") == "{entry:06}"

    def test_hash_to_entry_macro_with_prefix_and_suffix(self) -> None:
        assert hash_pattern_to_entry_macro("render_####.exr") == "render_{entry:04}.exr"

    def test_hash_to_entry_macro_no_hashes_unchanged(self) -> None:
        assert hash_pattern_to_entry_macro("frame.exr") == "frame.exr"

    def test_hash_to_entry_macro_single_hash(self) -> None:
        assert hash_pattern_to_entry_macro("#") == "{entry:01}"

    def test_entry_macro_to_hash_with_explicit_width(self) -> None:
        assert entry_macro_to_hash_pattern("{entry:06}") == "######"

    def test_entry_macro_to_hash_four_width(self) -> None:
        assert entry_macro_to_hash_pattern("{entry:04}") == "####"

    def test_entry_macro_to_hash_no_width_defaults_to_4(self) -> None:
        assert entry_macro_to_hash_pattern("{entry}") == "####"

    def test_entry_macro_to_hash_with_prefix_and_suffix(self) -> None:
        assert entry_macro_to_hash_pattern("frame_{entry:04}.exr") == "frame_####.exr"

    def test_entry_macro_to_hash_no_entry_var_unchanged(self) -> None:
        assert entry_macro_to_hash_pattern("frame.exr") == "frame.exr"

    def test_roundtrip_hash_to_macro_to_hash(self) -> None:
        original = "render_####.exr"
        assert entry_macro_to_hash_pattern(hash_pattern_to_entry_macro(original)) == original

    def test_roundtrip_macro_to_hash_to_macro(self) -> None:
        original = "render_{entry:04}.exr"
        assert hash_pattern_to_entry_macro(entry_macro_to_hash_pattern(original)) == original

    def test_hash_to_entry_macro_printf_pattern(self) -> None:
        assert hash_pattern_to_entry_macro("render_%04d.exr") == "render_{entry:04}.exr"

    def test_hash_to_entry_macro_full_path_with_parent_dir(self) -> None:
        assert (
            hash_pattern_to_entry_macro("{outputs}/renders/render_####.exr")
            == "{outputs}/renders/render_{entry:04}.exr"
        )

    def test_hash_to_entry_macro_printf_in_full_path(self) -> None:
        assert (
            hash_pattern_to_entry_macro("{outputs}/renders/render_%04d.exr")
            == "{outputs}/renders/render_{entry:04}.exr"
        )


class TestFileSequenceConstructor:
    """Tests that FileSequence constructor stores the entry macro without I/O."""

    def test_stores_entry_macro(self) -> None:
        macro_path = MacroPath(ParsedMacro("{outputs}/frames/frame_{entry:04}.exr"), {"_index": 1})
        seq = FileSequence(macro_path)
        assert seq._entry_macro is macro_path

    def test_does_no_io(self) -> None:
        macro_path = MacroPath(ParsedMacro("{outputs}/frames/frame_{entry:04}.exr"), {"_index": 1})
        with patch(HANDLE_REQUEST_PATH) as mock_handle:
            FileSequence(macro_path)
        mock_handle.assert_not_called()


class TestFileSequenceLocation:
    """Tests for FileSequence.location property."""

    def test_location_returns_macro_template(self) -> None:
        template = "{outputs}/frames/frame_{entry:04}.exr"
        macro_path = MacroPath(ParsedMacro(template), {"_index": 1})
        seq = FileSequence(macro_path)
        assert seq.location == template

    def test_location_no_io_performed(self) -> None:
        macro_path = MacroPath(ParsedMacro("{outputs}/frames/frame_{entry:04}.exr"), {})
        with patch(HANDLE_REQUEST_PATH) as mock_handle:
            seq = FileSequence(macro_path)
            _ = seq.location
        mock_handle.assert_not_called()


class TestFileSequencePattern:
    """Tests for FileSequence.pattern property."""

    def test_pattern_converts_entry_var_to_hashes(self) -> None:
        template = "{outputs}/frames/frame_{entry:04}.exr"
        macro_path = MacroPath(ParsedMacro(template), {"_index": 1})
        seq = FileSequence(macro_path)
        assert seq.pattern == "{outputs}/frames/frame_####.exr"

    def test_pattern_with_six_digit_entry(self) -> None:
        template = "renders/frame_{entry:06}.png"
        macro_path = MacroPath(ParsedMacro(template), {})
        seq = FileSequence(macro_path)
        assert seq.pattern == "renders/frame_######.png"


class TestFileSequenceDirectory:
    """Tests for FileSequence.directory property."""

    def test_directory_returns_parent_of_template(self) -> None:
        template = "{outputs}/frames/frame_{entry:04}.exr"
        macro_path = MacroPath(ParsedMacro(template), {"_index": 1})
        seq = FileSequence(macro_path)
        directory = seq.directory
        assert directory.location == "{outputs}/frames"

    def test_directory_no_io_performed(self) -> None:
        macro_path = MacroPath(ParsedMacro("{outputs}/frames/frame_{entry:04}.exr"), {})
        with patch(HANDLE_REQUEST_PATH) as mock_handle:
            seq = FileSequence(macro_path)
            _ = seq.directory
        mock_handle.assert_not_called()


class TestFileSequenceEntry:
    """Tests for FileSequence.entry() method."""

    def test_entry_returns_file_with_correct_entry_number(self) -> None:
        entry_number = 5
        macro_path = MacroPath(ParsedMacro("{outputs}/frames/frame_{entry:04}.exr"), {"_index": 1})
        seq = FileSequence(macro_path)
        file = seq.entry(entry_number)
        assert isinstance(file._file_path, MacroPath)
        assert file._file_path.variables["entry"] == entry_number

    def test_entry_inherits_locked_index_variable(self) -> None:
        locked_index = 7
        entry_number = 3
        macro_path = MacroPath(
            ParsedMacro("{outputs}/renders_v{_index:03}/frame_{entry:04}.exr"), {"_index": locked_index}
        )
        seq = FileSequence(macro_path)
        file = seq.entry(entry_number)
        assert isinstance(file._file_path, MacroPath)
        assert file._file_path.variables["_index"] == locked_index
        assert file._file_path.variables["entry"] == entry_number

    def test_entry_does_no_io(self) -> None:
        macro_path = MacroPath(ParsedMacro("{outputs}/frames/frame_{entry:04}.exr"), {"_index": 1})
        seq = FileSequence(macro_path)
        with patch(HANDLE_REQUEST_PATH) as mock_handle:
            seq.entry(0)
        mock_handle.assert_not_called()

    def test_entry_zero(self) -> None:
        macro_path = MacroPath(ParsedMacro("{outputs}/frames/frame_{entry:04}.exr"), {})
        seq = FileSequence(macro_path)
        file = seq.entry(0)
        assert isinstance(file._file_path, MacroPath)
        assert file._file_path.variables["entry"] == 0


class TestFileSequenceDestination:
    """Tests for FileSequenceDestination."""

    def test_file_sequence_is_none_before_write(self) -> None:
        macro_path = MacroPath(ParsedMacro("{outputs}/frames/frame_{entry:04}.exr"), {"_index": 1})
        dest = FileSequenceDestination(macro_path)
        assert dest.file_sequence is None

    def test_entry_returns_file_destination(self) -> None:
        from griptape_nodes.files.file import FileDestination

        macro_path = MacroPath(ParsedMacro("{outputs}/frames/frame_{entry:04}.exr"), {"_index": 1})
        dest = FileSequenceDestination(macro_path)
        entry_dest = dest.entry(1)
        assert isinstance(entry_dest, FileDestination)

    def test_entry_destination_has_correct_entry_variable(self) -> None:
        entry_number = 42
        macro_path = MacroPath(ParsedMacro("{outputs}/frames/frame_{entry:04}.exr"), {"_index": 1})
        dest = FileSequenceDestination(macro_path)
        entry_dest = dest.entry(entry_number)
        assert isinstance(entry_dest._file._file_path, MacroPath)
        assert entry_dest._file._file_path.variables["entry"] == entry_number

    def test_on_entry_written_sets_file_sequence(self) -> None:
        from griptape_nodes.files.file import File

        macro_path = MacroPath(ParsedMacro("{outputs}/frames/frame_{entry:04}.exr"), {"_index": 1})
        dest = FileSequenceDestination(macro_path)
        assert dest.file_sequence is None
        dest._on_entry_written(File("workspace/frame_0001.exr"))
        assert dest.file_sequence is not None
        assert isinstance(dest.file_sequence, FileSequence)

    def test_file_sequence_not_reset_on_second_write(self) -> None:
        from griptape_nodes.files.file import File

        macro_path = MacroPath(ParsedMacro("{outputs}/frames/frame_{entry:04}.exr"), {"_index": 1})
        dest = FileSequenceDestination(macro_path)
        dest._on_entry_written(File("workspace/frame_0001.exr"))
        first_seq = dest.file_sequence
        dest._on_entry_written(File("workspace/frame_0002.exr"))
        assert dest.file_sequence is first_seq

    def test_file_sequence_uses_locked_macro(self) -> None:
        from griptape_nodes.files.file import File

        macro_path = MacroPath(ParsedMacro("{outputs}/renders_v{_index:03}/frame_{entry:04}.exr"), {"_index": 3})
        dest = FileSequenceDestination(macro_path)
        dest._on_entry_written(File("workspace/frame_0001.exr"))
        assert dest.file_sequence is not None
        assert dest.file_sequence._entry_macro is macro_path

    def test_defaults_overwrite_policy(self) -> None:
        macro_path = MacroPath(ParsedMacro("{outputs}/frames/frame_{entry:04}.exr"), {})
        dest = FileSequenceDestination(macro_path)
        assert dest._existing_file_policy == ExistingFilePolicy.OVERWRITE
        assert dest._create_parents is True

    def test_entry_write_destination_triggers_on_written_callback(self) -> None:
        from griptape_nodes.files.file import File
        from griptape_nodes.files.file_sequence import _EntryWriteDestination

        callback_calls: list[File] = []
        macro_path = MacroPath(ParsedMacro("{outputs}/frames/frame_{entry:04}.exr"), {"_index": 1})
        entry_path = MacroPath(macro_path.parsed_macro, {**macro_path.variables, "entry": 1})

        entry_dest = _EntryWriteDestination(
            entry_path,
            existing_file_policy=ExistingFilePolicy.OVERWRITE,
            create_parents=True,
            on_written=callback_calls.append,
        )

        written_file = File("workspace/frame_0001.exr")
        entry_dest._on_written(written_file)

        assert len(callback_calls) == 1
        assert callback_calls[0] is written_file


class TestFileSequenceScan:
    """Tests for FileSequence.scan().

    scan() makes two handle_request calls:
      1. GetPathForMacroRequest  — resolves the macro to an absolute directory path.
      2. ScanSequencesRequest    — delegates the actual filesystem scan to the engine.
    """

    _ABS_DIR = "/abs/work/frames"
    _TEMPLATE = "{outputs}/frames/frame_{entry:04}.exr"

    def _path_success(self) -> GetPathForMacroResultSuccess:
        return GetPathForMacroResultSuccess(
            result_details="OK",
            resolved_path=Path("frames/frame_0000.exr"),
            absolute_path=Path(f"{self._ABS_DIR}/frame_0000.exr"),
        )

    def _scan_success(self, sequences: list[Sequence] | None = None) -> ScanSequencesResultSuccess:
        seqs = sequences or []
        return ScanSequencesResultSuccess(
            result_details="ok",
            sequences=seqs,
            has_entries=any(s.entries for s in seqs),
            directory_had_matching_files=bool(seqs),
        )

    def _make_sequence(self) -> Sequence:
        return Sequence(
            entries=[SequenceEntry(number=1, padded_number="0001", path=f"{self._ABS_DIR}/frame_0001.exr")],
            first=1,
            last=1,
            discovered_first=1,
            discovered_last=1,
            padding=4,
            pattern="frame_####.exr",
            directory=self._ABS_DIR,
            policy=MissingItemPolicy.SPLIT,
            present_numbers={1},
        )

    def test_returns_empty_list_when_macro_resolution_fails(self) -> None:
        seq = FileSequence(MacroPath(ParsedMacro(self._TEMPLATE), {}))
        failure = GetPathForMacroResultFailure(
            result_details="missing outputs",
            failure_reason=PathResolutionFailureReason.MISSING_REQUIRED_VARIABLES,
        )
        with patch(HANDLE_REQUEST_PATH, return_value=failure):
            assert seq.scan() == []

    def test_returns_empty_list_when_scan_request_fails(self) -> None:
        seq = FileSequence(MacroPath(ParsedMacro(self._TEMPLATE), {}))
        scan_failure = ScanSequencesResultFailure(
            result_details="listing error",
            failure_reason=SequenceScanFailureReason.INVALID_TEMPLATE,
        )
        with patch(HANDLE_REQUEST_PATH, side_effect=[self._path_success(), scan_failure]):
            assert seq.scan() == []

    def test_returns_sequences_on_success(self) -> None:
        seq = FileSequence(MacroPath(ParsedMacro(self._TEMPLATE), {}))
        expected = [self._make_sequence()]
        with patch(HANDLE_REQUEST_PATH, side_effect=[self._path_success(), self._scan_success(expected)]):
            result = seq.scan()
        assert result == expected

    def test_returns_empty_list_when_no_sequences_found(self) -> None:
        seq = FileSequence(MacroPath(ParsedMacro(self._TEMPLATE), {}))
        with patch(HANDLE_REQUEST_PATH, side_effect=[self._path_success(), self._scan_success()]):
            assert seq.scan() == []

    def test_dispatches_resolved_directory_to_scan_request(self) -> None:
        seq = FileSequence(MacroPath(ParsedMacro(self._TEMPLATE), {}))
        with patch(HANDLE_REQUEST_PATH, side_effect=[self._path_success(), self._scan_success()]) as mock_handle:
            seq.scan()
        scan_request = mock_handle.call_args_list[1][0][0]
        assert isinstance(scan_request, ScanSequencesRequest)
        assert scan_request.directory == self._ABS_DIR

    def test_dispatches_filename_only_pattern_to_scan_request(self) -> None:
        seq = FileSequence(MacroPath(ParsedMacro(self._TEMPLATE), {}))
        with patch(HANDLE_REQUEST_PATH, side_effect=[self._path_success(), self._scan_success()]) as mock_handle:
            seq.scan()
        scan_request = mock_handle.call_args_list[1][0][0]
        assert isinstance(scan_request, ScanSequencesRequest)
        assert scan_request.pattern == "frame_####.exr"

    def test_forwards_policy_to_scan_request(self) -> None:
        seq = FileSequence(MacroPath(ParsedMacro(self._TEMPLATE), {}))
        with patch(HANDLE_REQUEST_PATH, side_effect=[self._path_success(), self._scan_success()]) as mock_handle:
            seq.scan(policy=MissingItemPolicy.SKIP)
        scan_request = mock_handle.call_args_list[1][0][0]
        assert isinstance(scan_request, ScanSequencesRequest)
        assert scan_request.policy == MissingItemPolicy.SKIP

    def test_forwards_start_and_end_to_scan_request(self) -> None:
        start, end = 2, 10
        seq = FileSequence(MacroPath(ParsedMacro(self._TEMPLATE), {}))
        with patch(HANDLE_REQUEST_PATH, side_effect=[self._path_success(), self._scan_success()]) as mock_handle:
            seq.scan(start=start, end=end)
        scan_request = mock_handle.call_args_list[1][0][0]
        assert isinstance(scan_request, ScanSequencesRequest)
        assert scan_request.start_number == start
        assert scan_request.end_number == end

    def test_probe_macro_includes_entry_zero(self) -> None:
        locked_index = 3
        macro_path = MacroPath(ParsedMacro(self._TEMPLATE), {"_index": locked_index})
        seq = FileSequence(macro_path)
        with patch(HANDLE_REQUEST_PATH, side_effect=[self._path_success(), self._scan_success()]) as mock_handle:
            seq.scan()
        path_request = mock_handle.call_args_list[0][0][0]
        assert path_request.variables["entry"] == 0
        assert path_request.variables["_index"] == locked_index


class TestBuildVersionedSequenceDestination:
    """Tests for build_versioned_sequence_destination."""

    def test_first_version_used_when_parent_missing(self, tmp_path: Path) -> None:
        missing_parent = tmp_path / "renders_v001"
        entry_path = missing_parent / "frame_0000.exr"

        resolve_result = GetPathForMacroResultSuccess(
            result_details="OK",
            resolved_path=Path("renders_v001/frame_0000.exr"),
            absolute_path=entry_path,
        )
        macro = MacroPath(ParsedMacro("{outputs}/renders_v{_index:03}/frame_{entry:04}.exr"), {})

        with patch(HANDLE_REQUEST_PATH, return_value=resolve_result):
            dest = build_versioned_sequence_destination(macro)

        assert dest._entry_macro.variables["_index"] == 1

    def test_second_version_used_when_first_parent_exists(self, tmp_path: Path) -> None:
        existing_parent = tmp_path / "renders_v001"
        existing_parent.mkdir()
        missing_parent = tmp_path / "renders_v002"

        resolve_result_1 = GetPathForMacroResultSuccess(
            result_details="OK",
            resolved_path=Path("renders_v001/frame_0000.exr"),
            absolute_path=existing_parent / "frame_0000.exr",
        )
        resolve_result_2 = GetPathForMacroResultSuccess(
            result_details="OK",
            resolved_path=Path("renders_v002/frame_0000.exr"),
            absolute_path=missing_parent / "frame_0000.exr",
        )
        macro = MacroPath(ParsedMacro("{outputs}/renders_v{_index:03}/frame_{entry:04}.exr"), {})

        expected_index = 2
        with patch(HANDLE_REQUEST_PATH, side_effect=[resolve_result_1, resolve_result_2]):
            dest = build_versioned_sequence_destination(macro)

        assert dest._entry_macro.variables["_index"] == expected_index

    def test_raises_when_macro_resolution_fails(self) -> None:
        failure = GetPathForMacroResultFailure(
            result_details="Missing variables: outputs",
            failure_reason=PathResolutionFailureReason.MISSING_REQUIRED_VARIABLES,
            missing_variables={"outputs"},
        )
        macro = MacroPath(ParsedMacro("{outputs}/renders_v{_index:03}/frame_{entry:04}.exr"), {})

        with patch(HANDLE_REQUEST_PATH, return_value=failure), pytest.raises(FileSequenceError):
            build_versioned_sequence_destination(macro)

    def test_raises_when_all_versions_exhausted(self, tmp_path: Path) -> None:
        existing_parent = tmp_path
        resolve_result = GetPathForMacroResultSuccess(
            result_details="OK",
            resolved_path=Path("frame_0000.exr"),
            absolute_path=existing_parent / "frame_0000.exr",
        )
        macro = MacroPath(ParsedMacro("{outputs}/renders_v{_index:03}/frame_{entry:04}.exr"), {})

        with (
            patch(HANDLE_REQUEST_PATH, return_value=resolve_result),
            patch("griptape_nodes.files.file_sequence._MAX_VERSION_INDEX", 3),
            pytest.raises(FileSequenceError),
        ):
            build_versioned_sequence_destination(macro)

    def test_locks_index_into_returned_destination_variables(self, tmp_path: Path) -> None:
        missing_parent = tmp_path / "seq_v001"
        resolve_result = GetPathForMacroResultSuccess(
            result_details="OK",
            resolved_path=Path("seq_v001/frame_0000.exr"),
            absolute_path=missing_parent / "frame_0000.exr",
        )
        macro = MacroPath(ParsedMacro("{outputs}/seq_v{_index:03}/frame_{entry:04}.exr"), {"extra": "value"})

        with patch(HANDLE_REQUEST_PATH, return_value=resolve_result):
            dest = build_versioned_sequence_destination(macro)

        assert "_index" in dest._entry_macro.variables
        assert "extra" in dest._entry_macro.variables
        assert "entry" not in dest._entry_macro.variables

    def test_existing_file_policy_forwarded(self, tmp_path: Path) -> None:
        missing_parent = tmp_path / "seq_v001"
        resolve_result = GetPathForMacroResultSuccess(
            result_details="OK",
            resolved_path=Path("seq_v001/frame_0000.exr"),
            absolute_path=missing_parent / "frame_0000.exr",
        )
        macro = MacroPath(ParsedMacro("{outputs}/seq_v{_index:03}/frame_{entry:04}.exr"), {})

        with patch(HANDLE_REQUEST_PATH, return_value=resolve_result):
            dest = build_versioned_sequence_destination(macro, existing_file_policy=ExistingFilePolicy.FAIL)

        assert dest._existing_file_policy == ExistingFilePolicy.FAIL
