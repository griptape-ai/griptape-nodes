"""Registry of model-catalog providers.

A model provider exposes a named catalog of prompt and image models, plus a
deprecation map. The chat sidebar and any future "pick a model" UI fetch a
provider's catalog through `ListModelsForProviderRequest(provider=...)`,
which routes through this registry.

Today only the Griptape Cloud provider is registered (see
`griptape_nodes.drivers.cloud_models`). The abstraction is intentionally
broader so that future providers (OpenAI, Anthropic, Ollama, Bedrock, etc.)
can be plugged in without changing the event shape.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, ClassVar

from griptape_nodes.utils.metaclasses import SingletonMeta


@dataclass
class ProviderModelInfo:
    """A single model entry in a provider's catalog.

    Args:
        name: Canonical model ID used at the driver layer (e.g. "claude-opus-4-7").
        metadata: Open-ended provider-specific extras (icon path, vision flag,
            per-family driver args, etc.). Kept as a free-form dict so providers
            can attach whatever the UI needs without rev-ing this dataclass.
    """

    name: str
    metadata: dict[str, Any] = field(default_factory=dict)


class ModelProvider(ABC):
    """Abstract base for a named model catalog."""

    @property
    @abstractmethod
    def name(self) -> str:
        """The provider's identifier (e.g. "griptape_cloud", "openai")."""

    @abstractmethod
    def list_prompt_models(self) -> list[ProviderModelInfo]:
        """The provider's prompt/chat models."""

    @abstractmethod
    def list_image_models(self) -> list[ProviderModelInfo]:
        """The provider's image-generation models."""

    @abstractmethod
    def deprecated_models(self) -> dict[str, str]:
        """Mapping of deprecated model ID to the live replacement ID."""


class StaticModelProvider(ModelProvider):
    """A `ModelProvider` backed by hand-curated lists.

    Suits providers whose catalogs are static and small enough to maintain by
    hand (Anthropic, Griptape Cloud, the curated portion of OpenAI/Bedrock).
    """

    def __init__(
        self,
        name: str,
        prompt: list[ProviderModelInfo],
        image: list[ProviderModelInfo],
        deprecated: dict[str, str],
    ) -> None:
        self._name = name
        self._prompt = prompt
        self._image = image
        self._deprecated = deprecated

    @property
    def name(self) -> str:
        return self._name

    def list_prompt_models(self) -> list[ProviderModelInfo]:
        return list(self._prompt)

    def list_image_models(self) -> list[ProviderModelInfo]:
        return list(self._image)

    def deprecated_models(self) -> dict[str, str]:
        return dict(self._deprecated)


class ModelProviderRegistry(metaclass=SingletonMeta):
    """Singleton registry of model providers, keyed by `ModelProvider.name`."""

    _providers: ClassVar[dict[str, ModelProvider]] = {}

    @classmethod
    def register(cls, provider: ModelProvider) -> None:
        instance = cls()
        if provider.name in instance._providers:
            msg = f"Model provider '{provider.name}' already registered."
            raise KeyError(msg)
        instance._providers[provider.name] = provider

    @classmethod
    def get(cls, name: str) -> ModelProvider | None:
        instance = cls()
        return instance._providers.get(name)

    @classmethod
    def list_provider_names(cls) -> list[str]:
        instance = cls()
        return list(instance._providers.keys())

    @classmethod
    def unregister(cls, name: str) -> None:
        instance = cls()
        if name not in instance._providers:
            msg = f"Model provider '{name}' was requested to be unregistered, but it wasn't registered in the first place."
            raise KeyError(msg)
        del instance._providers[name]
