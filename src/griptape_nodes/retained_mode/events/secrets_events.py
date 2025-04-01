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
class GetSecretValueRequest(RequestPayload):
    key: str


@dataclass
@PayloadRegistry.register
class GetSecretValueResultSuccess(ResultPayloadSuccess):
    value: Any


@dataclass
@PayloadRegistry.register
class GetSecretValueResultFailure(ResultPayloadFailure):
    pass


@dataclass
@PayloadRegistry.register
class SetSecretValueRequest(RequestPayload):
    key: str
    value: Any


@dataclass
@PayloadRegistry.register
class SetSecretValueResultSuccess(ResultPayloadSuccess):
    pass


@dataclass
@PayloadRegistry.register
class SetSecretValueResultFailure(ResultPayloadFailure):
    pass


@dataclass
@PayloadRegistry.register
class GetAllSecretValuesRequest(RequestPayload):
    pass


@dataclass
@PayloadRegistry.register
class GetAllSecretValuesResultSuccess(ResultPayloadSuccess):
    values: dict[str, Any]


@dataclass
@PayloadRegistry.register
class GetAllSecretValuesResultFailure(ResultPayloadFailure):
    pass


@dataclass
@PayloadRegistry.register
class DeleteSecretValueRequest(RequestPayload):
    key: str


@dataclass
@PayloadRegistry.register
class DeleteSecretValueResultSuccess(ResultPayloadSuccess):
    pass


@dataclass
@PayloadRegistry.register
class DeleteSecretValueResultFailure(ResultPayloadFailure):
    pass
