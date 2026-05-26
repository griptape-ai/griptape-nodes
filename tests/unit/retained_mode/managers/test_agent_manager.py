"""Tests for `AgentManager.on_handle_list_models_for_provider_request`.

The handler is a pure dispatch layer over `ModelProviderRegistry`, so the tests
construct providers directly rather than spinning up the full agent stack.
"""

import pytest

from griptape_nodes.drivers.model_provider_registry import (
    ModelProviderRegistry,
    ProviderModelInfo,
    StaticModelProvider,
)
from griptape_nodes.retained_mode.events.model_provider_events import (
    ListModelsForProviderRequest,
    ListModelsForProviderResultFailure,
    ListModelsForProviderResultSuccess,
)
from griptape_nodes.retained_mode.managers.agent_manager import AgentManager


@pytest.fixture(autouse=True)
def clean_registry() -> None:
    """Clear the registry's `ClassVar` provider dict between tests."""
    ModelProviderRegistry._providers.clear()


@pytest.fixture
def agent_manager() -> AgentManager:
    """Build a bare `AgentManager` without running `__init__`.

    The handler only touches `ModelProviderRegistry`, so the rest of the
    manager's wiring (thread storage, event handlers, MCP) is irrelevant.
    """
    return AgentManager.__new__(AgentManager)


class TestOnHandleListModelsForProviderRequest:
    def test_success_returns_provider_catalog(self, agent_manager: AgentManager) -> None:
        ModelProviderRegistry.register(
            StaticModelProvider(
                name="fake",
                prompt=[ProviderModelInfo(name="m1", metadata={"vision": True})],
                image=[ProviderModelInfo(name="img1", metadata={})],
                deprecated={"old-id": "m1"},
            )
        )

        result = agent_manager.on_handle_list_models_for_provider_request(ListModelsForProviderRequest(provider="fake"))

        assert isinstance(result, ListModelsForProviderResultSuccess)
        assert result.provider == "fake"
        assert [m.name for m in result.prompt_models] == ["m1"]
        assert [m.name for m in result.image_models] == ["img1"]
        assert result.deprecated_models == {"old-id": "m1"}

    def test_unknown_provider_returns_failure_with_available_providers(self, agent_manager: AgentManager) -> None:
        ModelProviderRegistry.register(StaticModelProvider(name="real", prompt=[], image=[], deprecated={}))

        result = agent_manager.on_handle_list_models_for_provider_request(
            ListModelsForProviderRequest(provider="missing")
        )

        assert isinstance(result, ListModelsForProviderResultFailure)
        assert result.provider == "missing"
        assert result.available_providers == ["real"]

    def test_unknown_provider_with_empty_registry_returns_empty_available_list(
        self, agent_manager: AgentManager
    ) -> None:
        result = agent_manager.on_handle_list_models_for_provider_request(
            ListModelsForProviderRequest(provider="missing")
        )

        assert isinstance(result, ListModelsForProviderResultFailure)
        assert result.provider == "missing"
        assert result.available_providers == []
