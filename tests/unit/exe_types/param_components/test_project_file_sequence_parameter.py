"""Unit tests for _build_sequence_destination_from_situation."""

from unittest.mock import MagicMock, patch

from griptape_nodes.common.project_templates.situation import (
    SituationFilePolicy,
    SituationPolicy,
    SituationTemplate,
)
from griptape_nodes.exe_types.param_components.project_file_sequence_parameter import (
    _FALLBACK_SEQUENCE_MACRO,
    _build_sequence_destination_from_situation,
)
from griptape_nodes.files.file_sequence import FileSequenceDestination
from griptape_nodes.retained_mode.events.os_events import ExistingFilePolicy
from griptape_nodes.retained_mode.events.project_events import (
    GetSituationResultFailure,
    GetSituationResultSuccess,
)

HANDLE_REQUEST_PATH = (
    "griptape_nodes.exe_types.param_components.project_file_sequence_parameter.GriptapeNodes.handle_request"
)
BUILD_VERSIONED_PATH = (
    "griptape_nodes.exe_types.param_components.project_file_sequence_parameter.build_versioned_sequence_destination"
)

_POLICY_MAP = {
    "CREATE_NEW": SituationFilePolicy.CREATE_NEW,
    "OVERWRITE": SituationFilePolicy.OVERWRITE,
    "FAIL": SituationFilePolicy.FAIL,
}


def _make_situation(
    macro: str,
    on_collision: str = "OVERWRITE",
    *,
    create_dirs: bool = True,
) -> SituationTemplate:
    return SituationTemplate(
        name="test_situation",
        macro=macro,
        policy=SituationPolicy(on_collision=_POLICY_MAP[on_collision], create_dirs=create_dirs),
    )


class TestBuildSequenceDestinationFromSituation:
    """Tests for _build_sequence_destination_from_situation helper."""

    def test_uses_situation_macro(self) -> None:
        situation_macro = (
            "{outputs}/{node_name?:_}{file_name_base}_v{_index:03}/{file_name_base}_{entry:04}.{file_extension}"
        )
        situation = _make_situation(situation_macro)
        success = GetSituationResultSuccess(situation=situation, result_details="ok")
        mock_dest = MagicMock(spec=FileSequenceDestination)

        with (
            patch(HANDLE_REQUEST_PATH, return_value=success),
            patch(BUILD_VERSIONED_PATH, return_value=mock_dest) as mock_build,
        ):
            _build_sequence_destination_from_situation("frame.exr", "save_file_sequence_entry")

        call_args = mock_build.call_args
        macro_path = call_args.args[0]
        assert macro_path.parsed_macro.template == situation_macro

    def test_falls_back_to_default_macro_when_situation_not_found(self) -> None:
        failure = GetSituationResultFailure(result_details="not found")
        mock_dest = MagicMock(spec=FileSequenceDestination)

        with (
            patch(HANDLE_REQUEST_PATH, return_value=failure),
            patch(BUILD_VERSIONED_PATH, return_value=mock_dest) as mock_build,
        ):
            _build_sequence_destination_from_situation("frame.exr", "missing_situation")

        call_args = mock_build.call_args
        macro_path = call_args.args[0]
        assert macro_path.parsed_macro.template == _FALLBACK_SEQUENCE_MACRO

    def test_plain_filename_parsed_into_stem_and_extension(self) -> None:
        situation = _make_situation("{outputs}/{file_name_base}_{entry:04}.{file_extension}")
        success = GetSituationResultSuccess(situation=situation, result_details="ok")
        mock_dest = MagicMock(spec=FileSequenceDestination)

        with (
            patch(HANDLE_REQUEST_PATH, return_value=success),
            patch(BUILD_VERSIONED_PATH, return_value=mock_dest) as mock_build,
        ):
            _build_sequence_destination_from_situation("frame.exr", "save_file_sequence_entry")

        macro_path = mock_build.call_args.args[0]
        assert macro_path.variables["file_name_base"] == "frame"
        assert macro_path.variables["file_extension"] == "exr"

    def test_hash_pattern_filename_converted_before_parsing(self) -> None:
        situation = _make_situation("{outputs}/{file_name_base}_{entry:04}.{file_extension}")
        success = GetSituationResultSuccess(situation=situation, result_details="ok")
        mock_dest = MagicMock(spec=FileSequenceDestination)

        with (
            patch(HANDLE_REQUEST_PATH, return_value=success),
            patch(BUILD_VERSIONED_PATH, return_value=mock_dest) as mock_build,
        ):
            _build_sequence_destination_from_situation("frame_####.exr", "save_file_sequence_entry")

        macro_path = mock_build.call_args.args[0]
        assert macro_path.variables["file_extension"] == "exr"

    def test_extra_vars_forwarded_to_macro(self) -> None:
        situation = _make_situation("{outputs}/{node_name}/{file_name_base}_{entry:04}.{file_extension}")
        success = GetSituationResultSuccess(situation=situation, result_details="ok")
        mock_dest = MagicMock(spec=FileSequenceDestination)

        with (
            patch(HANDLE_REQUEST_PATH, return_value=success),
            patch(BUILD_VERSIONED_PATH, return_value=mock_dest) as mock_build,
        ):
            _build_sequence_destination_from_situation("frame.exr", "save_file_sequence_entry", node_name="MyNode")

        macro_path = mock_build.call_args.args[0]
        assert macro_path.variables["node_name"] == "MyNode"

    def test_situation_overwrite_policy_forwarded(self) -> None:
        situation = _make_situation("{outputs}/{entry:04}.exr", on_collision="OVERWRITE")
        success = GetSituationResultSuccess(situation=situation, result_details="ok")
        mock_dest = MagicMock(spec=FileSequenceDestination)

        with (
            patch(HANDLE_REQUEST_PATH, return_value=success),
            patch(BUILD_VERSIONED_PATH, return_value=mock_dest) as mock_build,
        ):
            _build_sequence_destination_from_situation("frame.exr", "save_file_sequence_entry")

        call_kwargs = mock_build.call_args.kwargs
        assert call_kwargs["existing_file_policy"] == ExistingFilePolicy.OVERWRITE

    def test_situation_create_dirs_forwarded(self) -> None:
        situation = _make_situation("{outputs}/{entry:04}.exr", create_dirs=False)
        success = GetSituationResultSuccess(situation=situation, result_details="ok")
        mock_dest = MagicMock(spec=FileSequenceDestination)

        with (
            patch(HANDLE_REQUEST_PATH, return_value=success),
            patch(BUILD_VERSIONED_PATH, return_value=mock_dest) as mock_build,
        ):
            _build_sequence_destination_from_situation("frame.exr", "save_file_sequence_entry")

        call_kwargs = mock_build.call_args.kwargs
        assert call_kwargs["create_parents"] is False

    def test_fallback_uses_overwrite_policy(self) -> None:
        failure = GetSituationResultFailure(result_details="not found")
        mock_dest = MagicMock(spec=FileSequenceDestination)

        with (
            patch(HANDLE_REQUEST_PATH, return_value=failure),
            patch(BUILD_VERSIONED_PATH, return_value=mock_dest) as mock_build,
        ):
            _build_sequence_destination_from_situation("frame.exr", "missing_situation")

        call_kwargs = mock_build.call_args.kwargs
        assert call_kwargs["existing_file_policy"] == ExistingFilePolicy.OVERWRITE

    def test_returns_file_sequence_destination(self) -> None:
        situation = _make_situation("{outputs}/{entry:04}.exr")
        success = GetSituationResultSuccess(situation=situation, result_details="ok")
        mock_dest = MagicMock(spec=FileSequenceDestination)

        with patch(HANDLE_REQUEST_PATH, return_value=success), patch(BUILD_VERSIONED_PATH, return_value=mock_dest):
            result = _build_sequence_destination_from_situation("frame.exr", "save_file_sequence_entry")

        assert result is mock_dest

    def test_multiple_extra_vars_all_forwarded(self) -> None:
        situation = _make_situation("{outputs}/{file_name_base}_{entry:04}.{file_extension}")
        success = GetSituationResultSuccess(situation=situation, result_details="ok")
        mock_dest = MagicMock(spec=FileSequenceDestination)

        with (
            patch(HANDLE_REQUEST_PATH, return_value=success),
            patch(BUILD_VERSIONED_PATH, return_value=mock_dest) as mock_build,
        ):
            _build_sequence_destination_from_situation(
                "render.exr",
                "save_file_sequence_entry",
                node_name="Renderer",
                sub_dirs="pass_1",
            )

        macro_path = mock_build.call_args.args[0]
        assert macro_path.variables["node_name"] == "Renderer"
        assert macro_path.variables["sub_dirs"] == "pass_1"
        assert macro_path.variables["file_name_base"] == "render"
        assert macro_path.variables["file_extension"] == "exr"
