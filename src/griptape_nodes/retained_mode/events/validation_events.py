# Validates that the flow they are trying to run has all it's dependencies
from dataclasses import dataclass

from griptape_nodes.retained_mode.events.base_events import RequestPayload, ResultPayload_Failure, ResultPayload_Success
from griptape_nodes.retained_mode.events.payload_registry import PayloadRegistry


@dataclass
@PayloadRegistry.register
class ValidateFlowDependenciesRequest(RequestPayload):
    # Same inputs as StartFlow
    flow_name: str
    flow_node_name: str | None = None


@dataclass
@PayloadRegistry.register
class ValidateFlowDependenciesResult_Success(ResultPayload_Success):
    validation_succeeded: bool
    exceptions: list[Exception] | None = None


# if it doesn't have a dependency we want
@dataclass
@PayloadRegistry.register
class ValidateFlowDependenciesResult_Failure(ResultPayload_Failure):
    pass


@dataclass
@PayloadRegistry.register
class ValidateNodeDependenciesRequest(RequestPayload):
    # Same inputs as StartFlow
    node_name: str


@dataclass
@PayloadRegistry.register
class ValidateNodeDependenciesResult_Success(ResultPayload_Success):
    validation_succeeded: bool
    exceptions: list[Exception] | None = None


# if it doesn't have a dependency we want
@dataclass
@PayloadRegistry.register
class ValidateNodeDependenciesResult_Failure(ResultPayload_Failure):
    pass
