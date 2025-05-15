from pydantic.dataclasses import dataclass
from typing import Any

from griptape_nodes.retained_mode.events.base_events import (
    RequestPayload,
    ResultPayloadFailure,
    ResultPayloadSuccess,
    WorkflowNotAlteredMixin,
)
from griptape_nodes.retained_mode.events.payload_registry import PayloadRegistry


@PayloadRegistry.register
class GetSecretValueRequest(RequestPayload):
    key: str


@PayloadRegistry.register
class GetSecretValueResultSuccess(WorkflowNotAlteredMixin, ResultPayloadSuccess):
    value: Any


@PayloadRegistry.register
class GetSecretValueResultFailure(WorkflowNotAlteredMixin, ResultPayloadFailure):
    pass


@PayloadRegistry.register
class SetSecretValueRequest(RequestPayload):
    key: str
    value: Any


@PayloadRegistry.register
class SetSecretValueResultSuccess(WorkflowNotAlteredMixin, ResultPayloadSuccess):
    pass


@PayloadRegistry.register
class SetSecretValueResultFailure(WorkflowNotAlteredMixin, ResultPayloadFailure):
    pass


@PayloadRegistry.register
class GetAllSecretValuesRequest(RequestPayload):
    pass


@PayloadRegistry.register
class GetAllSecretValuesResultSuccess(WorkflowNotAlteredMixin, ResultPayloadSuccess):
    values: dict[str, Any]


@PayloadRegistry.register
class GetAllSecretValuesResultFailure(WorkflowNotAlteredMixin, ResultPayloadFailure):
    pass


@PayloadRegistry.register
class DeleteSecretValueRequest(RequestPayload):
    key: str


@PayloadRegistry.register
class DeleteSecretValueResultSuccess(WorkflowNotAlteredMixin, ResultPayloadSuccess):
    pass


@PayloadRegistry.register
class DeleteSecretValueResultFailure(WorkflowNotAlteredMixin, ResultPayloadFailure):
    pass
