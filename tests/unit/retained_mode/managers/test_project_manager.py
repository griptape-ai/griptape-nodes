"""Tests for ProjectManager macro event handlers."""

from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from griptape_nodes.common.macro_parser import MacroMatchFailureReason
from griptape_nodes.retained_mode.events.project_events import (
    GetPathForMacroRequest,
    GetPathForMacroResultFailure,
    GetPathForMacroResultSuccess,
    GetStateForMacroRequest,
    GetStateForMacroResultFailure,
    GetStateForMacroResultSuccess,
    MatchPathAgainstMacroRequest,
    MatchPathAgainstMacroResultFailure,
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
        """Test MatchPathAgainstMacro successfully matches path."""
        from griptape_nodes.common.macro_parser import ParsedMacro
        from griptape_nodes.retained_mode.events.project_events import MatchPathAgainstMacroResultSuccess

        parsed_macro = ParsedMacro("{inputs}/{file_name}.{ext}")

        request = MatchPathAgainstMacroRequest(
            parsed_macro=parsed_macro,
            file_path="inputs/render.png",
            known_variables={"inputs": "inputs"},
        )

        result = project_manager.on_match_path_against_macro_request(request)

        assert isinstance(result, MatchPathAgainstMacroResultSuccess)
        assert result.extracted_variables == {"inputs": "inputs", "file_name": "render", "ext": "png"}

    def test_match_path_mismatch(self, project_manager: ProjectManager) -> None:
        """Test that MatchPathAgainstMacro returns failure when path doesn't match."""
        from griptape_nodes.common.macro_parser import ParsedMacro

        known_vars: dict[str, str | int] = {"inputs": "outputs", "ext": "png"}
        parsed_macro = ParsedMacro("{inputs}/{file_name}.{ext}")

        request = MatchPathAgainstMacroRequest(
            parsed_macro=parsed_macro,
            file_path="wrong_folder/render.png",
            known_variables=known_vars,
        )

        result = project_manager.on_match_path_against_macro_request(request)

        assert isinstance(result, MatchPathAgainstMacroResultFailure)
        assert result.match_failure.failure_reason == MacroMatchFailureReason.STATIC_TEXT_MISMATCH
        assert result.match_failure.known_variables_used == known_vars

    def test_match_path_empty_known_variables(self, project_manager: ProjectManager) -> None:
        """Test MatchPathAgainstMacro with empty known_variables."""
        from griptape_nodes.common.macro_parser import ParsedMacro
        from griptape_nodes.retained_mode.events.project_events import MatchPathAgainstMacroResultSuccess

        parsed_macro = ParsedMacro("{file_name}")

        request = MatchPathAgainstMacroRequest(
            parsed_macro=parsed_macro,
            file_path="test.txt",
            known_variables={},
        )

        result = project_manager.on_match_path_against_macro_request(request)

        assert isinstance(result, MatchPathAgainstMacroResultSuccess)
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
        assert pm._successful_templates == {}
        assert pm._parsed_situation_schemas == {}
        assert pm._parsed_directory_schemas == {}
        assert pm._current_project_path is None

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
        from griptape_nodes.common.project_templates.default_project_template import DEFAULT_PROJECT_TEMPLATE

        mock_config = Mock()
        mock_secrets = Mock()
        mock_event_manager = Mock()
        pm = ProjectManager(mock_event_manager, mock_config, mock_secrets)

        project_path = Path("/test/project.yml")
        pm._successful_templates[project_path] = DEFAULT_PROJECT_TEMPLATE
        pm._current_project_path = project_path

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
        mock_config_manager.get_config_value.assert_called_once_with("workspace.directory")

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
        from griptape_nodes.common.project_templates.default_project_template import DEFAULT_PROJECT_TEMPLATE

        mock_config = Mock()
        mock_secrets = Mock()
        mock_event_manager = Mock()
        pm = ProjectManager(mock_event_manager, mock_config, mock_secrets)

        project_path = Path("/test/project.yml")
        pm._successful_templates[project_path] = DEFAULT_PROJECT_TEMPLATE
        pm._current_project_path = project_path

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
