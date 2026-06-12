"""Unit tests for FileSequence and FileSequenceDestination."""

import pathlib
from unittest import mock

import pytest

from griptape_nodes.common import macro_parser, sequences
from griptape_nodes.files import file as file_mod
from griptape_nodes.files import file_sequence
from griptape_nodes.retained_mode.events import os_events, project_events

HANDLE_REQUEST_PATH = "griptape_nodes.retained_mode.griptape_nodes.GriptapeNodes.handle_request"


class TestHashPatternConversion:
    """Tests for hash_pattern_to_entry_macro and entry_macro_to_hash_pattern (pure functions)."""

    def test_hash_to_entry_macro_four_hashes(self) -> None:
        assert file_sequence.hash_pattern_to_entry_macro("####") == "{entry:04}"

    def test_hash_to_entry_macro_two_hashes(self) -> None:
        assert file_sequence.hash_pattern_to_entry_macro("##") == "{entry:02}"

    def test_hash_to_entry_macro_six_hashes(self) -> None:
        assert file_sequence.hash_pattern_to_entry_macro("######") == "{entry:06}"

    def test_hash_to_entry_macro_with_prefix_and_suffix(self) -> None:
        assert file_sequence.hash_pattern_to_entry_macro("render_####.exr") == "render_{entry:04}.exr"

    def test_hash_to_entry_macro_no_hashes_unchanged(self) -> None:
        assert file_sequence.hash_pattern_to_entry_macro("frame.exr") == "frame.exr"

    def test_hash_to_entry_macro_single_hash(self) -> None:
        assert file_sequence.hash_pattern_to_entry_macro("#") == "{entry:01}"

    def test_entry_macro_to_hash_with_explicit_width(self) -> None:
        assert file_sequence.entry_macro_to_hash_pattern("{entry:06}") == "######"

    def test_entry_macro_to_hash_four_width(self) -> None:
        assert file_sequence.entry_macro_to_hash_pattern("{entry:04}") == "####"

    def test_entry_macro_to_hash_no_width_defaults_to_4(self) -> None:
        assert file_sequence.entry_macro_to_hash_pattern("{entry}") == "####"

    def test_entry_macro_to_hash_with_prefix_and_suffix(self) -> None:
        assert file_sequence.entry_macro_to_hash_pattern("frame_{entry:04}.exr") == "frame_####.exr"

    def test_entry_macro_to_hash_no_entry_var_unchanged(self) -> None:
        assert file_sequence.entry_macro_to_hash_pattern("frame.exr") == "frame.exr"

    def test_roundtrip_hash_to_macro_to_hash(self) -> None:
        original = "render_####.exr"
        assert (
            file_sequence.entry_macro_to_hash_pattern(file_sequence.hash_pattern_to_entry_macro(original)) == original
        )

    def test_roundtrip_macro_to_hash_to_macro(self) -> None:
        original = "render_{entry:04}.exr"
        assert (
            file_sequence.hash_pattern_to_entry_macro(file_sequence.entry_macro_to_hash_pattern(original)) == original
        )

    def test_hash_to_entry_macro_printf_pattern(self) -> None:
        assert file_sequence.hash_pattern_to_entry_macro("render_%04d.exr") == "render_{entry:04}.exr"

    def test_hash_to_entry_macro_full_path_with_parent_dir(self) -> None:
        assert (
            file_sequence.hash_pattern_to_entry_macro("{outputs}/renders/render_####.exr")
            == "{outputs}/renders/render_{entry:04}.exr"
        )

    def test_hash_to_entry_macro_printf_in_full_path(self) -> None:
        assert (
            file_sequence.hash_pattern_to_entry_macro("{outputs}/renders/render_%04d.exr")
            == "{outputs}/renders/render_{entry:04}.exr"
        )


class TestFileSequenceConstructor:
    """Tests that FileSequence constructor stores the entry macro without I/O."""

    def test_stores_entry_macro(self) -> None:
        macro_path = project_events.MacroPath(
            macro_parser.ParsedMacro("{outputs}/frames/frame_{entry:04}.exr"), {"_index": 1}
        )
        seq = file_sequence.FileSequence(macro_path)
        assert seq._entry_macro is macro_path

    def test_does_no_io(self) -> None:
        macro_path = project_events.MacroPath(
            macro_parser.ParsedMacro("{outputs}/frames/frame_{entry:04}.exr"), {"_index": 1}
        )
        with mock.patch(HANDLE_REQUEST_PATH) as mock_handle:
            file_sequence.FileSequence(macro_path)
        mock_handle.assert_not_called()


class TestFileSequenceLocation:
    """Tests for FileSequence.location property."""

    def test_location_returns_macro_template(self) -> None:
        template = "{outputs}/frames/frame_{entry:04}.exr"
        macro_path = project_events.MacroPath(macro_parser.ParsedMacro(template), {"_index": 1})
        seq = file_sequence.FileSequence(macro_path)
        assert seq.location == template

    def test_location_no_io_performed(self) -> None:
        macro_path = project_events.MacroPath(macro_parser.ParsedMacro("{outputs}/frames/frame_{entry:04}.exr"), {})
        with mock.patch(HANDLE_REQUEST_PATH) as mock_handle:
            seq = file_sequence.FileSequence(macro_path)
            _ = seq.location
        mock_handle.assert_not_called()


class TestFileSequencePattern:
    """Tests for FileSequence.pattern property."""

    def test_pattern_converts_entry_var_to_hashes(self) -> None:
        template = "{outputs}/frames/frame_{entry:04}.exr"
        macro_path = project_events.MacroPath(macro_parser.ParsedMacro(template), {"_index": 1})
        seq = file_sequence.FileSequence(macro_path)
        assert seq.pattern == "{outputs}/frames/frame_####.exr"

    def test_pattern_with_six_digit_entry(self) -> None:
        template = "renders/frame_{entry:06}.png"
        macro_path = project_events.MacroPath(macro_parser.ParsedMacro(template), {})
        seq = file_sequence.FileSequence(macro_path)
        assert seq.pattern == "renders/frame_######.png"


class TestFileSequenceDirectory:
    """Tests for FileSequence.directory property."""

    def test_directory_returns_parent_of_template(self) -> None:
        template = "{outputs}/frames/frame_{entry:04}.exr"
        macro_path = project_events.MacroPath(macro_parser.ParsedMacro(template), {"_index": 1})
        seq = file_sequence.FileSequence(macro_path)
        directory = seq.directory
        assert directory.location == "{outputs}/frames"

    def test_directory_preserves_locked_index_variable(self) -> None:
        locked_index = 2
        template = "{outputs}/renders_v{_index:03}/frame_{entry:04}.exr"
        macro_path = project_events.MacroPath(macro_parser.ParsedMacro(template), {"_index": locked_index})
        seq = file_sequence.FileSequence(macro_path)
        directory = seq.directory
        assert isinstance(directory._dir_path, project_events.MacroPath)
        assert directory._dir_path.variables["_index"] == locked_index

    def test_directory_does_not_carry_entry_variable(self) -> None:
        template = "{outputs}/frames/frame_{entry:04}.exr"
        macro_path = project_events.MacroPath(macro_parser.ParsedMacro(template), {"_index": 1, "entry": 5})
        seq = file_sequence.FileSequence(macro_path)
        directory = seq.directory
        assert isinstance(directory._dir_path, project_events.MacroPath)
        assert "entry" not in directory._dir_path.variables

    def test_directory_no_io_performed(self) -> None:
        macro_path = project_events.MacroPath(macro_parser.ParsedMacro("{outputs}/frames/frame_{entry:04}.exr"), {})
        with mock.patch(HANDLE_REQUEST_PATH) as mock_handle:
            seq = file_sequence.FileSequence(macro_path)
            _ = seq.directory
        mock_handle.assert_not_called()


class TestFileSequenceEntry:
    """Tests for FileSequence.entry() method."""

    def test_entry_returns_file_with_correct_entry_number(self) -> None:
        entry_number = 5
        macro_path = project_events.MacroPath(
            macro_parser.ParsedMacro("{outputs}/frames/frame_{entry:04}.exr"), {"_index": 1}
        )
        seq = file_sequence.FileSequence(macro_path)
        f = seq.entry(entry_number)
        assert isinstance(f._file_path, project_events.MacroPath)
        assert f._file_path.variables["entry"] == entry_number

    def test_entry_inherits_locked_index_variable(self) -> None:
        locked_index = 7
        entry_number = 3
        macro_path = project_events.MacroPath(
            macro_parser.ParsedMacro("{outputs}/renders_v{_index:03}/frame_{entry:04}.exr"), {"_index": locked_index}
        )
        seq = file_sequence.FileSequence(macro_path)
        f = seq.entry(entry_number)
        assert isinstance(f._file_path, project_events.MacroPath)
        assert f._file_path.variables["_index"] == locked_index
        assert f._file_path.variables["entry"] == entry_number

    def test_entry_does_no_io(self) -> None:
        macro_path = project_events.MacroPath(
            macro_parser.ParsedMacro("{outputs}/frames/frame_{entry:04}.exr"), {"_index": 1}
        )
        seq = file_sequence.FileSequence(macro_path)
        with mock.patch(HANDLE_REQUEST_PATH) as mock_handle:
            seq.entry(0)
        mock_handle.assert_not_called()

    def test_entry_zero(self) -> None:
        macro_path = project_events.MacroPath(macro_parser.ParsedMacro("{outputs}/frames/frame_{entry:04}.exr"), {})
        seq = file_sequence.FileSequence(macro_path)
        f = seq.entry(0)
        assert isinstance(f._file_path, project_events.MacroPath)
        assert f._file_path.variables["entry"] == 0


class TestFileSequenceDestination:
    """Tests for FileSequenceDestination."""

    def test_file_sequence_is_none_before_write(self) -> None:
        macro_path = project_events.MacroPath(
            macro_parser.ParsedMacro("{outputs}/frames/frame_{entry:04}.exr"), {"_index": 1}
        )
        dest = file_sequence.FileSequenceDestination(macro_path)
        assert dest.file_sequence is None

    def test_entry_returns_file_destination(self) -> None:
        macro_path = project_events.MacroPath(
            macro_parser.ParsedMacro("{outputs}/frames/frame_{entry:04}.exr"), {"_index": 1}
        )
        dest = file_sequence.FileSequenceDestination(macro_path)
        entry_dest = dest.entry(1)
        assert isinstance(entry_dest, file_mod.FileDestination)

    def test_entry_destination_has_correct_entry_variable(self) -> None:
        entry_number = 42
        macro_path = project_events.MacroPath(
            macro_parser.ParsedMacro("{outputs}/frames/frame_{entry:04}.exr"), {"_index": 1}
        )
        dest = file_sequence.FileSequenceDestination(macro_path)
        entry_dest = dest.entry(entry_number)
        assert isinstance(entry_dest._file._file_path, project_events.MacroPath)
        assert entry_dest._file._file_path.variables["entry"] == entry_number

    def test_on_entry_written_sets_file_sequence(self) -> None:
        macro_path = project_events.MacroPath(
            macro_parser.ParsedMacro("{outputs}/frames/frame_{entry:04}.exr"), {"_index": 1}
        )
        dest = file_sequence.FileSequenceDestination(macro_path)
        assert dest.file_sequence is None
        dest._on_entry_written(file_mod.File("workspace/frame_0001.exr"))
        assert dest.file_sequence is not None
        assert isinstance(dest.file_sequence, file_sequence.FileSequence)

    def test_file_sequence_not_reset_on_second_write(self) -> None:
        macro_path = project_events.MacroPath(
            macro_parser.ParsedMacro("{outputs}/frames/frame_{entry:04}.exr"), {"_index": 1}
        )
        dest = file_sequence.FileSequenceDestination(macro_path)
        dest._on_entry_written(file_mod.File("workspace/frame_0001.exr"))
        first_seq = dest.file_sequence
        dest._on_entry_written(file_mod.File("workspace/frame_0002.exr"))
        assert dest.file_sequence is first_seq

    def test_file_sequence_uses_locked_macro(self) -> None:
        macro_path = project_events.MacroPath(
            macro_parser.ParsedMacro("{outputs}/renders_v{_index:03}/frame_{entry:04}.exr"), {"_index": 3}
        )
        dest = file_sequence.FileSequenceDestination(macro_path)
        dest._on_entry_written(file_mod.File("workspace/frame_0001.exr"))
        assert dest.file_sequence is not None
        assert dest.file_sequence._entry_macro is macro_path

    def test_defaults_overwrite_policy(self) -> None:
        macro_path = project_events.MacroPath(macro_parser.ParsedMacro("{outputs}/frames/frame_{entry:04}.exr"), {})
        dest = file_sequence.FileSequenceDestination(macro_path)
        assert dest._existing_file_policy == os_events.ExistingFilePolicy.OVERWRITE
        assert dest._create_parents is True

    def test_entry_write_destination_triggers_on_written_callback(self) -> None:
        callback_calls: list[file_mod.File] = []
        macro_path = project_events.MacroPath(
            macro_parser.ParsedMacro("{outputs}/frames/frame_{entry:04}.exr"), {"_index": 1}
        )
        entry_path = project_events.MacroPath(macro_path.parsed_macro, {**macro_path.variables, "entry": 1})

        entry_dest = file_sequence._EntryWriteDestination(
            entry_path,
            existing_file_policy=os_events.ExistingFilePolicy.OVERWRITE,
            create_parents=True,
            on_written=callback_calls.append,
        )

        written_file = file_mod.File("workspace/frame_0001.exr")
        entry_dest._on_written(written_file)

        assert len(callback_calls) == 1
        assert callback_calls[0] is written_file


class TestFileSequenceScan:
    """Tests for FileSequence.scan().

    scan() makes two handle_request calls:
      1. GetPathForMacroRequest  — resolves the macro to an absolute directory path.
      2. ScanSequencesRequest    — delegates the actual filesystem scan to the engine.
    """

    _TEMPLATE = "{outputs}/frames/frame_{entry:04}.exr"

    def _path_success(self, abs_dir: pathlib.Path) -> project_events.GetPathForMacroResultSuccess:
        return project_events.GetPathForMacroResultSuccess(
            result_details="OK",
            resolved_path=pathlib.Path("frames/frame_0000.exr"),
            absolute_path=abs_dir / "frame_0000.exr",
        )

    def _scan_success(self, seqs: list[sequences.Sequence] | None = None) -> os_events.ScanSequencesResultSuccess:
        found = seqs or []
        return os_events.ScanSequencesResultSuccess(
            result_details="ok",
            sequences=found,
            has_entries=any(s.entries for s in found),
            directory_had_matching_files=bool(found),
        )

    def _make_sequence(self, abs_dir: pathlib.Path) -> sequences.Sequence:
        return sequences.Sequence(
            entries=[sequences.SequenceEntry(number=1, padded_number="0001", path=str(abs_dir / "frame_0001.exr"))],
            first=1,
            last=1,
            discovered_first=1,
            discovered_last=1,
            padding=4,
            pattern="frame_####.exr",
            directory=str(abs_dir),
            policy=sequences.MissingItemPolicy.SPLIT,
            present_numbers={1},
        )

    def test_returns_empty_list_when_macro_resolution_fails(self) -> None:
        seq = file_sequence.FileSequence(project_events.MacroPath(macro_parser.ParsedMacro(self._TEMPLATE), {}))
        failure = project_events.GetPathForMacroResultFailure(
            result_details="missing outputs",
            failure_reason=project_events.PathResolutionFailureReason.MISSING_REQUIRED_VARIABLES,
        )
        with mock.patch(HANDLE_REQUEST_PATH, return_value=failure):
            assert seq.scan() == []

    def test_returns_empty_list_when_scan_request_fails(self, tmp_path: pathlib.Path) -> None:
        seq = file_sequence.FileSequence(project_events.MacroPath(macro_parser.ParsedMacro(self._TEMPLATE), {}))
        scan_failure = os_events.ScanSequencesResultFailure(
            result_details="listing error",
            failure_reason=os_events.SequenceScanFailureReason.INVALID_TEMPLATE,
        )
        with mock.patch(HANDLE_REQUEST_PATH, side_effect=[self._path_success(tmp_path), scan_failure]):
            assert seq.scan() == []

    def test_returns_sequences_on_success(self, tmp_path: pathlib.Path) -> None:
        seq = file_sequence.FileSequence(project_events.MacroPath(macro_parser.ParsedMacro(self._TEMPLATE), {}))
        expected = [self._make_sequence(tmp_path)]
        with mock.patch(HANDLE_REQUEST_PATH, side_effect=[self._path_success(tmp_path), self._scan_success(expected)]):
            result = seq.scan()
        assert result == expected

    def test_returns_empty_list_when_no_sequences_found(self, tmp_path: pathlib.Path) -> None:
        seq = file_sequence.FileSequence(project_events.MacroPath(macro_parser.ParsedMacro(self._TEMPLATE), {}))
        with mock.patch(HANDLE_REQUEST_PATH, side_effect=[self._path_success(tmp_path), self._scan_success()]):
            assert seq.scan() == []

    def test_dispatches_resolved_directory_to_scan_request(self, tmp_path: pathlib.Path) -> None:
        seq = file_sequence.FileSequence(project_events.MacroPath(macro_parser.ParsedMacro(self._TEMPLATE), {}))
        with mock.patch(
            HANDLE_REQUEST_PATH, side_effect=[self._path_success(tmp_path), self._scan_success()]
        ) as mock_handle:
            seq.scan()
        scan_request = mock_handle.call_args_list[1][0][0]
        assert isinstance(scan_request, os_events.ScanSequencesRequest)
        assert pathlib.Path(scan_request.path).parent == tmp_path

    def test_dispatches_filename_only_pattern_to_scan_request(self, tmp_path: pathlib.Path) -> None:
        seq = file_sequence.FileSequence(project_events.MacroPath(macro_parser.ParsedMacro(self._TEMPLATE), {}))
        with mock.patch(
            HANDLE_REQUEST_PATH, side_effect=[self._path_success(tmp_path), self._scan_success()]
        ) as mock_handle:
            seq.scan()
        scan_request = mock_handle.call_args_list[1][0][0]
        assert isinstance(scan_request, os_events.ScanSequencesRequest)
        assert pathlib.Path(scan_request.path).name == "frame_####.exr"

    def test_forwards_policy_to_scan_request(self, tmp_path: pathlib.Path) -> None:
        seq = file_sequence.FileSequence(project_events.MacroPath(macro_parser.ParsedMacro(self._TEMPLATE), {}))
        with mock.patch(
            HANDLE_REQUEST_PATH, side_effect=[self._path_success(tmp_path), self._scan_success()]
        ) as mock_handle:
            seq.scan(policy=sequences.MissingItemPolicy.SKIP)
        scan_request = mock_handle.call_args_list[1][0][0]
        assert isinstance(scan_request, os_events.ScanSequencesRequest)
        assert scan_request.policy == sequences.MissingItemPolicy.SKIP

    def test_forwards_start_and_end_to_scan_request(self, tmp_path: pathlib.Path) -> None:
        start, end = 2, 10
        seq = file_sequence.FileSequence(project_events.MacroPath(macro_parser.ParsedMacro(self._TEMPLATE), {}))
        with mock.patch(
            HANDLE_REQUEST_PATH, side_effect=[self._path_success(tmp_path), self._scan_success()]
        ) as mock_handle:
            seq.scan(start=start, end=end)
        scan_request = mock_handle.call_args_list[1][0][0]
        assert isinstance(scan_request, os_events.ScanSequencesRequest)
        assert scan_request.start_number == start
        assert scan_request.end_number == end

    def test_probe_macro_includes_entry_zero(self, tmp_path: pathlib.Path) -> None:
        locked_index = 3
        macro_path = project_events.MacroPath(macro_parser.ParsedMacro(self._TEMPLATE), {"_index": locked_index})
        seq = file_sequence.FileSequence(macro_path)
        with mock.patch(
            HANDLE_REQUEST_PATH, side_effect=[self._path_success(tmp_path), self._scan_success()]
        ) as mock_handle:
            seq.scan()
        path_request = mock_handle.call_args_list[0][0][0]
        assert path_request.variables["entry"] == 0
        assert path_request.variables["_index"] == locked_index


class TestBuildVersionedSequenceDestination:
    """Tests for build_versioned_sequence_destination."""

    def test_first_version_used_when_engine_returns_index_one(self) -> None:
        index_result = os_events.GetNextVersionIndexResultSuccess(result_details="OK", index=1)
        macro = project_events.MacroPath(
            macro_parser.ParsedMacro("{outputs}/renders_v{_index:03}/frame_{entry:04}.exr"), {}
        )

        with mock.patch(HANDLE_REQUEST_PATH, return_value=index_result):
            dest = file_sequence.build_versioned_sequence_destination(macro)

        assert dest._entry_macro.variables["_index"] == 1

    def test_uses_index_returned_by_engine(self) -> None:
        expected_index = 3
        index_result = os_events.GetNextVersionIndexResultSuccess(result_details="OK", index=expected_index)
        macro = project_events.MacroPath(
            macro_parser.ParsedMacro("{outputs}/renders_v{_index:03}/frame_{entry:04}.exr"), {}
        )

        with mock.patch(HANDLE_REQUEST_PATH, return_value=index_result):
            dest = file_sequence.build_versioned_sequence_destination(macro)

        assert dest._entry_macro.variables["_index"] == expected_index

    def test_none_index_treated_as_one(self) -> None:
        index_result = os_events.GetNextVersionIndexResultSuccess(result_details="OK", index=None)
        macro = project_events.MacroPath(
            macro_parser.ParsedMacro("{outputs}/renders_v{_index:03}/frame_{entry:04}.exr"), {}
        )

        with mock.patch(HANDLE_REQUEST_PATH, return_value=index_result):
            dest = file_sequence.build_versioned_sequence_destination(macro)

        assert dest._entry_macro.variables["_index"] == 1

    def test_raises_when_index_request_fails(self) -> None:
        failure = os_events.GetNextVersionIndexResultFailure(
            result_details="Failed to determine next index",
            failure_reason=os_events.FileIOFailureReason.MISSING_MACRO_VARIABLES,
        )
        macro = project_events.MacroPath(
            macro_parser.ParsedMacro("{outputs}/renders_v{_index:03}/frame_{entry:04}.exr"), {}
        )

        with mock.patch(HANDLE_REQUEST_PATH, return_value=failure), pytest.raises(file_sequence.FileSequenceError):
            file_sequence.build_versioned_sequence_destination(macro)

    def test_locks_index_into_returned_destination_variables(self) -> None:
        index_result = os_events.GetNextVersionIndexResultSuccess(result_details="OK", index=1)
        macro = project_events.MacroPath(
            macro_parser.ParsedMacro("{outputs}/seq_v{_index:03}/frame_{entry:04}.exr"), {"extra": "value"}
        )

        with mock.patch(HANDLE_REQUEST_PATH, return_value=index_result):
            dest = file_sequence.build_versioned_sequence_destination(macro)

        assert "_index" in dest._entry_macro.variables
        assert "extra" in dest._entry_macro.variables
        assert "entry" not in dest._entry_macro.variables

    def test_existing_file_policy_forwarded(self) -> None:
        index_result = os_events.GetNextVersionIndexResultSuccess(result_details="OK", index=1)
        macro = project_events.MacroPath(
            macro_parser.ParsedMacro("{outputs}/seq_v{_index:03}/frame_{entry:04}.exr"), {}
        )

        with mock.patch(HANDLE_REQUEST_PATH, return_value=index_result):
            dest = file_sequence.build_versioned_sequence_destination(
                macro, existing_file_policy=os_events.ExistingFilePolicy.FAIL
            )

        assert dest._existing_file_policy == os_events.ExistingFilePolicy.FAIL

    def test_passes_directory_macro_without_entry_variable(self) -> None:
        index_result = os_events.GetNextVersionIndexResultSuccess(result_details="OK", index=1)
        macro = project_events.MacroPath(
            macro_parser.ParsedMacro("{outputs}/seq_v{_index:03}/frame_{entry:04}.exr"), {"extra": "val"}
        )

        with mock.patch(HANDLE_REQUEST_PATH, return_value=index_result) as mock_handle:
            file_sequence.build_versioned_sequence_destination(macro)

        request = mock_handle.call_args[0][0]
        assert isinstance(request, os_events.GetNextVersionIndexRequest)
        assert "entry" not in request.macro_path.variables
