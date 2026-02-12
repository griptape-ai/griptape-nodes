"""Tests for situation_utils module."""

from unittest.mock import MagicMock, patch

import pytest

from griptape_nodes.common.project_templates.situation import (
    SituationFilePolicy,
    SituationPolicy,
    SituationTemplate,
)
from griptape_nodes.project.situation_utils import SituationConfig, fetch_situation_config
from griptape_nodes.project.types import ExistingFilePolicy
from griptape_nodes.retained_mode.events.project_events import (
    GetSituationResultFailure,
    GetSituationResultSuccess,
)


class TestSituationConfig:
    """Test SituationConfig NamedTuple."""

    def test_situation_config_fields(self) -> None:
        """Verify SituationConfig has correct fields."""
        config = SituationConfig(
            macro_template="{outputs}/{node_name}.png",
            policy=ExistingFilePolicy.CREATE_NEW,
            create_dirs=True,
        )

        assert config.macro_template == "{outputs}/{node_name}.png"
        assert config.policy == ExistingFilePolicy.CREATE_NEW
        assert config.create_dirs is True

    def test_situation_config_is_immutable(self) -> None:
        """Verify SituationConfig is immutable."""
        config = SituationConfig(
            macro_template="{outputs}/{node_name}.png",
            policy=ExistingFilePolicy.CREATE_NEW,
            create_dirs=True,
        )

        with pytest.raises(AttributeError):
            config.macro_template = "new_value"  # type: ignore[misc]


class TestFetchSituationConfig:
    """Test fetch_situation_config function."""

    def test_fetch_situation_config_success_create_new(self) -> None:
        """Test successfully fetching situation with CREATE_NEW policy."""
        mock_situation = SituationTemplate(
            name="test_situation",
            macro="{outputs}/{node_name}.png",
            policy=SituationPolicy(
                on_collision=SituationFilePolicy.CREATE_NEW,
                create_dirs=True,
            ),
        )
        mock_result = GetSituationResultSuccess(
            situation=mock_situation,
            result_details="Situation fetched successfully",
        )

        with patch("griptape_nodes.project.situation_utils.GriptapeNodes") as mock_griptape_nodes:
            mock_project_manager = MagicMock()
            mock_project_manager.on_get_situation_request.return_value = mock_result
            mock_griptape_nodes.ProjectManager.return_value = mock_project_manager

            config = fetch_situation_config("test_situation")

            assert config is not None
            assert config.macro_template == "{outputs}/{node_name}.png"
            assert config.policy == ExistingFilePolicy.CREATE_NEW
            assert config.create_dirs is True

    def test_fetch_situation_config_success_overwrite(self) -> None:
        """Test successfully fetching situation with OVERWRITE policy."""
        mock_situation = SituationTemplate(
            name="test_situation",
            macro="{outputs}/file.txt",
            policy=SituationPolicy(
                on_collision=SituationFilePolicy.OVERWRITE,
                create_dirs=False,
            ),
        )
        mock_result = GetSituationResultSuccess(
            situation=mock_situation,
            result_details="Situation fetched successfully",
        )

        with patch("griptape_nodes.project.situation_utils.GriptapeNodes") as mock_griptape_nodes:
            mock_project_manager = MagicMock()
            mock_project_manager.on_get_situation_request.return_value = mock_result
            mock_griptape_nodes.ProjectManager.return_value = mock_project_manager

            config = fetch_situation_config("test_situation")

            assert config is not None
            assert config.macro_template == "{outputs}/file.txt"
            assert config.policy == ExistingFilePolicy.OVERWRITE
            assert config.create_dirs is False

    def test_fetch_situation_config_success_fail(self) -> None:
        """Test successfully fetching situation with FAIL policy."""
        mock_situation = SituationTemplate(
            name="test_situation",
            macro="{outputs}/critical.dat",
            policy=SituationPolicy(
                on_collision=SituationFilePolicy.FAIL,
                create_dirs=True,
            ),
        )
        mock_result = GetSituationResultSuccess(
            situation=mock_situation,
            result_details="Situation fetched successfully",
        )

        with patch("griptape_nodes.project.situation_utils.GriptapeNodes") as mock_griptape_nodes:
            mock_project_manager = MagicMock()
            mock_project_manager.on_get_situation_request.return_value = mock_result
            mock_griptape_nodes.ProjectManager.return_value = mock_project_manager

            config = fetch_situation_config("test_situation")

            assert config is not None
            assert config.macro_template == "{outputs}/critical.dat"
            assert config.policy == ExistingFilePolicy.FAIL
            assert config.create_dirs is True

    def test_fetch_situation_config_failure(self) -> None:
        """Test fetching situation returns None on failure."""
        mock_result = GetSituationResultFailure(result_details="Situation not found")

        with patch("griptape_nodes.project.situation_utils.GriptapeNodes") as mock_griptape_nodes:
            mock_project_manager = MagicMock()
            mock_project_manager.on_get_situation_request.return_value = mock_result
            mock_griptape_nodes.ProjectManager.return_value = mock_project_manager

            config = fetch_situation_config("nonexistent_situation")

            assert config is None

    def test_fetch_situation_config_with_node_name(self) -> None:
        """Test fetching situation with node name for logging context."""
        mock_situation = SituationTemplate(
            name="test_situation",
            macro="{outputs}/test.png",
            policy=SituationPolicy(
                on_collision=SituationFilePolicy.CREATE_NEW,
                create_dirs=True,
            ),
        )
        mock_result = GetSituationResultSuccess(
            situation=mock_situation,
            result_details="Situation fetched successfully",
        )

        with patch("griptape_nodes.project.situation_utils.GriptapeNodes") as mock_griptape_nodes:
            mock_project_manager = MagicMock()
            mock_project_manager.on_get_situation_request.return_value = mock_result
            mock_griptape_nodes.ProjectManager.return_value = mock_project_manager

            config = fetch_situation_config("test_situation", node_name="TestNode")

            assert config is not None
            assert config.macro_template == "{outputs}/test.png"

    def test_fetch_situation_config_unknown_policy_uses_default(self) -> None:
        """Test that unknown policy falls back to CREATE_NEW."""
        mock_situation = SituationTemplate(
            name="test_situation",
            macro="{outputs}/test.png",
            policy=SituationPolicy(
                on_collision=SituationFilePolicy.PROMPT,
                create_dirs=True,
            ),
        )
        mock_result = GetSituationResultSuccess(
            situation=mock_situation,
            result_details="Situation fetched successfully",
        )

        with patch("griptape_nodes.project.situation_utils.GriptapeNodes") as mock_griptape_nodes:
            mock_project_manager = MagicMock()
            mock_project_manager.on_get_situation_request.return_value = mock_result
            mock_griptape_nodes.ProjectManager.return_value = mock_project_manager

            config = fetch_situation_config("test_situation")

            assert config is not None
            assert config.policy == ExistingFilePolicy.CREATE_NEW
