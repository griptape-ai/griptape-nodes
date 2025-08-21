from dataclasses import dataclass
from typing import Any

from griptape_nodes.retained_mode.events.base_events import (
    RequestPayload,
    ResultPayloadFailure,
    ResultPayloadSuccess,
    WorkflowAlteredMixin,
    WorkflowNotAlteredMixin,
)
from griptape_nodes.retained_mode.events.payload_registry import PayloadRegistry
from griptape_nodes.retained_mode.workflow_variable_types import FlowVariable, VariableScope


# Variable Events
@dataclass
@PayloadRegistry.register
class CreateVariableRequest(RequestPayload):
    """Create a new variable.

    Args:
        name: The name of the variable
        scope: The scope of the variable (global or current_workflow)
        type: The user-defined type (e.g., "JSON", "str", "int")
        value: The initial value of the variable
        uuid: Optional UUID for the variable (used during serialization/deserialization)
        initial_setup: True when loading from serialized workflow, False for new variables
    """

    name: str
    scope: VariableScope
    type: str
    value: Any = None
    uuid: str | None = None
    initial_setup: bool = False


@dataclass
@PayloadRegistry.register
class CreateVariableResultSuccess(WorkflowAlteredMixin, ResultPayloadSuccess):
    """Variable created successfully."""

    variable_uuid: str


@dataclass
@PayloadRegistry.register
class CreateVariableResultFailure(WorkflowAlteredMixin, ResultPayloadFailure):
    """Variable creation failed."""


# Get Variable Events
@dataclass
@PayloadRegistry.register
class GetVariableRequest(RequestPayload):
    """Get a complete variable by UUID or name.

    Args:
        uuid: Optional variable UUID (takes precedence if provided)
        name: Optional variable name (used if uuid not provided)
        scope: Optional scope filter (global, current_workflow, or None for both)
    """

    uuid: str | None = None
    name: str | None = None
    scope: VariableScope | None = None


@dataclass
@PayloadRegistry.register
class GetVariableResultSuccess(WorkflowNotAlteredMixin, ResultPayloadSuccess):
    """Variable retrieved successfully."""

    variable: FlowVariable


@dataclass
@PayloadRegistry.register
class GetVariableResultFailure(WorkflowNotAlteredMixin, ResultPayloadFailure):
    """Variable retrieval failed."""


# Get Variable Value Events
@dataclass
@PayloadRegistry.register
class GetVariableValueRequest(RequestPayload):
    """Get the value of a variable by UUID or name.

    Args:
        uuid: Optional variable UUID (takes precedence if provided)
        name: Optional variable name (used if uuid not provided)
        scope: Optional scope filter (global, current_workflow, or None for both)
    """

    uuid: str | None = None
    name: str | None = None
    scope: VariableScope | None = None


@dataclass
@PayloadRegistry.register
class GetVariableValueResultSuccess(WorkflowNotAlteredMixin, ResultPayloadSuccess):
    """Variable value retrieved successfully."""

    value: Any


@dataclass
@PayloadRegistry.register
class GetVariableValueResultFailure(WorkflowNotAlteredMixin, ResultPayloadFailure):
    """Variable value retrieval failed."""


# Set Variable Value Events
@dataclass
@PayloadRegistry.register
class SetVariableValueRequest(RequestPayload):
    """Set the value of a variable by UUID or name.

    Args:
        value: The new value to set
        uuid: Optional variable UUID (takes precedence if provided)
        name: Optional variable name (used if uuid not provided)
        scope: Optional scope filter (global, current_workflow, or None for both)
    """

    value: Any
    uuid: str | None = None
    name: str | None = None
    scope: VariableScope | None = None


@dataclass
@PayloadRegistry.register
class SetVariableValueResultSuccess(WorkflowAlteredMixin, ResultPayloadSuccess):
    """Variable value set successfully."""


@dataclass
@PayloadRegistry.register
class SetVariableValueResultFailure(WorkflowAlteredMixin, ResultPayloadFailure):
    """Variable value setting failed."""


# Get Variable Type Events
@dataclass
@PayloadRegistry.register
class GetVariableTypeRequest(RequestPayload):
    """Get the type of a variable by UUID or name.

    Args:
        uuid: Optional variable UUID (takes precedence if provided)
        name: Optional variable name (used if uuid not provided)
        scope: Optional scope filter (global, current_workflow, or None for both)
    """

    uuid: str | None = None
    name: str | None = None
    scope: VariableScope | None = None


@dataclass
@PayloadRegistry.register
class GetVariableTypeResultSuccess(WorkflowNotAlteredMixin, ResultPayloadSuccess):
    """Variable type retrieved successfully."""

    type: str


@dataclass
@PayloadRegistry.register
class GetVariableTypeResultFailure(WorkflowNotAlteredMixin, ResultPayloadFailure):
    """Variable type retrieval failed."""


# Set Variable Type Events
@dataclass
@PayloadRegistry.register
class SetVariableTypeRequest(RequestPayload):
    """Set the type of a variable by UUID or name.

    Args:
        type: The new user-defined type (e.g., "JSON", "str", "int")
        uuid: Optional variable UUID (takes precedence if provided)
        name: Optional variable name (used if uuid not provided)
        scope: Optional scope filter (global, current_workflow, or None for both)
    """

    type: str
    uuid: str | None = None
    name: str | None = None
    scope: VariableScope | None = None


@dataclass
@PayloadRegistry.register
class SetVariableTypeResultSuccess(WorkflowAlteredMixin, ResultPayloadSuccess):
    """Variable type set successfully."""


@dataclass
@PayloadRegistry.register
class SetVariableTypeResultFailure(WorkflowAlteredMixin, ResultPayloadFailure):
    """Variable type setting failed."""


# Delete Variable Events
@dataclass
@PayloadRegistry.register
class DeleteVariableRequest(RequestPayload):
    """Delete a variable by UUID or name.

    Args:
        uuid: Optional variable UUID (takes precedence if provided)
        name: Optional variable name (used if uuid not provided)
        scope: Optional scope filter (global, current_workflow, or None for both)
    """

    uuid: str | None = None
    name: str | None = None
    scope: VariableScope | None = None


@dataclass
@PayloadRegistry.register
class DeleteVariableResultSuccess(WorkflowAlteredMixin, ResultPayloadSuccess):
    """Variable deleted successfully."""


@dataclass
@PayloadRegistry.register
class DeleteVariableResultFailure(WorkflowAlteredMixin, ResultPayloadFailure):
    """Variable deletion failed."""


# Rename Variable Events
@dataclass
@PayloadRegistry.register
class RenameVariableRequest(RequestPayload):
    """Rename a variable by UUID or name.

    Args:
        new_name: The new name for the variable
        uuid: Optional variable UUID (takes precedence if provided)
        name: Optional current variable name (used if uuid not provided)
        scope: Optional scope filter (global, current_workflow, or None for both)
    """

    new_name: str
    uuid: str | None = None
    name: str | None = None
    scope: VariableScope | None = None


@dataclass
@PayloadRegistry.register
class RenameVariableResultSuccess(WorkflowAlteredMixin, ResultPayloadSuccess):
    """Variable renamed successfully."""


@dataclass
@PayloadRegistry.register
class RenameVariableResultFailure(WorkflowAlteredMixin, ResultPayloadFailure):
    """Variable renaming failed."""


# Has Variable Events
@dataclass
@PayloadRegistry.register
class HasVariableRequest(RequestPayload):
    """Check if a variable exists by UUID or name.

    Args:
        uuid: Optional variable UUID (takes precedence if provided)
        name: Optional variable name (used if uuid not provided)
        scope: Optional scope filter (global, current_workflow, or None for both)
    """

    uuid: str | None = None
    name: str | None = None
    scope: VariableScope | None = None


@dataclass
@PayloadRegistry.register
class HasVariableResultSuccess(WorkflowNotAlteredMixin, ResultPayloadSuccess):
    """Variable existence check completed."""

    exists: bool
    found_scope: VariableScope | None = None


@dataclass
@PayloadRegistry.register
class HasVariableResultFailure(WorkflowNotAlteredMixin, ResultPayloadFailure):
    """Variable existence check failed."""


# List Variables Events
@dataclass
@PayloadRegistry.register
class ListVariablesRequest(RequestPayload):
    """List all variables in the specified scope.

    Args:
        scope: Optional scope filter (global, current_workflow, or None for both)
    """

    scope: VariableScope | None = None


@dataclass
@PayloadRegistry.register
class ListVariablesResultSuccess(WorkflowNotAlteredMixin, ResultPayloadSuccess):
    """Variables listed successfully."""

    variables: list[FlowVariable]


@dataclass
@PayloadRegistry.register
class ListVariablesResultFailure(WorkflowNotAlteredMixin, ResultPayloadFailure):
    """Variables listing failed."""


# Get Variable Details Events
@dataclass
@PayloadRegistry.register
class GetVariableDetailsRequest(RequestPayload):
    """Get variable details (metadata only, no heavy values).

    Args:
        uuid: Optional variable UUID (takes precedence if provided)
        name: Optional variable name (used if uuid not provided)
        scope: Optional scope filter (global, current_workflow, or None for both)
    """

    uuid: str | None = None
    name: str | None = None
    scope: VariableScope | None = None


@dataclass
class VariableDetails:
    """Lightweight variable details without heavy values."""

    uuid: str
    name: str
    scope: VariableScope
    type: str


@dataclass
@PayloadRegistry.register
class GetVariableDetailsResultSuccess(WorkflowNotAlteredMixin, ResultPayloadSuccess):
    """Variable details retrieved successfully."""

    details: VariableDetails


@dataclass
@PayloadRegistry.register
class GetVariableDetailsResultFailure(WorkflowNotAlteredMixin, ResultPayloadFailure):
    """Variable details retrieval failed."""
