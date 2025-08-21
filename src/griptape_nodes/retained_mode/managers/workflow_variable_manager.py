import logging
import uuid

from griptape_nodes.retained_mode.events.base_events import ResultPayload
from griptape_nodes.retained_mode.events.workflow_variable_events import (
    CreateVariableRequest,
    CreateVariableResultFailure,
    CreateVariableResultSuccess,
    DeleteVariableRequest,
    DeleteVariableResultFailure,
    DeleteVariableResultSuccess,
    GetVariableDetailsRequest,
    GetVariableDetailsResultFailure,
    GetVariableDetailsResultSuccess,
    GetVariableRequest,
    GetVariableResultFailure,
    GetVariableResultSuccess,
    GetVariableTypeRequest,
    GetVariableTypeResultFailure,
    GetVariableTypeResultSuccess,
    GetVariableValueRequest,
    GetVariableValueResultFailure,
    GetVariableValueResultSuccess,
    HasVariableRequest,
    HasVariableResultFailure,
    HasVariableResultSuccess,
    ListVariablesRequest,
    ListVariablesResultFailure,
    ListVariablesResultSuccess,
    RenameVariableRequest,
    RenameVariableResultFailure,
    RenameVariableResultSuccess,
    SetVariableTypeRequest,
    SetVariableTypeResultFailure,
    SetVariableTypeResultSuccess,
    SetVariableValueRequest,
    SetVariableValueResultFailure,
    SetVariableValueResultSuccess,
    VariableDetails,
)
from griptape_nodes.retained_mode.managers.event_manager import EventManager
from griptape_nodes.retained_mode.workflow_variable_types import FlowVariable, VariableScope

logger = logging.getLogger("griptape_nodes")


class VariablesManager:
    """Manager for variables with scoped access control."""

    def __init__(self, event_manager: EventManager | None = None) -> None:
        # Storage for current variables: {uuid: FlowVariable}
        self._local_workflow_variables: dict[str, FlowVariable] = {}
        if event_manager is not None:
            event_manager.assign_manager_to_request_type(CreateVariableRequest, self.on_create_variable_request)
            event_manager.assign_manager_to_request_type(GetVariableRequest, self.on_get_variable_request)
            event_manager.assign_manager_to_request_type(GetVariableValueRequest, self.on_get_variable_value_request)
            event_manager.assign_manager_to_request_type(SetVariableValueRequest, self.on_set_variable_value_request)
            event_manager.assign_manager_to_request_type(GetVariableTypeRequest, self.on_get_variable_type_request)
            event_manager.assign_manager_to_request_type(SetVariableTypeRequest, self.on_set_variable_type_request)
            event_manager.assign_manager_to_request_type(DeleteVariableRequest, self.on_delete_variable_request)
            event_manager.assign_manager_to_request_type(RenameVariableRequest, self.on_rename_variable_request)
            event_manager.assign_manager_to_request_type(HasVariableRequest, self.on_has_variable_request)
            event_manager.assign_manager_to_request_type(ListVariablesRequest, self.on_list_variables_request)
            event_manager.assign_manager_to_request_type(
                GetVariableDetailsRequest, self.on_get_variable_details_request
            )

    def on_clear_object_state(self) -> None:
        """Clear all local variables."""
        self._local_workflow_variables.clear()

    def on_create_variable_request(self, request: CreateVariableRequest) -> ResultPayload:
        """Create a new variable."""
        # Reject GLOBAL scope for now
        if request.scope == VariableScope.GLOBAL:
            return CreateVariableResultFailure(
                result_details=f"Attempted to create a variable named '{request.name}' with global scope. Failed because global variables are not yet supported."
            )

        # Validate UUID and initial_setup parameters
        if not request.initial_setup and request.uuid is not None:
            return CreateVariableResultFailure(
                result_details=f"Attempted to create a new variable named '{request.name}' with a specified UUID. Failed because UUIDs can only be specified during initial setup from serialized workflows."
            )

        if request.initial_setup and request.uuid is None:
            return CreateVariableResultFailure(
                result_details=f"Attempted to create a variable named '{request.name}' during initial setup without providing a UUID. Failed because initial setup requires a UUID from the serialized workflow."
            )

        # Check for name collision in current variables
        existing = self._find_variable_by_uuid_or_name(None, request.name)
        if existing:
            return CreateVariableResultFailure(
                result_details=f"Attempted to create a variable named '{request.name}'. Failed because a variable with that name already exists."
            )

        # Use provided UUID for initial setup, or generate new UUID for new variables
        if request.initial_setup:
            variable_uuid = request.uuid  # type: ignore[assignment]  # Validation above ensures this is not None

            # Check for UUID collision when using provided UUID
            if variable_uuid in self._local_workflow_variables:
                return CreateVariableResultFailure(
                    result_details=f"Attempted to create a variable named '{request.name}' with UUID: {variable_uuid} during initial setup. Failed because a variable with that UUID already exists."
                )
        else:
            variable_uuid = uuid.uuid4().hex

        variable = FlowVariable(
            uuid=variable_uuid,  # type: ignore[arg-type]  # UUID validated above
            name=request.name,
            scope=request.scope,
            type=request.type,
            value=request.value,
        )

        self._local_workflow_variables[variable_uuid] = variable  # type: ignore[index]  # UUID validated above
        return CreateVariableResultSuccess(variable_uuid=variable_uuid)  # type: ignore[arg-type]  # UUID validated above

    def on_get_variable_request(self, request: GetVariableRequest) -> ResultPayload:
        """Get a full variable by UUID or name."""
        # Reject GLOBAL scope requests for now
        if request.scope == VariableScope.GLOBAL:
            identifier = self._get_variable_identifier_for_error(request.uuid, request.name)
            return GetVariableResultFailure(
                result_details=f"Attempted to get variable {identifier} with global scope. Failed because global variables are not yet supported."
            )

        variable = self._find_variable_by_uuid_or_name(request.uuid, request.name)
        if not variable:
            identifier = self._get_variable_identifier_for_error(request.uuid, request.name)
            return GetVariableResultFailure(
                result_details=f"Attempted to get variable {identifier}. Failed because no such variable could be found."
            )

        return GetVariableResultSuccess(variable=variable)

    def on_get_variable_value_request(self, request: GetVariableValueRequest) -> ResultPayload:
        """Get the value of a variable."""
        # Reject GLOBAL scope requests for now
        if request.scope == VariableScope.GLOBAL:
            identifier = self._get_variable_identifier_for_error(request.uuid, request.name)
            return GetVariableValueResultFailure(
                result_details=f"Attempted to get value for variable {identifier} with global scope. Failed because global variables are not yet supported."
            )

        variable = self._find_variable_by_uuid_or_name(request.uuid, request.name)
        if not variable:
            identifier = self._get_variable_identifier_for_error(request.uuid, request.name)
            return GetVariableValueResultFailure(
                result_details=f"Attempted to get value for variable {identifier}. Failed because no such variable could be found."
            )

        return GetVariableValueResultSuccess(value=variable.value)

    def on_set_variable_value_request(self, request: SetVariableValueRequest) -> ResultPayload:
        """Set the value of an existing variable."""
        # Reject GLOBAL scope requests for now
        if request.scope == VariableScope.GLOBAL:
            identifier = self._get_variable_identifier_for_error(request.uuid, request.name)
            return SetVariableValueResultFailure(
                result_details=f"Attempted to set value for variable {identifier} with global scope. Failed because global variables are not yet supported."
            )

        variable = self._find_variable_by_uuid_or_name(request.uuid, request.name)
        if not variable:
            identifier = self._get_variable_identifier_for_error(request.uuid, request.name)
            return SetVariableValueResultFailure(
                result_details=f"Attempted to set value for variable {identifier}. Failed because no such variable could be found."
            )

        variable.value = request.value
        return SetVariableValueResultSuccess()

    def on_get_variable_type_request(self, request: GetVariableTypeRequest) -> ResultPayload:
        """Get the type of a variable."""
        # Reject GLOBAL scope requests for now
        if request.scope == VariableScope.GLOBAL:
            identifier = self._get_variable_identifier_for_error(request.uuid, request.name)
            return GetVariableTypeResultFailure(
                result_details=f"Attempted to get type for variable {identifier} with global scope. Failed because global variables are not yet supported."
            )

        variable = self._find_variable_by_uuid_or_name(request.uuid, request.name)
        if not variable:
            identifier = self._get_variable_identifier_for_error(request.uuid, request.name)
            return GetVariableTypeResultFailure(
                result_details=f"Attempted to get type for variable {identifier}. Failed because no such variable could be found."
            )

        return GetVariableTypeResultSuccess(type=variable.type)

    def on_set_variable_type_request(self, request: SetVariableTypeRequest) -> ResultPayload:
        """Set the type of an existing variable."""
        # Reject GLOBAL scope requests for now
        if request.scope == VariableScope.GLOBAL:
            identifier = self._get_variable_identifier_for_error(request.uuid, request.name)
            return SetVariableTypeResultFailure(
                result_details=f"Attempted to set type for variable {identifier} with global scope. Failed because global variables are not yet supported."
            )

        variable = self._find_variable_by_uuid_or_name(request.uuid, request.name)
        if not variable:
            identifier = self._get_variable_identifier_for_error(request.uuid, request.name)
            return SetVariableTypeResultFailure(
                result_details=f"Attempted to set type for variable {identifier}. Failed because no such variable could be found."
            )

        variable.type = request.type
        return SetVariableTypeResultSuccess()

    def on_delete_variable_request(self, request: DeleteVariableRequest) -> ResultPayload:
        """Delete a variable."""
        # Reject GLOBAL scope requests for now
        if request.scope == VariableScope.GLOBAL:
            identifier = self._get_variable_identifier_for_error(request.uuid, request.name)
            return DeleteVariableResultFailure(
                result_details=f"Attempted to delete variable {identifier} with global scope. Failed because global variables are not yet supported."
            )

        variable = self._find_variable_by_uuid_or_name(request.uuid, request.name)
        if not variable:
            identifier = self._get_variable_identifier_for_error(request.uuid, request.name)
            return DeleteVariableResultFailure(
                result_details=f"Attempted to delete variable {identifier}. Failed because no such variable could be found."
            )

        # Remove from storage
        del self._local_workflow_variables[variable.uuid]
        return DeleteVariableResultSuccess()

    def on_rename_variable_request(self, request: RenameVariableRequest) -> ResultPayload:
        """Rename a variable."""
        # Reject GLOBAL scope requests for now
        if request.scope == VariableScope.GLOBAL:
            identifier = self._get_variable_identifier_for_error(request.uuid, request.name)
            return RenameVariableResultFailure(
                result_details=f"Attempted to rename variable {identifier} with global scope. Failed because global variables are not yet supported."
            )

        variable = self._find_variable_by_uuid_or_name(request.uuid, request.name)
        if not variable:
            identifier = self._get_variable_identifier_for_error(request.uuid, request.name)
            return RenameVariableResultFailure(
                result_details=f"Attempted to rename variable {identifier}. Failed because no such variable could be found."
            )

        # Check for name collision with new name
        existing = self._find_variable_by_uuid_or_name(None, request.new_name)
        if existing and existing.uuid != variable.uuid:
            old_identifier = self._get_variable_identifier_for_error(request.uuid, request.name)
            return RenameVariableResultFailure(
                result_details=f"Attempted to rename variable {old_identifier} to '{request.new_name}'. Failed because a variable with that name already exists."
            )

        variable.name = request.new_name
        return RenameVariableResultSuccess()

    def on_has_variable_request(self, request: HasVariableRequest) -> ResultPayload:
        """Check if a variable exists."""
        # Reject GLOBAL scope requests for now
        if request.scope == VariableScope.GLOBAL:
            identifier = self._get_variable_identifier_for_error(request.uuid, request.name)
            return HasVariableResultFailure(
                result_details=f"Attempted to check existence of variable {identifier} with global scope. Failed because global variables are not yet supported."
            )

        variable = self._find_variable_by_uuid_or_name(request.uuid, request.name)
        exists = variable is not None
        found_scope = VariableScope.CURRENT_FLOW if exists else None

        return HasVariableResultSuccess(exists=exists, found_scope=found_scope)

    def on_list_variables_request(self, request: ListVariablesRequest) -> ResultPayload:
        """List all variables in the specified scope."""
        # Reject GLOBAL scope requests for now
        if request.scope == VariableScope.GLOBAL:
            return ListVariablesResultFailure(
                result_details="Attempted to list variables with global scope. Failed because global variables are not yet supported."
            )

        # For current workflow scope (or no scope specified), return local variables sorted by name
        variables = sorted(self._local_workflow_variables.values(), key=lambda v: v.name)
        return ListVariablesResultSuccess(variables=variables)

    def on_get_variable_details_request(self, request: GetVariableDetailsRequest) -> ResultPayload:
        """Get variable details (metadata only, no heavy values)."""
        # Reject GLOBAL scope requests for now
        if request.scope == VariableScope.GLOBAL:
            identifier = self._get_variable_identifier_for_error(request.uuid, request.name)
            return GetVariableDetailsResultFailure(
                result_details=f"Attempted to get details for variable {identifier} with global scope. Failed because global variables are not yet supported."
            )

        variable = self._find_variable_by_uuid_or_name(request.uuid, request.name)
        if not variable:
            identifier = self._get_variable_identifier_for_error(request.uuid, request.name)
            return GetVariableDetailsResultFailure(
                result_details=f"Attempted to get details for variable {identifier}. Failed because no such variable could be found."
            )

        details = VariableDetails(uuid=variable.uuid, name=variable.name, scope=variable.scope, type=variable.type)
        return GetVariableDetailsResultSuccess(details=details)

    def _find_variable_by_uuid_or_name(self, uuid_param: str | None, name: str | None) -> FlowVariable | None:
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
