"""Tests for ProjectManager macro event handlers."""

import os
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from griptape_nodes.common.macro_parser import MacroMatchFailureReason
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

    @patch("griptape_nodes.retained_mode.managers.project_manager.GriptapeNodes")
    def test_builtin_workspace_dir_resolves_correctly(
        self, mock_griptape_nodes: Mock, project_manager_with_template: ProjectManager
    ) -> None:
        """Test that {workspace_dir} builtin resolves from ConfigManager."""
        from griptape_nodes.common.macro_parser import ParsedMacro

        mock_config_manager = Mock()
        mock_config_manager.get_config_value.return_value = "/workspace"
        mock_griptape_nodes.ConfigManager.return_value = mock_config_manager

        parsed_macro = ParsedMacro("{workspace_dir}/output.txt")

        request = GetPathForMacroRequest(parsed_macro=parsed_macro, variables={})

        result = project_manager_with_template.on_get_path_for_macro_request(request)

        assert isinstance(result, GetPathForMacroResultSuccess)
        assert result.resolved_path == Path("/workspace/output.txt")
        mock_config_manager.get_config_value.assert_called_once_with("workspace_directory")

    @patch("griptape_nodes.retained_mode.managers.project_manager.GriptapeNodes")
    def test_builtin_workflow_name_resolves_correctly(
        self, mock_griptape_nodes: Mock, project_manager_with_template: ProjectManager
    ) -> None:
        """Test that {workflow_name} builtin resolves from ContextManager."""
        from griptape_nodes.common.macro_parser import ParsedMacro

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

    def test_builtin_workflow_dir_not_implemented(self, project_manager_with_template: ProjectManager) -> None:
        """Test that {workflow_dir} raises NotImplementedError."""
        from griptape_nodes.common.macro_parser import ParsedMacro

        parsed_macro = ParsedMacro("{workflow_dir}/output.txt")

        request = GetPathForMacroRequest(parsed_macro=parsed_macro, variables={})

        result = project_manager_with_template.on_get_path_for_macro_request(request)

        assert isinstance(result, GetPathForMacroResultFailure)
        assert result.failure_reason == PathResolutionFailureReason.MACRO_RESOLUTION_ERROR
        from griptape_nodes.retained_mode.events.base_events import ResultDetails

        assert isinstance(result.result_details, ResultDetails)
        assert "workflow_dir not yet implemented" in str(result.result_details)

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

        # Mock GriptapeNodes.ConfigManager(), ContextManager(), and OSManager()
        with patch("griptape_nodes.retained_mode.managers.project_manager.GriptapeNodes") as mock_gn:
            mock_config = Mock()
            mock_config.get_config_value.return_value = str(project_base)  # workspace_dir
            mock_gn.ConfigManager.return_value = mock_config

            mock_context = Mock()
            mock_context.has_current_workflow.return_value = False  # No workflow needed for this test
            mock_gn.ContextManager.return_value = mock_context

            # Mock OSManager - use real resolve_path_safely implementation
            from griptape_nodes.retained_mode.managers.os_manager import OSManager
            mock_os_manager = Mock(spec=OSManager)
            mock_os_manager.resolve_path_safely.side_effect = lambda p: Path(os.path.normpath(p if p.is_absolute() else Path.cwd() / p))
            mock_gn.OSManager.return_value = mock_os_manager

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

        # Mock GriptapeNodes.ConfigManager() and ContextManager()
        with patch("griptape_nodes.retained_mode.managers.project_manager.GriptapeNodes") as mock_gn:
            mock_config = Mock()
            mock_config.get_config_value.return_value = str(project_base)  # workspace_dir
            mock_gn.ConfigManager.return_value = mock_config

            mock_context = Mock()
            mock_context.has_current_workflow.return_value = False  # No workflow needed for this test
            mock_gn.ContextManager.return_value = mock_context

            # Mock OSManager - use real resolve_path_safely implementation
            from griptape_nodes.retained_mode.managers.os_manager import OSManager
            mock_os_manager = Mock(spec=OSManager)
            mock_os_manager.resolve_path_safely.side_effect = lambda p: Path(os.path.normpath(p if p.is_absolute() else Path.cwd() / p))
            mock_gn.OSManager.return_value = mock_os_manager

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

        # Mock GriptapeNodes.ConfigManager() and ContextManager()
        with patch("griptape_nodes.retained_mode.managers.project_manager.GriptapeNodes") as mock_gn:
            mock_config = Mock()
            mock_config.get_config_value.return_value = str(project_base)  # workspace_dir
            mock_gn.ConfigManager.return_value = mock_config

            mock_context = Mock()
            mock_context.has_current_workflow.return_value = False  # No workflow needed for this test
            mock_gn.ContextManager.return_value = mock_context

            # Mock OSManager - use real resolve_path_safely implementation
            from griptape_nodes.retained_mode.managers.os_manager import OSManager
            mock_os_manager = Mock(spec=OSManager)
            mock_os_manager.resolve_path_safely.side_effect = lambda p: Path(os.path.normpath(p if p.is_absolute() else Path.cwd() / p))
            mock_gn.OSManager.return_value = mock_os_manager

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

        # Mock GriptapeNodes.ConfigManager() and ContextManager()
        with patch("griptape_nodes.retained_mode.managers.project_manager.GriptapeNodes") as mock_gn:
            mock_config = Mock()
            mock_config.get_config_value.return_value = str(project_base)  # workspace_dir
            mock_gn.ConfigManager.return_value = mock_config

            mock_context = Mock()
            mock_context.has_current_workflow.return_value = False  # No workflow needed for this test
            mock_gn.ContextManager.return_value = mock_context

            # Mock OSManager - use real resolve_path_safely implementation
            from griptape_nodes.retained_mode.managers.os_manager import OSManager
            mock_os_manager = Mock(spec=OSManager)
            mock_os_manager.resolve_path_safely.side_effect = lambda p: Path(os.path.normpath(p if p.is_absolute() else Path.cwd() / p))
            mock_gn.OSManager.return_value = mock_os_manager

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

        # Mock GriptapeNodes.ConfigManager() and ContextManager()
        with patch("griptape_nodes.retained_mode.managers.project_manager.GriptapeNodes") as mock_gn:
            mock_config = Mock()
            mock_config.get_config_value.return_value = str(project_base)
            mock_gn.ConfigManager.return_value = mock_config

            mock_context = Mock()
            mock_context.has_current_workflow.return_value = False
            mock_gn.ContextManager.return_value = mock_context

            # Mock OSManager - use real resolve_path_safely implementation
            from griptape_nodes.retained_mode.managers.os_manager import OSManager
            mock_os_manager = Mock(spec=OSManager)
            mock_os_manager.resolve_path_safely.side_effect = lambda p: Path(os.path.normpath(p if p.is_absolute() else Path.cwd() / p))
            mock_gn.OSManager.return_value = mock_os_manager

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

        # Mock GriptapeNodes - workflow_name will fail because no workflow
        with patch("griptape_nodes.retained_mode.managers.project_manager.GriptapeNodes") as mock_gn:
            mock_config = Mock()
            mock_config.get_config_value.return_value = str(project_base)
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
