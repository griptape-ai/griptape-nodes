"""Unit tests for ProjectFileDestination."""

from pathlib import Path
from unittest.mock import patch

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

    def test_from_situation_absolute_filename_bypasses_macro(self, tmp_path: Path) -> None:
        """An absolute filename is honored verbatim rather than routed through the situation macro."""
        from griptape_nodes.common.project_templates.situation import (
            SituationFilePolicy,
            SituationPolicy,
            SituationTemplate,
        )
        from griptape_nodes.retained_mode.events.project_events import GetSituationResultSuccess

        situation = SituationTemplate(
            name="save_node_output",
            macro="{outputs}/{sub_dirs?:/}{file_name_base}.{file_extension}",
            policy=SituationPolicy(on_collision=SituationFilePolicy.OVERWRITE, create_dirs=True),
        )

        absolute_filename = str(tmp_path / "foo" / "bar" / "output.png")

        with patch(
            HANDLE_REQUEST_PATH, return_value=GetSituationResultSuccess(situation=situation, result_details="ok")
        ):
            dest = ProjectFileDestination.from_situation(absolute_filename, "save_node_output")

        # The resolved path should be the absolute path as-is, not routed under {outputs}.
        assert dest._file.location == absolute_filename
        # No sidecar metadata: the situation macro+variables don't re-resolve to
        # the absolute path we honored verbatim, so recording them would be a lie.
        assert dest._file._file_metadata is None

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
