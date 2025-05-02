from dataclasses import dataclass
from typing import Any

from griptape_nodes.retained_mode.events.base_events import (
    RequestPayload,
    ResultPayloadFailure,
    ResultPayloadSuccess,
    WorkflowNotAlteredMixin,
)
from griptape_nodes.retained_mode.events.payload_registry import PayloadRegistry


@dataclass
@PayloadRegistry.register
class GetConfigValueRequest(RequestPayload):
    category_and_key: str


@dataclass
@PayloadRegistry.register
class GetConfigValueResultSuccess(WorkflowNotAlteredMixin, ResultPayloadSuccess):
    value: Any


@dataclass
@PayloadRegistry.register
class GetConfigValueResultFailure(WorkflowNotAlteredMixin, ResultPayloadFailure):
    pass


@dataclass
@PayloadRegistry.register
class SetConfigValueRequest(RequestPayload):
    category_and_key: str
    value: Any


@dataclass
@PayloadRegistry.register
class SetConfigValueResultSuccess(ResultPayloadSuccess):
    pass


@dataclass
@PayloadRegistry.register
class SetConfigValueResultFailure(ResultPayloadFailure):
    pass


@dataclass
@PayloadRegistry.register
class GetConfigCategoryRequest(RequestPayload):
    category: str | None = None


@dataclass
@PayloadRegistry.register
class GetConfigCategoryResultSuccess(WorkflowNotAlteredMixin, ResultPayloadSuccess):
    contents: dict[str, Any]


@dataclass
@PayloadRegistry.register
class GetConfigCategoryResultFailure(WorkflowNotAlteredMixin, ResultPayloadFailure):
    pass


@dataclass
@PayloadRegistry.register
class SetConfigCategoryRequest(RequestPayload):
    contents: dict[str, Any]
    category: str | None = None


@dataclass
@PayloadRegistry.register
class SetConfigCategoryResultSuccess(ResultPayloadSuccess):
    pass


@dataclass
@PayloadRegistry.register
class SetConfigCategoryResultFailure(ResultPayloadFailure):
    pass


@dataclass
@PayloadRegistry.register
class GetConfigPathRequest(RequestPayload):
    pass


@dataclass
@PayloadRegistry.register
class GetConfigPathResultSuccess(WorkflowNotAlteredMixin, ResultPayloadSuccess):
    config_path: str | None = None


@dataclass
@PayloadRegistry.register
class GetConfigPathResultFailure(WorkflowNotAlteredMixin, ResultPayloadFailure):
    pass


@dataclass
@PayloadRegistry.register
class ResetConfigRequest(RequestPayload):
    pass


@dataclass
@PayloadRegistry.register
class ResetConfigResultSuccess(ResultPayloadSuccess):
    pass


@dataclass
@PayloadRegistry.register
class ResetConfigResultFailure(ResultPayloadFailure):
    pass
