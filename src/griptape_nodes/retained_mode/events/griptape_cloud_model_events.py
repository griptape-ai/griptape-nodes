from dataclasses import dataclass, field

from griptape_nodes.retained_mode.events.base_events import (
    RequestPayload,
    ResultPayloadFailure,
    ResultPayloadSuccess,
    WorkflowNotAlteredMixin,
)
from griptape_nodes.retained_mode.events.payload_registry import PayloadRegistry


@dataclass
@PayloadRegistry.register
class ListGriptapeCloudModelsRequest(RequestPayload):
    """List the prompt and image models afforded by Griptape Cloud's drivers.

    Use when: Populating any dropdown of GTC-backed models (e.g. the chat
    sidebar's model picker). The returned lists mirror the canonical catalog
    in `griptape_nodes.drivers.cloud_models`, which is also what the Agent /
    GriptapeCloudPrompt / GriptapeCloudImage nodes use.

    Results: ListGriptapeCloudModelsResultSuccess (with model lists) | ListGriptapeCloudModelsResultFailure
    """


@dataclass
@PayloadRegistry.register
class ListGriptapeCloudModelsResultSuccess(WorkflowNotAlteredMixin, ResultPayloadSuccess):
    """Griptape Cloud model lists retrieved successfully.

    Args:
        prompt_models: Ordered list of GTC prompt-model IDs
        image_models: Ordered list of GTC image-model IDs
    """

    prompt_models: list[str] = field(default_factory=list)
    image_models: list[str] = field(default_factory=list)


@dataclass
@PayloadRegistry.register
class ListGriptapeCloudModelsResultFailure(WorkflowNotAlteredMixin, ResultPayloadFailure):
    """Griptape Cloud model list retrieval failed."""
