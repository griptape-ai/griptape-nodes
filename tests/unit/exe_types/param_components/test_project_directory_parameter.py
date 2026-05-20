"""Unit tests for _build_directory_destination_from_situation."""

from unittest.mock import patch

from griptape_nodes.common.project_templates.situation import (
    SituationFilePolicy,
    SituationPolicy,
    SituationTemplate,
)
from griptape_nodes.exe_types.param_components.project_directory_parameter import (
    _FALLBACK_DIRECTORY_MACRO,
    _build_directory_destination_from_situation,
)
from griptape_nodes.files.directory import DirectoryDestination
from griptape_nodes.retained_mode.events.os_events import ExistingFilePolicy
from griptape_nodes.retained_mode.events.project_events import (
    GetSituationResultFailure,
    GetSituationResultSuccess,
    MacroPath,
)

HANDLE_REQUEST_PATH = (
    "griptape_nodes.exe_types.param_components.project_directory_parameter.GriptapeNodes.handle_request"
)

_POLICY_MAP = {
    "CREATE_NEW": SituationFilePolicy.CREATE_NEW,
    "OVERWRITE": SituationFilePolicy.OVERWRITE,
    "FAIL": SituationFilePolicy.FAIL,
}


def _make_situation(
    macro: str,
    on_collision: str = "CREATE_NEW",
    *,
    create_dirs: bool = True,
) -> SituationTemplate:
    return SituationTemplate(
        name="test_situation",
        macro=macro,
        policy=SituationPolicy(on_collision=_POLICY_MAP[on_collision], create_dirs=create_dirs),
    )


class TestBuildDirectoryDestinationFromSituation:
    """Tests for _build_directory_destination_from_situation helper."""

    def test_uses_situation_macro(self) -> None:
        situation = _make_situation("{outputs}/{node_name}/{dir_name}_v{_index:03}")
        success = GetSituationResultSuccess(situation=situation, result_details="ok")

        with patch(HANDLE_REQUEST_PATH, return_value=success):
            dest = _build_directory_destination_from_situation("renders", "save_output_directory")

        assert isinstance(dest, DirectoryDestination)
        assert isinstance(dest._dir_path, MacroPath)
        assert dest._dir_path.parsed_macro.template == "{outputs}/{node_name}/{dir_name}_v{_index:03}"

    def test_falls_back_to_default_macro_when_situation_not_found(self) -> None:
        failure = GetSituationResultFailure(result_details="not found")

        with patch(HANDLE_REQUEST_PATH, return_value=failure):
            dest = _build_directory_destination_from_situation("renders", "missing_situation")

        assert isinstance(dest._dir_path, MacroPath)
        assert dest._dir_path.parsed_macro.template == _FALLBACK_DIRECTORY_MACRO

    def test_wires_dirname_as_macro_variable(self) -> None:
        situation = _make_situation("{outputs}/{dir_name}_v{_index:03}")
        success = GetSituationResultSuccess(situation=situation, result_details="ok")

        with patch(HANDLE_REQUEST_PATH, return_value=success):
            dest = _build_directory_destination_from_situation("frames", "save_output_directory")

        assert isinstance(dest._dir_path, MacroPath)
        assert dest._dir_path.variables["dir_name"] == "frames"

    def test_extra_vars_forwarded_to_macro(self) -> None:
        situation = _make_situation("{outputs}/{node_name}/{dir_name}_v{_index:03}")
        success = GetSituationResultSuccess(situation=situation, result_details="ok")

        with patch(HANDLE_REQUEST_PATH, return_value=success):
            dest = _build_directory_destination_from_situation("renders", "save_output_directory", node_name="MyNode")

        assert isinstance(dest._dir_path, MacroPath)
        assert dest._dir_path.variables["node_name"] == "MyNode"

    def test_situation_overwrite_policy_maps_to_overwrite(self) -> None:
        situation = _make_situation("{outputs}/{dir_name}", on_collision="OVERWRITE")
        success = GetSituationResultSuccess(situation=situation, result_details="ok")

        with patch(HANDLE_REQUEST_PATH, return_value=success):
            dest = _build_directory_destination_from_situation("renders", "save_output_directory")

        assert dest._existing_dir_policy == ExistingFilePolicy.OVERWRITE

    def test_situation_create_new_policy_maps_to_create_new(self) -> None:
        situation = _make_situation("{outputs}/{dir_name}", on_collision="CREATE_NEW")
        success = GetSituationResultSuccess(situation=situation, result_details="ok")

        with patch(HANDLE_REQUEST_PATH, return_value=success):
            dest = _build_directory_destination_from_situation("renders", "save_output_directory")

        assert dest._existing_dir_policy == ExistingFilePolicy.CREATE_NEW

    def test_situation_fail_policy_maps_to_fail(self) -> None:
        situation = _make_situation("{outputs}/{dir_name}", on_collision="FAIL")
        success = GetSituationResultSuccess(situation=situation, result_details="ok")

        with patch(HANDLE_REQUEST_PATH, return_value=success):
            dest = _build_directory_destination_from_situation("renders", "save_output_directory")

        assert dest._existing_dir_policy == ExistingFilePolicy.FAIL

    def test_situation_create_dirs_false_propagated(self) -> None:
        situation = _make_situation("{outputs}/{dir_name}", create_dirs=False)
        success = GetSituationResultSuccess(situation=situation, result_details="ok")

        with patch(HANDLE_REQUEST_PATH, return_value=success):
            dest = _build_directory_destination_from_situation("renders", "save_output_directory")

        assert dest._create_parents is False

    def test_fallback_uses_create_new_policy(self) -> None:
        failure = GetSituationResultFailure(result_details="not found")

        with patch(HANDLE_REQUEST_PATH, return_value=failure):
            dest = _build_directory_destination_from_situation("renders", "missing_situation")

        assert dest._existing_dir_policy == ExistingFilePolicy.CREATE_NEW

    def test_multiple_extra_vars_all_forwarded(self) -> None:
        situation = _make_situation("{outputs}/{dir_name}")
        success = GetSituationResultSuccess(situation=situation, result_details="ok")

        with patch(HANDLE_REQUEST_PATH, return_value=success):
            dest = _build_directory_destination_from_situation(
                "renders",
                "save_output_directory",
                node_name="MyNode",
                sub_dirs="pass_1",
            )

        assert isinstance(dest._dir_path, MacroPath)
        assert dest._dir_path.variables["node_name"] == "MyNode"
        assert dest._dir_path.variables["sub_dirs"] == "pass_1"
        assert dest._dir_path.variables["dir_name"] == "renders"

    def test_returns_directory_destination(self) -> None:
        situation = _make_situation("{outputs}/{dir_name}")
        success = GetSituationResultSuccess(situation=situation, result_details="ok")

        with patch(HANDLE_REQUEST_PATH, return_value=success):
            dest = _build_directory_destination_from_situation("renders", "save_output_directory")

        assert isinstance(dest, DirectoryDestination)
