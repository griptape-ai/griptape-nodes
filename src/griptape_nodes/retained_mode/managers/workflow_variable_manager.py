import logging
import uuid

from griptape_nodes.retained_mode.events.base_events import ResultPayload
from griptape_nodes.retained_mode.events.workflow_variable_events import (
    CreateWorkflowVariableRequest,
    CreateWorkflowVariableResultFailure,
    CreateWorkflowVariableResultSuccess,
    DeleteWorkflowVariableRequest,
    DeleteWorkflowVariableResultFailure,
    DeleteWorkflowVariableResultSuccess,
    GetWorkflowVariableDetailsRequest,
    GetWorkflowVariableDetailsResultFailure,
    GetWorkflowVariableDetailsResultSuccess,
    GetWorkflowVariableRequest,
    GetWorkflowVariableResultFailure,
    GetWorkflowVariableResultSuccess,
    GetWorkflowVariableTypeRequest,
    GetWorkflowVariableTypeResultFailure,
    GetWorkflowVariableTypeResultSuccess,
    GetWorkflowVariableValueRequest,
    GetWorkflowVariableValueResultFailure,
    GetWorkflowVariableValueResultSuccess,
    HasWorkflowVariableRequest,
    HasWorkflowVariableResultFailure,
    HasWorkflowVariableResultSuccess,
    ListWorkflowVariablesRequest,
    ListWorkflowVariablesResultFailure,
    ListWorkflowVariablesResultSuccess,
    RenameWorkflowVariableRequest,
    RenameWorkflowVariableResultFailure,
    RenameWorkflowVariableResultSuccess,
    SetWorkflowVariableTypeRequest,
    SetWorkflowVariableTypeResultFailure,
    SetWorkflowVariableTypeResultSuccess,
    SetWorkflowVariableValueRequest,
    SetWorkflowVariableValueResultFailure,
    SetWorkflowVariableValueResultSuccess,
    WorkflowVariableDetails,
)
from griptape_nodes.retained_mode.managers.event_manager import EventManager
from griptape_nodes.retained_mode.workflow_variable_types import VariableScope, WorkflowVariable

logger = logging.getLogger("griptape_nodes")


class WorkflowVariablesManager:
    """Manager for workflow variables with scoped access control."""

    def __init__(self, event_manager: EventManager | None = None) -> None:
        # Storage for current workflow variables: {uuid: WorkflowVariable}
        self._local_workflow_variables: dict[str, WorkflowVariable] = {}
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
            event_manager.assign_manager_to_request_type(
                ListWorkflowVariablesRequest, self.on_list_workflow_variables_request
            )
            event_manager.assign_manager_to_request_type(
                GetWorkflowVariableDetailsRequest, self.on_get_workflow_variable_details_request
            )

    def on_clear_object_state(self) -> None:
        """Clear all local workflow variables."""
        self._local_workflow_variables.clear()

    def on_create_workflow_variable_request(self, request: CreateWorkflowVariableRequest) -> ResultPayload:
        """Create a new workflow variable."""
        # Reject GLOBAL scope for now
        if request.scope == VariableScope.GLOBAL:
            return CreateWorkflowVariableResultFailure(
                result_details=f"Attempted to create a workflow variable named '{request.name}' with global scope. Failed because global workflow variables are not yet supported."
            )

        # Validate UUID and initial_setup parameters
        if not request.initial_setup and request.uuid is not None:
            return CreateWorkflowVariableResultFailure(
                result_details=f"Attempted to create a new workflow variable named '{request.name}' with a specified UUID. Failed because UUIDs can only be specified during initial setup from serialized workflows."
            )

        if request.initial_setup and request.uuid is None:
            return CreateWorkflowVariableResultFailure(
                result_details=f"Attempted to create a workflow variable named '{request.name}' during initial setup without providing a UUID. Failed because initial setup requires a UUID from the serialized workflow."
            )

        # Check for name collision in current workflow variables
        existing = self._find_variable_by_uuid_or_name(None, request.name)
        if existing:
            return CreateWorkflowVariableResultFailure(
                result_details=f"Attempted to create a workflow variable named '{request.name}'. Failed because a variable with that name already exists."
            )

        # Use provided UUID for initial setup, or generate new UUID for new variables
        if request.initial_setup:
            variable_uuid = request.uuid  # type: ignore[assignment]  # Validation above ensures this is not None

            # Check for UUID collision when using provided UUID
            if variable_uuid in self._local_workflow_variables:
                return CreateWorkflowVariableResultFailure(
                    result_details=f"Attempted to create a workflow variable named '{request.name}' with UUID: {variable_uuid} during initial setup. Failed because a variable with that UUID already exists."
                )
        else:
            variable_uuid = uuid.uuid4().hex

        variable = WorkflowVariable(
            uuid=variable_uuid,  # type: ignore[arg-type]  # UUID validated above
            name=request.name,
            scope=request.scope,
            type=request.type,
            value=request.value,
        )

        self._local_workflow_variables[variable_uuid] = variable  # type: ignore[index]  # UUID validated above
        return CreateWorkflowVariableResultSuccess(variable_uuid=variable_uuid)  # type: ignore[arg-type]  # UUID validated above

    def on_get_workflow_variable_request(self, request: GetWorkflowVariableRequest) -> ResultPayload:
        """Get a full workflow variable by UUID or name."""
        # Reject GLOBAL scope requests for now
        if request.scope == VariableScope.GLOBAL:
            identifier = self._get_variable_identifier_for_error(request.uuid, request.name)
            return GetWorkflowVariableResultFailure(
                result_details=f"Attempted to get workflow variable {identifier} with global scope. Failed because global workflow variables are not yet supported."
            )

        variable = self._find_variable_by_uuid_or_name(request.uuid, request.name)
        if not variable:
            identifier = self._get_variable_identifier_for_error(request.uuid, request.name)
            return GetWorkflowVariableResultFailure(
                result_details=f"Attempted to get workflow variable {identifier}. Failed because no such variable could be found."
            )

        return GetWorkflowVariableResultSuccess(variable=variable)

    def on_get_workflow_variable_value_request(self, request: GetWorkflowVariableValueRequest) -> ResultPayload:
        """Get the value of a workflow variable."""
        # Reject GLOBAL scope requests for now
        if request.scope == VariableScope.GLOBAL:
            identifier = self._get_variable_identifier_for_error(request.uuid, request.name)
            return GetWorkflowVariableValueResultFailure(
                result_details=f"Attempted to get value for workflow variable {identifier} with global scope. Failed because global workflow variables are not yet supported."
            )

        variable = self._find_variable_by_uuid_or_name(request.uuid, request.name)
        if not variable:
            identifier = self._get_variable_identifier_for_error(request.uuid, request.name)
            return GetWorkflowVariableValueResultFailure(
                result_details=f"Attempted to get value for workflow variable {identifier}. Failed because no such variable could be found."
            )

        return GetWorkflowVariableValueResultSuccess(value=variable.value)

    def on_set_workflow_variable_value_request(self, request: SetWorkflowVariableValueRequest) -> ResultPayload:
        """Set the value of an existing workflow variable."""
        # Reject GLOBAL scope requests for now
        if request.scope == VariableScope.GLOBAL:
            identifier = self._get_variable_identifier_for_error(request.uuid, request.name)
            return SetWorkflowVariableValueResultFailure(
                result_details=f"Attempted to set value for workflow variable {identifier} with global scope. Failed because global workflow variables are not yet supported."
            )

        variable = self._find_variable_by_uuid_or_name(request.uuid, request.name)
        if not variable:
            identifier = self._get_variable_identifier_for_error(request.uuid, request.name)
            return SetWorkflowVariableValueResultFailure(
                result_details=f"Attempted to set value for workflow variable {identifier}. Failed because no such variable could be found."
            )

        variable.value = request.value
        return SetWorkflowVariableValueResultSuccess()

    def on_get_workflow_variable_type_request(self, request: GetWorkflowVariableTypeRequest) -> ResultPayload:
        """Get the type of a workflow variable."""
        # Reject GLOBAL scope requests for now
        if request.scope == VariableScope.GLOBAL:
            identifier = self._get_variable_identifier_for_error(request.uuid, request.name)
            return GetWorkflowVariableTypeResultFailure(
                result_details=f"Attempted to get type for workflow variable {identifier} with global scope. Failed because global workflow variables are not yet supported."
            )

        variable = self._find_variable_by_uuid_or_name(request.uuid, request.name)
        if not variable:
            identifier = self._get_variable_identifier_for_error(request.uuid, request.name)
            return GetWorkflowVariableTypeResultFailure(
                result_details=f"Attempted to get type for workflow variable {identifier}. Failed because no such variable could be found."
            )

        return GetWorkflowVariableTypeResultSuccess(type=variable.type)

    def on_set_workflow_variable_type_request(self, request: SetWorkflowVariableTypeRequest) -> ResultPayload:
        """Set the type of an existing workflow variable."""
        # Reject GLOBAL scope requests for now
        if request.scope == VariableScope.GLOBAL:
            identifier = self._get_variable_identifier_for_error(request.uuid, request.name)
            return SetWorkflowVariableTypeResultFailure(
                result_details=f"Attempted to set type for workflow variable {identifier} with global scope. Failed because global workflow variables are not yet supported."
            )

        variable = self._find_variable_by_uuid_or_name(request.uuid, request.name)
        if not variable:
            identifier = self._get_variable_identifier_for_error(request.uuid, request.name)
            return SetWorkflowVariableTypeResultFailure(
                result_details=f"Attempted to set type for workflow variable {identifier}. Failed because no such variable could be found."
            )

        variable.type = request.type
        return SetWorkflowVariableTypeResultSuccess()

    def on_delete_workflow_variable_request(self, request: DeleteWorkflowVariableRequest) -> ResultPayload:
        """Delete a workflow variable."""
        # Reject GLOBAL scope requests for now
        if request.scope == VariableScope.GLOBAL:
            identifier = self._get_variable_identifier_for_error(request.uuid, request.name)
            return DeleteWorkflowVariableResultFailure(
                result_details=f"Attempted to delete workflow variable {identifier} with global scope. Failed because global workflow variables are not yet supported."
            )

        variable = self._find_variable_by_uuid_or_name(request.uuid, request.name)
        if not variable:
            identifier = self._get_variable_identifier_for_error(request.uuid, request.name)
            return DeleteWorkflowVariableResultFailure(
                result_details=f"Attempted to delete workflow variable {identifier}. Failed because no such variable could be found."
            )

        # Remove from storage
        del self._local_workflow_variables[variable.uuid]
        return DeleteWorkflowVariableResultSuccess()

    def on_rename_workflow_variable_request(self, request: RenameWorkflowVariableRequest) -> ResultPayload:
        """Rename a workflow variable."""
        # Reject GLOBAL scope requests for now
        if request.scope == VariableScope.GLOBAL:
            identifier = self._get_variable_identifier_for_error(request.uuid, request.name)
            return RenameWorkflowVariableResultFailure(
                result_details=f"Attempted to rename workflow variable {identifier} with global scope. Failed because global workflow variables are not yet supported."
            )

        variable = self._find_variable_by_uuid_or_name(request.uuid, request.name)
        if not variable:
            identifier = self._get_variable_identifier_for_error(request.uuid, request.name)
            return RenameWorkflowVariableResultFailure(
                result_details=f"Attempted to rename workflow variable {identifier}. Failed because no such variable could be found."
            )

        # Check for name collision with new name
        existing = self._find_variable_by_uuid_or_name(None, request.new_name)
        if existing and existing.uuid != variable.uuid:
            old_identifier = self._get_variable_identifier_for_error(request.uuid, request.name)
            return RenameWorkflowVariableResultFailure(
                result_details=f"Attempted to rename workflow variable {old_identifier} to '{request.new_name}'. Failed because a variable with that name already exists."
            )

        variable.name = request.new_name
        return RenameWorkflowVariableResultSuccess()

    def on_has_workflow_variable_request(self, request: HasWorkflowVariableRequest) -> ResultPayload:
        """Check if a workflow variable exists."""
        # Reject GLOBAL scope requests for now
        if request.scope == VariableScope.GLOBAL:
            identifier = self._get_variable_identifier_for_error(request.uuid, request.name)
            return HasWorkflowVariableResultFailure(
                result_details=f"Attempted to check existence of workflow variable {identifier} with global scope. Failed because global workflow variables are not yet supported."
            )

        variable = self._find_variable_by_uuid_or_name(request.uuid, request.name)
        exists = variable is not None
        found_scope = VariableScope.CURRENT_WORKFLOW if exists else None

        return HasWorkflowVariableResultSuccess(exists=exists, found_scope=found_scope)

    def on_list_workflow_variables_request(self, request: ListWorkflowVariablesRequest) -> ResultPayload:
        """List all workflow variables in the specified scope."""
        # Reject GLOBAL scope requests for now
        if request.scope == VariableScope.GLOBAL:
            return ListWorkflowVariablesResultFailure(
                result_details="Attempted to list workflow variables with global scope. Failed because global workflow variables are not yet supported."
            )

        # For current workflow scope (or no scope specified), return local variables sorted by name
        variables = sorted(self._local_workflow_variables.values(), key=lambda v: v.name)
        return ListWorkflowVariablesResultSuccess(variables=variables)

    def on_get_workflow_variable_details_request(self, request: GetWorkflowVariableDetailsRequest) -> ResultPayload:
        """Get workflow variable details (metadata only, no heavy values)."""
        # Reject GLOBAL scope requests for now
        if request.scope == VariableScope.GLOBAL:
            identifier = self._get_variable_identifier_for_error(request.uuid, request.name)
            return GetWorkflowVariableDetailsResultFailure(
                result_details=f"Attempted to get details for workflow variable {identifier} with global scope. Failed because global workflow variables are not yet supported."
            )

        variable = self._find_variable_by_uuid_or_name(request.uuid, request.name)
        if not variable:
            identifier = self._get_variable_identifier_for_error(request.uuid, request.name)
            return GetWorkflowVariableDetailsResultFailure(
                result_details=f"Attempted to get details for workflow variable {identifier}. Failed because no such variable could be found."
            )

        details = WorkflowVariableDetails(
            uuid=variable.uuid, name=variable.name, scope=variable.scope, type=variable.type
        )
        return GetWorkflowVariableDetailsResultSuccess(details=details)

    def _find_variable_by_uuid_or_name(self, uuid_param: str | None, name: str | None) -> WorkflowVariable | None:
        """Find a variable by UUID (preferred) or name."""
        if uuid_param:
            return self._local_workflow_variables.get(uuid_param)

        if name:
            # Search by name (less efficient, but necessary)
            for variable in self._local_workflow_variables.values():
                if variable.name == name:
                    return variable

        return None

    def _get_variable_identifier_for_error(self, uuid_param: str | None, name: str | None) -> str:
        """Generate a clear error message identifier based on what was provided."""
        if name and uuid_param:
            return f"'{name}' (UUID: {uuid_param})"
        if name:
            return f"'{name}'"
        if uuid_param:
            return f"UUID: {uuid_param}"
        return "no name or UUID specified"
