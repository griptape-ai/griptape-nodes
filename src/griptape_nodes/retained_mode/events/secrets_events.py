from dataclasses import dataclass
from typing import Any

from griptape_nodes.retained_mode.events.base_events import (
    RequestPayload,
    ResultPayloadFailureUnalteredWorkflow,
    ResultPayloadSuccessUnalteredWorkflow,
)
from griptape_nodes.retained_mode.events.payload_registry import PayloadRegistry


@dataclass
@PayloadRegistry.register
class GetSecretValueRequest(RequestPayload):
    key: str


@dataclass
@PayloadRegistry.register
class GetSecretValueResultSuccess(ResultPayloadSuccessUnalteredWorkflow):
    value: Any


@dataclass
@PayloadRegistry.register
class GetSecretValueResultFailure(ResultPayloadFailureUnalteredWorkflow):
    pass


@dataclass
@PayloadRegistry.register
class SetSecretValueRequest(RequestPayload):
    key: str
    value: Any


@dataclass
@PayloadRegistry.register
class SetSecretValueResultSuccess(ResultPayloadSuccessUnalteredWorkflow):
    pass


@dataclass
@PayloadRegistry.register
class SetSecretValueResultFailure(ResultPayloadFailureUnalteredWorkflow):
    pass


@dataclass
@PayloadRegistry.register
class GetAllSecretValuesRequest(RequestPayload):
    pass


@dataclass
@PayloadRegistry.register
class GetAllSecretValuesResultSuccess(ResultPayloadSuccessUnalteredWorkflow):
    values: dict[str, Any]


@dataclass
@PayloadRegistry.register
class GetAllSecretValuesResultFailure(ResultPayloadFailureUnalteredWorkflow):
    pass


@dataclass
@PayloadRegistry.register
class DeleteSecretValueRequest(RequestPayload):
    key: str


@dataclass
@PayloadRegistry.register
class DeleteSecretValueResultSuccess(ResultPayloadSuccessUnalteredWorkflow):
    pass


@dataclass
@PayloadRegistry.register
class DeleteSecretValueResultFailure(ResultPayloadFailureUnalteredWorkflow):
    pass
