"""Tests for ModelProviderRegistry and the Griptape Cloud provider registration."""

import pytest

from griptape_nodes.drivers.cloud_models import (
    GRIPTAPE_CLOUD_PROVIDER_NAME,
    register_griptape_cloud_provider,
)
from griptape_nodes.drivers.model_provider_registry import (
    ModelProviderRegistry,
    ProviderModelInfo,
    StaticModelProvider,
)


@pytest.fixture(autouse=True)
def clean_registry() -> None:
    """Clear the registry's `ClassVar` provider dict between tests.

    The registry is process-scoped via `SingletonMeta` + a `ClassVar` dict,
    so without this fixture state would leak across test cases.
    """
    ModelProviderRegistry._providers.clear()


def _make_provider(name: str = "test") -> StaticModelProvider:
    return StaticModelProvider(
        name=name,
        prompt=[ProviderModelInfo(name="m1", metadata={"vision": True})],
        image=[ProviderModelInfo(name="img1", metadata={})],
        deprecated={"old-id": "m1"},
    )


class TestModelProviderRegistry:
    def test_register_and_get_round_trip(self) -> None:
        provider = _make_provider("test")

        ModelProviderRegistry.register(provider)

        assert ModelProviderRegistry.get("test") is provider

    def test_get_returns_none_for_unknown_provider(self) -> None:
        assert ModelProviderRegistry.get("nope") is None

    def test_list_provider_names_reflects_registrations(self) -> None:
        ModelProviderRegistry.register(_make_provider("a"))
        ModelProviderRegistry.register(_make_provider("b"))

        names = ModelProviderRegistry.list_provider_names()

        assert set(names) == {"a", "b"}

    def test_register_duplicate_name_raises_key_error(self) -> None:
        ModelProviderRegistry.register(_make_provider("dupe"))

        with pytest.raises(KeyError, match="dupe"):
            ModelProviderRegistry.register(_make_provider("dupe"))

    def test_unregister_removes_provider(self) -> None:
        ModelProviderRegistry.register(_make_provider("temp"))

        ModelProviderRegistry.unregister("temp")

        assert ModelProviderRegistry.get("temp") is None
        assert "temp" not in ModelProviderRegistry.list_provider_names()

    def test_unregister_unknown_name_raises_key_error(self) -> None:
        with pytest.raises(KeyError, match="never_registered"):
            ModelProviderRegistry.unregister("never_registered")


class TestStaticModelProviderReadback:
    def test_static_provider_returns_independent_copies(self) -> None:
        provider = _make_provider()

        first = provider.list_prompt_models()
        second = provider.list_prompt_models()

        assert first == second
        assert first is not second

    def test_static_provider_exposes_deprecation_map(self) -> None:
        provider = _make_provider()

        assert provider.deprecated_models() == {"old-id": "m1"}


class TestRegisterGriptapeCloudProvider:
    def test_registers_provider_with_canonical_name(self) -> None:
        register_griptape_cloud_provider()

        provider = ModelProviderRegistry.get(GRIPTAPE_CLOUD_PROVIDER_NAME)

        assert provider is not None
        assert provider.name == GRIPTAPE_CLOUD_PROVIDER_NAME

    def test_provider_exposes_prompt_image_and_deprecation_data(self) -> None:
        register_griptape_cloud_provider()

        provider = ModelProviderRegistry.get(GRIPTAPE_CLOUD_PROVIDER_NAME)

        assert provider is not None
        assert len(provider.list_prompt_models()) > 0
        assert len(provider.list_image_models()) > 0
        assert len(provider.deprecated_models()) > 0

    def test_idempotent_under_repeat_calls(self) -> None:
        """The helper is called from `AgentManager.__init__`; test fixtures clear
        `SingletonMeta._instances` between tests, so the manager (and this call)
        re-runs while the registry's `ClassVar` dict persists. The helper must
        tolerate that without raising.
        """  # noqa: D205
        register_griptape_cloud_provider()
        first = ModelProviderRegistry.get(GRIPTAPE_CLOUD_PROVIDER_NAME)

        register_griptape_cloud_provider()
        second = ModelProviderRegistry.get(GRIPTAPE_CLOUD_PROVIDER_NAME)

        assert first is second
