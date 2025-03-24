from dataclasses import dataclass
from typing import Any

from griptape_nodes.retained_mode.events.base_events import (
    RequestPayload,
    ResultPayload_Failure,
    ResultPayload_Success,
)
from griptape_nodes.retained_mode.events.payload_registry import PayloadRegistry


@dataclass
@PayloadRegistry.register
class GetConfigValueRequest(RequestPayload):
    category_and_key: str


@dataclass
@PayloadRegistry.register
class GetConfigValueResult_Success(ResultPayload_Success):
    value: Any


@dataclass
@PayloadRegistry.register
class GetConfigValueResult_Failure(ResultPayload_Failure):
    pass


@dataclass
@PayloadRegistry.register
class SetConfigValueRequest(RequestPayload):
    category_and_key: str
    value: Any


@dataclass
@PayloadRegistry.register
class SetConfigValueResult_Success(ResultPayload_Success):
    pass


@dataclass
@PayloadRegistry.register
class SetConfigValueResult_Failure(ResultPayload_Failure):
    pass


@dataclass
@PayloadRegistry.register
class GetConfigCategoryRequest(RequestPayload):
    category: str | None = None


@dataclass
@PayloadRegistry.register
class GetConfigCategoryResult_Success(ResultPayload_Success):
    contents: dict[str, Any]


@dataclass
@PayloadRegistry.register
class GetConfigCategoryResult_Failure(ResultPayload_Failure):
    pass


@dataclass
@PayloadRegistry.register
class SetConfigCategoryRequest(RequestPayload):
    contents: dict[str, Any]
    category: str | None = None


@dataclass
@PayloadRegistry.register
class SetConfigCategoryResult_Success(ResultPayload_Success):
    pass


@dataclass
@PayloadRegistry.register
class SetConfigCategoryResult_Failure(ResultPayload_Failure):
    pass
