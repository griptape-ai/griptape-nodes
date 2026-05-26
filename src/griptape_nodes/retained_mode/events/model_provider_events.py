from dataclasses import dataclass, field

from griptape_nodes.drivers.model_provider_registry import ProviderModelInfo
from griptape_nodes.retained_mode.events.base_events import (
    RequestPayload,
    ResultPayloadFailure,
    ResultPayloadSuccess,
    WorkflowNotAlteredMixin,
)
from griptape_nodes.retained_mode.events.payload_registry import PayloadRegistry


@dataclass
@PayloadRegistry.register
class ListModelsForProviderRequest(RequestPayload):
    """List the prompt and image models afforded by a named model provider.

    Use when: Populating any "pick a model" dropdown that targets a specific
    provider (the chat sidebar uses `provider="griptape_cloud"`). Future
    providers (OpenAI, Anthropic, Ollama, Bedrock, ...) can be added by
    registering them on `ModelProviderRegistry`; the event shape does not
    change.

    Args:
        provider: The provider name registered with `ModelProviderRegistry`
            (e.g. "griptape_cloud").

    Results: ListModelsForProviderResultSuccess (with model lists and
        deprecation map) | ListModelsForProviderResultFailure (unknown
        provider, dynamic-fetch failure, etc.)
    """

    provider: str


@dataclass
@PayloadRegistry.register
class ListModelsForProviderResultSuccess(WorkflowNotAlteredMixin, ResultPayloadSuccess):
    """Model lists for a provider retrieved successfully.

    Args:
        provider: The provider name that was queried.
        prompt_models: Ordered list of prompt-model entries.
        image_models: Ordered list of image-model entries.
        deprecated_models: Mapping of deprecated model ID to live replacement.
    """

    provider: str
    prompt_models: list[ProviderModelInfo] = field(default_factory=list)
    image_models: list[ProviderModelInfo] = field(default_factory=list)
    deprecated_models: dict[str, str] = field(default_factory=dict)


@dataclass
@PayloadRegistry.register
class ListModelsForProviderResultFailure(WorkflowNotAlteredMixin, ResultPayloadFailure):
    """Model list retrieval for a provider failed.

    Args:
        provider: The provider name that was queried.
        available_providers: Names of providers currently registered, surfaced
            so callers can debug typos / library-load ordering issues.
    """

    provider: str
    available_providers: list[str] = field(default_factory=list)
