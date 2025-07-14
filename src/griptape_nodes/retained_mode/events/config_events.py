from dataclasses import dataclass
from typing import Any

from griptape_nodes.retained_mode.events.base_events import (
    RequestPayload,
    ResultDetails,
    ResultPayloadFailure,
    ResultPayloadSuccess,
    WorkflowNotAlteredMixin,
)
from griptape_nodes.retained_mode.events.payload_registry import PayloadRegistry


@dataclass
@PayloadRegistry.register
class GetConfigValueRequest(RequestPayload):
    category_and_key: str


@PayloadRegistry.register
class GetConfigValueResultSuccess(WorkflowNotAlteredMixin, ResultPayloadSuccess):
    def __init__(self, value: Any, details: ResultDetails | str):
        self.value = value
        # Initialize the dataclass mixin first
        WorkflowNotAlteredMixin.__init__(self)
        # Then initialize the ResultPayload base class
        ResultPayloadSuccess.__init__(self, details=details)


@PayloadRegistry.register
class GetConfigValueResultFailure(WorkflowNotAlteredMixin, ResultPayloadFailure):
    def __init__(self, details: ResultDetails | str):
        # Initialize the dataclass mixin first
        WorkflowNotAlteredMixin.__init__(self)
        # Then initialize the ResultPayload base class
        ResultPayloadFailure.__init__(self, details=details)


@dataclass
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


@dataclass
@PayloadRegistry.register
class GetConfigCategoryRequest(RequestPayload):
    category: str | None = None


@PayloadRegistry.register
class GetConfigCategoryResultSuccess(WorkflowNotAlteredMixin, ResultPayloadSuccess):
    def __init__(self, contents: dict[str, Any], details: ResultDetails | str):
        self.contents = contents
        # Initialize the dataclass mixin first
        WorkflowNotAlteredMixin.__init__(self)
        # Then initialize the ResultPayload base class
        ResultPayloadSuccess.__init__(self, details=details)


@PayloadRegistry.register
class GetConfigCategoryResultFailure(WorkflowNotAlteredMixin, ResultPayloadFailure):
    def __init__(self, details: ResultDetails | str):
        # Initialize the dataclass mixin first
        WorkflowNotAlteredMixin.__init__(self)
        # Then initialize the ResultPayload base class
        ResultPayloadFailure.__init__(self, details=details)


@dataclass
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


@dataclass
@PayloadRegistry.register
class GetConfigPathRequest(RequestPayload):
    pass


@PayloadRegistry.register
class GetConfigPathResultSuccess(WorkflowNotAlteredMixin, ResultPayloadSuccess):
    def __init__(self, config_path: str | None = None, details: ResultDetails | str = "Success"):
        self.config_path = config_path
        # Initialize the dataclass mixin first
        WorkflowNotAlteredMixin.__init__(self)
        # Then initialize the ResultPayload base class
        ResultPayloadSuccess.__init__(self, details=details)


@PayloadRegistry.register
class GetConfigPathResultFailure(WorkflowNotAlteredMixin, ResultPayloadFailure):
    def __init__(self, details: ResultDetails | str):
        # Initialize the dataclass mixin first
        WorkflowNotAlteredMixin.__init__(self)
        # Then initialize the ResultPayload base class
        ResultPayloadFailure.__init__(self, details=details)


@dataclass
@PayloadRegistry.register
class ResetConfigRequest(RequestPayload):
    pass


@PayloadRegistry.register
class ResetConfigResultSuccess(ResultPayloadSuccess):
    pass


@PayloadRegistry.register
class ResetConfigResultFailure(ResultPayloadFailure):
    pass
