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
class GetSecretValueRequest(RequestPayload):
    key: str


@dataclass
@PayloadRegistry.register
class GetSecretValueResultSuccess(WorkflowNotAlteredMixin, ResultPayloadSuccess):
    value: Any


@dataclass
@PayloadRegistry.register
class GetSecretValueResultFailure(WorkflowNotAlteredMixin, ResultPayloadFailure):
    pass


@dataclass
@PayloadRegistry.register
class SetSecretValueRequest(RequestPayload):
    key: str
    value: Any


@dataclass
@PayloadRegistry.register
class SetSecretValueResultSuccess(WorkflowNotAlteredMixin, ResultPayloadSuccess):
    pass


@dataclass
@PayloadRegistry.register
class SetSecretValueResultFailure(WorkflowNotAlteredMixin, ResultPayloadFailure):
    pass


@dataclass
@PayloadRegistry.register
class GetAllSecretValuesRequest(RequestPayload):
    pass


@dataclass
@PayloadRegistry.register
class GetAllSecretValuesResultSuccess(WorkflowNotAlteredMixin, ResultPayloadSuccess):
    values: dict[str, Any]


@dataclass
@PayloadRegistry.register
class GetAllSecretValuesResultFailure(WorkflowNotAlteredMixin, ResultPayloadFailure):
    pass


@dataclass
@PayloadRegistry.register
class DeleteSecretValueRequest(RequestPayload):
    key: str


@dataclass
@PayloadRegistry.register
class DeleteSecretValueResultSuccess(WorkflowNotAlteredMixin, ResultPayloadSuccess):
    pass


@dataclass
@PayloadRegistry.register
class DeleteSecretValueResultFailure(WorkflowNotAlteredMixin, ResultPayloadFailure):
    pass
