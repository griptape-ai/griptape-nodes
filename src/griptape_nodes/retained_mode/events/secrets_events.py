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
class GetSecretValueResultSuccess(ResultPayloadSuccess, WorkflowNotAlteredMixin):
    value: Any


@dataclass
@PayloadRegistry.register
class GetSecretValueResultFailure(ResultPayloadFailure, WorkflowNotAlteredMixin):
    pass


@dataclass
@PayloadRegistry.register
class SetSecretValueRequest(RequestPayload):
    key: str
    value: Any


@dataclass
@PayloadRegistry.register
class SetSecretValueResultSuccess(ResultPayloadSuccess, WorkflowNotAlteredMixin):
    pass


@dataclass
@PayloadRegistry.register
class SetSecretValueResultFailure(ResultPayloadFailure, WorkflowNotAlteredMixin):
    pass


@dataclass
@PayloadRegistry.register
class GetAllSecretValuesRequest(RequestPayload):
    pass


@dataclass
@PayloadRegistry.register
class GetAllSecretValuesResultSuccess(ResultPayloadSuccess, WorkflowNotAlteredMixin):
    values: dict[str, Any]


@dataclass
@PayloadRegistry.register
class GetAllSecretValuesResultFailure(ResultPayloadFailure, WorkflowNotAlteredMixin):
    pass


@dataclass
@PayloadRegistry.register
class DeleteSecretValueRequest(RequestPayload):
    key: str


@dataclass
@PayloadRegistry.register
class DeleteSecretValueResultSuccess(ResultPayloadSuccess, WorkflowNotAlteredMixin):
    pass


@dataclass
@PayloadRegistry.register
class DeleteSecretValueResultFailure(ResultPayloadFailure, WorkflowNotAlteredMixin):
    pass
