"""Tests for ProjectManager macro event handlers."""

from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from griptape_nodes.common.macro_parser import MacroMatchFailureReason
from griptape_nodes.retained_mode.events.project_events import (
    GetPathForMacroRequest,
    GetPathForMacroResultFailure,
    GetPathForMacroResultSuccess,
    GetVariablesForMacroRequest,
    MatchPathAgainstMacroRequest,
    MatchPathAgainstMacroResultFailure,
    PathResolutionFailureReason,
    ValidateMacroSyntaxRequest,
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
        from griptape_nodes.retained_mode.events.project_events import MatchPathAgainstMacroResultSuccess

        request = MatchPathAgainstMacroRequest(
            project_path=Path("/test/project.yml"),
            macro_schema="{inputs}/{file_name}.{ext}",
            file_path="inputs/render.png",
            known_variables={"inputs": "inputs"},
        )

        result = project_manager.on_match_path_against_macro_request(request)

        assert isinstance(result, MatchPathAgainstMacroResultSuccess)
        assert result.extracted_variables == {"inputs": "inputs", "file_name": "render", "ext": "png"}

    def test_get_variables_for_macro_success(self, project_manager: ProjectManager) -> None:
        """Test GetVariablesForMacro extracts variables."""
        from griptape_nodes.retained_mode.events.project_events import GetVariablesForMacroResultSuccess

        request = GetVariablesForMacroRequest(
            macro_schema="{inputs}/{file_name}.{ext}",
        )

        result = project_manager.on_get_variables_for_macro_request(request)

        assert isinstance(result, GetVariablesForMacroResultSuccess)
        var_names = {v.name for v in result.variables}
        assert var_names == {"inputs", "file_name", "ext"}

    def test_validate_macro_syntax_success(self, project_manager: ProjectManager) -> None:
        """Test ValidateMacroSyntax validates valid macro."""
        from griptape_nodes.retained_mode.events.project_events import ValidateMacroSyntaxResultSuccess

        request = ValidateMacroSyntaxRequest(
            macro_schema="{inputs}/{file_name}.{ext}",
        )

        result = project_manager.on_validate_macro_syntax_request(request)

        assert isinstance(result, ValidateMacroSyntaxResultSuccess)
        var_names = {v.name for v in result.variables}
        assert var_names == {"inputs", "file_name", "ext"}
        assert result.warnings == set()

    def test_match_path_mismatch(self, project_manager: ProjectManager) -> None:
        """Test that MatchPathAgainstMacro returns failure when path doesn't match."""
        known_vars: dict[str, str | int] = {"inputs": "outputs", "ext": "png"}
        request = MatchPathAgainstMacroRequest(
            project_path=Path("/test/project.yml"),
            macro_schema="{inputs}/{file_name}.{ext}",
            file_path="wrong_folder/render.png",
            known_variables=known_vars,
        )

        result = project_manager.on_match_path_against_macro_request(request)

        assert isinstance(result, MatchPathAgainstMacroResultFailure)
        assert result.match_failure.failure_reason == MacroMatchFailureReason.STATIC_TEXT_MISMATCH
        assert result.match_failure.known_variables_used == known_vars

    def test_match_path_empty_known_variables(self, project_manager: ProjectManager) -> None:
        """Test MatchPathAgainstMacro with empty known_variables."""
        from griptape_nodes.retained_mode.events.project_events import MatchPathAgainstMacroResultSuccess

        request = MatchPathAgainstMacroRequest(
            project_path=Path("/test/project.yml"),
            macro_schema="{file_name}",
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

        assert pm.registered_template_status == {}
        assert pm.successful_templates == {}
        assert pm.parsed_situation_schemas == {}
        assert pm.parsed_directory_schemas == {}
        assert pm.current_project_path is None

    def test_project_manager_stores_manager_references(self) -> None:
        """Test ProjectManager stores config and secrets manager references."""
        mock_config = Mock()
        mock_secrets = Mock()
        mock_event_manager = Mock()

        pm = ProjectManager(mock_event_manager, mock_config, mock_secrets)

        assert pm.config_manager is mock_config
        assert pm.secrets_manager is mock_secrets


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
        pm.successful_templates[project_path] = DEFAULT_PROJECT_TEMPLATE

        return pm

    def test_builtin_project_dir_resolves_correctly(self, project_manager_with_template: ProjectManager) -> None:
        """Test that {project_dir} builtin resolves to project_path.parent."""
        project_path = Path("/test/project.yml")

        request = GetPathForMacroRequest(
            project_path=project_path, macro_schema="{project_dir}/output.txt", variables={}
        )

        result = project_manager_with_template.on_get_path_for_macro_request(request)

        assert isinstance(result, GetPathForMacroResultSuccess)
        assert result.resolved_path == Path("/test/output.txt")

    @patch("griptape_nodes.retained_mode.managers.project_manager.GriptapeNodes")
    def test_builtin_workspace_dir_resolves_correctly(
        self, mock_griptape_nodes: Mock, project_manager_with_template: ProjectManager
    ) -> None:
        """Test that {workspace_dir} builtin resolves from ConfigManager."""
        mock_config_manager = Mock()
        mock_config_manager.get_config_value.return_value = "/workspace"
        mock_griptape_nodes.ConfigManager.return_value = mock_config_manager

        project_path = Path("/test/project.yml")

        request = GetPathForMacroRequest(
            project_path=project_path, macro_schema="{workspace_dir}/output.txt", variables={}
        )

        result = project_manager_with_template.on_get_path_for_macro_request(request)

        assert isinstance(result, GetPathForMacroResultSuccess)
        assert result.resolved_path == Path("/workspace/output.txt")
        mock_config_manager.get_config_value.assert_called_once_with("workspace.directory")

    @patch("griptape_nodes.retained_mode.managers.project_manager.GriptapeNodes")
    def test_builtin_workflow_name_resolves_correctly(
        self, mock_griptape_nodes: Mock, project_manager_with_template: ProjectManager
    ) -> None:
        """Test that {workflow_name} builtin resolves from ContextManager."""
        mock_context_manager = Mock()
        mock_context_manager.has_current_workflow.return_value = True
        mock_context_manager.get_current_workflow_name.return_value = "my_workflow"
        mock_griptape_nodes.ContextManager.return_value = mock_context_manager

        project_path = Path("/test/project.yml")

        request = GetPathForMacroRequest(
            project_path=project_path, macro_schema="{workflow_name}_output.txt", variables={}
        )

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
        mock_context_manager = Mock()
        mock_context_manager.has_current_workflow.return_value = False
        mock_griptape_nodes.ContextManager.return_value = mock_context_manager

        project_path = Path("/test/project.yml")

        request = GetPathForMacroRequest(
            project_path=project_path, macro_schema="{workflow_name}_output.txt", variables={}
        )

        result = project_manager_with_template.on_get_path_for_macro_request(request)

        assert isinstance(result, GetPathForMacroResultFailure)
        assert result.failure_reason == PathResolutionFailureReason.MACRO_RESOLUTION_ERROR
        assert result.error_details is not None
        assert "No current workflow" in result.error_details

    def test_builtin_project_name_not_implemented(self, project_manager_with_template: ProjectManager) -> None:
        """Test that {project_name} raises NotImplementedError."""
        project_path = Path("/test/project.yml")

        request = GetPathForMacroRequest(
            project_path=project_path, macro_schema="{project_name}/output.txt", variables={}
        )

        result = project_manager_with_template.on_get_path_for_macro_request(request)

        assert isinstance(result, GetPathForMacroResultFailure)
        assert result.failure_reason == PathResolutionFailureReason.MACRO_RESOLUTION_ERROR
        assert result.error_details is not None
        assert "project_name not yet implemented" in result.error_details

    def test_builtin_workflow_dir_not_implemented(self, project_manager_with_template: ProjectManager) -> None:
        """Test that {workflow_dir} raises NotImplementedError."""
        project_path = Path("/test/project.yml")

        request = GetPathForMacroRequest(
            project_path=project_path, macro_schema="{workflow_dir}/output.txt", variables={}
        )

        result = project_manager_with_template.on_get_path_for_macro_request(request)

        assert isinstance(result, GetPathForMacroResultFailure)
        assert result.failure_reason == PathResolutionFailureReason.MACRO_RESOLUTION_ERROR
        assert result.error_details is not None
        assert "workflow_dir not yet implemented" in result.error_details

    def test_builtin_override_matching_value_allowed(self, project_manager_with_template: ProjectManager) -> None:
        """Test that providing matching value for builtin variable is allowed."""
        project_path = Path("/test/project.yml")

        request = GetPathForMacroRequest(
            project_path=project_path,
            macro_schema="{project_dir}/output.txt",
            variables={"project_dir": "/test"},
        )

        result = project_manager_with_template.on_get_path_for_macro_request(request)

        assert isinstance(result, GetPathForMacroResultSuccess)
        assert result.resolved_path == Path("/test/output.txt")

    def test_builtin_override_different_value_rejected(self, project_manager_with_template: ProjectManager) -> None:
        """Test that providing different value for builtin variable is rejected."""
        project_path = Path("/test/project.yml")

        request = GetPathForMacroRequest(
            project_path=project_path,
            macro_schema="{project_dir}/output.txt",
            variables={"project_dir": "/different"},
        )

        result = project_manager_with_template.on_get_path_for_macro_request(request)

        assert isinstance(result, GetPathForMacroResultFailure)
        assert result.failure_reason == PathResolutionFailureReason.DIRECTORY_OVERRIDE_ATTEMPTED
        assert result.conflicting_variables == {"project_dir"}
        from griptape_nodes.retained_mode.events.base_events import ResultDetails

        assert isinstance(result.result_details, ResultDetails)
        assert "Cannot override builtin variables" in str(result.result_details)
