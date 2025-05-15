from typing import Any

from griptape_nodes.retained_mode.events.base_events import (
    RequestPayload,
    ResultPayloadFailure,
    ResultPayloadSuccess,
    WorkflowNotAlteredMixin,
)
from griptape_nodes.retained_mode.events.payload_registry import PayloadRegistry


@PayloadRegistry.register
class GetConfigValueRequest(RequestPayload):
    category_and_key: str


@PayloadRegistry.register
class GetConfigValueResultSuccess(WorkflowNotAlteredMixin, ResultPayloadSuccess):
    value: Any


@PayloadRegistry.register
class GetConfigValueResultFailure(WorkflowNotAlteredMixin, ResultPayloadFailure):
    pass


@PayloadRegistry.register
class SetConfigValueRequest(RequestPayload):
    category_and_key: str
    value: Any


@PayloadRegistry.register
class SetConfigValueResultSuccess(ResultPayloadSuccess):
    pass


@PayloadRegistry.register
class SetConfigValueResultFailure(ResultPayloadFailure):
    pass


@PayloadRegistry.register
class GetConfigCategoryRequest(RequestPayload):
    category: str | None = None


@PayloadRegistry.register
class GetConfigCategoryResultSuccess(WorkflowNotAlteredMixin, ResultPayloadSuccess):
    contents: dict[str, Any]


@PayloadRegistry.register
class GetConfigCategoryResultFailure(WorkflowNotAlteredMixin, ResultPayloadFailure):
    pass


@PayloadRegistry.register
class SetConfigCategoryRequest(RequestPayload):
    contents: dict[str, Any]
    category: str | None = None


@PayloadRegistry.register
class SetConfigCategoryResultSuccess(ResultPayloadSuccess):
    pass


@PayloadRegistry.register
class SetConfigCategoryResultFailure(ResultPayloadFailure):
    pass


@PayloadRegistry.register
class GetConfigPathRequest(RequestPayload):
    pass


@PayloadRegistry.register
class GetConfigPathResultSuccess(WorkflowNotAlteredMixin, ResultPayloadSuccess):
    config_path: str | None = None


@PayloadRegistry.register
class GetConfigPathResultFailure(WorkflowNotAlteredMixin, ResultPayloadFailure):
    pass


@PayloadRegistry.register
class ResetConfigRequest(RequestPayload):
    pass


@PayloadRegistry.register
class ResetConfigResultSuccess(ResultPayloadSuccess):
    pass


@PayloadRegistry.register
class ResetConfigResultFailure(ResultPayloadFailure):
    pass
