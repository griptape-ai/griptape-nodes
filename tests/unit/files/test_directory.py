"""Unit tests for Directory and DirectoryDestination."""

from pathlib import Path
from unittest.mock import patch

import pytest

from griptape_nodes.common.macro_parser import MacroSyntaxError, ParsedMacro
from griptape_nodes.files.directory import Directory, DirectoryDestination, DirectoryError
from griptape_nodes.retained_mode.events.os_events import ExistingFilePolicy
from griptape_nodes.retained_mode.events.project_events import (
    AttemptMapAbsolutePathToProjectResultSuccess,
    GetPathForMacroResultFailure,
    GetPathForMacroResultSuccess,
    MacroPath,
    PathResolutionFailureReason,
)

HANDLE_REQUEST_PATH = "griptape_nodes.files.directory.GriptapeNodes.handle_request"


class TestDirectoryConstructor:
    """Tests that Directory constructor stores references without I/O."""

    def test_stores_plain_string(self) -> None:
        d = Directory("workspace/renders")
        assert d._dir_path == "workspace/renders"

    def test_does_no_io(self) -> None:
        with patch(HANDLE_REQUEST_PATH) as mock_handle:
            Directory("workspace/renders")
        mock_handle.assert_not_called()

    def test_auto_wraps_macro_string_in_macro_path(self) -> None:
        d = Directory("{outputs}/frames")
        assert isinstance(d._dir_path, MacroPath)
        assert d._dir_path.variables == {}

    def test_keeps_plain_string_without_vars_unchanged(self) -> None:
        d = Directory("workspace/frames")
        assert d._dir_path == "workspace/frames"

    def test_stores_macro_path_unchanged(self) -> None:
        macro_path = MacroPath(ParsedMacro("{outputs}/renders"), {"outputs": "/resolved"})
        d = Directory(macro_path)
        assert d._dir_path is macro_path

    def test_invalid_macro_syntax_stored_as_plain_string(self) -> None:
        with patch("griptape_nodes.files.directory.ParsedMacro", side_effect=MacroSyntaxError("bad")):
            d = Directory("{unclosed")
        assert d._dir_path == "{unclosed"

    def test_macro_string_preserves_template(self) -> None:
        d = Directory("{outputs}/renders_v001")
        assert isinstance(d._dir_path, MacroPath)
        assert d._dir_path.parsed_macro.template == "{outputs}/renders_v001"


class TestDirectoryResolve:
    """Tests for Directory.resolve()."""

    def test_resolve_plain_string_returns_path(self, tmp_path: Path) -> None:
        dir_path = str(tmp_path / "renders")
        d = Directory(dir_path)
        with patch(HANDLE_REQUEST_PATH) as mock_handle:
            result = d.resolve()
        mock_handle.assert_not_called()
        assert result == Path(dir_path)

    def test_resolve_macro_path_calls_handle_request(self) -> None:
        macro_path = MacroPath(ParsedMacro("{outputs}/renders"), {"outputs": "/workspace/outputs"})
        resolve_result = GetPathForMacroResultSuccess(
            result_details="OK",
            resolved_path=Path("outputs/renders"),
            absolute_path=Path("/workspace/outputs/renders"),
        )
        with patch(HANDLE_REQUEST_PATH, return_value=resolve_result):
            result = Directory(macro_path).resolve()
        assert result == Path("/workspace/outputs/renders")

    def test_resolve_macro_path_failure_raises_directory_error(self) -> None:
        macro_path = MacroPath(ParsedMacro("{outputs}/renders"), {})
        failure = GetPathForMacroResultFailure(
            result_details="Missing variables: outputs",
            failure_reason=PathResolutionFailureReason.MISSING_REQUIRED_VARIABLES,
            missing_variables={"outputs"},
        )
        with patch(HANDLE_REQUEST_PATH, return_value=failure), pytest.raises(DirectoryError):
            Directory(macro_path).resolve()


class TestDirectoryLocation:
    """Tests for Directory.location property."""

    def test_location_plain_string(self) -> None:
        d = Directory("workspace/renders")
        assert d.location == "workspace/renders"

    def test_location_macro_path_returns_template(self) -> None:
        d = Directory("{outputs}/renders")
        assert d.location == "{outputs}/renders"

    def test_location_macro_path_object_returns_template(self) -> None:
        macro_path = MacroPath(ParsedMacro("{outputs}/renders"), {"outputs": "/resolved"})
        d = Directory(macro_path)
        assert d.location == "{outputs}/renders"

    def test_location_no_io_performed(self) -> None:
        with patch(HANDLE_REQUEST_PATH) as mock_handle:
            d = Directory("{outputs}/renders")
            _ = d.location
        mock_handle.assert_not_called()


class TestDirectoryName:
    """Tests for Directory.name property."""

    def test_name_plain_string(self) -> None:
        d = Directory("workspace/renders")
        assert d.name == "renders"

    def test_name_macro_template(self) -> None:
        d = Directory("{outputs}/renders_v001")
        assert d.name == "renders_v001"

    def test_name_nested_path(self) -> None:
        d = Directory("workspace/project/outputs/frames")
        assert d.name == "frames"


class TestDirectoryDestinationConstructor:
    """Tests for DirectoryDestination constructor."""

    def test_does_no_io(self) -> None:
        with patch(HANDLE_REQUEST_PATH) as mock_handle:
            DirectoryDestination("workspace/renders")
        mock_handle.assert_not_called()

    def test_defaults_create_new_and_create_parents(self) -> None:
        dest = DirectoryDestination("workspace/renders")
        assert dest._existing_dir_policy == ExistingFilePolicy.CREATE_NEW
        assert dest._create_parents is True

    def test_stores_overwrite_policy(self) -> None:
        dest = DirectoryDestination("workspace/renders", existing_dir_policy=ExistingFilePolicy.OVERWRITE)
        assert dest._existing_dir_policy == ExistingFilePolicy.OVERWRITE

    def test_stores_create_parents_false(self) -> None:
        dest = DirectoryDestination("workspace/renders", create_parents=False)
        assert dest._create_parents is False


class TestDirectoryDestinationCreateDirect:
    """Tests for DirectoryDestination.create() in non-versioning (direct) mode."""

    def test_create_plain_string_creates_directory(self, tmp_path: Path) -> None:
        dir_path = str(tmp_path / "renders")
        map_result = AttemptMapAbsolutePathToProjectResultSuccess(result_details="OK", mapped_path=None)
        dest = DirectoryDestination(dir_path, existing_dir_policy=ExistingFilePolicy.OVERWRITE)
        with patch(HANDLE_REQUEST_PATH, return_value=map_result):
            directory = dest.create()
        assert (tmp_path / "renders").is_dir()
        assert directory.resolve() == tmp_path / "renders"

    def test_create_overwrite_existing_dir_succeeds(self, tmp_path: Path) -> None:
        existing = tmp_path / "renders"
        existing.mkdir()
        map_result = AttemptMapAbsolutePathToProjectResultSuccess(result_details="OK", mapped_path=None)
        dest = DirectoryDestination(str(existing), existing_dir_policy=ExistingFilePolicy.OVERWRITE)
        with patch(HANDLE_REQUEST_PATH, return_value=map_result):
            directory = dest.create()
        assert existing.is_dir()
        assert directory.resolve() == existing

    def test_create_fail_policy_on_existing_raises(self, tmp_path: Path) -> None:
        existing = tmp_path / "renders"
        existing.mkdir()
        dest = DirectoryDestination(str(existing), existing_dir_policy=ExistingFilePolicy.FAIL)
        with patch(HANDLE_REQUEST_PATH) as mock_handle, pytest.raises(DirectoryError):
            dest.create()
        mock_handle.assert_not_called()

    def test_create_returns_directory_with_absolute_location(self, tmp_path: Path) -> None:
        dir_path = str(tmp_path / "output")
        map_result = AttemptMapAbsolutePathToProjectResultSuccess(result_details="OK", mapped_path=None)
        dest = DirectoryDestination(dir_path, existing_dir_policy=ExistingFilePolicy.OVERWRITE)
        with patch(HANDLE_REQUEST_PATH, return_value=map_result):
            directory = dest.create()
        assert Path(directory.location).is_absolute()

    def test_create_returns_directory_with_mapped_macro_when_inside_project(self, tmp_path: Path) -> None:
        dir_path = str(tmp_path / "renders")
        map_result = AttemptMapAbsolutePathToProjectResultSuccess(
            result_details="OK",
            mapped_path="{outputs}/renders",
        )
        dest = DirectoryDestination(dir_path, existing_dir_policy=ExistingFilePolicy.OVERWRITE)
        with patch(HANDLE_REQUEST_PATH, return_value=map_result):
            directory = dest.create()
        assert directory.location == "{outputs}/renders"


class TestDirectoryDestinationCreateVersioning:
    """Tests for DirectoryDestination.create() in versioning (CREATE_NEW + MacroPath) mode."""

    def test_versioning_first_available_used(self, tmp_path: Path) -> None:
        missing_dir = tmp_path / "renders_v001"

        resolve_result = GetPathForMacroResultSuccess(
            result_details="OK",
            resolved_path=Path("renders_v001"),
            absolute_path=missing_dir,
        )
        map_result = AttemptMapAbsolutePathToProjectResultSuccess(result_details="OK", mapped_path=None)

        macro_path = MacroPath(ParsedMacro("{outputs}/renders_v{_index:03}"), {})
        dest = DirectoryDestination(macro_path, existing_dir_policy=ExistingFilePolicy.CREATE_NEW)

        with patch(HANDLE_REQUEST_PATH, side_effect=[resolve_result, map_result]):
            directory = dest.create()

        assert missing_dir.is_dir()
        assert directory.location == "{outputs}/renders_v{_index:03}"

    def test_versioning_increments_index_when_first_taken(self, tmp_path: Path) -> None:
        existing_dir = tmp_path / "renders_v001"
        existing_dir.mkdir()
        missing_dir = tmp_path / "renders_v002"

        resolve_result_1 = GetPathForMacroResultSuccess(
            result_details="OK",
            resolved_path=Path("renders_v001"),
            absolute_path=existing_dir,
        )
        resolve_result_2 = GetPathForMacroResultSuccess(
            result_details="OK",
            resolved_path=Path("renders_v002"),
            absolute_path=missing_dir,
        )
        map_result = AttemptMapAbsolutePathToProjectResultSuccess(result_details="OK", mapped_path=None)

        macro_path = MacroPath(ParsedMacro("{outputs}/renders_v{_index:03}"), {})
        dest = DirectoryDestination(macro_path, existing_dir_policy=ExistingFilePolicy.CREATE_NEW)

        with patch(HANDLE_REQUEST_PATH, side_effect=[resolve_result_1, resolve_result_2, map_result]):
            directory = dest.create()

        assert missing_dir.is_dir()
        assert directory.location == "{outputs}/renders_v{_index:03}"

    def test_versioning_handle_request_failure_raises_directory_error(self) -> None:
        failure = GetPathForMacroResultFailure(
            result_details="Macro resolution failed",
            failure_reason=PathResolutionFailureReason.MISSING_REQUIRED_VARIABLES,
            missing_variables={"outputs"},
        )
        macro_path = MacroPath(ParsedMacro("{outputs}/renders_v{_index:03}"), {})
        dest = DirectoryDestination(macro_path, existing_dir_policy=ExistingFilePolicy.CREATE_NEW)

        with patch(HANDLE_REQUEST_PATH, return_value=failure), pytest.raises(DirectoryError):
            dest.create()

    def test_versioning_all_indexes_exhausted_raises(self, tmp_path: Path) -> None:
        # tmp_path always exists, so every probe returns an already-existing directory.
        resolve_result = GetPathForMacroResultSuccess(
            result_details="OK",
            resolved_path=Path("renders_v001"),
            absolute_path=tmp_path,
        )
        macro_path = MacroPath(ParsedMacro("{outputs}/renders_v{_index:03}"), {})
        dest = DirectoryDestination(macro_path, existing_dir_policy=ExistingFilePolicy.CREATE_NEW)

        with (
            patch(HANDLE_REQUEST_PATH, return_value=resolve_result),
            patch("griptape_nodes.files.directory._MAX_VERSION_INDEX", 3),
            pytest.raises(DirectoryError),
        ):
            dest.create()
