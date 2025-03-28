from dataclasses import dataclass
from typing import Any

from griptape_nodes.retained_mode.events.base_events import (
    RequestPayload,
    ResultPayloadFailure,
    ResultPayloadSuccess,
)
from griptape_nodes.retained_mode.events.payload_registry import PayloadRegistry


@dataclass
@PayloadRegistry.register
class GetConfigValueRequest(RequestPayload):
    category_and_key: str


@dataclass
@PayloadRegistry.register
class GetConfigValueResultSuccess(ResultPayloadSuccess):
    value: Any


@dataclass
@PayloadRegistry.register
class GetConfigValueResultFailure(ResultPayloadFailure):
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
class GetConfigCategoryResultSuccess(ResultPayloadSuccess):
    contents: dict[str, Any]


@dataclass
@PayloadRegistry.register
class GetConfigCategoryResultFailure(ResultPayloadFailure):
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
