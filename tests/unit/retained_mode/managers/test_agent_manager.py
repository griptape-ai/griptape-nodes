"""Tests for `AgentManager.on_handle_list_agent_models_request`.

The handler is a thin wrapper over the module-level catalog constants in
`cloud_models.py`, so tests instantiate the manager without running its
`__init__` and exercise the handler directly.
"""

import pytest

from griptape_nodes.drivers.cloud_models import (
    DEPRECATED_MODELS,
    IMAGE_DEPRECATED_MODELS,
    IMAGE_MODEL_CHOICES,
    MODEL_CHOICES,
)
from griptape_nodes.retained_mode.events.agent_events import (
    ListAgentModelsRequest,
    ListAgentModelsResultSuccess,
)
from griptape_nodes.retained_mode.managers.agent_manager import AgentManager


@pytest.fixture
def agent_manager() -> AgentManager:
    """Build a bare `AgentManager` without running `__init__`.

    The handler only reads module constants, so the manager's wiring (thread
    storage, event handlers, MCP) is irrelevant.
    """
    return AgentManager.__new__(AgentManager)


class TestOnHandleListAgentModelsRequest:
    def test_returns_full_griptape_cloud_catalog(self, agent_manager: AgentManager) -> None:
        result = agent_manager.on_handle_list_agent_models_request(ListAgentModelsRequest())

        assert isinstance(result, ListAgentModelsResultSuccess)
        assert result.prompt_models == list(MODEL_CHOICES)
        assert result.image_models == list(IMAGE_MODEL_CHOICES)
        assert result.deprecated_models == {**DEPRECATED_MODELS, **IMAGE_DEPRECATED_MODELS}

    def test_returns_independent_copies_of_module_constants(self, agent_manager: AgentManager) -> None:
        original_prompt = list(MODEL_CHOICES)
        original_image = list(IMAGE_MODEL_CHOICES)
        original_prompt_dep = dict(DEPRECATED_MODELS)
        original_image_dep = dict(IMAGE_DEPRECATED_MODELS)

        result = agent_manager.on_handle_list_agent_models_request(ListAgentModelsRequest())
        assert isinstance(result, ListAgentModelsResultSuccess)

        result.prompt_models.append("polluted")
        result.image_models.append("polluted")
        result.deprecated_models["polluted"] = "polluted"

        assert original_prompt == MODEL_CHOICES
        assert original_image == IMAGE_MODEL_CHOICES
        assert original_prompt_dep == DEPRECATED_MODELS
        assert original_image_dep == IMAGE_DEPRECATED_MODELS

    def test_deprecation_map_merges_prompt_and_image_namespaces(self, agent_manager: AgentManager) -> None:
        result = agent_manager.on_handle_list_agent_models_request(ListAgentModelsRequest())
        assert isinstance(result, ListAgentModelsResultSuccess)

        for key in DEPRECATED_MODELS:
            assert key in result.deprecated_models
        for key in IMAGE_DEPRECATED_MODELS:
            assert key in result.deprecated_models
