from dataclasses import dataclass
from typing import Any

from griptape_nodes.retained_mode.events.base_events import (
    RequestPayload,
    ResultPayloadFailure,
    ResultPayloadFailureUnalteredWorkflow,
    ResultPayloadSuccess,
    ResultPayloadSuccessUnalteredWorkflow,
)
from griptape_nodes.retained_mode.events.payload_registry import PayloadRegistry


@dataclass
@PayloadRegistry.register
class GetConfigValueRequest(RequestPayload):
    category_and_key: str


@dataclass
@PayloadRegistry.register
class GetConfigValueResultSuccess(ResultPayloadSuccessUnalteredWorkflow):
    value: Any


@dataclass
@PayloadRegistry.register
class GetConfigValueResultFailure(ResultPayloadFailureUnalteredWorkflow):
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
class GetConfigCategoryResultSuccess(ResultPayloadSuccessUnalteredWorkflow):
    contents: dict[str, Any]


@dataclass
@PayloadRegistry.register
class GetConfigCategoryResultFailure(ResultPayloadFailureUnalteredWorkflow):
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
