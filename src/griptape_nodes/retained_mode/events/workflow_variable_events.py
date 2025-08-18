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
from griptape_nodes.retained_mode.managers.workflow_variable_manager import VariableScope, WorkflowVariable


# Create Variable Events
@dataclass
@PayloadRegistry.register
class CreateWorkflowVariableRequest(RequestPayload):
    """Create a new workflow variable.
    
    Args:
        name: The name of the variable
        scope: The scope of the variable (global or current_workflow)  
        type: The user-defined type (e.g., "JSON", "str", "int")
        value: The initial value of the variable
    """
    name: str
    scope: VariableScope
    type: str
    value: Any = None


@dataclass
@PayloadRegistry.register
class CreateWorkflowVariableResultSuccess(WorkflowAlteredMixin, ResultPayloadSuccess):
    """Workflow variable created successfully."""
    variable_uuid: str


@dataclass
@PayloadRegistry.register
class CreateWorkflowVariableResultFailure(WorkflowAlteredMixin, ResultPayloadFailure):
    """Workflow variable creation failed."""


# Get Variable Events
@dataclass
@PayloadRegistry.register
class GetWorkflowVariableRequest(RequestPayload):
    """Get a complete workflow variable by UUID or name.
    
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
class GetWorkflowVariableResultSuccess(WorkflowNotAlteredMixin, ResultPayloadSuccess):
    """Workflow variable retrieved successfully."""
    variable: WorkflowVariable


@dataclass
@PayloadRegistry.register
class GetWorkflowVariableResultFailure(WorkflowNotAlteredMixin, ResultPayloadFailure):
    """Workflow variable retrieval failed."""


# Get Variable Value Events
@dataclass
@PayloadRegistry.register
class GetWorkflowVariableValueRequest(RequestPayload):
    """Get the value of a workflow variable by UUID or name.
    
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
class GetWorkflowVariableValueResultSuccess(WorkflowNotAlteredMixin, ResultPayloadSuccess):
    """Workflow variable value retrieved successfully."""
    value: Any


@dataclass
@PayloadRegistry.register
class GetWorkflowVariableValueResultFailure(WorkflowNotAlteredMixin, ResultPayloadFailure):
    """Workflow variable value retrieval failed."""


# Set Variable Value Events
@dataclass
@PayloadRegistry.register
class SetWorkflowVariableValueRequest(RequestPayload):
    """Set the value of a workflow variable by UUID or name.
    
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
class SetWorkflowVariableValueResultSuccess(WorkflowAlteredMixin, ResultPayloadSuccess):
    """Workflow variable value set successfully."""


@dataclass
@PayloadRegistry.register
class SetWorkflowVariableValueResultFailure(WorkflowAlteredMixin, ResultPayloadFailure):
    """Workflow variable value setting failed."""


# Get Variable Type Events
@dataclass
@PayloadRegistry.register
class GetWorkflowVariableTypeRequest(RequestPayload):
    """Get the type of a workflow variable by UUID or name.
    
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
class GetWorkflowVariableTypeResultSuccess(WorkflowNotAlteredMixin, ResultPayloadSuccess):
    """Workflow variable type retrieved successfully."""
    type: str


@dataclass
@PayloadRegistry.register
class GetWorkflowVariableTypeResultFailure(WorkflowNotAlteredMixin, ResultPayloadFailure):
    """Workflow variable type retrieval failed."""


# Set Variable Type Events
@dataclass
@PayloadRegistry.register
class SetWorkflowVariableTypeRequest(RequestPayload):
    """Set the type of a workflow variable by UUID or name.
    
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
class SetWorkflowVariableTypeResultSuccess(WorkflowAlteredMixin, ResultPayloadSuccess):
    """Workflow variable type set successfully."""


@dataclass
@PayloadRegistry.register
class SetWorkflowVariableTypeResultFailure(WorkflowAlteredMixin, ResultPayloadFailure):
    """Workflow variable type setting failed."""


# Delete Variable Events
@dataclass
@PayloadRegistry.register
class DeleteWorkflowVariableRequest(RequestPayload):
    """Delete a workflow variable by UUID or name.
    
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
class DeleteWorkflowVariableResultSuccess(WorkflowAlteredMixin, ResultPayloadSuccess):
    """Workflow variable deleted successfully."""


@dataclass
@PayloadRegistry.register
class DeleteWorkflowVariableResultFailure(WorkflowAlteredMixin, ResultPayloadFailure):
    """Workflow variable deletion failed."""


# Rename Variable Events
@dataclass
@PayloadRegistry.register
class RenameWorkflowVariableRequest(RequestPayload):
    """Rename a workflow variable by UUID or name.
    
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
class RenameWorkflowVariableResultSuccess(WorkflowAlteredMixin, ResultPayloadSuccess):
    """Workflow variable renamed successfully."""


@dataclass
@PayloadRegistry.register
class RenameWorkflowVariableResultFailure(WorkflowAlteredMixin, ResultPayloadFailure):
    """Workflow variable renaming failed."""


# Has Variable Events
@dataclass
@PayloadRegistry.register
class HasWorkflowVariableRequest(RequestPayload):
    """Check if a workflow variable exists by UUID or name.
    
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
class HasWorkflowVariableResultSuccess(WorkflowNotAlteredMixin, ResultPayloadSuccess):
    """Workflow variable existence check completed."""
    exists: bool
    found_scope: VariableScope | None = None


@dataclass
@PayloadRegistry.register
class HasWorkflowVariableResultFailure(WorkflowNotAlteredMixin, ResultPayloadFailure):
    """Workflow variable existence check failed."""