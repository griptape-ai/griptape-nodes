"""Tests for ProjectManager macro event handlers."""

from pathlib import Path
from unittest.mock import Mock

import pytest

from griptape_nodes.common.macro_parser import MacroMatchFailureReason
from griptape_nodes.retained_mode.events.project_events import (
    GetVariablesForMacroRequest,
    MatchPathAgainstMacroRequest,
    MatchPathAgainstMacroResultFailure,
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
        var_names = [v.name for v in result.variables]
        assert var_names == ["inputs", "file_name", "ext"]

    def test_validate_macro_syntax_success(self, project_manager: ProjectManager) -> None:
        """Test ValidateMacroSyntax validates valid macro."""
        from griptape_nodes.retained_mode.events.project_events import ValidateMacroSyntaxResultSuccess

        request = ValidateMacroSyntaxRequest(
            macro_schema="{inputs}/{file_name}.{ext}",
        )

        result = project_manager.on_validate_macro_syntax_request(request)

        assert isinstance(result, ValidateMacroSyntaxResultSuccess)
        var_names = [v.name for v in result.variables]
        assert var_names == ["inputs", "file_name", "ext"]
        assert result.warnings == []

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
