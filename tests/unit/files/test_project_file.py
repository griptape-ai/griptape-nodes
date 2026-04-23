"""Unit tests for ProjectFileDestination."""

from collections.abc import Callable
from pathlib import Path
from unittest.mock import patch

from griptape_nodes.common.project_templates.situation import SituationTemplate
from griptape_nodes.files.project_file import ProjectFileDestination
from griptape_nodes.retained_mode.file_metadata.sidecar_metadata import SidecarContent

HANDLE_REQUEST_PATH = "griptape_nodes.files.project_file.GriptapeNodes.handle_request"


class TestProjectFileDestinationInit:
    """Tests for ProjectFileDestination.__init__() metadata construction."""

    def test_file_metadata_set_when_situation_found(self) -> None:
        """ProjectFileDestination builds SidecarContent when the situation is resolved."""
        from griptape_nodes.common.project_templates.situation import (
            SituationFilePolicy,
            SituationPolicy,
            SituationTemplate,
        )
        from griptape_nodes.retained_mode.events.project_events import GetSituationResultSuccess

        situation = SituationTemplate(
            name="save_node_output",
            macro="{outputs}/{file_name_base}.{file_extension}",
            policy=SituationPolicy(on_collision=SituationFilePolicy.OVERWRITE, create_dirs=True),
        )

        with patch(
            HANDLE_REQUEST_PATH, return_value=GetSituationResultSuccess(situation=situation, result_details="ok")
        ):
            dest = ProjectFileDestination.from_situation("image.png", "save_node_output")

        assert dest._file._file_metadata is not None
        assert isinstance(dest._file._file_metadata, SidecarContent)
        assert dest._file._file_metadata.situation is not None
        assert dest._file._file_metadata.situation.name == "save_node_output"
        assert dest._file._file_metadata.situation.macro == "{outputs}/{file_name_base}.{file_extension}"

    def test_file_metadata_contains_variables(self) -> None:
        """SidecarContent variables include filename parts and extra_vars."""
        from griptape_nodes.common.project_templates.situation import (
            SituationFilePolicy,
            SituationPolicy,
            SituationTemplate,
        )
        from griptape_nodes.retained_mode.events.project_events import GetSituationResultSuccess

        situation = SituationTemplate(
            name="save_node_output",
            macro="{outputs}/{node_name}/{file_name_base}.{file_extension}",
            policy=SituationPolicy(on_collision=SituationFilePolicy.OVERWRITE, create_dirs=True),
        )

        with patch(
            HANDLE_REQUEST_PATH, return_value=GetSituationResultSuccess(situation=situation, result_details="ok")
        ):
            dest = ProjectFileDestination.from_situation("render.png", "save_node_output", node_name="MyNode")

        assert dest._file._file_metadata is not None
        assert dest._file._file_metadata.situation is not None
        assert dest._file._file_metadata.situation.variables is not None
        variables = dest._file._file_metadata.situation.variables
        assert variables["file_name_base"] == "render"
        assert variables["file_extension"] == "png"
        assert variables["node_name"] == "MyNode"

    def test_file_metadata_is_none_when_situation_not_found(self) -> None:
        """file_metadata is None when the situation lookup fails (fallback path)."""
        from griptape_nodes.retained_mode.events.project_events import GetSituationResultFailure

        with patch(HANDLE_REQUEST_PATH, return_value=GetSituationResultFailure(result_details="not found")):
            dest = ProjectFileDestination.from_situation("image.png", "missing_situation")

        assert dest._file._file_metadata is None

    def _make_extension_group_handle_request(
        self,
        situation: SituationTemplate,
        file_extension_groups: dict[str, str],
        macro_resolver: Callable[[object], object] | None = None,
        call_log: list[object] | None = None,
    ) -> Callable[[object], object]:
        """Build a handle_request side_effect that answers situation + current-project lookups.

        The file_extension_group lookup in from_situation calls
        GetCurrentProjectRequest to read the project's taxonomy, so the mock
        has to dispatch by request type instead of the blanket return_value
        the older tests use.

        When a group value contains macro syntax, from_situation also issues a
        GetPathForMacroRequest. Pass ``macro_resolver`` to handle those; omitting
        it asserts no such request is expected (plain-name groups, explicit
        overrides). ``call_log``, if provided, receives every dispatched request
        so tests can assert on request ordering / absence.
        """
        from griptape_nodes.common.project_templates.default_project_template import DEFAULT_PROJECT_TEMPLATE
        from griptape_nodes.common.project_templates.project import ProjectTemplate
        from griptape_nodes.common.project_templates.validation import (
            ProjectValidationInfo,
            ProjectValidationStatus,
        )
        from griptape_nodes.retained_mode.events.project_events import (
            GetCurrentProjectRequest,
            GetCurrentProjectResultSuccess,
            GetPathForMacroRequest,
            GetSituationRequest,
            GetSituationResultSuccess,
        )
        from griptape_nodes.retained_mode.managers.project_manager import ProjectInfo

        template = ProjectTemplate(
            project_template_schema_version=DEFAULT_PROJECT_TEMPLATE.project_template_schema_version,
            name="Test",
            situations={situation.name: situation},
            directories={},
            environment={},
            file_extension_groups=file_extension_groups,
        )
        project_info = ProjectInfo(
            project_id="test",
            project_file_path=None,
            project_base_dir=Path("/tmp/test"),  # noqa: S108
            template=template,
            validation=ProjectValidationInfo(status=ProjectValidationStatus.GOOD),
            parsed_situation_schemas={},
            parsed_directory_schemas={},
        )

        def dispatch(request: object) -> object:
            if call_log is not None:
                call_log.append(request)
            if isinstance(request, GetSituationRequest):
                return GetSituationResultSuccess(situation=situation, result_details="ok")
            if isinstance(request, GetCurrentProjectRequest):
                return GetCurrentProjectResultSuccess(project_info=project_info, result_details="ok")
            if isinstance(request, GetPathForMacroRequest):
                if macro_resolver is None:
                    msg = "Unexpected GetPathForMacroRequest - test did not supply a macro_resolver"
                    raise AssertionError(msg)
                return macro_resolver(request)
            msg = f"Unexpected request type: {type(request).__name__}"
            raise AssertionError(msg)

        return dispatch

    def test_from_situation_file_extension_group_derived_from_extension(self) -> None:
        """Known extensions populate file_extension_group; siblings like png/jpg share a group."""
        from griptape_nodes.common.project_templates.default_project_template import DEFAULT_PROJECT_TEMPLATE
        from griptape_nodes.common.project_templates.situation import (
            SituationFilePolicy,
            SituationPolicy,
            SituationTemplate,
        )

        situation = SituationTemplate(
            name="save_node_output",
            macro="{outputs}/{file_extension_group?:/}{file_name_base}.{file_extension}",
            policy=SituationPolicy(on_collision=SituationFilePolicy.OVERWRITE, create_dirs=True),
        )

        dispatch = self._make_extension_group_handle_request(situation, DEFAULT_PROJECT_TEMPLATE.file_extension_groups)

        with patch(HANDLE_REQUEST_PATH, side_effect=dispatch):
            png_dest = ProjectFileDestination.from_situation("foo.png", "save_node_output")
            jpg_dest = ProjectFileDestination.from_situation("bar.jpg", "save_node_output")

        assert png_dest._file._file_metadata is not None
        assert png_dest._file._file_metadata.situation is not None
        png_vars = png_dest._file._file_metadata.situation.variables
        assert png_vars is not None
        assert png_vars["file_extension_group"] == "images"

        assert jpg_dest._file._file_metadata is not None
        assert jpg_dest._file._file_metadata.situation is not None
        jpg_vars = jpg_dest._file._file_metadata.situation.variables
        assert jpg_vars is not None
        assert jpg_vars["file_extension_group"] == "images"

    def test_from_situation_file_extension_group_unmapped_extension(self) -> None:
        """An extension with no mapping leaves file_extension_group unset so the optional slot degrades."""
        from griptape_nodes.common.project_templates.default_project_template import DEFAULT_PROJECT_TEMPLATE
        from griptape_nodes.common.project_templates.situation import (
            SituationFilePolicy,
            SituationPolicy,
            SituationTemplate,
        )

        situation = SituationTemplate(
            name="save_node_output",
            macro="{outputs}/{file_extension_group?:/}{file_name_base}.{file_extension}",
            policy=SituationPolicy(on_collision=SituationFilePolicy.OVERWRITE, create_dirs=True),
        )

        dispatch = self._make_extension_group_handle_request(situation, DEFAULT_PROJECT_TEMPLATE.file_extension_groups)

        with patch(HANDLE_REQUEST_PATH, side_effect=dispatch):
            dest = ProjectFileDestination.from_situation("foo.xyz", "save_node_output")

        assert dest._file._file_metadata is not None
        assert dest._file._file_metadata.situation is not None
        variables = dest._file._file_metadata.situation.variables
        assert variables is not None
        assert "file_extension_group" not in variables

    def test_from_situation_explicit_file_extension_group_wins_over_extension_derived(self) -> None:
        """An explicit file_extension_group kwarg is not clobbered by the mapping-derived default."""
        from griptape_nodes.common.project_templates.default_project_template import DEFAULT_PROJECT_TEMPLATE
        from griptape_nodes.common.project_templates.situation import (
            SituationFilePolicy,
            SituationPolicy,
            SituationTemplate,
        )

        situation = SituationTemplate(
            name="save_node_output",
            macro="{outputs}/{file_extension_group?:/}{file_name_base}.{file_extension}",
            policy=SituationPolicy(on_collision=SituationFilePolicy.OVERWRITE, create_dirs=True),
        )

        dispatch = self._make_extension_group_handle_request(situation, DEFAULT_PROJECT_TEMPLATE.file_extension_groups)

        with patch(HANDLE_REQUEST_PATH, side_effect=dispatch):
            dest = ProjectFileDestination.from_situation("foo.png", "save_node_output", file_extension_group="custom")

        assert dest._file._file_metadata is not None
        assert dest._file._file_metadata.situation is not None
        variables = dest._file._file_metadata.situation.variables
        assert variables is not None
        assert variables["file_extension_group"] == "custom"

    def test_from_situation_file_extension_group_case_insensitive(self) -> None:
        """Uppercase extensions still map to the same group as their lowercase siblings."""
        from griptape_nodes.common.project_templates.default_project_template import DEFAULT_PROJECT_TEMPLATE
        from griptape_nodes.common.project_templates.situation import (
            SituationFilePolicy,
            SituationPolicy,
            SituationTemplate,
        )

        situation = SituationTemplate(
            name="save_node_output",
            macro="{outputs}/{file_extension_group?:/}{file_name_base}.{file_extension}",
            policy=SituationPolicy(on_collision=SituationFilePolicy.OVERWRITE, create_dirs=True),
        )

        dispatch = self._make_extension_group_handle_request(situation, DEFAULT_PROJECT_TEMPLATE.file_extension_groups)

        with patch(HANDLE_REQUEST_PATH, side_effect=dispatch):
            dest = ProjectFileDestination.from_situation("FOO.PNG", "save_node_output")

        assert dest._file._file_metadata is not None
        assert dest._file._file_metadata.situation is not None
        variables = dest._file._file_metadata.situation.variables
        assert variables is not None
        assert variables["file_extension_group"] == "images"

    def test_from_situation_file_extension_group_uses_project_taxonomy(self) -> None:
        """The mapping comes from the current project's template, not an engine constant."""
        from griptape_nodes.common.project_templates.situation import (
            SituationFilePolicy,
            SituationPolicy,
            SituationTemplate,
        )

        situation = SituationTemplate(
            name="save_node_output",
            macro="{outputs}/{file_extension_group?:/}{file_name_base}.{file_extension}",
            policy=SituationPolicy(on_collision=SituationFilePolicy.OVERWRITE, create_dirs=True),
        )

        # Project supplies its own taxonomy, including a bespoke extension.
        dispatch = self._make_extension_group_handle_request(situation, {"png": "renders", "psd": "renders"})

        with patch(HANDLE_REQUEST_PATH, side_effect=dispatch):
            png_dest = ProjectFileDestination.from_situation("foo.png", "save_node_output")
            psd_dest = ProjectFileDestination.from_situation("bar.psd", "save_node_output")

        assert png_dest._file._file_metadata is not None
        assert png_dest._file._file_metadata.situation is not None
        assert png_dest._file._file_metadata.situation.variables is not None
        assert png_dest._file._file_metadata.situation.variables["file_extension_group"] == "renders"
        assert psd_dest._file._file_metadata is not None
        assert psd_dest._file._file_metadata.situation is not None
        assert psd_dest._file._file_metadata.situation.variables is not None
        assert psd_dest._file._file_metadata.situation.variables["file_extension_group"] == "renders"

    def test_from_situation_file_extension_group_plain_name_skips_resolution(self) -> None:
        """A plain-name group value (no `{`) must not trigger a GetPathForMacroRequest."""
        from griptape_nodes.common.project_templates.situation import (
            SituationFilePolicy,
            SituationPolicy,
            SituationTemplate,
        )
        from griptape_nodes.retained_mode.events.project_events import GetPathForMacroRequest

        situation = SituationTemplate(
            name="save_node_output",
            macro="{outputs}/{file_extension_group?:/}{file_name_base}.{file_extension}",
            policy=SituationPolicy(on_collision=SituationFilePolicy.OVERWRITE, create_dirs=True),
        )

        call_log: list[object] = []
        # No macro_resolver supplied -- if the code issues a GetPathForMacroRequest, the
        # dispatcher raises AssertionError.
        dispatch = self._make_extension_group_handle_request(
            situation, {"png": "images"}, call_log=call_log
        )

        with patch(HANDLE_REQUEST_PATH, side_effect=dispatch):
            dest = ProjectFileDestination.from_situation("foo.png", "save_node_output")

        assert dest._file._file_metadata is not None
        assert dest._file._file_metadata.situation is not None
        assert dest._file._file_metadata.situation.variables is not None
        assert dest._file._file_metadata.situation.variables["file_extension_group"] == "images"
        assert not any(isinstance(req, GetPathForMacroRequest) for req in call_log)

    def test_from_situation_file_extension_group_macro_value_resolves(self) -> None:
        """A group value containing `{...}` is resolved via GetPathForMacroRequest."""
        from griptape_nodes.common.project_templates.situation import (
            SituationFilePolicy,
            SituationPolicy,
            SituationTemplate,
        )
        from griptape_nodes.retained_mode.events.project_events import (
            GetPathForMacroRequest,
            GetPathForMacroResultSuccess,
        )

        situation = SituationTemplate(
            name="save_node_output",
            macro="{file_extension_group?:/}{file_name_base}.{file_extension}",
            policy=SituationPolicy(on_collision=SituationFilePolicy.OVERWRITE, create_dirs=True),
        )

        def macro_resolver(_req: object) -> object:
            return GetPathForMacroResultSuccess(
                resolved_path=Path("outputs/videos"),
                absolute_path=Path("/tmp/test/outputs/videos"),  # noqa: S108
                result_details="ok",
            )

        call_log: list[object] = []
        dispatch = self._make_extension_group_handle_request(
            situation,
            {"mp4": "{outputs}/videos"},
            macro_resolver=macro_resolver,
            call_log=call_log,
        )

        with patch(HANDLE_REQUEST_PATH, side_effect=dispatch):
            dest = ProjectFileDestination.from_situation("clip.mp4", "save_node_output")

        assert dest._file._file_metadata is not None
        assert dest._file._file_metadata.situation is not None
        assert dest._file._file_metadata.situation.variables is not None
        assert dest._file._file_metadata.situation.variables["file_extension_group"] == "outputs/videos"
        assert any(isinstance(req, GetPathForMacroRequest) for req in call_log)

    def test_from_situation_file_extension_group_macro_value_absolute_still_a_string(self) -> None:
        """Absolute resolved group values land in variables verbatim; no bypass of the situation macro."""
        from griptape_nodes.common.project_templates.situation import (
            SituationFilePolicy,
            SituationPolicy,
            SituationTemplate,
        )
        from griptape_nodes.retained_mode.events.project_events import GetPathForMacroResultSuccess

        situation = SituationTemplate(
            name="save_node_output",
            macro="{file_extension_group?:/}{file_name_base}.{file_extension}",
            policy=SituationPolicy(on_collision=SituationFilePolicy.OVERWRITE, create_dirs=True),
        )

        absolute_dir = "/Volumes/share/videos"

        def macro_resolver(_req: object) -> object:
            return GetPathForMacroResultSuccess(
                resolved_path=Path(absolute_dir),
                absolute_path=Path(absolute_dir),
                result_details="ok",
            )

        dispatch = self._make_extension_group_handle_request(
            situation,
            {"mp4": "{workspace_dir}/share/videos"},
            macro_resolver=macro_resolver,
        )

        with patch(HANDLE_REQUEST_PATH, side_effect=dispatch):
            dest = ProjectFileDestination.from_situation("clip.mp4", "save_node_output")

        assert dest._file._file_metadata is not None
        assert dest._file._file_metadata.situation is not None
        assert dest._file._file_metadata.situation.variables is not None
        assert dest._file._file_metadata.situation.variables["file_extension_group"] == absolute_dir
        # Situation macro unchanged -- no engine-side bypass rewriting the template.
        assert dest._file._file_metadata.situation.macro == situation.macro

    def test_from_situation_file_extension_group_resolution_failure_falls_through(self) -> None:
        """Resolution failures leave file_extension_group unset so the optional slot degrades."""
        from griptape_nodes.common.project_templates.situation import (
            SituationFilePolicy,
            SituationPolicy,
            SituationTemplate,
        )
        from griptape_nodes.retained_mode.events.project_events import (
            GetPathForMacroResultFailure,
            PathResolutionFailureReason,
        )

        situation = SituationTemplate(
            name="save_node_output",
            macro="{outputs}/{file_extension_group?:/}{file_name_base}.{file_extension}",
            policy=SituationPolicy(on_collision=SituationFilePolicy.OVERWRITE, create_dirs=True),
        )

        def macro_resolver(_req: object) -> object:
            return GetPathForMacroResultFailure(
                failure_reason=PathResolutionFailureReason.MISSING_REQUIRED_VARIABLES,
                missing_variables={"does_not_exist"},
                result_details="missing variable",
            )

        dispatch = self._make_extension_group_handle_request(
            situation,
            {"mp4": "{does_not_exist}/videos"},
            macro_resolver=macro_resolver,
        )

        with patch(HANDLE_REQUEST_PATH, side_effect=dispatch):
            dest = ProjectFileDestination.from_situation("clip.mp4", "save_node_output")

        assert dest._file._file_metadata is not None
        assert dest._file._file_metadata.situation is not None
        assert dest._file._file_metadata.situation.variables is not None
        assert "file_extension_group" not in dest._file._file_metadata.situation.variables

    def test_from_situation_explicit_file_extension_group_skips_resolution(self) -> None:
        """Explicit caller override wins and never consults the project taxonomy or resolver."""
        from griptape_nodes.common.project_templates.situation import (
            SituationFilePolicy,
            SituationPolicy,
            SituationTemplate,
        )
        from griptape_nodes.retained_mode.events.project_events import (
            GetCurrentProjectRequest,
            GetPathForMacroRequest,
        )

        situation = SituationTemplate(
            name="save_node_output",
            macro="{outputs}/{file_extension_group?:/}{file_name_base}.{file_extension}",
            policy=SituationPolicy(on_collision=SituationFilePolicy.OVERWRITE, create_dirs=True),
        )

        call_log: list[object] = []
        # Even though the taxonomy would need a resolver, we don't supply one --
        # the explicit kwarg must short-circuit before any lookup.
        dispatch = self._make_extension_group_handle_request(
            situation,
            {"mp4": "{outputs}/videos"},
            call_log=call_log,
        )

        with patch(HANDLE_REQUEST_PATH, side_effect=dispatch):
            dest = ProjectFileDestination.from_situation(
                "clip.mp4", "save_node_output", file_extension_group="caller_wins"
            )

        assert dest._file._file_metadata is not None
        assert dest._file._file_metadata.situation is not None
        assert dest._file._file_metadata.situation.variables is not None
        assert dest._file._file_metadata.situation.variables["file_extension_group"] == "caller_wins"
        # Neither the project lookup nor the macro resolver should fire.
        assert not any(isinstance(req, GetCurrentProjectRequest) for req in call_log)
        assert not any(isinstance(req, GetPathForMacroRequest) for req in call_log)

    def test_from_situation_file_extension_group_macro_value_sees_caller_extras(self) -> None:
        """Caller kwargs (node_name, etc.) are in scope for group-value resolution; filename parts are not."""
        from griptape_nodes.common.project_templates.situation import (
            SituationFilePolicy,
            SituationPolicy,
            SituationTemplate,
        )
        from griptape_nodes.retained_mode.events.project_events import (
            GetPathForMacroRequest,
            GetPathForMacroResultSuccess,
        )

        situation = SituationTemplate(
            name="save_node_output",
            macro="{outputs}/{file_extension_group?:/}{file_name_base}.{file_extension}",
            policy=SituationPolicy(on_collision=SituationFilePolicy.OVERWRITE, create_dirs=True),
        )

        captured_requests: list[GetPathForMacroRequest] = []

        def macro_resolver(req: object) -> object:
            assert isinstance(req, GetPathForMacroRequest)
            captured_requests.append(req)
            return GetPathForMacroResultSuccess(
                resolved_path=Path("Save Image/foo"),
                absolute_path=Path("/tmp/test/Save Image/foo"),  # noqa: S108
                result_details="ok",
            )

        dispatch = self._make_extension_group_handle_request(
            situation,
            {"png": "{node_name?:/}foo"},
            macro_resolver=macro_resolver,
        )

        with patch(HANDLE_REQUEST_PATH, side_effect=dispatch):
            dest = ProjectFileDestination.from_situation(
                "render.png", "save_node_output", node_name="Save Image"
            )

        assert dest._file._file_metadata is not None
        assert dest._file._file_metadata.situation is not None
        assert dest._file._file_metadata.situation.variables is not None
        assert dest._file._file_metadata.situation.variables["file_extension_group"] == "Save Image/foo"

        assert len(captured_requests) == 1
        request_vars = captured_requests[0].variables
        assert request_vars["node_name"] == "Save Image"
        assert "file_name_base" not in request_vars
        assert "file_extension" not in request_vars

    def test_file_metadata_policy_matches_situation(self) -> None:
        """SidecarContent.situation.policy mirrors the situation's policy."""
        from griptape_nodes.common.project_templates.situation import (
            SituationFilePolicy,
            SituationPolicy,
            SituationTemplate,
        )
        from griptape_nodes.retained_mode.events.project_events import GetSituationResultSuccess

        situation = SituationTemplate(
            name="save_node_output",
            macro="{outputs}/{file_name_base}.{file_extension}",
            policy=SituationPolicy(on_collision=SituationFilePolicy.CREATE_NEW, create_dirs=False),
        )

        with patch(
            HANDLE_REQUEST_PATH, return_value=GetSituationResultSuccess(situation=situation, result_details="ok")
        ):
            dest = ProjectFileDestination.from_situation("data.json", "save_node_output")

        assert dest._file._file_metadata is not None
        assert dest._file._file_metadata.situation is not None
        assert dest._file._file_metadata.situation.policy is not None
        policy = dest._file._file_metadata.situation.policy
        assert policy.on_collision == SituationFilePolicy.CREATE_NEW
        assert policy.create_dirs is False
