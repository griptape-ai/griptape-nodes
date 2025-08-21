import logging

from griptape_nodes.retained_mode.events.base_events import ResultPayload
from griptape_nodes.retained_mode.events.variable_events import (
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
from griptape_nodes.retained_mode.variable_types import FlowVariable, VariableScope

logger = logging.getLogger("griptape_nodes")


class VariablesManager:
    """Manager for variables with scoped access control."""

    def __init__(self, event_manager: EventManager | None = None) -> None:
        # Storage for current variables: {name: FlowVariable}
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
        # Reject global variables for now
        if request.is_global:
            return CreateVariableResultFailure(
                result_details=f"Attempted to create a global variable named '{request.name}'. Failed because global variables are not yet supported."
            )

        # Check for name collision in current variables
        existing = self._find_variable_by_name(request.name)
        if existing:
            return CreateVariableResultFailure(
                result_details=f"Attempted to create a variable named '{request.name}'. Failed because a variable with that name already exists."
            )

        # Determine scope based on is_global flag
        scope = VariableScope.GLOBAL_ONLY if request.is_global else VariableScope.CURRENT_FLOW_ONLY

        variable = FlowVariable(
            name=request.name,
            scope=scope,
            type=request.type,
            value=request.value,
        )

        self._local_workflow_variables[request.name] = variable
        return CreateVariableResultSuccess()

    def on_get_variable_request(self, request: GetVariableRequest) -> ResultPayload:
        """Get a full variable by name."""
        # For now, just look in current flow variables
        if request.lookup_scope == VariableScope.GLOBAL_ONLY:
            return GetVariableResultFailure(
                result_details=f"Attempted to get variable '{request.name}' with global scope. Failed because global variables are not yet supported."
            )

        variable = self._find_variable_by_name(request.name)
        if not variable:
            return GetVariableResultFailure(
                result_details=f"Attempted to get variable '{request.name}'. Failed because no such variable could be found."
            )

        return GetVariableResultSuccess(variable=variable)

    def on_get_variable_value_request(self, request: GetVariableValueRequest) -> ResultPayload:
        """Get the value of a variable."""
        # For now, just look in current flow variables
        # Reject GLOBAL scope requests for now
        if request.lookup_scope == VariableScope.GLOBAL_ONLY:
            return GetVariableValueResultFailure(
                result_details=f"Attempted to get value for variable '{request.name}' with global scope. Failed because global variables are not yet supported."
            )

        variable = self._find_variable_by_name(request.name)
        if not variable:
            identifier = f"'{request.name}'"
            return GetVariableValueResultFailure(
                result_details=f"Attempted to get value for variable {identifier}. Failed because no such variable could be found."
            )

        return GetVariableValueResultSuccess(value=variable.value)

    def on_set_variable_value_request(self, request: SetVariableValueRequest) -> ResultPayload:
        """Set the value of an existing variable."""
        # For now, just look in current flow variables
        # Reject GLOBAL scope requests for now
        if request.lookup_scope == VariableScope.GLOBAL_ONLY:
            return SetVariableValueResultFailure(
                result_details=f"Attempted to set value for variable '{request.name}' with global scope. Failed because global variables are not yet supported."
            )

        variable = self._find_variable_by_name(request.name)
        if not variable:
            return SetVariableValueResultFailure(
                result_details=f"Attempted to set value for variable '{request.name}'. Failed because no such variable could be found."
            )

        variable.value = request.value
        return SetVariableValueResultSuccess()

    def on_get_variable_type_request(self, request: GetVariableTypeRequest) -> ResultPayload:
        """Get the type of a variable."""
        # For now, just look in current flow variables
        # Reject GLOBAL scope requests for now
        if request.lookup_scope == VariableScope.GLOBAL_ONLY:
            return GetVariableTypeResultFailure(
                result_details=f"Attempted to get type for variable '{request.name}' with global scope. Failed because global variables are not yet supported."
            )

        variable = self._find_variable_by_name(request.name)
        if not variable:
            return GetVariableTypeResultFailure(
                result_details=f"Attempted to get type for variable '{request.name}'. Failed because no such variable could be found."
            )

        return GetVariableTypeResultSuccess(type=variable.type)

    def on_set_variable_type_request(self, request: SetVariableTypeRequest) -> ResultPayload:
        """Set the type of an existing variable."""
        # For now, just look in current flow variables
        # Reject GLOBAL scope requests for now
        if request.lookup_scope == VariableScope.GLOBAL_ONLY:
            return SetVariableTypeResultFailure(
                result_details=f"Attempted to set type for variable '{request.name}' with global scope. Failed because global variables are not yet supported."
            )

        variable = self._find_variable_by_name(request.name)
        if not variable:
            return SetVariableTypeResultFailure(
                result_details=f"Attempted to set type for variable '{request.name}'. Failed because no such variable could be found."
            )

        variable.type = request.type
        return SetVariableTypeResultSuccess()

    def on_delete_variable_request(self, request: DeleteVariableRequest) -> ResultPayload:
        """Delete a variable."""
        # For now, just look in current flow variables
        # Reject GLOBAL scope requests for now
        if request.lookup_scope == VariableScope.GLOBAL_ONLY:
            return DeleteVariableResultFailure(
                result_details=f"Attempted to delete variable '{request.name}' with global scope. Failed because global variables are not yet supported."
            )

        variable = self._find_variable_by_name(request.name)
        if not variable:
            return DeleteVariableResultFailure(
                result_details=f"Attempted to delete variable '{request.name}'. Failed because no such variable could be found."
            )

        # Remove from storage
        del self._local_workflow_variables[variable.name]
        return DeleteVariableResultSuccess()

    def on_rename_variable_request(self, request: RenameVariableRequest) -> ResultPayload:
        """Rename a variable."""
        # For now, just look in current flow variables
        # Reject GLOBAL scope requests for now
        if request.lookup_scope == VariableScope.GLOBAL_ONLY:
            return RenameVariableResultFailure(
                result_details=f"Attempted to rename variable '{request.name}' with global scope. Failed because global variables are not yet supported."
            )

        variable = self._find_variable_by_name(request.name)
        if not variable:
            return RenameVariableResultFailure(
                result_details=f"Attempted to rename variable '{request.name}'. Failed because no such variable could be found."
            )

        # Check for name collision with new name
        existing = self._find_variable_by_name(request.new_name)
        if existing and existing.name != variable.name:
            return RenameVariableResultFailure(
                result_details=f"Attempted to rename variable '{request.name}' to '{request.new_name}'. Failed because a variable with that name already exists."
            )

        # Update the dictionary key and variable name
        old_name = variable.name
        variable.name = request.new_name
        del self._local_workflow_variables[old_name]
        self._local_workflow_variables[request.new_name] = variable
        return RenameVariableResultSuccess()

    def on_has_variable_request(self, request: HasVariableRequest) -> ResultPayload:
        """Check if a variable exists."""
        # For now, just look in current flow variables
        # Reject GLOBAL scope requests for now
        if request.lookup_scope == VariableScope.GLOBAL_ONLY:
            return HasVariableResultFailure(
                result_details=f"Attempted to check existence of variable '{request.name}' with global scope. Failed because global variables are not yet supported."
            )

        variable = self._find_variable_by_name(request.name)
        exists = variable is not None
        found_scope = VariableScope.CURRENT_FLOW_ONLY if exists else None

        return HasVariableResultSuccess(exists=exists, found_scope=found_scope)

    def on_list_variables_request(self, request: ListVariablesRequest) -> ResultPayload:
        """List all variables in the specified scope."""
        # Reject GLOBAL scope requests for now
        if request.lookup_scope == VariableScope.GLOBAL_ONLY:
            return ListVariablesResultFailure(
                result_details="Attempted to list variables with global scope. Failed because global variables are not yet supported."
            )

        # For current workflow scope (or no scope specified), return local variables sorted by name
        variables = sorted(self._local_workflow_variables.values(), key=lambda v: v.name)
        return ListVariablesResultSuccess(variables=variables)

    def on_get_variable_details_request(self, request: GetVariableDetailsRequest) -> ResultPayload:
        """Get variable details (metadata only, no heavy values)."""
        # For now, just look in current flow variables
        # Reject GLOBAL scope requests for now
        if request.lookup_scope == VariableScope.GLOBAL_ONLY:
            return GetVariableDetailsResultFailure(
                result_details=f"Attempted to get details for variable '{request.name}' with global scope. Failed because global variables are not yet supported."
            )

        variable = self._find_variable_by_name(request.name)
        if not variable:
            return GetVariableDetailsResultFailure(
                result_details=f"Attempted to get details for variable '{request.name}'. Failed because no such variable could be found."
            )

        details = VariableDetails(name=variable.name, scope=variable.scope, type=variable.type)
        return GetVariableDetailsResultSuccess(details=details)

    def _find_variable_by_name(self, name: str) -> FlowVariable | None:
        """Find a variable by name."""
        return self._local_workflow_variables.get(name)
