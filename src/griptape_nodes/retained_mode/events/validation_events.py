# Validates that the flow they are trying to run has all it's dependencies
from dataclasses import dataclass

from griptape_nodes.retained_mode.events.base_events import (
    RequestPayload,
    ResultPayloadFailure,
    ResultPayloadSuccess,
    WorkflowNotAlteredMixin,
)
from griptape_nodes.retained_mode.events.payload_registry import PayloadRegistry


@dataclass
@PayloadRegistry.register
class ValidateFlowDependenciesRequest(RequestPayload):
    # Same inputs as StartFlow
    flow_name: str
    flow_node_name: str | None = None


@dataclass
@PayloadRegistry.register
class ValidateFlowDependenciesResultSuccess(WorkflowNotAlteredMixin, ResultPayloadSuccess):
    validation_succeeded: bool
    exceptions: list[Exception]


# if it doesn't have a dependency we want
@dataclass
@PayloadRegistry.register
class ValidateFlowDependenciesResultFailure(WorkflowNotAlteredMixin, ResultPayloadFailure):
    pass


@dataclass
@PayloadRegistry.register
class ValidateNodeDependenciesRequest(RequestPayload):
    # Same inputs as StartFlow
    node_name: str


@dataclass
@PayloadRegistry.register
class ValidateNodeDependenciesResultSuccess(WorkflowNotAlteredMixin, ResultPayloadSuccess):
    validation_succeeded: bool
    exceptions: list[Exception]


# if it doesn't have a dependency we want
@dataclass
@PayloadRegistry.register
class ValidateNodeDependenciesResultFailure(WorkflowNotAlteredMixin, ResultPayloadFailure):
    pass
