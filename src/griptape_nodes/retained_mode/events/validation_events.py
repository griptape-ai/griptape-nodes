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
    """Validate that a flow has all required dependencies before execution.

    Use when: Pre-flight checks before flow execution, preventing runtime failures,
    debugging dependency issues, validating flow readiness.

    Args:
        flow_name: Name of the flow to validate dependencies for
        flow_node_name: Name of the flow node to validate (None for default)

    Results: ValidateFlowDependenciesResultSuccess (with validation status) | ValidateFlowDependenciesResultFailure (validation error)
    """

    # Same inputs as StartFlow
    flow_name: str
    flow_node_name: str | None = None


@dataclass
@PayloadRegistry.register
class ValidateFlowDependenciesResultSuccess(WorkflowNotAlteredMixin, ResultPayloadSuccess):
    """Flow dependencies validated successfully.

    Args:
        validation_succeeded: True if all dependencies are satisfied, False if issues found
        exceptions: List of dependency validation exceptions (empty if validation_succeeded=True)
    """

    validation_succeeded: bool
    exceptions: list[Exception]


@dataclass
@PayloadRegistry.register
class ValidateFlowDependenciesResultFailure(WorkflowNotAlteredMixin, ResultPayloadFailure):
    """Flow dependency validation failed. Common causes: flow not found, validation system error, missing dependencies."""


@dataclass
@PayloadRegistry.register
class ValidateNodeDependenciesRequest(RequestPayload):
    """Validate that a node has all required dependencies before execution.

    Use when: Pre-flight checks before node execution, preventing runtime failures,
    debugging node dependency issues, validating node readiness.

    Args:
        node_name: Name of the node to validate dependencies for

    Results: ValidateNodeDependenciesResultSuccess (with validation status) | ValidateNodeDependenciesResultFailure (validation error)
    """

    # Same inputs as StartFlow
    node_name: str


@dataclass
@PayloadRegistry.register
class ValidateNodeDependenciesResultSuccess(WorkflowNotAlteredMixin, ResultPayloadSuccess):
    """Node dependencies validated successfully.

    Args:
        validation_succeeded: True if all dependencies are satisfied, False if issues found
        exceptions: List of dependency validation exceptions (empty if validation_succeeded=True)
    """

    validation_succeeded: bool
    exceptions: list[Exception]


@dataclass
@PayloadRegistry.register
class ValidateNodeDependenciesResultFailure(WorkflowNotAlteredMixin, ResultPayloadFailure):
    """Node dependency validation failed. Common causes: node not found, validation system error, missing dependencies."""
