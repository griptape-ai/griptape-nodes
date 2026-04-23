"""Tests for ProjectManager macro event handlers."""

import logging
import os
from pathlib import Path
from typing import cast
from unittest.mock import Mock, patch

import pytest

from griptape_nodes.common.macro_parser import MacroMatchFailureReason
from griptape_nodes.common.project_templates import ProjectTemplate
from griptape_nodes.retained_mode.events.project_events import (
    AttemptMapAbsolutePathToProjectRequest,
    AttemptMapAbsolutePathToProjectResultSuccess,
    AttemptMatchPathAgainstMacroRequest,
    AttemptMatchPathAgainstMacroResultSuccess,
    GetPathForMacroRequest,
    GetPathForMacroResultFailure,
    GetPathForMacroResultSuccess,
    GetStateForMacroRequest,
    GetStateForMacroResultFailure,
    GetStateForMacroResultSuccess,
    PathResolutionFailureReason,
)
from griptape_nodes.retained_mode.managers.project_manager import ProjectManager


class TestProjectManagerMacroHandlers:
    """Test ProjectManager macro-related event handlers."""

    @pytest.fixture
    def project_manager(self) -> ProjectManager:
        """Create a ProjectManager instance for testing."""
        mock_config = Mock()
        mock_secrets = Mock()
        mock_event_manager = Mock()
        return ProjectManager(mock_event_manager, mock_config, mock_secrets)

    def test_match_path_against_macro_success(self, project_manager: ProjectManager) -> None:
        """Test AttemptMatchPathAgainstMacro successfully matches path."""
        from griptape_nodes.common.macro_parser import ParsedMacro

        parsed_macro = ParsedMacro("{inputs}/{file_name}.{ext}")

        request = AttemptMatchPathAgainstMacroRequest(
            parsed_macro=parsed_macro,
            file_path="inputs/render.png",
            known_variables={"inputs": "inputs"},
        )

        result = project_manager.on_match_path_against_macro_request(request)

        assert isinstance(result, AttemptMatchPathAgainstMacroResultSuccess)
        assert result.match_failure is None
        assert result.extracted_variables == {"inputs": "inputs", "file_name": "render", "ext": "png"}

    def test_match_path_mismatch(self, project_manager: ProjectManager) -> None:
        """Test that AttemptMatchPathAgainstMacro returns success with match_failure when path doesn't match."""
        from griptape_nodes.common.macro_parser import ParsedMacro

        known_vars: dict[str, str | int] = {"inputs": "outputs", "ext": "png"}
        parsed_macro = ParsedMacro("{inputs}/{file_name}.{ext}")

        request = AttemptMatchPathAgainstMacroRequest(
            parsed_macro=parsed_macro,
            file_path="wrong_folder/render.png",
            known_variables=known_vars,
        )

        result = project_manager.on_match_path_against_macro_request(request)

        assert isinstance(result, AttemptMatchPathAgainstMacroResultSuccess)
        assert result.match_failure is not None
        assert result.extracted_variables is None
        assert result.match_failure.failure_reason == MacroMatchFailureReason.STATIC_TEXT_MISMATCH
        assert result.match_failure.known_variables_used == known_vars

    def test_match_path_empty_known_variables(self, project_manager: ProjectManager) -> None:
        """Test AttemptMatchPathAgainstMacro with empty known_variables."""
        from griptape_nodes.common.macro_parser import ParsedMacro

        parsed_macro = ParsedMacro("{file_name}")

        request = AttemptMatchPathAgainstMacroRequest(
            parsed_macro=parsed_macro,
            file_path="test.txt",
            known_variables={},
        )

        result = project_manager.on_match_path_against_macro_request(request)

        assert isinstance(result, AttemptMatchPathAgainstMacroResultSuccess)
        assert result.match_failure is None
        assert result.extracted_variables == {"file_name": "test.txt"}


class TestProjectManagerInitialization:
    """Test ProjectManager initialization and state."""

    def test_project_manager_initializes_empty(self) -> None:
        """Test ProjectManager starts with empty state."""
        mock_config = Mock()
        mock_secrets = Mock()
        mock_event_manager = Mock()

        pm = ProjectManager(mock_event_manager, mock_config, mock_secrets)

        assert pm._registered_template_status == {}
        assert pm._successfully_loaded_project_templates == {}
        assert pm._current_project_id is None

    def test_project_manager_stores_manager_references(self) -> None:
        """Test ProjectManager stores config and secrets manager references."""
        mock_config = Mock()
        mock_secrets = Mock()
        mock_event_manager = Mock()

        pm = ProjectManager(mock_event_manager, mock_config, mock_secrets)

        assert pm._config_manager is mock_config
        assert pm._secrets_manager is mock_secrets


class TestProjectManagerBuiltinVariables:
    """Test ProjectManager builtin variable resolution."""

    @pytest.fixture
    def project_manager_with_template(self) -> ProjectManager:
        """Create a ProjectManager with system defaults loaded."""
        from griptape_nodes.common.project_templates import ProjectValidationInfo, ProjectValidationStatus
        from griptape_nodes.common.project_templates.default_project_template import DEFAULT_PROJECT_TEMPLATE
        from griptape_nodes.retained_mode.managers.project_manager import ProjectInfo

        mock_config = Mock()
        mock_config.workspace_path = Path("/workspace")
        mock_secrets = Mock()
        mock_event_manager = Mock()
        pm = ProjectManager(mock_event_manager, mock_config, mock_secrets)

        project_path = Path("/test/project.yml")
        project_id = str(project_path)

        # Parse macros first
        validation = ProjectValidationInfo(status=ProjectValidationStatus.GOOD)
        situation_schemas = pm._parse_situation_macros(DEFAULT_PROJECT_TEMPLATE.situations, validation)
        directory_schemas = pm._parse_directory_macros(DEFAULT_PROJECT_TEMPLATE.directories, validation)

        # Create ProjectInfo with fully populated caches
        project_info = ProjectInfo(
            project_id=project_id,
            project_file_path=project_path,
            project_base_dir=project_path.parent,
            template=DEFAULT_PROJECT_TEMPLATE,
            validation=validation,
            parsed_situation_schemas=situation_schemas,
            parsed_directory_schemas=directory_schemas,
        )

        # Set up new consolidated dict
        pm._successfully_loaded_project_templates[project_id] = project_info
        pm._current_project_id = project_id

        return pm

    def test_builtin_project_dir_resolves_correctly(self, project_manager_with_template: ProjectManager) -> None:
        """Test that {project_dir} builtin resolves to project_path.parent."""
        from griptape_nodes.common.macro_parser import ParsedMacro

        parsed_macro = ParsedMacro("{project_dir}/output.txt")

        request = GetPathForMacroRequest(parsed_macro=parsed_macro, variables={})

        result = project_manager_with_template.on_get_path_for_macro_request(request)

        assert isinstance(result, GetPathForMacroResultSuccess)
        assert result.resolved_path == Path("/test/output.txt")

    def test_builtin_workspace_dir_resolves_correctly(self, project_manager_with_template: ProjectManager) -> None:
        """Test that {workspace_dir} builtin resolves from ConfigManager."""
        from griptape_nodes.common.macro_parser import ParsedMacro

        cast("Mock", project_manager_with_template._config_manager).workspace_path = Path("/workspace")

        parsed_macro = ParsedMacro("{workspace_dir}/output.txt")

        request = GetPathForMacroRequest(parsed_macro=parsed_macro, variables={})

        result = project_manager_with_template.on_get_path_for_macro_request(request)

        assert isinstance(result, GetPathForMacroResultSuccess)
        assert result.resolved_path == Path("/workspace/output.txt")

    @patch("griptape_nodes.retained_mode.managers.project_manager.GriptapeNodes")
    def test_builtin_workflow_name_resolves_correctly(
        self, mock_griptape_nodes: Mock, project_manager_with_template: ProjectManager
    ) -> None:
        """Test that {workflow_name} builtin resolves from ContextManager."""
        from griptape_nodes.common.macro_parser import ParsedMacro

        cast("Mock", project_manager_with_template._config_manager).workspace_path = Path("/workspace")

        mock_context_manager = Mock()
        mock_context_manager.has_current_workflow.return_value = True
        mock_context_manager.get_current_workflow_name.return_value = "my_workflow"
        mock_griptape_nodes.ContextManager.return_value = mock_context_manager

        parsed_macro = ParsedMacro("{workflow_name}_output.txt")

        request = GetPathForMacroRequest(parsed_macro=parsed_macro, variables={})

        result = project_manager_with_template.on_get_path_for_macro_request(request)

        assert isinstance(result, GetPathForMacroResultSuccess)
        assert result.resolved_path == Path("my_workflow_output.txt")
        mock_context_manager.has_current_workflow.assert_called_once()
        mock_context_manager.get_current_workflow_name.assert_called_once()

    @patch("griptape_nodes.retained_mode.managers.project_manager.GriptapeNodes")
    def test_builtin_workflow_name_no_current_workflow(
        self, mock_griptape_nodes: Mock, project_manager_with_template: ProjectManager
    ) -> None:
        """Test that {workflow_name} raises RuntimeError when no current workflow."""
        from griptape_nodes.common.macro_parser import ParsedMacro

        mock_context_manager = Mock()
        mock_context_manager.has_current_workflow.return_value = False
        mock_griptape_nodes.ContextManager.return_value = mock_context_manager

        parsed_macro = ParsedMacro("{workflow_name}_output.txt")

        request = GetPathForMacroRequest(parsed_macro=parsed_macro, variables={})

        result = project_manager_with_template.on_get_path_for_macro_request(request)

        assert isinstance(result, GetPathForMacroResultFailure)
        assert result.failure_reason == PathResolutionFailureReason.MACRO_RESOLUTION_ERROR
        from griptape_nodes.retained_mode.events.base_events import ResultDetails

        assert isinstance(result.result_details, ResultDetails)
        assert "No current workflow" in str(result.result_details)

    def test_builtin_project_name_not_implemented(self, project_manager_with_template: ProjectManager) -> None:
        """Test that {project_name} raises NotImplementedError."""
        from griptape_nodes.common.macro_parser import ParsedMacro

        parsed_macro = ParsedMacro("{project_name}/output.txt")

        request = GetPathForMacroRequest(parsed_macro=parsed_macro, variables={})

        result = project_manager_with_template.on_get_path_for_macro_request(request)

        assert isinstance(result, GetPathForMacroResultFailure)
        assert result.failure_reason == PathResolutionFailureReason.MACRO_RESOLUTION_ERROR
        from griptape_nodes.retained_mode.events.base_events import ResultDetails

        assert isinstance(result.result_details, ResultDetails)
        assert "project_name not yet implemented" in str(result.result_details)

    @patch("griptape_nodes.retained_mode.managers.project_manager.WorkflowRegistry")
    @patch("griptape_nodes.retained_mode.managers.project_manager.GriptapeNodes")
    def test_builtin_workflow_dir_resolves_correctly(
        self,
        mock_griptape_nodes: Mock,
        mock_workflow_registry: Mock,
        project_manager_with_template: ProjectManager,
    ) -> None:
        """Test that {workflow_dir} resolves to the workflow file's parent directory."""
        from griptape_nodes.common.macro_parser import ParsedMacro

        mock_context_manager = Mock()
        mock_context_manager.has_current_workflow.return_value = True
        mock_context_manager.get_current_workflow_name.return_value = "my_workflow"
        mock_griptape_nodes.ContextManager.return_value = mock_context_manager

        mock_workflow = Mock()
        mock_workflow.file_path = "my_project/my_workflow.json"
        mock_workflow_registry.get_workflow_by_name.return_value = mock_workflow
        mock_workflow_registry.get_complete_file_path.return_value = "/workspace/my_project/my_workflow.json"

        parsed_macro = ParsedMacro("{workflow_dir}/output.txt")
        request = GetPathForMacroRequest(parsed_macro=parsed_macro, variables={})

        result = project_manager_with_template.on_get_path_for_macro_request(request)

        assert isinstance(result, GetPathForMacroResultSuccess)
        assert result.resolved_path == Path("/workspace/my_project/output.txt")

    @patch("griptape_nodes.retained_mode.managers.project_manager.GriptapeNodes")
    def test_builtin_workflow_dir_no_current_workflow(
        self, mock_griptape_nodes: Mock, project_manager_with_template: ProjectManager
    ) -> None:
        """Test that required {workflow_dir} fails when there is no current workflow."""
        from griptape_nodes.common.macro_parser import ParsedMacro

        mock_context_manager = Mock()
        mock_context_manager.has_current_workflow.return_value = False
        mock_griptape_nodes.ContextManager.return_value = mock_context_manager

        parsed_macro = ParsedMacro("{workflow_dir}/output.txt")
        request = GetPathForMacroRequest(parsed_macro=parsed_macro, variables={})

        result = project_manager_with_template.on_get_path_for_macro_request(request)

        assert isinstance(result, GetPathForMacroResultFailure)
        assert result.failure_reason == PathResolutionFailureReason.MACRO_RESOLUTION_ERROR
        from griptape_nodes.retained_mode.events.base_events import ResultDetails

        assert isinstance(result.result_details, ResultDetails)
        assert "No current workflow" in str(result.result_details)

    @patch("griptape_nodes.retained_mode.managers.project_manager.GriptapeNodes")
    def test_builtin_workflow_dir_optional_skipped_when_no_workflow(
        self, mock_griptape_nodes: Mock, project_manager_with_template: ProjectManager
    ) -> None:
        """Test that optional {workflow_dir?:/} is skipped (not an error) when no current workflow."""
        from griptape_nodes.common.macro_parser import ParsedMacro

        cast("Mock", project_manager_with_template._config_manager).workspace_path = Path("/workspace")

        mock_context_manager = Mock()
        mock_context_manager.has_current_workflow.return_value = False
        mock_griptape_nodes.ContextManager.return_value = mock_context_manager

        parsed_macro = ParsedMacro("{workflow_dir?:/}staticfiles/output.txt")
        request = GetPathForMacroRequest(parsed_macro=parsed_macro, variables={})

        result = project_manager_with_template.on_get_path_for_macro_request(request)

        assert isinstance(result, GetPathForMacroResultSuccess)
        assert result.resolved_path == Path("staticfiles/output.txt")

    @patch("griptape_nodes.retained_mode.managers.project_manager.WorkflowRegistry")
    @patch("griptape_nodes.retained_mode.managers.project_manager.GriptapeNodes")
    def test_builtin_workflow_dir_unregistered_workflow_fails(
        self,
        mock_griptape_nodes: Mock,
        mock_workflow_registry: Mock,
        project_manager_with_template: ProjectManager,
    ) -> None:
        """Test that required {workflow_dir} fails when the workflow exists but is not registered (unsaved)."""
        from griptape_nodes.common.macro_parser import ParsedMacro

        mock_context_manager = Mock()
        mock_context_manager.has_current_workflow.return_value = True
        mock_context_manager.get_current_workflow_name.return_value = "workflow_5"
        mock_griptape_nodes.ContextManager.return_value = mock_context_manager

        mock_workflow_registry.get_workflow_by_name.side_effect = KeyError("workflow_5")

        parsed_macro = ParsedMacro("{workflow_dir}/output.txt")
        request = GetPathForMacroRequest(parsed_macro=parsed_macro, variables={})

        result = project_manager_with_template.on_get_path_for_macro_request(request)

        assert isinstance(result, GetPathForMacroResultFailure)
        assert result.failure_reason == PathResolutionFailureReason.MACRO_RESOLUTION_ERROR
        from griptape_nodes.retained_mode.events.base_events import ResultDetails

        assert isinstance(result.result_details, ResultDetails)
        assert "workflow_5" in str(result.result_details)

    @patch("griptape_nodes.retained_mode.managers.project_manager.WorkflowRegistry")
    @patch("griptape_nodes.retained_mode.managers.project_manager.GriptapeNodes")
    def test_builtin_workflow_dir_optional_skipped_when_workflow_unregistered(
        self,
        mock_griptape_nodes: Mock,
        mock_workflow_registry: Mock,
        project_manager_with_template: ProjectManager,
    ) -> None:
        """Test that optional {workflow_dir?:/} falls back gracefully when the workflow is not registered (unsaved)."""
        from griptape_nodes.common.macro_parser import ParsedMacro

        cast("Mock", project_manager_with_template._config_manager).workspace_path = Path("/workspace")

        mock_context_manager = Mock()
        mock_context_manager.has_current_workflow.return_value = True
        mock_context_manager.get_current_workflow_name.return_value = "workflow_5"
        mock_griptape_nodes.ContextManager.return_value = mock_context_manager

        mock_workflow_registry.get_workflow_by_name.side_effect = KeyError("workflow_5")

        parsed_macro = ParsedMacro("{workflow_dir?:/}staticfiles/output.txt")
        request = GetPathForMacroRequest(parsed_macro=parsed_macro, variables={})

        result = project_manager_with_template.on_get_path_for_macro_request(request)

        assert isinstance(result, GetPathForMacroResultSuccess)
        assert result.resolved_path == Path("staticfiles/output.txt")

    def test_builtin_static_files_dir_resolves_from_config(self, project_manager_with_template: ProjectManager) -> None:
        """Test that {static_files_dir} resolves to the configured static_files_directory setting."""
        from griptape_nodes.common.macro_parser import ParsedMacro

        cast("Mock", project_manager_with_template._config_manager).get_config_value.return_value = "my_static"
        cast("Mock", project_manager_with_template._config_manager).workspace_path = Path("/test")

        parsed_macro = ParsedMacro("{static_files_dir}/output.png")
        request = GetPathForMacroRequest(parsed_macro=parsed_macro, variables={})

        result = project_manager_with_template.on_get_path_for_macro_request(request)

        assert isinstance(result, GetPathForMacroResultSuccess)
        assert result.resolved_path == Path("my_static/output.png")

    def test_builtin_override_matching_value_allowed(self, project_manager_with_template: ProjectManager) -> None:
        """Test that providing matching value for builtin variable is allowed."""
        from griptape_nodes.common.macro_parser import ParsedMacro

        parsed_macro = ParsedMacro("{project_dir}/output.txt")

        request = GetPathForMacroRequest(
            parsed_macro=parsed_macro,
            variables={"project_dir": "/test"},
        )

        result = project_manager_with_template.on_get_path_for_macro_request(request)

        assert isinstance(result, GetPathForMacroResultSuccess)
        assert result.resolved_path == Path("/test/output.txt")

    def test_builtin_override_different_value_rejected(self, project_manager_with_template: ProjectManager) -> None:
        """Test that providing different value for builtin variable is rejected."""
        from griptape_nodes.common.macro_parser import ParsedMacro

        parsed_macro = ParsedMacro("{project_dir}/output.txt")

        request = GetPathForMacroRequest(
            parsed_macro=parsed_macro,
            variables={"project_dir": "/different"},
        )

        result = project_manager_with_template.on_get_path_for_macro_request(request)

        assert isinstance(result, GetPathForMacroResultFailure)
        assert result.failure_reason == PathResolutionFailureReason.DIRECTORY_OVERRIDE_ATTEMPTED
        assert result.conflicting_variables == {"project_dir"}
        from griptape_nodes.retained_mode.events.base_events import ResultDetails

        assert isinstance(result.result_details, ResultDetails)
        assert "cannot override builtin variables" in str(result.result_details)


class TestProjectManagerNestedDirectoryResolution:
    """Test that directory path_macros can reference other directories (nested resolution)."""

    @staticmethod
    def _build_project_manager_with_template(template: ProjectTemplate, project_base: Path) -> ProjectManager:
        """Build a ProjectManager with the given template registered as the current project."""
        from griptape_nodes.common.project_templates import ProjectValidationInfo, ProjectValidationStatus
        from griptape_nodes.retained_mode.managers.project_manager import ProjectInfo

        mock_config = Mock()
        mock_config.workspace_path = project_base
        mock_secrets = Mock()
        mock_event_manager = Mock()
        pm = ProjectManager(mock_event_manager, mock_config, mock_secrets)

        validation = ProjectValidationInfo(status=ProjectValidationStatus.GOOD)
        situation_schemas = pm._parse_situation_macros(template.situations, validation)
        directory_schemas = pm._parse_directory_macros(template.directories, validation)

        project_path = project_base / "project.yml"
        project_id = str(project_path)
        project_info = ProjectInfo(
            project_id=project_id,
            project_file_path=project_path,
            project_base_dir=project_base,
            template=template,
            validation=validation,
            parsed_situation_schemas=situation_schemas,
            parsed_directory_schemas=directory_schemas,
        )

        pm._successfully_loaded_project_templates[project_id] = project_info
        pm._current_project_id = project_id
        return pm

    def test_directory_path_macro_referencing_another_directory_is_fully_resolved(self) -> None:
        """A directory whose path_macro references another directory must recurse.

        Previously the resolver copied ``DirectoryDefinition.path_macro`` verbatim
        into the resolution bag, so nested references (watch_outputs -> watch_folder)
        leaked literal ``{watch_folder}`` tokens into the final path. This test
        pins the fixed behavior.
        """
        from griptape_nodes.common.macro_parser import ParsedMacro
        from griptape_nodes.common.project_templates import (
            DirectoryDefinition,
            ProjectTemplate,
        )

        template = ProjectTemplate(
            project_template_schema_version="0.1.0",
            name="nested_project",
            directories={
                "watch_folder": DirectoryDefinition(name="watch_folder", path_macro="/fake/WATCH"),
                "watch_outputs": DirectoryDefinition(name="watch_outputs", path_macro="{watch_folder}/outputs"),
            },
            situations={},
        )

        pm = self._build_project_manager_with_template(template, Path("/fake/WATCH"))

        parsed_macro = ParsedMacro("{watch_outputs}/{node_name}.{file_extension}")
        result = pm.on_get_path_for_macro_request(
            GetPathForMacroRequest(
                parsed_macro=parsed_macro,
                variables={"node_name": "MyNode", "file_extension": "png"},
            )
        )

        assert isinstance(result, GetPathForMacroResultSuccess)
        assert result.resolved_path == Path("/fake/WATCH/outputs/MyNode.png")

    def test_optional_variable_omitted_with_nested_directory(self) -> None:
        """Omitting an optional variable must still drop its separator cleanly.

        Mirrors the real ``save_node_watch_output`` macro that originally
        triggered the bug report.
        """
        from griptape_nodes.common.macro_parser import ParsedMacro
        from griptape_nodes.common.project_templates import (
            DirectoryDefinition,
            ProjectTemplate,
        )

        template = ProjectTemplate(
            project_template_schema_version="0.1.0",
            name="nested_project",
            directories={
                "watch_folder": DirectoryDefinition(name="watch_folder", path_macro="/fake/WATCH"),
                "watch_outputs": DirectoryDefinition(name="watch_outputs", path_macro="{watch_folder}/outputs"),
            },
            situations={},
        )

        pm = self._build_project_manager_with_template(template, Path("/fake/WATCH"))

        parsed_macro = ParsedMacro("{watch_outputs}/{sub_dirs?:/}{node_name}.{file_extension}")

        with_subdirs = pm.on_get_path_for_macro_request(
            GetPathForMacroRequest(
                parsed_macro=parsed_macro,
                variables={
                    "node_name": "MyNode",
                    "file_extension": "png",
                    "sub_dirs": "renders",
                },
            )
        )
        assert isinstance(with_subdirs, GetPathForMacroResultSuccess)
        assert with_subdirs.resolved_path == Path("/fake/WATCH/outputs/renders/MyNode.png")

        without_subdirs = pm.on_get_path_for_macro_request(
            GetPathForMacroRequest(
                parsed_macro=parsed_macro,
                variables={"node_name": "MyNode", "file_extension": "png"},
            )
        )
        assert isinstance(without_subdirs, GetPathForMacroResultSuccess)
        assert without_subdirs.resolved_path == Path("/fake/WATCH/outputs/MyNode.png")

    def test_directory_cycle_returns_failure(self) -> None:
        """A cycle in directory references must be detected and reported, not infinite-looped."""
        from griptape_nodes.common.macro_parser import ParsedMacro
        from griptape_nodes.common.project_templates import (
            DirectoryDefinition,
            ProjectTemplate,
        )

        template = ProjectTemplate(
            project_template_schema_version="0.1.0",
            name="cyclic_project",
            directories={
                "a": DirectoryDefinition(name="a", path_macro="{b}/a"),
                "b": DirectoryDefinition(name="b", path_macro="{a}/b"),
            },
            situations={},
        )

        pm = self._build_project_manager_with_template(template, Path("/fake/cycle"))

        parsed_macro = ParsedMacro("{a}/file.txt")
        result = pm.on_get_path_for_macro_request(GetPathForMacroRequest(parsed_macro=parsed_macro, variables={}))

        assert isinstance(result, GetPathForMacroResultFailure)
        assert result.failure_reason == PathResolutionFailureReason.MACRO_RESOLUTION_ERROR
        assert "cycle" in str(result.result_details).lower()

    @patch("griptape_nodes.retained_mode.managers.project_manager.GriptapeNodes")
    def test_directory_optional_builtin_drops_when_unresolvable(self, mock_griptape_nodes: Mock) -> None:
        """An optional builtin inside a directory macro drops cleanly if unresolvable.

        Directory macros should be as expressive as situation macros: when
        {workflow_name?:/} appears inside a directory path_macro and there is no
        current workflow, the entire optional segment (variable + separator)
        must be omitted instead of failing the whole request.
        """
        from griptape_nodes.common.macro_parser import ParsedMacro
        from griptape_nodes.common.project_templates import DirectoryDefinition, ProjectTemplate

        # No current workflow → {workflow_name} raises RuntimeError inside the helper.
        mock_context = Mock()
        mock_context.has_current_workflow.return_value = False
        mock_griptape_nodes.ContextManager.return_value = mock_context

        template = ProjectTemplate(
            project_template_schema_version="0.1.0",
            name="scratch_project",
            directories={
                "scratch": DirectoryDefinition(name="scratch", path_macro="{workspace_dir}/scratch/{workflow_name?:/}"),
            },
            situations={},
        )

        pm = self._build_project_manager_with_template(template, Path("/workspace"))

        parsed_macro = ParsedMacro("{scratch}/{file_name_base}.{file_extension}")
        result = pm.on_get_path_for_macro_request(
            GetPathForMacroRequest(
                parsed_macro=parsed_macro,
                variables={"file_name_base": "notes", "file_extension": "txt"},
            )
        )

        assert isinstance(result, GetPathForMacroResultSuccess)
        assert result.resolved_path == Path("/workspace/scratch/notes.txt")

    def test_directory_optional_unimplemented_builtin_drops(self) -> None:
        """An optional {project_name?:...} inside a directory macro drops silently.

        ``project_name`` raises NotImplementedError today; like RuntimeError, an
        optional reference must be dropped instead of aborting the request.
        """
        from griptape_nodes.common.macro_parser import ParsedMacro
        from griptape_nodes.common.project_templates import DirectoryDefinition, ProjectTemplate

        template = ProjectTemplate(
            project_template_schema_version="0.1.0",
            name="labeled_project",
            directories={
                "labeled": DirectoryDefinition(name="labeled", path_macro="{workspace_dir}/outputs/{project_name?:_}"),
            },
            situations={},
        )

        pm = self._build_project_manager_with_template(template, Path("/workspace"))

        parsed_macro = ParsedMacro("{labeled}/{file_name_base}.{file_extension}")
        result = pm.on_get_path_for_macro_request(
            GetPathForMacroRequest(
                parsed_macro=parsed_macro,
                variables={"file_name_base": "image", "file_extension": "png"},
            )
        )

        assert isinstance(result, GetPathForMacroResultSuccess)
        assert result.resolved_path == Path("/workspace/outputs/image.png")

    @patch("griptape_nodes.retained_mode.managers.project_manager.GriptapeNodes")
    def test_directory_required_builtin_failure_propagates(self, mock_griptape_nodes: Mock) -> None:
        """A *required* builtin failure inside a directory macro must fail loudly.

        Symmetric to the optional-drop behavior: we suppress errors only for
        optional references. A bare {workflow_name} with no current workflow
        must surface as MACRO_RESOLUTION_ERROR, not silently produce garbage.
        """
        from griptape_nodes.common.macro_parser import ParsedMacro
        from griptape_nodes.common.project_templates import DirectoryDefinition, ProjectTemplate

        mock_context = Mock()
        mock_context.has_current_workflow.return_value = False
        mock_griptape_nodes.ContextManager.return_value = mock_context

        template = ProjectTemplate(
            project_template_schema_version="0.1.0",
            name="strict_project",
            directories={
                # No '?' marker -> workflow_name is required inside this directory's macro.
                "strict": DirectoryDefinition(name="strict", path_macro="{workspace_dir}/{workflow_name}/out"),
            },
            situations={},
        )

        pm = self._build_project_manager_with_template(template, Path("/workspace"))

        parsed_macro = ParsedMacro("{strict}/{file_name_base}.{file_extension}")
        result = pm.on_get_path_for_macro_request(
            GetPathForMacroRequest(
                parsed_macro=parsed_macro,
                variables={"file_name_base": "image", "file_extension": "png"},
            )
        )

        assert isinstance(result, GetPathForMacroResultFailure)
        assert result.failure_reason == PathResolutionFailureReason.MACRO_RESOLUTION_ERROR
        assert "no current workflow" in str(result.result_details).lower()

    def test_user_variable_available_inside_directory_macro(self) -> None:
        """A directory macro may reference a user-supplied variable from the outer request.

        Pins the plumbing that passes `request.variables` down into
        `_resolve_directory_path`, so directory macros are as expressive as
        situation macros.
        """
        from griptape_nodes.common.macro_parser import ParsedMacro
        from griptape_nodes.common.project_templates import DirectoryDefinition, ProjectTemplate

        template = ProjectTemplate(
            project_template_schema_version="0.1.0",
            name="tenant_project",
            directories={
                # {tenant} is supplied by the caller, not by project config.
                "tenant_outputs": DirectoryDefinition(
                    name="tenant_outputs", path_macro="{workspace_dir}/tenants/{tenant}/outputs"
                ),
            },
            situations={},
        )

        pm = self._build_project_manager_with_template(template, Path("/workspace"))

        parsed_macro = ParsedMacro("{tenant_outputs}/{file_name_base}.{file_extension}")
        result = pm.on_get_path_for_macro_request(
            GetPathForMacroRequest(
                parsed_macro=parsed_macro,
                variables={"tenant": "acme", "file_name_base": "report", "file_extension": "pdf"},
            )
        )

        assert isinstance(result, GetPathForMacroResultSuccess)
        assert result.resolved_path == Path("/workspace/tenants/acme/outputs/report.pdf")


class TestProjectManagerGetStateForMacro:
    """Test ProjectManager GetStateForMacro request handler."""

    @pytest.fixture
    def project_manager_with_current_project(self) -> ProjectManager:
        """Create a ProjectManager with current project set."""
        from griptape_nodes.common.project_templates import ProjectValidationInfo, ProjectValidationStatus
        from griptape_nodes.common.project_templates.default_project_template import DEFAULT_PROJECT_TEMPLATE
        from griptape_nodes.retained_mode.managers.project_manager import ProjectInfo

        mock_config = Mock()
        mock_secrets = Mock()
        mock_event_manager = Mock()
        pm = ProjectManager(mock_event_manager, mock_config, mock_secrets)

        project_path = Path("/test/project.yml")
        project_id = str(project_path)

        # Parse macros first
        validation = ProjectValidationInfo(status=ProjectValidationStatus.GOOD)
        situation_schemas = pm._parse_situation_macros(DEFAULT_PROJECT_TEMPLATE.situations, validation)
        directory_schemas = pm._parse_directory_macros(DEFAULT_PROJECT_TEMPLATE.directories, validation)

        # Create ProjectInfo with fully populated caches
        project_info = ProjectInfo(
            project_id=project_id,
            project_file_path=project_path,
            project_base_dir=project_path.parent,
            template=DEFAULT_PROJECT_TEMPLATE,
            validation=validation,
            parsed_situation_schemas=situation_schemas,
            parsed_directory_schemas=directory_schemas,
        )

        # Set up new consolidated dict
        pm._successfully_loaded_project_templates[project_id] = project_info
        pm._current_project_id = project_id

        return pm

    def test_get_state_for_macro_no_current_project(self) -> None:
        """Test GetStateForMacro fails when no current project is set."""
        from griptape_nodes.common.macro_parser import ParsedMacro

        mock_config = Mock()
        mock_secrets = Mock()
        mock_event_manager = Mock()
        pm = ProjectManager(mock_event_manager, mock_config, mock_secrets)

        parsed_macro = ParsedMacro("{file_name}.txt")

        request = GetStateForMacroRequest(parsed_macro=parsed_macro, variables={})

        result = pm.on_get_state_for_macro_request(request)

        assert isinstance(result, GetStateForMacroResultFailure)
        from griptape_nodes.retained_mode.events.base_events import ResultDetails

        assert isinstance(result.result_details, ResultDetails)
        assert "no current project is set" in str(result.result_details)

    def test_get_state_for_macro_all_variables_satisfied(
        self, project_manager_with_current_project: ProjectManager
    ) -> None:
        """Test GetStateForMacro when all variables are satisfied."""
        from griptape_nodes.common.macro_parser import ParsedMacro

        parsed_macro = ParsedMacro("{file_name}.{ext}")

        request = GetStateForMacroRequest(parsed_macro=parsed_macro, variables={"file_name": "output", "ext": "txt"})

        result = project_manager_with_current_project.on_get_state_for_macro_request(request)

        assert isinstance(result, GetStateForMacroResultSuccess)
        var_names = {v.name for v in result.all_variables}
        assert var_names == {"file_name", "ext"}
        assert result.satisfied_variables == {"file_name", "ext"}
        assert result.missing_required_variables == set()
        assert result.conflicting_variables == set()
        assert result.can_resolve is True

    def test_get_state_for_macro_missing_required_variables(
        self, project_manager_with_current_project: ProjectManager
    ) -> None:
        """Test GetStateForMacro when required variables are missing."""
        from griptape_nodes.common.macro_parser import ParsedMacro

        parsed_macro = ParsedMacro("{file_name}.{ext}")

        request = GetStateForMacroRequest(parsed_macro=parsed_macro, variables={"file_name": "output"})

        result = project_manager_with_current_project.on_get_state_for_macro_request(request)

        assert isinstance(result, GetStateForMacroResultSuccess)
        assert result.satisfied_variables == {"file_name"}
        assert result.missing_required_variables == {"ext"}
        assert result.can_resolve is False

    def test_get_state_for_macro_conflicting_variables_directory(
        self, project_manager_with_current_project: ProjectManager
    ) -> None:
        """Test GetStateForMacro when user provides directory name."""
        from griptape_nodes.common.macro_parser import ParsedMacro

        parsed_macro = ParsedMacro("{inputs}/{file_name}.txt")

        request = GetStateForMacroRequest(
            parsed_macro=parsed_macro, variables={"inputs": "custom_inputs", "file_name": "output"}
        )

        result = project_manager_with_current_project.on_get_state_for_macro_request(request)

        assert isinstance(result, GetStateForMacroResultSuccess)
        assert "inputs" in result.conflicting_variables
        assert result.can_resolve is False

    @patch("griptape_nodes.retained_mode.managers.project_manager.GriptapeNodes")
    def test_get_state_for_macro_builtin_variable_satisfied(
        self, mock_griptape_nodes: Mock, project_manager_with_current_project: ProjectManager
    ) -> None:
        """Test GetStateForMacro with satisfied builtin variable."""
        from griptape_nodes.common.macro_parser import ParsedMacro

        mock_config_manager = Mock()
        mock_config_manager.get_config_value.return_value = "/workspace"
        mock_griptape_nodes.ConfigManager.return_value = mock_config_manager

        parsed_macro = ParsedMacro("{workspace_dir}/output.txt")

        request = GetStateForMacroRequest(parsed_macro=parsed_macro, variables={})

        result = project_manager_with_current_project.on_get_state_for_macro_request(request)

        assert isinstance(result, GetStateForMacroResultSuccess)
        assert result.satisfied_variables == {"workspace_dir"}
        assert result.can_resolve is True

    @patch("griptape_nodes.retained_mode.managers.project_manager.GriptapeNodes")
    def test_get_state_for_macro_builtin_variable_fails(
        self, mock_griptape_nodes: Mock, project_manager_with_current_project: ProjectManager
    ) -> None:
        """Test GetStateForMacro fails when builtin variable cannot be resolved."""
        from griptape_nodes.common.macro_parser import ParsedMacro

        mock_context_manager = Mock()
        mock_context_manager.has_current_workflow.return_value = False
        mock_griptape_nodes.ContextManager.return_value = mock_context_manager

        parsed_macro = ParsedMacro("{workflow_name}_output.txt")

        request = GetStateForMacroRequest(parsed_macro=parsed_macro, variables={})

        result = project_manager_with_current_project.on_get_state_for_macro_request(request)

        assert isinstance(result, GetStateForMacroResultFailure)
        from griptape_nodes.retained_mode.events.base_events import ResultDetails

        assert isinstance(result.result_details, ResultDetails)
        assert "workflow_name" in str(result.result_details)
        assert "cannot be resolved" in str(result.result_details)

    def test_get_state_for_macro_conflicting_builtin_override(
        self, project_manager_with_current_project: ProjectManager
    ) -> None:
        """Test GetStateForMacro when user tries to override builtin with different value."""
        from griptape_nodes.common.macro_parser import ParsedMacro

        parsed_macro = ParsedMacro("{project_dir}/output.txt")

        request = GetStateForMacroRequest(parsed_macro=parsed_macro, variables={"project_dir": "/different"})

        result = project_manager_with_current_project.on_get_state_for_macro_request(request)

        assert isinstance(result, GetStateForMacroResultSuccess)
        assert "project_dir" in result.conflicting_variables
        assert result.can_resolve is False


class TestProjectManagerGetCurrentProject:
    """Test ProjectManager GetCurrentProject request handler."""

    def test_get_current_project_no_project_set(self) -> None:
        """Test GetCurrentProject fails when no project is set."""
        from griptape_nodes.retained_mode.events.project_events import (
            GetCurrentProjectRequest,
            GetCurrentProjectResultFailure,
        )

        mock_config = Mock()
        mock_secrets = Mock()
        mock_event_manager = Mock()
        pm = ProjectManager(mock_event_manager, mock_config, mock_secrets)

        request = GetCurrentProjectRequest()
        result = pm.on_get_current_project_request(request)

        assert isinstance(result, GetCurrentProjectResultFailure)
        assert "no project is currently set" in str(result.result_details)

    def test_get_current_project_returns_project_info(self) -> None:
        """Test GetCurrentProject returns complete ProjectInfo."""
        from griptape_nodes.common.project_templates import ProjectValidationInfo, ProjectValidationStatus
        from griptape_nodes.common.project_templates.default_project_template import DEFAULT_PROJECT_TEMPLATE
        from griptape_nodes.retained_mode.events.project_events import (
            GetCurrentProjectRequest,
            GetCurrentProjectResultSuccess,
        )
        from griptape_nodes.retained_mode.managers.project_manager import ProjectInfo

        mock_config = Mock()
        mock_secrets = Mock()
        mock_event_manager = Mock()
        pm = ProjectManager(mock_event_manager, mock_config, mock_secrets)

        project_path = Path("/test/project.yml")
        project_id = str(project_path)

        # Parse macros first
        validation = ProjectValidationInfo(status=ProjectValidationStatus.GOOD)
        situation_schemas = pm._parse_situation_macros(DEFAULT_PROJECT_TEMPLATE.situations, validation)
        directory_schemas = pm._parse_directory_macros(DEFAULT_PROJECT_TEMPLATE.directories, validation)

        # Create ProjectInfo
        project_info = ProjectInfo(
            project_id=project_id,
            project_file_path=project_path,
            project_base_dir=project_path.parent,
            template=DEFAULT_PROJECT_TEMPLATE,
            validation=validation,
            parsed_situation_schemas=situation_schemas,
            parsed_directory_schemas=directory_schemas,
        )

        pm._successfully_loaded_project_templates[project_id] = project_info
        pm._current_project_id = project_id

        request = GetCurrentProjectRequest()
        result = pm.on_get_current_project_request(request)

        assert isinstance(result, GetCurrentProjectResultSuccess)
        assert result.project_info == project_info
        assert result.project_info.project_id == project_id
        assert result.project_info.template == DEFAULT_PROJECT_TEMPLATE
        assert result.project_info.project_base_dir == Path("/test")
        assert result.project_info.validation.status == ProjectValidationStatus.GOOD

    def test_get_current_project_id_not_found_in_templates(self) -> None:
        """Test GetCurrentProject fails when current project ID is not in loaded templates."""
        from griptape_nodes.retained_mode.events.project_events import (
            GetCurrentProjectRequest,
            GetCurrentProjectResultFailure,
        )

        mock_config = Mock()
        mock_secrets = Mock()
        mock_event_manager = Mock()
        pm = ProjectManager(mock_event_manager, mock_config, mock_secrets)

        # Set current project ID but don't add to loaded templates
        pm._current_project_id = "missing_project"

        request = GetCurrentProjectRequest()
        result = pm.on_get_current_project_request(request)

        assert isinstance(result, GetCurrentProjectResultFailure)
        assert "project not found" in str(result.result_details)


class TestProjectManagerListProjectTemplates:
    """Test ProjectManager ListProjectTemplates request handler."""

    def test_list_project_templates_empty(self) -> None:
        """Test ListProjectTemplates with no projects loaded."""
        from griptape_nodes.retained_mode.events.project_events import (
            ListProjectTemplatesRequest,
            ListProjectTemplatesResultSuccess,
        )

        mock_config = Mock()
        mock_secrets = Mock()
        mock_event_manager = Mock()
        pm = ProjectManager(mock_event_manager, mock_config, mock_secrets)

        request = ListProjectTemplatesRequest(include_system_builtins=False)
        result = pm.on_list_project_templates_request(request)

        assert isinstance(result, ListProjectTemplatesResultSuccess)
        assert result.successfully_loaded == []
        assert result.failed_to_load == []

    def test_list_project_templates_successfully_loaded(self) -> None:
        """Test ListProjectTemplates returns successfully loaded projects."""
        from griptape_nodes.common.project_templates import ProjectValidationInfo, ProjectValidationStatus
        from griptape_nodes.common.project_templates.default_project_template import DEFAULT_PROJECT_TEMPLATE
        from griptape_nodes.retained_mode.events.project_events import (
            ListProjectTemplatesRequest,
            ListProjectTemplatesResultSuccess,
        )
        from griptape_nodes.retained_mode.managers.project_manager import ProjectInfo

        mock_config = Mock()
        mock_secrets = Mock()
        mock_event_manager = Mock()
        pm = ProjectManager(mock_event_manager, mock_config, mock_secrets)

        # Add two successfully loaded projects
        project1_path = Path("/test/project1.yml")
        project1_id = str(project1_path)
        validation1 = ProjectValidationInfo(status=ProjectValidationStatus.GOOD)
        situation_schemas = pm._parse_situation_macros(DEFAULT_PROJECT_TEMPLATE.situations, validation1)
        directory_schemas = pm._parse_directory_macros(DEFAULT_PROJECT_TEMPLATE.directories, validation1)

        project_info1 = ProjectInfo(
            project_id=project1_id,
            project_file_path=project1_path,
            project_base_dir=project1_path.parent,
            template=DEFAULT_PROJECT_TEMPLATE,
            validation=validation1,
            parsed_situation_schemas=situation_schemas,
            parsed_directory_schemas=directory_schemas,
        )

        project2_path = Path("/test/project2.yml")
        project2_id = str(project2_path)
        validation2 = ProjectValidationInfo(status=ProjectValidationStatus.FLAWED)
        situation_schemas2 = pm._parse_situation_macros(DEFAULT_PROJECT_TEMPLATE.situations, validation2)
        directory_schemas2 = pm._parse_directory_macros(DEFAULT_PROJECT_TEMPLATE.directories, validation2)

        project_info2 = ProjectInfo(
            project_id=project2_id,
            project_file_path=project2_path,
            project_base_dir=project2_path.parent,
            template=DEFAULT_PROJECT_TEMPLATE,
            validation=validation2,
            parsed_situation_schemas=situation_schemas2,
            parsed_directory_schemas=directory_schemas2,
        )

        pm._successfully_loaded_project_templates[project1_id] = project_info1
        pm._successfully_loaded_project_templates[project2_id] = project_info2

        request = ListProjectTemplatesRequest(include_system_builtins=False)
        result = pm.on_list_project_templates_request(request)

        assert isinstance(result, ListProjectTemplatesResultSuccess)
        assert result.failed_to_load == []

        # Verify both projects are in successfully_loaded
        project_ids = {info.project_id for info in result.successfully_loaded}
        assert project_ids == {project1_id, project2_id}

    def test_list_project_templates_with_failures(self) -> None:
        """Test ListProjectTemplates returns failed projects."""
        from griptape_nodes.common.project_templates import ProjectValidationInfo, ProjectValidationStatus
        from griptape_nodes.retained_mode.events.project_events import (
            ListProjectTemplatesRequest,
            ListProjectTemplatesResultSuccess,
        )

        mock_config = Mock()
        mock_secrets = Mock()
        mock_event_manager = Mock()
        pm = ProjectManager(mock_event_manager, mock_config, mock_secrets)

        # Add a failed project to registered_template_status
        failed_path = Path("/test/failed.yml")
        failed_validation = ProjectValidationInfo(status=ProjectValidationStatus.UNUSABLE)
        failed_validation.add_error("template", "Invalid YAML")

        pm._registered_template_status[failed_path] = failed_validation

        request = ListProjectTemplatesRequest(include_system_builtins=False)
        result = pm.on_list_project_templates_request(request)

        assert isinstance(result, ListProjectTemplatesResultSuccess)
        assert result.successfully_loaded == []
        assert len(result.failed_to_load) == 1
        assert result.failed_to_load[0].project_id == str(failed_path)
        assert result.failed_to_load[0].validation.status == ProjectValidationStatus.UNUSABLE

    def test_list_project_templates_filters_system_builtins(self) -> None:
        """Test ListProjectTemplates filters system builtins when requested."""
        from griptape_nodes.common.project_templates import ProjectValidationInfo, ProjectValidationStatus
        from griptape_nodes.common.project_templates.default_project_template import DEFAULT_PROJECT_TEMPLATE
        from griptape_nodes.retained_mode.events.project_events import (
            ListProjectTemplatesRequest,
            ListProjectTemplatesResultSuccess,
        )
        from griptape_nodes.retained_mode.managers.project_manager import SYSTEM_DEFAULTS_KEY, ProjectInfo

        mock_config = Mock()
        mock_secrets = Mock()
        mock_event_manager = Mock()
        pm = ProjectManager(mock_event_manager, mock_config, mock_secrets)

        # Add system defaults
        validation_sys = ProjectValidationInfo(status=ProjectValidationStatus.GOOD)
        situation_schemas = pm._parse_situation_macros(DEFAULT_PROJECT_TEMPLATE.situations, validation_sys)
        directory_schemas = pm._parse_directory_macros(DEFAULT_PROJECT_TEMPLATE.directories, validation_sys)

        system_info = ProjectInfo(
            project_id=SYSTEM_DEFAULTS_KEY,
            project_file_path=None,
            project_base_dir=Path("/workspace"),
            template=DEFAULT_PROJECT_TEMPLATE,
            validation=validation_sys,
            parsed_situation_schemas=situation_schemas,
            parsed_directory_schemas=directory_schemas,
        )

        pm._successfully_loaded_project_templates[SYSTEM_DEFAULTS_KEY] = system_info

        # Test with include_system_builtins=False (default)
        request_no_builtins = ListProjectTemplatesRequest(include_system_builtins=False)
        result_no_builtins = pm.on_list_project_templates_request(request_no_builtins)

        assert isinstance(result_no_builtins, ListProjectTemplatesResultSuccess)
        assert result_no_builtins.successfully_loaded == []

        # Test with include_system_builtins=True
        request_with_builtins = ListProjectTemplatesRequest(include_system_builtins=True)
        result_with_builtins = pm.on_list_project_templates_request(request_with_builtins)

        assert isinstance(result_with_builtins, ListProjectTemplatesResultSuccess)
        assert len(result_with_builtins.successfully_loaded) == 1
        assert result_with_builtins.successfully_loaded[0].project_id == SYSTEM_DEFAULTS_KEY

    def test_list_project_templates_mixed_state(self) -> None:
        """Test ListProjectTemplates with mix of successful and failed projects."""
        from griptape_nodes.common.project_templates import ProjectValidationInfo, ProjectValidationStatus
        from griptape_nodes.common.project_templates.default_project_template import DEFAULT_PROJECT_TEMPLATE
        from griptape_nodes.retained_mode.events.project_events import (
            ListProjectTemplatesRequest,
            ListProjectTemplatesResultSuccess,
        )
        from griptape_nodes.retained_mode.managers.project_manager import ProjectInfo

        mock_config = Mock()
        mock_secrets = Mock()
        mock_event_manager = Mock()
        pm = ProjectManager(mock_event_manager, mock_config, mock_secrets)

        # Add successful project
        success_path = Path("/test/success.yml")
        success_id = str(success_path)
        validation_success = ProjectValidationInfo(status=ProjectValidationStatus.GOOD)
        situation_schemas = pm._parse_situation_macros(DEFAULT_PROJECT_TEMPLATE.situations, validation_success)
        directory_schemas = pm._parse_directory_macros(DEFAULT_PROJECT_TEMPLATE.directories, validation_success)

        success_info = ProjectInfo(
            project_id=success_id,
            project_file_path=success_path,
            project_base_dir=success_path.parent,
            template=DEFAULT_PROJECT_TEMPLATE,
            validation=validation_success,
            parsed_situation_schemas=situation_schemas,
            parsed_directory_schemas=directory_schemas,
        )

        pm._successfully_loaded_project_templates[success_id] = success_info
        pm._registered_template_status[success_path] = validation_success

        # Add failed project
        failed_path = Path("/test/failed.yml")
        failed_validation = ProjectValidationInfo(status=ProjectValidationStatus.UNUSABLE)
        failed_validation.add_error("template", "Parse error")

        pm._registered_template_status[failed_path] = failed_validation

        request = ListProjectTemplatesRequest(include_system_builtins=False)
        result = pm.on_list_project_templates_request(request)

        assert isinstance(result, ListProjectTemplatesResultSuccess)
        assert len(result.successfully_loaded) == 1
        assert len(result.failed_to_load) == 1
        assert result.successfully_loaded[0].project_id == success_id
        assert result.failed_to_load[0].project_id == str(failed_path)


class TestProjectManagerAttemptMapAbsolutePathToProject:
    """Test ProjectManager AttemptMapAbsolutePathToProject event handler."""

    @pytest.fixture
    def project_manager(self) -> ProjectManager:
        """Create a ProjectManager instance for testing."""
        mock_config = Mock()
        mock_secrets = Mock()
        mock_event_manager = Mock()
        return ProjectManager(mock_event_manager, mock_config, mock_secrets)

    def test_attempt_map_path_inside_project_directory(self, project_manager: ProjectManager) -> None:
        """Test mapping an absolute path that's inside a project directory."""
        from griptape_nodes.common.macro_parser import ParsedMacro
        from griptape_nodes.common.project_templates import (
            DEFAULT_PROJECT_TEMPLATE,
            ProjectValidationInfo,
            ProjectValidationStatus,
        )
        from griptape_nodes.retained_mode.managers.project_manager import SYSTEM_DEFAULTS_KEY, ProjectInfo

        # Set up project with outputs directory
        project_base = Path("/Users/test/project")

        # Parse directory macros
        directory_schemas = {}
        for dir_name, dir_def in DEFAULT_PROJECT_TEMPLATE.directories.items():
            directory_schemas[dir_name] = ParsedMacro(dir_def.path_macro)

        project_info = ProjectInfo(
            project_id=SYSTEM_DEFAULTS_KEY,
            project_file_path=project_base / "project.yml",
            project_base_dir=project_base,
            template=DEFAULT_PROJECT_TEMPLATE,
            validation=ProjectValidationInfo(status=ProjectValidationStatus.GOOD),
            parsed_situation_schemas={},
            parsed_directory_schemas=directory_schemas,
        )

        project_manager._successfully_loaded_project_templates[SYSTEM_DEFAULTS_KEY] = project_info
        project_manager._current_project_id = SYSTEM_DEFAULTS_KEY

        # Mock secrets manager
        project_manager._secrets_manager = Mock()
        project_manager._secrets_manager.resolve.return_value = "test_value"

        cast("Mock", project_manager._config_manager).workspace_path = project_base

        # Mock GriptapeNodes.ContextManager()
        with patch("griptape_nodes.retained_mode.managers.project_manager.GriptapeNodes") as mock_gn:
            mock_context = Mock()
            mock_context.has_current_workflow.return_value = False  # No workflow needed for this test
            mock_gn.ContextManager.return_value = mock_context

            # Test path inside outputs directory
            absolute_path = project_base / "outputs" / "renders" / "file.png"

            request = AttemptMapAbsolutePathToProjectRequest(absolute_path=absolute_path)
            result = project_manager.on_attempt_map_absolute_path_to_project_request(request)

            assert isinstance(result, AttemptMapAbsolutePathToProjectResultSuccess)
            assert result.mapped_path == "{outputs}/renders/file.png"

    def test_attempt_map_path_outside_project_directories(self, project_manager: ProjectManager) -> None:
        """Test mapping an absolute path that's outside all project directories."""
        from griptape_nodes.common.macro_parser import ParsedMacro
        from griptape_nodes.common.project_templates import (
            DEFAULT_PROJECT_TEMPLATE,
            ProjectValidationInfo,
            ProjectValidationStatus,
        )
        from griptape_nodes.retained_mode.managers.project_manager import SYSTEM_DEFAULTS_KEY, ProjectInfo

        # Set up project
        project_base = Path("/Users/test/project")

        # Parse directory macros
        directory_schemas = {}
        for dir_name, dir_def in DEFAULT_PROJECT_TEMPLATE.directories.items():
            directory_schemas[dir_name] = ParsedMacro(dir_def.path_macro)

        project_info = ProjectInfo(
            project_id=SYSTEM_DEFAULTS_KEY,
            project_file_path=project_base / "project.yml",
            project_base_dir=project_base,
            template=DEFAULT_PROJECT_TEMPLATE,
            validation=ProjectValidationInfo(status=ProjectValidationStatus.GOOD),
            parsed_situation_schemas={},
            parsed_directory_schemas=directory_schemas,
        )

        project_manager._successfully_loaded_project_templates[SYSTEM_DEFAULTS_KEY] = project_info
        project_manager._current_project_id = SYSTEM_DEFAULTS_KEY

        # Mock secrets manager
        project_manager._secrets_manager = Mock()
        project_manager._secrets_manager.resolve.return_value = "test_value"

        cast("Mock", project_manager._config_manager).workspace_path = project_base

        # Mock GriptapeNodes.ConfigManager() and ContextManager()
        with patch("griptape_nodes.retained_mode.managers.project_manager.GriptapeNodes") as mock_gn:
            mock_context = Mock()
            mock_context.has_current_workflow.return_value = False  # No workflow needed for this test
            mock_gn.ContextManager.return_value = mock_context

            # Test path outside project
            absolute_path = Path("/Users/test/Downloads/file.png")

            request = AttemptMapAbsolutePathToProjectRequest(absolute_path=absolute_path)
            result = project_manager.on_attempt_map_absolute_path_to_project_request(request)

            assert isinstance(result, AttemptMapAbsolutePathToProjectResultSuccess)
            assert result.mapped_path is None

    def test_attempt_map_path_no_current_project(self, project_manager: ProjectManager) -> None:
        """Test mapping when no current project is set (returns failure)."""
        from griptape_nodes.retained_mode.events.project_events import AttemptMapAbsolutePathToProjectResultFailure

        # No project set up

        absolute_path = Path("/Users/test/project/outputs/file.png")

        request = AttemptMapAbsolutePathToProjectRequest(absolute_path=absolute_path)
        result = project_manager.on_attempt_map_absolute_path_to_project_request(request)

        # Should return failure because no current project (cannot perform operation)
        assert isinstance(result, AttemptMapAbsolutePathToProjectResultFailure)
        assert "no current project" in str(result.result_details).lower()

    def test_attempt_map_path_longest_prefix_matching(self, project_manager: ProjectManager) -> None:
        """Test that longest prefix matching works correctly for nested directories."""
        from griptape_nodes.common.macro_parser import ParsedMacro
        from griptape_nodes.common.project_templates import (
            DEFAULT_PROJECT_TEMPLATE,
            ProjectValidationInfo,
            ProjectValidationStatus,
        )
        from griptape_nodes.retained_mode.managers.project_manager import SYSTEM_DEFAULTS_KEY, ProjectInfo

        # Set up project
        project_base = Path("/Users/test/project")

        # Parse directory macros
        directory_schemas = {}
        for dir_name, dir_def in DEFAULT_PROJECT_TEMPLATE.directories.items():
            directory_schemas[dir_name] = ParsedMacro(dir_def.path_macro)

        project_info = ProjectInfo(
            project_id=SYSTEM_DEFAULTS_KEY,
            project_file_path=project_base / "project.yml",
            project_base_dir=project_base,
            template=DEFAULT_PROJECT_TEMPLATE,
            validation=ProjectValidationInfo(status=ProjectValidationStatus.GOOD),
            parsed_situation_schemas={},
            parsed_directory_schemas=directory_schemas,
        )

        project_manager._successfully_loaded_project_templates[SYSTEM_DEFAULTS_KEY] = project_info
        project_manager._current_project_id = SYSTEM_DEFAULTS_KEY

        # Mock secrets manager
        project_manager._secrets_manager = Mock()
        project_manager._secrets_manager.resolve.return_value = "test_value"

        cast("Mock", project_manager._config_manager).workspace_path = project_base

        # Mock GriptapeNodes.ConfigManager() and ContextManager()
        with patch("griptape_nodes.retained_mode.managers.project_manager.GriptapeNodes") as mock_gn:
            mock_context = Mock()
            mock_context.has_current_workflow.return_value = False  # No workflow needed for this test
            mock_gn.ContextManager.return_value = mock_context

            # Test path inside outputs/inputs subdirectory (should match outputs, not inputs)
            absolute_path = project_base / "outputs" / "inputs" / "file.png"

            request = AttemptMapAbsolutePathToProjectRequest(absolute_path=absolute_path)
            result = project_manager.on_attempt_map_absolute_path_to_project_request(request)

            assert isinstance(result, AttemptMapAbsolutePathToProjectResultSuccess)
            assert result.mapped_path == "{outputs}/inputs/file.png"

    def test_attempt_map_path_at_directory_root(self, project_manager: ProjectManager) -> None:
        """Test mapping a path that's exactly at a directory root (no subdirectories)."""
        from griptape_nodes.common.macro_parser import ParsedMacro
        from griptape_nodes.common.project_templates import (
            DEFAULT_PROJECT_TEMPLATE,
            ProjectValidationInfo,
            ProjectValidationStatus,
        )
        from griptape_nodes.retained_mode.managers.project_manager import SYSTEM_DEFAULTS_KEY, ProjectInfo

        # Set up project
        project_base = Path("/Users/test/project")

        # Parse directory macros
        directory_schemas = {}
        for dir_name, dir_def in DEFAULT_PROJECT_TEMPLATE.directories.items():
            directory_schemas[dir_name] = ParsedMacro(dir_def.path_macro)

        project_info = ProjectInfo(
            project_id=SYSTEM_DEFAULTS_KEY,
            project_file_path=project_base / "project.yml",
            project_base_dir=project_base,
            template=DEFAULT_PROJECT_TEMPLATE,
            validation=ProjectValidationInfo(status=ProjectValidationStatus.GOOD),
            parsed_situation_schemas={},
            parsed_directory_schemas=directory_schemas,
        )

        project_manager._successfully_loaded_project_templates[SYSTEM_DEFAULTS_KEY] = project_info
        project_manager._current_project_id = SYSTEM_DEFAULTS_KEY

        # Mock secrets manager
        project_manager._secrets_manager = Mock()
        project_manager._secrets_manager.resolve.return_value = "test_value"

        cast("Mock", project_manager._config_manager).workspace_path = project_base

        # Mock GriptapeNodes.ConfigManager() and ContextManager()
        with patch("griptape_nodes.retained_mode.managers.project_manager.GriptapeNodes") as mock_gn:
            mock_context = Mock()
            mock_context.has_current_workflow.return_value = False  # No workflow needed for this test
            mock_gn.ContextManager.return_value = mock_context

            # Test path exactly at outputs directory
            absolute_path = project_base / "outputs"

            request = AttemptMapAbsolutePathToProjectRequest(absolute_path=absolute_path)
            result = project_manager.on_attempt_map_absolute_path_to_project_request(request)

            assert isinstance(result, AttemptMapAbsolutePathToProjectResultSuccess)
            assert result.mapped_path == "{outputs}"

    def test_attempt_map_path_fallback_to_project_dir(self, project_manager: ProjectManager) -> None:
        """Test that paths not in defined directories fall back to {project_dir}."""
        from griptape_nodes.common.macro_parser import ParsedMacro
        from griptape_nodes.common.project_templates import (
            DEFAULT_PROJECT_TEMPLATE,
            ProjectValidationInfo,
            ProjectValidationStatus,
        )
        from griptape_nodes.retained_mode.managers.project_manager import SYSTEM_DEFAULTS_KEY, ProjectInfo

        # Set up project
        project_base = Path("/Users/test/project")

        # Parse directory macros
        directory_schemas = {}
        for dir_name, dir_def in DEFAULT_PROJECT_TEMPLATE.directories.items():
            directory_schemas[dir_name] = ParsedMacro(dir_def.path_macro)

        project_info = ProjectInfo(
            project_id=SYSTEM_DEFAULTS_KEY,
            project_file_path=project_base / "project.yml",
            project_base_dir=project_base,
            template=DEFAULT_PROJECT_TEMPLATE,
            validation=ProjectValidationInfo(status=ProjectValidationStatus.GOOD),
            parsed_situation_schemas={},
            parsed_directory_schemas=directory_schemas,
        )

        project_manager._successfully_loaded_project_templates[SYSTEM_DEFAULTS_KEY] = project_info
        project_manager._current_project_id = SYSTEM_DEFAULTS_KEY
        project_manager._secrets_manager = Mock()
        project_manager._secrets_manager.resolve.return_value = "test_value"

        cast("Mock", project_manager._config_manager).workspace_path = project_base

        # Mock GriptapeNodes.ConfigManager() and ContextManager()
        with patch("griptape_nodes.retained_mode.managers.project_manager.GriptapeNodes") as mock_gn:
            mock_context = Mock()
            mock_context.has_current_workflow.return_value = False
            mock_gn.ContextManager.return_value = mock_context

            # Test path inside project_base_dir but not in any defined directory
            absolute_path = project_base / "random_folder" / "file.txt"

            request = AttemptMapAbsolutePathToProjectRequest(absolute_path=absolute_path)
            result = project_manager.on_attempt_map_absolute_path_to_project_request(request)

            assert isinstance(result, AttemptMapAbsolutePathToProjectResultSuccess)
            assert result.mapped_path == "{project_dir}/random_folder/file.txt"

    def test_attempt_map_path_with_unresolvable_builtin_variable(self, project_manager: ProjectManager) -> None:
        """Test that if a directory macro needs an unresolvable builtin, returns failure."""
        from griptape_nodes.common.macro_parser import ParsedMacro
        from griptape_nodes.common.project_templates import (
            DirectoryDefinition,
            ProjectTemplate,
            ProjectValidationInfo,
            ProjectValidationStatus,
        )
        from griptape_nodes.retained_mode.events.project_events import AttemptMapAbsolutePathToProjectResultFailure
        from griptape_nodes.retained_mode.managers.project_manager import SYSTEM_DEFAULTS_KEY, ProjectInfo

        # Create a custom template with a directory that uses workflow_name (will fail without workflow)
        custom_template = ProjectTemplate(
            project_template_schema_version="0.1.0",
            name="test_project",
            directories={
                "outputs": DirectoryDefinition(name="outputs", path_macro="{workflow_name}_outputs"),
            },
            situations={},
        )

        project_base = Path("/Users/test/project")

        # Parse directory macros
        directory_schemas = {}
        for dir_name, dir_def in custom_template.directories.items():
            directory_schemas[dir_name] = ParsedMacro(dir_def.path_macro)

        project_info = ProjectInfo(
            project_id=SYSTEM_DEFAULTS_KEY,
            project_file_path=project_base / "project.yml",
            project_base_dir=project_base,
            template=custom_template,
            validation=ProjectValidationInfo(status=ProjectValidationStatus.GOOD),
            parsed_situation_schemas={},
            parsed_directory_schemas=directory_schemas,
        )

        project_manager._successfully_loaded_project_templates[SYSTEM_DEFAULTS_KEY] = project_info
        project_manager._current_project_id = SYSTEM_DEFAULTS_KEY
        project_manager._secrets_manager = Mock()
        project_manager._secrets_manager.resolve.return_value = "test_value"

        cast("Mock", project_manager._config_manager).workspace_path = project_base

        # Mock GriptapeNodes - workflow_name will fail because no workflow
        with patch("griptape_nodes.retained_mode.managers.project_manager.GriptapeNodes") as mock_gn:
            mock_config = Mock()
            mock_config.get_config_value.return_value = str(project_base)
            mock_config.workspace_path = project_base
            mock_gn.ConfigManager.return_value = mock_config

            mock_context = Mock()
            mock_context.has_current_workflow.return_value = False  # No workflow available
            mock_gn.ContextManager.return_value = mock_context

            absolute_path = project_base / "outputs" / "file.png"

            request = AttemptMapAbsolutePathToProjectRequest(absolute_path=absolute_path)
            result = project_manager.on_attempt_map_absolute_path_to_project_request(request)

            # Should return failure because workflow_name cannot be resolved (operation cannot complete)
            assert isinstance(result, AttemptMapAbsolutePathToProjectResultFailure)
            result_message = str(result.result_details)
            assert "failed" in result_message.lower()
            assert "workflow" in result_message.lower() or "no current workflow" in result_message.lower()


class TestLoadWorkspaceProject:
    """Test _load_workspace_project and on_app_initialization_complete."""

    VALID_PROJECT_YAML = """\
project_template_schema_version: "0.1.0"
name: Workspace Project
situations:
  save_node_output:
    macro: "{outputs}/custom/{file_name_base}.{file_extension}"
    policy:
      on_collision: create_new
      create_dirs: true
"""

    @pytest.fixture
    def pm(self) -> ProjectManager:
        mock_event_manager = Mock()
        mock_config_manager = Mock()
        mock_config_manager.project_config = {}
        mock_config_manager.env_config = {}
        mock_config_manager.merged_config = {}
        mock_config_manager.get_config_value.return_value = {}
        return ProjectManager(mock_event_manager, mock_config_manager, Mock())

    def _setup_system_defaults(self, pm: ProjectManager, workspace_dir: str = "/workspace") -> None:
        """Load system defaults into pm, mirroring _load_system_defaults."""
        from griptape_nodes.common.project_templates import ProjectValidationInfo, ProjectValidationStatus
        from griptape_nodes.common.project_templates.default_project_template import DEFAULT_PROJECT_TEMPLATE
        from griptape_nodes.retained_mode.managers.project_manager import SYSTEM_DEFAULTS_KEY, ProjectInfo

        validation = ProjectValidationInfo(status=ProjectValidationStatus.GOOD)
        situation_schemas = pm._parse_situation_macros(DEFAULT_PROJECT_TEMPLATE.situations, validation)
        directory_schemas = pm._parse_directory_macros(DEFAULT_PROJECT_TEMPLATE.directories, validation)

        project_info = ProjectInfo(
            project_id=SYSTEM_DEFAULTS_KEY,
            project_file_path=None,
            project_base_dir=Path(workspace_dir),
            template=DEFAULT_PROJECT_TEMPLATE,
            validation=validation,
            parsed_situation_schemas=situation_schemas,
            parsed_directory_schemas=directory_schemas,
        )
        pm._successfully_loaded_project_templates[SYSTEM_DEFAULTS_KEY] = project_info
        pm._current_project_id = SYSTEM_DEFAULTS_KEY

    @pytest.mark.asyncio
    async def test_load_workspace_project_not_present(self, pm: ProjectManager, tmp_path: Path) -> None:
        """No project file in workspace leaves system defaults as current project."""
        from griptape_nodes.retained_mode.managers.project_manager import SYSTEM_DEFAULTS_KEY

        self._setup_system_defaults(pm, str(tmp_path))

        def get_config_value_side_effect(key: str, **_: object) -> str | dict | None:
            if key == "project_file":
                return None
            if "project_workspaces" in key:
                return {}
            return str(tmp_path)

        cast("Mock", pm._config_manager).get_config_value.side_effect = get_config_value_side_effect
        cast("Mock", pm._config_manager).workspace_path = tmp_path

        await pm._load_workspace_project()

        assert pm._current_project_id == SYSTEM_DEFAULTS_KEY

    @pytest.mark.asyncio
    async def test_load_workspace_project_loads_and_sets_current(self, pm: ProjectManager, tmp_path: Path) -> None:
        """Valid griptape-nodes-project.yml is loaded and set as current project."""
        from griptape_nodes.retained_mode.managers.project_manager import WORKSPACE_PROJECT_FILE

        self._setup_system_defaults(pm, str(tmp_path))

        workspace_project_path = tmp_path / WORKSPACE_PROJECT_FILE
        workspace_project_path.write_text(self.VALID_PROJECT_YAML)

        def get_config_value_side_effect(key: str, **_: object) -> str | dict | None:
            if key == "project_file":
                return None
            if "project_workspaces" in key:
                return {}
            return str(tmp_path)

        cast("Mock", pm._config_manager).get_config_value.side_effect = get_config_value_side_effect
        cast("Mock", pm._config_manager).workspace_path = tmp_path

        with patch("griptape_nodes.retained_mode.managers.project_manager.File") as mock_file_cls:
            mock_file_instance = Mock()
            mock_file_instance.read_text.return_value = self.VALID_PROJECT_YAML
            mock_file_cls.return_value = mock_file_instance

            await pm._load_workspace_project()

        assert pm._current_project_id == str(workspace_project_path)
        assert str(workspace_project_path) in pm._successfully_loaded_project_templates

    @pytest.mark.asyncio
    async def test_load_workspace_project_merges_with_defaults(self, pm: ProjectManager, tmp_path: Path) -> None:
        """Workspace project merges on top of defaults, preserving unoverridden situations."""
        from griptape_nodes.retained_mode.managers.project_manager import WORKSPACE_PROJECT_FILE

        self._setup_system_defaults(pm, str(tmp_path))

        workspace_project_path = tmp_path / WORKSPACE_PROJECT_FILE
        workspace_project_path.write_text(self.VALID_PROJECT_YAML)

        def get_config_value_side_effect(key: str, **_: object) -> str | dict | None:
            if key == "project_file":
                return None
            if "project_workspaces" in key:
                return {}
            return str(tmp_path)

        cast("Mock", pm._config_manager).get_config_value.side_effect = get_config_value_side_effect
        cast("Mock", pm._config_manager).workspace_path = tmp_path

        with patch("griptape_nodes.retained_mode.managers.project_manager.File") as mock_file_cls:
            mock_file_instance = Mock()
            mock_file_instance.read_text.return_value = self.VALID_PROJECT_YAML
            mock_file_cls.return_value = mock_file_instance

            await pm._load_workspace_project()

        project_info = pm._successfully_loaded_project_templates[str(workspace_project_path)]
        template = project_info.template

        # Overridden situation uses workspace macro
        assert "custom" in template.situations["save_node_output"].macro

        # Default-only situations are still present (inherited from defaults)
        assert "save_file" in template.situations
        assert "save_griptape_nodes_preview" in template.situations
        assert "copy_external_file" in template.situations

    @pytest.mark.asyncio
    async def test_load_workspace_project_read_failure_keeps_defaults(self, pm: ProjectManager, tmp_path: Path) -> None:
        """A file read failure leaves system defaults as current project."""
        from griptape_nodes.files.file import FileLoadError
        from griptape_nodes.retained_mode.events.os_events import FileIOFailureReason
        from griptape_nodes.retained_mode.managers.project_manager import SYSTEM_DEFAULTS_KEY, WORKSPACE_PROJECT_FILE

        self._setup_system_defaults(pm, str(tmp_path))

        # Create the file so the existence check passes
        workspace_project_path = tmp_path / WORKSPACE_PROJECT_FILE
        workspace_project_path.write_text(self.VALID_PROJECT_YAML)

        def get_config_value_side_effect(key: str, **_: object) -> str | dict | None:
            if key == "project_file":
                return None
            if "project_workspaces" in key:
                return {}
            return str(tmp_path)

        cast("Mock", pm._config_manager).get_config_value.side_effect = get_config_value_side_effect
        cast("Mock", pm._config_manager).workspace_path = tmp_path

        with patch("griptape_nodes.retained_mode.managers.project_manager.File") as mock_file_cls:
            mock_file_instance = Mock()
            mock_file_instance.read_text.side_effect = FileLoadError(
                failure_reason=FileIOFailureReason.FILE_NOT_FOUND,
                result_details="permission denied",
            )
            mock_file_cls.return_value = mock_file_instance

            await pm._load_workspace_project()

        assert pm._current_project_id == SYSTEM_DEFAULTS_KEY

    @pytest.mark.asyncio
    async def test_load_workspace_project_invalid_yaml_keeps_defaults(self, pm: ProjectManager, tmp_path: Path) -> None:
        """Invalid YAML in project file leaves system defaults as current project."""
        from griptape_nodes.retained_mode.managers.project_manager import SYSTEM_DEFAULTS_KEY, WORKSPACE_PROJECT_FILE

        self._setup_system_defaults(pm, str(tmp_path))

        workspace_project_path = tmp_path / WORKSPACE_PROJECT_FILE
        workspace_project_path.write_text(self.VALID_PROJECT_YAML)

        def get_config_value_side_effect(key: str, **_: object) -> str | dict | None:
            if key == "project_file":
                return None
            if "project_workspaces" in key:
                return {}
            return str(tmp_path)

        cast("Mock", pm._config_manager).get_config_value.side_effect = get_config_value_side_effect
        cast("Mock", pm._config_manager).workspace_path = tmp_path

        with patch("griptape_nodes.retained_mode.managers.project_manager.File") as mock_file_cls:
            mock_file_instance = Mock()
            mock_file_instance.read_text.return_value = "not: valid: yaml: ]["
            mock_file_cls.return_value = mock_file_instance

            await pm._load_workspace_project()

        assert pm._current_project_id == SYSTEM_DEFAULTS_KEY

    @pytest.mark.asyncio
    async def test_load_workspace_project_missing_workspace_dir_skips(self, pm: ProjectManager, tmp_path: Path) -> None:
        """Workspace directory without a project file skips loading without error."""
        from griptape_nodes.retained_mode.managers.project_manager import SYSTEM_DEFAULTS_KEY

        self._setup_system_defaults(pm)

        cast("Mock", pm._config_manager).get_config_value.return_value = None
        # Point workspace_path at an empty directory so the existence check fails.
        cast("Mock", pm._config_manager).workspace_path = tmp_path

        with patch("griptape_nodes.retained_mode.managers.project_manager.File") as mock_file_cls:
            await pm._load_workspace_project()

            mock_file_cls.assert_not_called()

        assert pm._current_project_id == SYSTEM_DEFAULTS_KEY

    @pytest.mark.asyncio
    async def test_app_initialization_complete_loads_workspace_project(
        self, pm: ProjectManager, tmp_path: Path
    ) -> None:
        """on_app_initialization_complete sets workspace project as current when present."""
        from griptape_nodes.retained_mode.events.app_events import AppInitializationComplete
        from griptape_nodes.retained_mode.managers.project_manager import WORKSPACE_PROJECT_FILE

        workspace_project_path = tmp_path / WORKSPACE_PROJECT_FILE
        workspace_project_path.write_text(self.VALID_PROJECT_YAML)

        def get_config_value_side_effect(key: str, **_: object) -> str | dict | None:
            if key == "project_file":
                return None
            if "project_workspaces" in key:
                return {}
            return str(tmp_path)

        cast("Mock", pm._config_manager).get_config_value.side_effect = get_config_value_side_effect
        cast("Mock", pm._config_manager).workspace_path = tmp_path

        with patch("griptape_nodes.retained_mode.managers.project_manager.File") as mock_file_cls:
            mock_file_instance = Mock()
            mock_file_instance.read_text.return_value = self.VALID_PROJECT_YAML
            mock_file_cls.return_value = mock_file_instance

            await pm.on_app_initialization_complete(AppInitializationComplete())

        assert pm._current_project_id == str(workspace_project_path)

    @pytest.mark.asyncio
    async def test_app_initialization_complete_uses_defaults_when_no_workspace_project(
        self, pm: ProjectManager, tmp_path: Path
    ) -> None:
        """on_app_initialization_complete keeps system defaults when no workspace project file exists."""
        from griptape_nodes.retained_mode.events.app_events import AppInitializationComplete
        from griptape_nodes.retained_mode.managers.project_manager import SYSTEM_DEFAULTS_KEY

        def get_config_value_side_effect(key: str, **_: object) -> str | dict | None:
            if key == "project_file":
                return None
            if "project_workspaces" in key:
                return {}
            return str(tmp_path)

        cast("Mock", pm._config_manager).get_config_value.side_effect = get_config_value_side_effect
        cast("Mock", pm._config_manager).workspace_path = tmp_path

        await pm.on_app_initialization_complete(AppInitializationComplete())

        assert pm._current_project_id == SYSTEM_DEFAULTS_KEY

    @pytest.mark.asyncio
    async def test_load_workspace_project_uses_project_file_setting(self, pm: ProjectManager, tmp_path: Path) -> None:
        """When project_file config is set, that path is used instead of workspace default."""
        self._setup_system_defaults(pm, str(tmp_path))

        # Project file is outside the workspace directory
        external_project_path = tmp_path / "external" / "my-project.yml"
        external_project_path.parent.mkdir(parents=True)
        external_project_path.write_text(self.VALID_PROJECT_YAML)

        def get_config_value_side_effect(key: str, **_: object) -> str | dict | None:
            if key == "project_file":
                return str(external_project_path)
            if "project_workspaces" in key:
                return {}
            return str(tmp_path)

        cast("Mock", pm._config_manager).get_config_value.side_effect = get_config_value_side_effect
        cast("Mock", pm._config_manager).workspace_path = tmp_path

        with patch("griptape_nodes.retained_mode.managers.project_manager.File") as mock_file_cls:
            mock_file_instance = Mock()
            mock_file_instance.read_text.return_value = self.VALID_PROJECT_YAML
            mock_file_cls.return_value = mock_file_instance

            await pm._load_workspace_project()

        assert pm._current_project_id == str(external_project_path)
        assert str(external_project_path) in pm._successfully_loaded_project_templates

    @pytest.mark.asyncio
    async def test_load_workspace_project_uses_workspace_default_when_no_project_file_setting(
        self, pm: ProjectManager, tmp_path: Path
    ) -> None:
        """When project_file config is None, falls back to workspace/griptape-nodes-project.yml."""
        from griptape_nodes.retained_mode.managers.project_manager import WORKSPACE_PROJECT_FILE

        self._setup_system_defaults(pm, str(tmp_path))

        workspace_project_path = tmp_path / WORKSPACE_PROJECT_FILE
        workspace_project_path.write_text(self.VALID_PROJECT_YAML)

        def get_config_value_side_effect(key: str, **_: object) -> str | dict | None:
            if key == "project_file":
                return None
            if "project_workspaces" in key:
                return {}
            return str(tmp_path)

        cast("Mock", pm._config_manager).get_config_value.side_effect = get_config_value_side_effect
        cast("Mock", pm._config_manager).workspace_path = tmp_path

        with patch("griptape_nodes.retained_mode.managers.project_manager.File") as mock_file_cls:
            mock_file_instance = Mock()
            mock_file_instance.read_text.return_value = self.VALID_PROJECT_YAML
            mock_file_cls.return_value = mock_file_instance

            await pm._load_workspace_project()

        assert pm._current_project_id == str(workspace_project_path)

    @pytest.mark.asyncio
    async def test_load_workspace_project_project_file_setting_nonexistent_falls_back_to_workspace(
        self, pm: ProjectManager, tmp_path: Path
    ) -> None:
        """When project_file config points to a nonexistent file, falls back to the workspace default."""
        from griptape_nodes.retained_mode.managers.project_manager import WORKSPACE_PROJECT_FILE

        self._setup_system_defaults(pm, str(tmp_path))

        nonexistent_path = tmp_path / "does_not_exist.yml"

        # Workspace default exists and should be loaded as fallback
        workspace_project_path = tmp_path / WORKSPACE_PROJECT_FILE
        workspace_project_path.write_text(self.VALID_PROJECT_YAML)

        def get_config_value_side_effect(key: str, **_: object) -> str | dict | None:
            if key == "project_file":
                return str(nonexistent_path)
            if "project_workspaces" in key:
                return {}
            return str(tmp_path)

        cast("Mock", pm._config_manager).get_config_value.side_effect = get_config_value_side_effect
        cast("Mock", pm._config_manager).workspace_path = tmp_path

        with patch("griptape_nodes.retained_mode.managers.project_manager.File") as mock_file_cls:
            mock_file_instance = Mock()
            mock_file_instance.read_text.return_value = self.VALID_PROJECT_YAML
            mock_file_cls.return_value = mock_file_instance

            await pm._load_workspace_project()

        assert pm._current_project_id == str(workspace_project_path)


class TestLoadSystemDefaults:
    """Test _load_system_defaults uses resolved workspace path for project_base_dir."""

    @pytest.fixture
    def pm(self) -> ProjectManager:
        mock_event_manager = Mock()
        mock_config_manager = Mock()
        mock_config_manager.project_config = {}
        mock_config_manager.env_config = {}
        mock_config_manager.merged_config = {}
        mock_config_manager.get_config_value.return_value = {}
        return ProjectManager(mock_event_manager, mock_config_manager, Mock())

    def test_project_base_dir_uses_resolved_workspace_path(self, pm: ProjectManager) -> None:
        """Test that _load_system_defaults uses config_manager.workspace_path (resolved) for project_base_dir.

        This ensures project_base_dir matches the resolved paths used for macro resolution,
        preventing workspace-internal files from being treated as external.
        """
        from griptape_nodes.retained_mode.managers.project_manager import SYSTEM_DEFAULTS_KEY

        resolved_path = Path("/Users/testuser/GriptapeNodes")
        cast("Mock", pm._config_manager).workspace_path = resolved_path

        pm._load_system_defaults()

        project_info = pm._successfully_loaded_project_templates[SYSTEM_DEFAULTS_KEY]
        assert project_info.project_base_dir == resolved_path

    def test_project_base_dir_not_raw_config_value(self, pm: ProjectManager) -> None:
        """Test that _load_system_defaults does NOT use the raw config value with ~ for project_base_dir.

        Previously, _load_system_defaults used get_config_value("workspace_directory") which
        returns the raw string (e.g., "~/GriptapeNodes"). This caused a mismatch with resolved
        source paths, making workspace-internal files appear external in preview URL generation.
        """
        from griptape_nodes.retained_mode.managers.project_manager import SYSTEM_DEFAULTS_KEY

        resolved_path = Path("/Users/testuser/GriptapeNodes")
        cast("Mock", pm._config_manager).workspace_path = resolved_path
        cast("Mock", pm._config_manager).get_config_value.return_value = "~/GriptapeNodes"

        pm._load_system_defaults()

        project_info = pm._successfully_loaded_project_templates[SYSTEM_DEFAULTS_KEY]
        # Should use the resolved path, not the raw config value
        assert project_info.project_base_dir == resolved_path
        assert str(project_info.project_base_dir) != "~/GriptapeNodes"


class TestProjectManagerProjectWorkspaces:
    """Test ProjectManager project_workspaces lookup in on_set_current_project_request."""

    def _make_project_manager_with_project(self, project_file_path: Path, mock_config: Mock) -> ProjectManager:
        """Create a ProjectManager with a loaded project template at the given path."""
        from griptape_nodes.common.project_templates import ProjectValidationInfo, ProjectValidationStatus
        from griptape_nodes.common.project_templates.default_project_template import DEFAULT_PROJECT_TEMPLATE
        from griptape_nodes.retained_mode.managers.project_manager import ProjectInfo

        mock_event_manager = Mock()
        mock_secrets = Mock()
        pm = ProjectManager(mock_event_manager, mock_config, mock_secrets)

        project_id = str(project_file_path)
        validation = ProjectValidationInfo(status=ProjectValidationStatus.GOOD)
        situation_schemas = pm._parse_situation_macros(DEFAULT_PROJECT_TEMPLATE.situations, validation)
        directory_schemas = pm._parse_directory_macros(DEFAULT_PROJECT_TEMPLATE.directories, validation)

        project_info = ProjectInfo(
            project_id=project_id,
            project_file_path=project_file_path,
            project_base_dir=project_file_path.parent,
            template=DEFAULT_PROJECT_TEMPLATE,
            validation=validation,
            parsed_situation_schemas=situation_schemas,
            parsed_directory_schemas=directory_schemas,
        )
        pm._successfully_loaded_project_templates[project_id] = project_info
        return pm

    @pytest.mark.asyncio
    async def test_project_workspaces_overrides_workspace(self, tmp_path: Path) -> None:
        """Test that a matching project_workspaces entry calls set_workspace_override with the mapped value."""
        import tempfile

        project_file = tmp_path / "project.yml"
        project_file.touch()
        workspace_dir = Path(tempfile.mkdtemp())

        mock_config = Mock()
        mock_config.project_config = {}
        mock_config.env_config = {}
        mock_config.merged_config = {}
        mock_config.get_config_value.return_value = {str(project_file.resolve()): str(workspace_dir)}

        pm = self._make_project_manager_with_project(project_file, mock_config)

        from griptape_nodes.retained_mode.events.project_events import SetCurrentProjectRequest

        await pm.on_set_current_project_request(SetCurrentProjectRequest(project_id=str(project_file)))

        mock_config.set_workspace_override.assert_called_once_with(Path(str(workspace_dir)))
        mock_config.load_workspace_config.assert_called_once()

    @pytest.mark.asyncio
    async def test_project_workspaces_key_resolved_before_lookup(self, tmp_path: Path) -> None:
        """Test that project_workspaces keys are resolved before matching, so symlinks and relative paths work."""
        import tempfile

        project_file = tmp_path / "project.yml"
        project_file.touch()
        workspace_dir = Path(tempfile.mkdtemp())

        mock_config = Mock()
        mock_config.project_config = {}
        mock_config.env_config = {}
        mock_config.merged_config = {}
        # Key uses the unresolved path; the code must resolve both sides before comparing.
        mock_config.get_config_value.return_value = {str(project_file): str(workspace_dir)}

        pm = self._make_project_manager_with_project(project_file, mock_config)

        from griptape_nodes.retained_mode.events.project_events import SetCurrentProjectRequest

        await pm.on_set_current_project_request(SetCurrentProjectRequest(project_id=str(project_file)))

        mock_config.set_workspace_override.assert_called_once_with(Path(str(workspace_dir)))
        mock_config.load_workspace_config.assert_called_once()

    @pytest.mark.asyncio
    async def test_project_workspaces_no_match_falls_back_to_project_dir(self, tmp_path: Path) -> None:
        """Test that when no project_workspaces entry matches, set_workspace_override is called with project dir."""
        project_file = tmp_path / "project.yml"
        project_file.touch()

        mock_config = Mock()
        mock_config.project_config = {}
        mock_config.env_config = {}
        mock_config.merged_config = {}
        mock_config.get_config_value.return_value = {}

        pm = self._make_project_manager_with_project(project_file, mock_config)

        from griptape_nodes.retained_mode.events.project_events import SetCurrentProjectRequest

        await pm.on_set_current_project_request(SetCurrentProjectRequest(project_id=str(project_file)))

        mock_config.set_workspace_override.assert_called_once_with(project_file.parent)
        mock_config.load_workspace_config.assert_called_once()

    @pytest.mark.asyncio
    async def test_project_workspaces_project_adjacent_config_not_overridden_when_set(self, tmp_path: Path) -> None:
        """Test that set_workspace_override is not called when project-adjacent config sets workspace_directory."""
        project_file = tmp_path / "project.yml"
        project_file.touch()

        mock_config = Mock()
        mock_config.project_config = {"workspace_directory": "/some/shared/workspace"}
        mock_config.env_config = {}
        mock_config.merged_config = {}
        mock_config.get_config_value.return_value = {}

        pm = self._make_project_manager_with_project(project_file, mock_config)

        from griptape_nodes.retained_mode.events.project_events import SetCurrentProjectRequest

        await pm.on_set_current_project_request(SetCurrentProjectRequest(project_id=str(project_file)))

        mock_config.set_workspace_override.assert_not_called()
        mock_config.load_workspace_config.assert_called_once()

    @pytest.mark.asyncio
    async def test_initialization_incomplete_skips_reload(self, tmp_path: Path) -> None:
        """When _initialization_complete is False, no library reload or workflow re-registration occurs."""
        from unittest.mock import AsyncMock, patch

        project_file = tmp_path / "project.yml"
        project_file.touch()

        mock_config = Mock()
        mock_config.project_config = {}
        mock_config.env_config = {}
        mock_config.merged_config = {}
        mock_config.get_config_value.return_value = {}

        pm = self._make_project_manager_with_project(project_file, mock_config)
        # _initialization_complete starts False

        from griptape_nodes.retained_mode.events.project_events import SetCurrentProjectRequest

        with patch("griptape_nodes.retained_mode.managers.project_manager.GriptapeNodes") as mock_gn:
            mock_gn.ahandle_request = AsyncMock()
            await pm.on_set_current_project_request(SetCurrentProjectRequest(project_id=str(project_file)))
            mock_gn.ahandle_request.assert_not_called()
            mock_gn.WorkflowManager.assert_not_called()

    @pytest.mark.asyncio
    async def test_initialization_complete_same_workspace_reloads_libraries_only(self, tmp_path: Path) -> None:
        """When workspace is unchanged, libraries are reloaded but workflows are NOT re-registered."""
        from unittest.mock import AsyncMock, patch

        from griptape_nodes.retained_mode.events.library_events import (
            ReloadAllLibrariesResultSuccess,
        )

        project_file = tmp_path / "project.yml"
        project_file.touch()

        mock_config = Mock()
        mock_config.project_config = {}
        mock_config.env_config = {}
        mock_config.merged_config = {}
        mock_config.get_config_value.return_value = {}
        # Same workspace before and after
        mock_config.workspace_path = str(tmp_path)

        pm = self._make_project_manager_with_project(project_file, mock_config)
        pm._initialization_complete = True

        from griptape_nodes.retained_mode.events.project_events import SetCurrentProjectRequest

        mock_workflow_manager = Mock()
        with patch("griptape_nodes.retained_mode.managers.project_manager.GriptapeNodes") as mock_gn:
            mock_gn.ahandle_request = AsyncMock(return_value=ReloadAllLibrariesResultSuccess(result_details="ok"))
            mock_gn.WorkflowManager.return_value = mock_workflow_manager

            result = await pm.on_set_current_project_request(SetCurrentProjectRequest(project_id=str(project_file)))

        mock_gn.ahandle_request.assert_called_once()
        mock_workflow_manager.refresh_workflow_registry.assert_not_called()
        assert not result.altered_workflow_state

    @pytest.mark.asyncio
    async def test_initialization_complete_different_workspace_reloads_and_re_registers(self, tmp_path: Path) -> None:
        """When workspace changes, both library reload and workflow re-registration occur."""
        import tempfile
        from unittest.mock import AsyncMock, patch

        from griptape_nodes.retained_mode.events.library_events import (
            ReloadAllLibrariesResultSuccess,
        )

        project_file = tmp_path / "project.yml"
        project_file.touch()
        new_workspace = Path(tempfile.mkdtemp())

        mock_config = Mock()
        mock_config.project_config = {}
        mock_config.env_config = {}
        mock_config.merged_config = {}
        mock_config.get_config_value.return_value = {}

        pm = self._make_project_manager_with_project(project_file, mock_config)
        pm._initialization_complete = True

        # workspace_path returns different values before and after config changes
        old_ws = str(tmp_path / "old_workspace")
        new_ws = str(new_workspace)
        mock_config.workspace_path = old_ws

        from griptape_nodes.retained_mode.events.project_events import SetCurrentProjectRequest

        mock_workflow_manager = Mock()
        with patch("griptape_nodes.retained_mode.managers.project_manager.GriptapeNodes") as mock_gn:
            mock_gn.ahandle_request = AsyncMock(return_value=ReloadAllLibrariesResultSuccess(result_details="ok"))
            mock_gn.WorkflowManager.return_value = mock_workflow_manager

            # Simulate workspace changing after config is applied
            def side_effect_set_workspace_override(_: object) -> None:
                mock_config.workspace_path = new_ws

            mock_config.set_workspace_override.side_effect = side_effect_set_workspace_override

            result = await pm.on_set_current_project_request(SetCurrentProjectRequest(project_id=str(project_file)))

        mock_gn.ahandle_request.assert_called_once()
        mock_workflow_manager.refresh_workflow_registry.assert_called_once()
        assert result.altered_workflow_state

    @pytest.mark.asyncio
    async def test_library_reload_failure_returns_failure(self, tmp_path: Path) -> None:
        """When library reload fails, SetCurrentProjectResultFailure is returned."""
        from unittest.mock import AsyncMock, patch

        from griptape_nodes.retained_mode.events.library_events import (
            ReloadAllLibrariesResultFailure,
        )

        project_file = tmp_path / "project.yml"
        project_file.touch()

        mock_config = Mock()
        mock_config.project_config = {}
        mock_config.env_config = {}
        mock_config.merged_config = {}
        mock_config.get_config_value.return_value = {}
        mock_config.workspace_path = str(tmp_path)

        pm = self._make_project_manager_with_project(project_file, mock_config)
        pm._initialization_complete = True

        from griptape_nodes.retained_mode.events.project_events import (
            SetCurrentProjectRequest,
            SetCurrentProjectResultFailure,
        )

        with patch("griptape_nodes.retained_mode.managers.project_manager.GriptapeNodes") as mock_gn:
            mock_gn.ahandle_request = AsyncMock(
                return_value=ReloadAllLibrariesResultFailure(result_details="reload failed")
            )

            result = await pm.on_set_current_project_request(SetCurrentProjectRequest(project_id=str(project_file)))

        assert isinstance(result, SetCurrentProjectResultFailure)
        assert "reload failed" in str(result.result_details)


class TestRegisterProjectPath:
    """Test ProjectManager._register_project_path."""

    @pytest.fixture
    def pm(self) -> ProjectManager:
        mock_event_manager = Mock()
        mock_config_manager = Mock()
        mock_config_manager.project_config = {}
        mock_config_manager.env_config = {}
        mock_config_manager.merged_config = {}
        mock_config_manager.get_config_value.return_value = []
        return ProjectManager(mock_event_manager, mock_config_manager, Mock())

    def test_register_new_path_appends_to_empty_list(self, pm: ProjectManager) -> None:
        """A new project_id is appended when the registered list is empty."""
        from griptape_nodes.retained_mode.managers.settings import PROJECTS_TO_REGISTER_KEY

        cast("Mock", pm._config_manager).get_config_value.return_value = []
        pm._register_project_path("/path/to/project.yml")
        cast("Mock", pm._config_manager).set_config_value.assert_called_once_with(
            PROJECTS_TO_REGISTER_KEY, ["/path/to/project.yml"]
        )

    def test_register_new_path_appends_to_existing_list(self, pm: ProjectManager) -> None:
        """A new project_id is appended alongside existing registered paths."""
        from griptape_nodes.retained_mode.managers.settings import PROJECTS_TO_REGISTER_KEY

        cast("Mock", pm._config_manager).get_config_value.return_value = ["/path/to/other.yml"]
        pm._register_project_path("/path/to/project.yml")
        cast("Mock", pm._config_manager).set_config_value.assert_called_once_with(
            PROJECTS_TO_REGISTER_KEY, ["/path/to/other.yml", "/path/to/project.yml"]
        )

    def test_register_already_present_does_not_modify_list(self, pm: ProjectManager) -> None:
        """If the project_id is already registered, set_config_value is not called."""
        project_id = "/path/to/project.yml"

        with patch("griptape_nodes.retained_mode.managers.project_manager.GriptapeNodes") as mock_gn:
            mock_config = Mock()
            mock_config.get_config_value.return_value = [project_id]
            mock_gn.ConfigManager.return_value = mock_config

            pm._register_project_path(project_id)

        mock_config.set_config_value.assert_not_called()

    def test_register_exception_is_swallowed(self, pm: ProjectManager) -> None:
        """A config manager exception does not propagate out of _register_project_path."""
        with patch("griptape_nodes.retained_mode.managers.project_manager.GriptapeNodes") as mock_gn:
            mock_config = Mock()
            mock_config.get_config_value.side_effect = RuntimeError("config failure")
            mock_gn.ConfigManager.return_value = mock_config

            # Should not raise
            pm._register_project_path("/path/to/project.yml")


class TestLoadRegisteredProjects:
    """Test ProjectManager._load_registered_projects."""

    VALID_PROJECT_YAML = """\
project_template_schema_version: "0.1.0"
name: Registered Project
situations:
  save_node_output:
    macro: "{outputs}/{file_name_base}.{file_extension}"
    policy:
      on_collision: create_new
      create_dirs: true
"""

    @pytest.fixture
    def pm(self) -> ProjectManager:
        mock_event_manager = Mock()
        mock_config_manager = Mock()
        mock_config_manager.project_config = {}
        mock_config_manager.env_config = {}
        mock_config_manager.merged_config = {}
        mock_config_manager.get_config_value.return_value = []
        return ProjectManager(mock_event_manager, mock_config_manager, Mock())

    def test_empty_list_does_nothing(self, pm: ProjectManager) -> None:
        """An empty projects_to_register list results in no load attempts."""
        with patch("griptape_nodes.retained_mode.managers.project_manager.GriptapeNodes") as mock_gn:
            mock_config = Mock()
            mock_config.get_config_value.return_value = []
            mock_gn.ConfigManager.return_value = mock_config

            with patch.object(pm, "on_load_project_template_request") as mock_load:
                pm._load_registered_projects()
                mock_load.assert_not_called()

    def test_none_config_return_does_nothing(self, pm: ProjectManager) -> None:
        """None from config (treated as empty via 'or []') results in no load attempts."""
        with patch("griptape_nodes.retained_mode.managers.project_manager.GriptapeNodes") as mock_gn:
            mock_config = Mock()
            mock_config.get_config_value.return_value = None
            mock_gn.ConfigManager.return_value = mock_config

            with patch.object(pm, "on_load_project_template_request") as mock_load:
                pm._load_registered_projects()
                mock_load.assert_not_called()

    def test_already_loaded_path_is_skipped(self, pm: ProjectManager, tmp_path: Path) -> None:
        """Paths already in _successfully_loaded_project_templates are not loaded again."""
        from griptape_nodes.common.project_templates import ProjectValidationInfo, ProjectValidationStatus
        from griptape_nodes.common.project_templates.default_project_template import DEFAULT_PROJECT_TEMPLATE
        from griptape_nodes.retained_mode.managers.project_manager import ProjectInfo

        existing_path = str(tmp_path / "existing.yml")
        validation = ProjectValidationInfo(status=ProjectValidationStatus.GOOD)
        situation_schemas = pm._parse_situation_macros(DEFAULT_PROJECT_TEMPLATE.situations, validation)
        directory_schemas = pm._parse_directory_macros(DEFAULT_PROJECT_TEMPLATE.directories, validation)
        project_info = ProjectInfo(
            project_id=existing_path,
            project_file_path=Path(existing_path),
            project_base_dir=tmp_path,
            template=DEFAULT_PROJECT_TEMPLATE,
            validation=validation,
            parsed_situation_schemas=situation_schemas,
            parsed_directory_schemas=directory_schemas,
        )
        pm._successfully_loaded_project_templates[existing_path] = project_info

        with patch("griptape_nodes.retained_mode.managers.project_manager.GriptapeNodes") as mock_gn:
            mock_config = Mock()
            mock_config.get_config_value.return_value = [existing_path]
            mock_gn.ConfigManager.return_value = mock_config

            with patch.object(pm, "on_load_project_template_request") as mock_load:
                pm._load_registered_projects()
                mock_load.assert_not_called()

    def test_unloaded_path_is_loaded(self, pm: ProjectManager, tmp_path: Path) -> None:
        """A path not already in memory gets loaded and added to the template registry."""
        from griptape_nodes.retained_mode.events.os_events import ReadFileResultSuccess
        from griptape_nodes.retained_mode.managers.settings import PROJECTS_TO_REGISTER_KEY

        project_path = tmp_path / "project.yml"
        yaml_content = self.VALID_PROJECT_YAML

        def get_config_value_side_effect(key: str, **_: object) -> object:
            if key == PROJECTS_TO_REGISTER_KEY:
                return [str(project_path)]
            return []  # for _register_project_path's follow-on call

        cast("Mock", pm._config_manager).get_config_value.side_effect = get_config_value_side_effect

        with patch("griptape_nodes.retained_mode.managers.project_manager.GriptapeNodes") as mock_gn:
            mock_gn.handle_request.return_value = ReadFileResultSuccess(
                content=yaml_content,
                file_size=len(yaml_content),
                mime_type="text/plain",
                encoding="utf-8",
                result_details="ok",
            )

            pm._load_registered_projects()

        assert str(project_path) in pm._successfully_loaded_project_templates

    def test_load_failure_is_logged_as_warning(
        self, pm: ProjectManager, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """A failed load is logged as a warning and does not raise."""
        from griptape_nodes.common.project_templates import ProjectValidationInfo, ProjectValidationStatus
        from griptape_nodes.retained_mode.events.project_events import LoadProjectTemplateResultFailure

        project_path = str(tmp_path / "missing.yml")
        failure = LoadProjectTemplateResultFailure(
            validation=ProjectValidationInfo(status=ProjectValidationStatus.MISSING),
            result_details="file not found",
        )

        cast("Mock", pm._config_manager).get_config_value.return_value = [project_path]

        with (
            patch.object(pm, "on_load_project_template_request", return_value=failure),
            caplog.at_level(logging.WARNING, logger="griptape_nodes"),
        ):
            pm._load_registered_projects()

        assert project_path not in pm._successfully_loaded_project_templates
        warning_messages = [r.message for r in caplog.records if r.levelno == logging.WARNING]
        assert any("Failed to load registered project" in msg for msg in warning_messages)

    @pytest.mark.asyncio
    async def test_app_initialization_complete_loads_registered_projects(
        self, pm: ProjectManager, tmp_path: Path
    ) -> None:
        """on_app_initialization_complete loads registered projects after the workspace project."""
        from griptape_nodes.retained_mode.events.app_events import AppInitializationComplete
        from griptape_nodes.retained_mode.events.os_events import ReadFileResultSuccess
        from griptape_nodes.retained_mode.managers.settings import PROJECTS_TO_REGISTER_KEY

        registered_path = tmp_path / "registered.yml"
        yaml_content = self.VALID_PROJECT_YAML

        def get_config_value_side_effect(key: str, **_: object) -> object:
            if key == "project_file":
                return None
            if key == PROJECTS_TO_REGISTER_KEY:
                return [str(registered_path)]
            if "project_workspaces" in key:
                return {}
            return str(tmp_path)

        cast("Mock", pm._config_manager).get_config_value.side_effect = get_config_value_side_effect
        cast("Mock", pm._config_manager).workspace_path = tmp_path

        with patch("griptape_nodes.retained_mode.managers.project_manager.GriptapeNodes") as mock_gn:
            mock_gn.handle_request.return_value = ReadFileResultSuccess(
                content=yaml_content,
                file_size=len(yaml_content),
                mime_type="text/plain",
                encoding="utf-8",
                result_details="ok",
            )

            await pm.on_app_initialization_complete(AppInitializationComplete())

        assert str(registered_path) in pm._successfully_loaded_project_templates


class TestValidateProjectTemplate:
    """Test ProjectManager.on_validate_project_template_request."""

    @pytest.fixture
    def pm(self) -> ProjectManager:
        mock_event_manager = Mock()
        mock_config_manager = Mock()
        mock_config_manager.project_config = {}
        mock_config_manager.env_config = {}
        mock_config_manager.merged_config = {}
        mock_config_manager.get_config_value.return_value = []
        return ProjectManager(mock_event_manager, mock_config_manager, Mock())

    @staticmethod
    def _minimal_valid_template() -> dict:
        return {
            "project_template_schema_version": "0.1.0",
            "name": "Test Project",
            "situations": {
                "save_file": {
                    "name": "save_file",
                    "macro": "{file_name_base}.{file_extension}",
                    "policy": {"on_collision": "create_new", "create_dirs": True},
                }
            },
            "directories": {
                "inputs": {"name": "inputs", "path_macro": "inputs"},
            },
        }

    def test_valid_template_returns_good_status(self, pm: ProjectManager) -> None:
        """A fully valid template validates with GOOD status and no problems."""
        from griptape_nodes.common.project_templates import ProjectValidationStatus
        from griptape_nodes.retained_mode.events.project_events import (
            ValidateProjectTemplateRequest,
            ValidateProjectTemplateResultSuccess,
        )

        request = ValidateProjectTemplateRequest(template_data=self._minimal_valid_template())
        result = pm.on_validate_project_template_request(request)

        assert isinstance(result, ValidateProjectTemplateResultSuccess)
        assert result.validation.status == ProjectValidationStatus.GOOD
        assert result.validation.problems == []

    def test_partial_policy_marks_template_unusable(self, pm: ProjectManager) -> None:
        """A situation policy missing on_collision should produce an UNUSABLE result."""
        from griptape_nodes.common.project_templates import ProjectValidationStatus
        from griptape_nodes.retained_mode.events.project_events import (
            ValidateProjectTemplateRequest,
            ValidateProjectTemplateResultSuccess,
        )

        template = self._minimal_valid_template()
        template["situations"]["save_file"]["policy"] = {"create_dirs": False}

        request = ValidateProjectTemplateRequest(template_data=template)
        result = pm.on_validate_project_template_request(request)

        assert isinstance(result, ValidateProjectTemplateResultSuccess)
        assert result.validation.status == ProjectValidationStatus.UNUSABLE
        assert any("situations.save_file.policy" in p.field_path for p in result.validation.problems)

    def test_invalid_directory_macro_marks_template_unusable(self, pm: ProjectManager) -> None:
        """A directory with an unparsable path_macro should produce a problem."""
        from griptape_nodes.common.project_templates import ProjectValidationStatus
        from griptape_nodes.retained_mode.events.project_events import (
            ValidateProjectTemplateRequest,
            ValidateProjectTemplateResultSuccess,
        )

        template = self._minimal_valid_template()
        # Unmatched brace is rejected by the macro parser
        template["directories"]["inputs"]["path_macro"] = "inputs/{unclosed"

        request = ValidateProjectTemplateRequest(template_data=template)
        result = pm.on_validate_project_template_request(request)

        assert isinstance(result, ValidateProjectTemplateResultSuccess)
        assert result.validation.status == ProjectValidationStatus.UNUSABLE
        assert any(p.field_path == "directories.inputs.path_macro" for p in result.validation.problems)

    def test_missing_name_marks_template_unusable(self, pm: ProjectManager) -> None:
        """Missing required `name` field returns UNUSABLE with a structured problem."""
        from griptape_nodes.common.project_templates import ProjectValidationStatus
        from griptape_nodes.retained_mode.events.project_events import (
            ValidateProjectTemplateRequest,
            ValidateProjectTemplateResultSuccess,
        )

        template = self._minimal_valid_template()
        del template["name"]

        request = ValidateProjectTemplateRequest(template_data=template)
        result = pm.on_validate_project_template_request(request)

        assert isinstance(result, ValidateProjectTemplateResultSuccess)
        assert result.validation.status == ProjectValidationStatus.UNUSABLE
        assert any(p.field_path == "name" for p in result.validation.problems)

    def test_pydantic_errors_surface_as_structured_problems(self, pm: ProjectManager) -> None:
        """Pydantic validation errors produce per-field problems, not a stringified exception."""
        from griptape_nodes.retained_mode.events.project_events import (
            ValidateProjectTemplateRequest,
            ValidateProjectTemplateResultSuccess,
        )

        template = self._minimal_valid_template()
        # Provide a bogus policy value to trigger a pydantic validator for the enum
        template["situations"]["save_file"]["policy"] = {
            "on_collision": "not_a_real_value",
            "create_dirs": True,
        }

        request = ValidateProjectTemplateRequest(template_data=template)
        result = pm.on_validate_project_template_request(request)

        assert isinstance(result, ValidateProjectTemplateResultSuccess)
        assert len(result.validation.problems) >= 1
        problem = result.validation.problems[0]
        assert problem.field_path.startswith("situations.save_file.policy")
        assert problem.message  # non-empty message


class TestLoadProjectTemplatePathCanonicalization:
    """Test that on_load_project_template_request canonicalizes project paths.

    Project IDs and validation-map keys must be keyed off the resolved absolute
    path so the same file loaded via different spellings (relative vs absolute,
    with or without trailing components, etc.) collapses to a single entry.
    """

    VALID_PROJECT_YAML = """\
project_template_schema_version: "0.1.0"
name: Canonicalization Test
situations:
  save_node_output:
    macro: "{outputs}/{file_name_base}.{file_extension}"
    policy:
      on_collision: create_new
      create_dirs: true
"""

    @pytest.fixture
    def pm(self) -> ProjectManager:
        mock_event_manager = Mock()
        mock_config_manager = Mock()
        mock_config_manager.project_config = {}
        mock_config_manager.env_config = {}
        mock_config_manager.merged_config = {}
        mock_config_manager.get_config_value.return_value = []
        return ProjectManager(mock_event_manager, mock_config_manager, Mock())

    def test_relative_and_absolute_spellings_share_project_id(self, pm: ProjectManager, tmp_path: Path) -> None:
        """Loading the same file via a relative and an absolute path produces one entry."""
        from griptape_nodes.retained_mode.events.os_events import ReadFileResultSuccess
        from griptape_nodes.retained_mode.events.project_events import (
            LoadProjectTemplateRequest,
            LoadProjectTemplateResultSuccess,
        )

        absolute_path = (tmp_path / "project.yml").resolve()

        with patch("griptape_nodes.retained_mode.managers.project_manager.GriptapeNodes") as mock_gn:
            mock_gn.handle_request.return_value = ReadFileResultSuccess(
                content=self.VALID_PROJECT_YAML,
                file_size=len(self.VALID_PROJECT_YAML),
                mime_type="text/plain",
                encoding="utf-8",
                result_details="ok",
            )

            cwd = Path.cwd()
            try:
                os.chdir(tmp_path)
                relative_path = Path("project.yml")
                absolute_result = pm.on_load_project_template_request(
                    LoadProjectTemplateRequest(project_path=absolute_path)
                )
                relative_result = pm.on_load_project_template_request(
                    LoadProjectTemplateRequest(project_path=relative_path)
                )
            finally:
                os.chdir(cwd)

        assert isinstance(absolute_result, LoadProjectTemplateResultSuccess)
        assert isinstance(relative_result, LoadProjectTemplateResultSuccess)
        assert absolute_result.project_id == relative_result.project_id
        assert absolute_result.project_id == str(absolute_path)
        assert list(pm._successfully_loaded_project_templates.keys()).count(str(absolute_path)) == 1

    def test_registered_template_status_keyed_by_resolved_path(self, pm: ProjectManager, tmp_path: Path) -> None:
        """Validation status is stored under the resolved path, not the raw input."""
        from griptape_nodes.retained_mode.events.project_events import LoadProjectTemplateRequest

        absolute_path = (tmp_path / "missing.yml").resolve()

        cwd = Path.cwd()
        try:
            os.chdir(tmp_path)
            pm.on_load_project_template_request(LoadProjectTemplateRequest(project_path=Path("missing.yml")))
        finally:
            os.chdir(cwd)

        assert absolute_path in pm._registered_template_status
        assert Path("missing.yml") not in pm._registered_template_status

    def test_tilde_and_absolute_spellings_share_project_id(
        self, pm: ProjectManager, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Loading the same file via `~/...` and its absolute path produces one entry."""
        from griptape_nodes.retained_mode.events.os_events import ReadFileResultSuccess
        from griptape_nodes.retained_mode.events.project_events import (
            LoadProjectTemplateRequest,
            LoadProjectTemplateResultSuccess,
        )

        # Point HOME/USERPROFILE at tmp_path so "~/project.yml" expands to tmp_path / project.yml
        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.setenv("USERPROFILE", str(tmp_path))
        absolute_path = (tmp_path / "project.yml").resolve()
        tilde_path = Path("~/project.yml")

        with patch("griptape_nodes.retained_mode.managers.project_manager.GriptapeNodes") as mock_gn:
            mock_gn.handle_request.return_value = ReadFileResultSuccess(
                content=self.VALID_PROJECT_YAML,
                file_size=len(self.VALID_PROJECT_YAML),
                mime_type="text/plain",
                encoding="utf-8",
                result_details="ok",
            )

            absolute_result = pm.on_load_project_template_request(
                LoadProjectTemplateRequest(project_path=absolute_path)
            )
            tilde_result = pm.on_load_project_template_request(LoadProjectTemplateRequest(project_path=tilde_path))

        assert isinstance(absolute_result, LoadProjectTemplateResultSuccess)
        assert isinstance(tilde_result, LoadProjectTemplateResultSuccess)
        assert absolute_result.project_id == tilde_result.project_id
        assert absolute_result.project_id == str(absolute_path)
        assert list(pm._successfully_loaded_project_templates.keys()).count(str(absolute_path)) == 1


class TestRegisterProjectPathCanonicalization:
    """Test that _register_project_path dedupes across path spellings."""

    @pytest.fixture
    def pm(self) -> ProjectManager:
        mock_event_manager = Mock()
        mock_config_manager = Mock()
        mock_config_manager.project_config = {}
        mock_config_manager.env_config = {}
        mock_config_manager.merged_config = {}
        mock_config_manager.get_config_value.return_value = []
        return ProjectManager(mock_event_manager, mock_config_manager, Mock())

    def test_already_registered_under_different_spelling_is_not_reappended(
        self, pm: ProjectManager, tmp_path: Path
    ) -> None:
        """If the same file is already persisted under a different spelling, skip it."""
        absolute_path = (tmp_path / "project.yml").resolve()

        cwd = Path.cwd()
        try:
            os.chdir(tmp_path)
            relative_spelling = str(Path("project.yml").resolve())
            cast("Mock", pm._config_manager).get_config_value.return_value = [relative_spelling]
            pm._register_project_path(str(absolute_path))
        finally:
            os.chdir(cwd)

        cast("Mock", pm._config_manager).set_config_value.assert_not_called()

    def test_tilde_spelling_dedupes_against_absolute_entry(
        self, pm: ProjectManager, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A ~-spelled persisted path is matched against an absolute incoming one."""
        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.setenv("USERPROFILE", str(tmp_path))
        absolute_path = (tmp_path / "project.yml").resolve()
        cast("Mock", pm._config_manager).get_config_value.return_value = ["~/project.yml"]

        pm._register_project_path(str(absolute_path))

        cast("Mock", pm._config_manager).set_config_value.assert_not_called()


class TestLoadRegisteredProjectsCanonicalization:
    """Test that _load_registered_projects treats differently-spelled persisted paths as duplicates."""

    @pytest.fixture
    def pm(self) -> ProjectManager:
        mock_event_manager = Mock()
        mock_config_manager = Mock()
        mock_config_manager.project_config = {}
        mock_config_manager.env_config = {}
        mock_config_manager.merged_config = {}
        mock_config_manager.get_config_value.return_value = []
        return ProjectManager(mock_event_manager, mock_config_manager, Mock())

    def test_persisted_unresolved_path_matches_loaded_resolved_entry(self, pm: ProjectManager, tmp_path: Path) -> None:
        """A persisted path is matched against _successfully_loaded_project_templates after resolution."""
        from griptape_nodes.common.project_templates import ProjectValidationInfo, ProjectValidationStatus
        from griptape_nodes.common.project_templates.default_project_template import DEFAULT_PROJECT_TEMPLATE
        from griptape_nodes.retained_mode.managers.project_manager import ProjectInfo

        resolved_path = (tmp_path / "existing.yml").resolve()
        validation = ProjectValidationInfo(status=ProjectValidationStatus.GOOD)
        situation_schemas = pm._parse_situation_macros(DEFAULT_PROJECT_TEMPLATE.situations, validation)
        directory_schemas = pm._parse_directory_macros(DEFAULT_PROJECT_TEMPLATE.directories, validation)
        project_info = ProjectInfo(
            project_id=str(resolved_path),
            project_file_path=resolved_path,
            project_base_dir=tmp_path,
            template=DEFAULT_PROJECT_TEMPLATE,
            validation=validation,
            parsed_situation_schemas=situation_schemas,
            parsed_directory_schemas=directory_schemas,
        )
        pm._successfully_loaded_project_templates[str(resolved_path)] = project_info

        cwd = Path.cwd()
        try:
            os.chdir(tmp_path)
            cast("Mock", pm._config_manager).get_config_value.return_value = ["existing.yml"]
            with patch.object(pm, "on_load_project_template_request") as mock_load:
                pm._load_registered_projects()
        finally:
            os.chdir(cwd)

        mock_load.assert_not_called()
