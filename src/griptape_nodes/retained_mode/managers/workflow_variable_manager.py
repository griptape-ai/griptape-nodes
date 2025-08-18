import logging
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from griptape_nodes.retained_mode.events.base_events import ResultPayload
from griptape_nodes.retained_mode.events.workflow_variable_events import (
    CreateWorkflowVariableRequest,
    DeleteWorkflowVariableRequest,
    GetWorkflowVariableRequest,
    GetWorkflowVariableTypeRequest,
    GetWorkflowVariableValueRequest,
    HasWorkflowVariableRequest,
    RenameWorkflowVariableRequest,
    SetWorkflowVariableTypeRequest,
    SetWorkflowVariableValueRequest,
)
from griptape_nodes.retained_mode.managers.event_manager import EventManager

logger = logging.getLogger("griptape_nodes")


class VariableScope(StrEnum):
    GLOBAL = "global"
    CURRENT_WORKFLOW = "current_workflow"


@dataclass
class WorkflowVariable:
    uuid: str
    name: str
    scope: VariableScope
    type: str
    value: Any


class WorkflowVariableManager:
    """Manager for workflow variables with scoped access control."""

    def __init__(self, event_manager: EventManager | None = None) -> None:
        if event_manager is not None:
            event_manager.assign_manager_to_request_type(
                CreateWorkflowVariableRequest, self.on_create_workflow_variable_request
            )
            event_manager.assign_manager_to_request_type(
                GetWorkflowVariableRequest, self.on_get_workflow_variable_request
            )
            event_manager.assign_manager_to_request_type(
                GetWorkflowVariableValueRequest, self.on_get_workflow_variable_value_request
            )
            event_manager.assign_manager_to_request_type(
                SetWorkflowVariableValueRequest, self.on_set_workflow_variable_value_request
            )
            event_manager.assign_manager_to_request_type(
                GetWorkflowVariableTypeRequest, self.on_get_workflow_variable_type_request
            )
            event_manager.assign_manager_to_request_type(
                SetWorkflowVariableTypeRequest, self.on_set_workflow_variable_type_request
            )
            event_manager.assign_manager_to_request_type(
                DeleteWorkflowVariableRequest, self.on_delete_workflow_variable_request
            )
            event_manager.assign_manager_to_request_type(
                RenameWorkflowVariableRequest, self.on_rename_workflow_variable_request
            )
            event_manager.assign_manager_to_request_type(
                HasWorkflowVariableRequest, self.on_has_workflow_variable_request
            )

    def on_create_workflow_variable_request(self, request: CreateWorkflowVariableRequest) -> ResultPayload:
        """Create a new workflow variable."""
        # TODO: Implement after events are defined
        pass

    def on_get_workflow_variable_request(self, request: GetWorkflowVariableRequest) -> ResultPayload:
        """Get a full workflow variable by UUID or name."""
        # TODO: Implement after events are defined
        pass

    def on_get_workflow_variable_value_request(self, request: GetWorkflowVariableValueRequest) -> ResultPayload:
        """Get the value of a workflow variable."""
        # TODO: Implement after events are defined
        pass

    def on_set_workflow_variable_value_request(self, request: SetWorkflowVariableValueRequest) -> ResultPayload:
        """Set the value of an existing workflow variable."""
        # TODO: Implement after events are defined
        pass

    def on_get_workflow_variable_type_request(self, request: GetWorkflowVariableTypeRequest) -> ResultPayload:
        """Get the type of a workflow variable."""
        # TODO: Implement after events are defined
        pass

    def on_set_workflow_variable_type_request(self, request: SetWorkflowVariableTypeRequest) -> ResultPayload:
        """Set the type of an existing workflow variable."""
        # TODO: Implement after events are defined
        pass

    def on_delete_workflow_variable_request(self, request: DeleteWorkflowVariableRequest) -> ResultPayload:
        """Delete a workflow variable."""
        # TODO: Implement after events are defined
        pass

    def on_rename_workflow_variable_request(self, request: RenameWorkflowVariableRequest) -> ResultPayload:
        """Rename a workflow variable."""
        # TODO: Implement after events are defined
        pass

    def on_has_workflow_variable_request(self, request: HasWorkflowVariableRequest) -> ResultPayload:
        """Check if a workflow variable exists."""
        # TODO: Implement after events are defined
        pass