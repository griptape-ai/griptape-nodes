import logging
from typing import Any, cast

from griptape.events import EventBus

from griptape_nodes.exe_types.core_types import (
    BaseNodeElement,
    Parameter,
    ParameterContainer,
    ParameterMode,
    ParameterTypeBuiltin,
)
from griptape_nodes.exe_types.flow import ControlFlow
from griptape_nodes.exe_types.node_types import BaseNode, NodeResolutionState
from griptape_nodes.exe_types.type_validator import TypeValidator
from griptape_nodes.node_library.library_registry import LibraryNameAndVersion, LibraryRegistry
from griptape_nodes.retained_mode.events.base_events import (
    ExecutionEvent,
    ExecutionGriptapeNodeEvent,
    ResultPayload,
    ResultPayloadFailure,
)
from griptape_nodes.retained_mode.events.connection_events import (
    DeleteConnectionRequest,
    DeleteConnectionResultFailure,
    IncomingConnection,
    ListConnectionsForNodeRequest,
    ListConnectionsForNodeResultFailure,
    ListConnectionsForNodeResultSuccess,
    OutgoingConnection,
)
from griptape_nodes.retained_mode.events.execution_events import (
    CancelFlowRequest,
    ResolveNodeRequest,
    ResolveNodeResultFailure,
    ResolveNodeResultSuccess,
    StartFlowResultFailure,
)
from griptape_nodes.retained_mode.events.flow_events import (
    ListNodesInFlowRequest,
    ListNodesInFlowResultSuccess,
)
from griptape_nodes.retained_mode.events.library_events import (
    GetLibraryMetadataRequest,
    GetLibraryMetadataResultSuccess,
)
from griptape_nodes.retained_mode.events.node_events import (
    CreateNodeRequest,
    CreateNodeResultFailure,
    CreateNodeResultSuccess,
    DeleteNodeRequest,
    DeleteNodeResultFailure,
    DeleteNodeResultSuccess,
    DeserializeNodeFromCommandsRequest,
    DeserializeNodeFromCommandsResultFailure,
    DeserializeNodeFromCommandsResultSuccess,
    GetAllNodeInfoRequest,
    GetAllNodeInfoResultFailure,
    GetAllNodeInfoResultSuccess,
    GetNodeMetadataRequest,
    GetNodeMetadataResultFailure,
    GetNodeMetadataResultSuccess,
    GetNodeResolutionStateRequest,
    GetNodeResolutionStateResultFailure,
    GetNodeResolutionStateResultSuccess,
    ListParametersOnNodeRequest,
    ListParametersOnNodeResultFailure,
    ListParametersOnNodeResultSuccess,
    SerializedNodeCommands,
    SerializeNodeToCommandsRequest,
    SerializeNodeToCommandsResultFailure,
    SerializeNodeToCommandsResultSuccess,
    SetNodeMetadataRequest,
    SetNodeMetadataResultFailure,
    SetNodeMetadataResultSuccess,
)
from griptape_nodes.retained_mode.events.parameter_events import (
    AddParameterToNodeRequest,
    AddParameterToNodeResultFailure,
    AddParameterToNodeResultSuccess,
    AlterParameterDetailsRequest,
    AlterParameterDetailsResultFailure,
    AlterParameterDetailsResultSuccess,
    AlterParameterEvent,
    GetCompatibleParametersRequest,
    GetCompatibleParametersResultFailure,
    GetCompatibleParametersResultSuccess,
    GetNodeElementDetailsRequest,
    GetNodeElementDetailsResultFailure,
    GetNodeElementDetailsResultSuccess,
    GetParameterDetailsRequest,
    GetParameterDetailsResultFailure,
    GetParameterDetailsResultSuccess,
    GetParameterValueRequest,
    GetParameterValueResultFailure,
    GetParameterValueResultSuccess,
    ParameterAndMode,
    RemoveParameterFromNodeRequest,
    RemoveParameterFromNodeResultFailure,
    RemoveParameterFromNodeResultSuccess,
    SetParameterValueRequest,
    SetParameterValueResultFailure,
    SetParameterValueResultSuccess,
)
from griptape_nodes.retained_mode.events.validation_events import (
    ValidateNodeDependenciesRequest,
    ValidateNodeDependenciesResultFailure,
    ValidateNodeDependenciesResultSuccess,
)
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
from griptape_nodes.retained_mode.managers.event_manager import EventManager

logger = logging.getLogger("griptape_nodes")


class NodeManager:
    _name_to_parent_flow_name: dict[str, str]

    def __init__(self, event_manager: EventManager) -> None:
        self._name_to_parent_flow_name = {}

        event_manager.assign_manager_to_request_type(CreateNodeRequest, self.on_create_node_request)
        event_manager.assign_manager_to_request_type(DeleteNodeRequest, self.on_delete_node_request)
        event_manager.assign_manager_to_request_type(
            GetNodeResolutionStateRequest, self.on_get_node_resolution_state_request
        )
        event_manager.assign_manager_to_request_type(GetNodeMetadataRequest, self.on_get_node_metadata_request)
        event_manager.assign_manager_to_request_type(SetNodeMetadataRequest, self.on_set_node_metadata_request)
        event_manager.assign_manager_to_request_type(
            ListConnectionsForNodeRequest, self.on_list_connections_for_node_request
        )
        event_manager.assign_manager_to_request_type(
            ListParametersOnNodeRequest, self.on_list_parameters_on_node_request
        )
        event_manager.assign_manager_to_request_type(AddParameterToNodeRequest, self.on_add_parameter_to_node_request)
        event_manager.assign_manager_to_request_type(
            RemoveParameterFromNodeRequest, self.on_remove_parameter_from_node_request
        )
        event_manager.assign_manager_to_request_type(GetParameterDetailsRequest, self.on_get_parameter_details_request)
        event_manager.assign_manager_to_request_type(
            AlterParameterDetailsRequest, self.on_alter_parameter_details_request
        )
        event_manager.assign_manager_to_request_type(GetParameterValueRequest, self.on_get_parameter_value_request)
        event_manager.assign_manager_to_request_type(SetParameterValueRequest, self.on_set_parameter_value_request)
        event_manager.assign_manager_to_request_type(ResolveNodeRequest, self.on_resolve_from_node_request)
        event_manager.assign_manager_to_request_type(GetAllNodeInfoRequest, self.on_get_all_node_info_request)
        event_manager.assign_manager_to_request_type(
            GetCompatibleParametersRequest, self.on_get_compatible_parameters_request
        )
        event_manager.assign_manager_to_request_type(
            ValidateNodeDependenciesRequest, self.on_validate_node_dependencies_request
        )
        event_manager.assign_manager_to_request_type(
            GetNodeElementDetailsRequest, self.on_get_node_element_details_request
        )
        event_manager.assign_manager_to_request_type(SerializeNodeToCommandsRequest, self.on_serialize_node_to_commands)
        event_manager.assign_manager_to_request_type(
            DeserializeNodeFromCommandsRequest, self.on_deserialize_node_from_commands
        )

    def handle_node_rename(self, old_name: str, new_name: str) -> None:
        # Replace the old node name and its parent.
        parent = self._name_to_parent_flow_name[old_name]
        self._name_to_parent_flow_name[new_name] = parent
        del self._name_to_parent_flow_name[old_name]

    def handle_flow_rename(self, old_name: str, new_name: str) -> None:
        # Find all instances where a node had the old parent and update it to the new one.
        for node_name, parent_flow_name in self._name_to_parent_flow_name.items():
            if parent_flow_name == old_name:
                self._name_to_parent_flow_name[node_name] = new_name

    def on_create_node_request(self, request: CreateNodeRequest) -> ResultPayload:
        # Validate as much as possible before we actually create one.
        parent_flow_name = request.override_parent_flow_name
        if parent_flow_name is None:
            # Try to get the current context flow
            if not GriptapeNodes.ContextManager().has_current_flow():
                details = (
                    "Attempted to create Node in the Current Context. Failed because the Current Context was empty."
                )
                logger.error(details)
                return CreateNodeResultFailure()
            parent_flow_name = GriptapeNodes.ContextManager().get_current_flow_name()

        # Does this flow actually exist?
        flow_mgr = GriptapeNodes.FlowManager()
        try:
            flow = flow_mgr.get_flow_by_name(parent_flow_name)
        except KeyError as err:
            details = f"Could not create Node of type '{request.node_type}'. Error: {err}"
            logger.error(details)
            return CreateNodeResultFailure()

        # Now ensure that we're giving a valid name.
        obj_mgr = GriptapeNodes.ObjectManager()
        final_node_name = obj_mgr.generate_name_for_object(
            type_name=request.node_type, requested_name=request.node_name
        )
        remapped_requested_node_name = (request.node_name is not None) and (request.node_name != final_node_name)

        # OK, let's try and create the Node.
        node = None
        try:
            node = LibraryRegistry.create_node(
                name=final_node_name,
                node_type=request.node_type,
                specific_library_name=request.specific_library_name,
                metadata=request.metadata,
            )
        # modifying to exception to try to catch all possible issues with node creation.
        except Exception as err:
            import traceback

            traceback.print_exc()
            details = f"Could not create Node '{final_node_name}' of type '{request.node_type}': {err}"
            logger.error(details)
            return CreateNodeResultFailure()

        # Add it to the Flow.
        flow.add_node(node)

        # Record keeping.
        obj_mgr.add_object_by_name(node.name, node)
        self._name_to_parent_flow_name[node.name] = parent_flow_name

        # We don't want to start in a resolving state, bump it back to unresolved.
        state = request.resolution
        if state == NodeResolutionState.RESOLVING:
            state = NodeResolutionState.UNRESOLVED
            logger.warning(
                "Node '%s' was created in a RESOLVING state. This is not allowed. Setting to UNRESOLVED.", node.name
            )
        node.state = NodeResolutionState(state)

        # See if we want to push this into the context of the current flow.
        if request.set_as_new_context:
            GriptapeNodes.ContextManager().push_node(final_node_name)

        # Success message based on whether we used Current Context or explicit flow
        if request.override_parent_flow_name is None:
            details = (
                f"Successfully created Node '{final_node_name}' in the Current Context (Flow '{parent_flow_name}')"
            )
        else:
            details = f"Successfully created Node '{final_node_name}' in Flow '{parent_flow_name}'"

        log_level = logging.DEBUG
        if remapped_requested_node_name:
            log_level = logging.WARNING
            details = f"{details}. WARNING: Had to rename from original node name requested '{request.node_name}' as an object with this name already existed."

        logger.log(level=log_level, msg=details)

        return CreateNodeResultSuccess(node_name=node.name)

    def cancel_conditionally(
        self, parent_flow: ControlFlow, parent_flow_name: str, node: BaseNode
    ) -> ResultPayload | None:
        """Conditionally cancels a parent flow if it's currently executing nodes are connected to the specified node.

        This method checks if the parent flow is running, and if so, determines whether the currently
        executing or resolving node is connected to the specified node. If a connection exists, the parent
        flow is cancelled to prevent operations on the deleted node.

        Args:
            parent_flow: The control flow object that may need to be cancelled.
            parent_flow_name: The name of the parent flow for use in cancellation requests.
            node: The base node that is trying to be deleted.

        Returns:
            ResultPayload: A DeleteNodeResultFailure if cancellation was attempted but failed.
            None: If no cancellation was needed or cancellation succeeded.

        Note:
            This method also clears the flow queue regardless of whether cancellation occurred,
            to ensure the specified node is not processed in the future.
        """
        if parent_flow.check_for_existing_running_flow():
            # get the current node executing / resolving
            # if it's in connected nodes, cancel flow.
            # otherwise, leave it.
            control_node_name, resolving_node_name = parent_flow.flow_state()
            connected_nodes = parent_flow.get_all_connected_nodes(node)
            cancelled = False
            if control_node_name is not None:
                control_node = GriptapeNodes.ObjectManager().get_object_by_name(control_node_name)
                if control_node in connected_nodes:
                    result = GriptapeNodes.handle_request(CancelFlowRequest(flow_name=parent_flow_name))
                    cancelled = True
                    if not result.succeeded():
                        details = (
                            f"Attempted to delete a Node '{node.name}'. Failed because running flow could not cancel."
                        )
                        logger.error(details)
                        return DeleteNodeResultFailure()
            if resolving_node_name is not None and not cancelled:
                resolving_node = GriptapeNodes.ObjectManager().get_object_by_name(resolving_node_name)
                if resolving_node in connected_nodes:
                    result = GriptapeNodes.handle_request(CancelFlowRequest(flow_name=parent_flow_name))
                    if not result.succeeded():
                        details = (
                            f"Attempted to delete a Node '{node.name}'. Failed because running flow could not cancel."
                        )
                        logger.error(details)
                        return DeleteNodeResultFailure()
            # Clear the queue, because we don't want to his this node eventually.
            parent_flow.clear_flow_queue()
        return None

    def on_delete_node_request(self, request: DeleteNodeRequest) -> ResultPayload:  # noqa: C901, PLR0911 (complex logic, lots of edge cases)
        node_name = request.node_name
        if node_name is None:
            # Get from the current context.
            if not GriptapeNodes.ContextManager().has_current_node():
                details = (
                    "Attempted to delete a Node from the Current Context. Failed because the Current Context is empty."
                )
                logger.error(details)
                return DeleteNodeResultFailure()

            node_name = GriptapeNodes.ContextManager().get_current_node_name()

        with GriptapeNodes.ContextManager().node(node_name=node_name):
            # Does this node exist?
            obj_mgr = GriptapeNodes.ObjectManager()

            node = obj_mgr.attempt_get_object_by_name_as_type(node_name, BaseNode)
            if node is None:
                details = f"Attempted to delete a Node '{node_name}', but no such Node was found."
                logger.error(details)
                return DeleteNodeResultFailure()

            parent_flow_name = self._name_to_parent_flow_name[node_name]
            try:
                parent_flow = GriptapeNodes.FlowManager().get_flow_by_name(parent_flow_name)
            except KeyError as err:
                details = f"Attempted to delete a Node '{node_name}'. Error: {err}"
                logger.error(details)
                return DeleteNodeResultFailure()

            cancel_result = self.cancel_conditionally(parent_flow, parent_flow_name, node)
            if cancel_result is not None:
                return cancel_result
            # Remove all connections from this Node.
            list_node_connections_request = ListConnectionsForNodeRequest(node_name=node_name)
            list_connections_result = GriptapeNodes.handle_request(request=list_node_connections_request)
            if not isinstance(list_connections_result, ListConnectionsForNodeResultSuccess):
                details = f"Attempted to delete a Node '{node_name}'. Failed because it could not gather Connections to the Node."
                logger.error(details)
                return DeleteNodeResultFailure()

            # Destroy all the incoming Connections
            for incoming_connection in list_connections_result.incoming_connections:
                delete_request = DeleteConnectionRequest(
                    source_node_name=incoming_connection.source_node_name,
                    source_parameter_name=incoming_connection.source_parameter_name,
                    target_node_name=node_name,
                    target_parameter_name=incoming_connection.target_parameter_name,
                )
                delete_result = GriptapeNodes.handle_request(delete_request)
                if isinstance(delete_result, ResultPayloadFailure):
                    details = f"Attempted to delete a Node '{node_name}'. Failed when attempting to delete Connection."
                    logger.error(details)
                    return DeleteNodeResultFailure()

            # Destroy all the outgoing Connections
            for outgoing_connection in list_connections_result.outgoing_connections:
                delete_request = DeleteConnectionRequest(
                    source_node_name=node_name,
                    source_parameter_name=outgoing_connection.source_parameter_name,
                    target_node_name=outgoing_connection.target_node_name,
                    target_parameter_name=outgoing_connection.target_parameter_name,
                )
                delete_result = GriptapeNodes.handle_request(delete_request)
                if isinstance(delete_result, ResultPayloadFailure):
                    details = f"Attempted to delete a Node '{node_name}'. Failed when attempting to delete Connection."
                    logger.error(details)
                    return DeleteNodeResultFailure()

        # Remove from the owning Flow
        parent_flow.remove_node(node.name)

        # Now remove the record keeping
        obj_mgr.del_obj_by_name(node_name)
        del self._name_to_parent_flow_name[node_name]

        # If we were part of the Current Context, pop it.
        if request.node_name is None:
            GriptapeNodes.ContextManager().pop_node()

        details = f"Successfully deleted Node '{node_name}'."
        logger.debug(details)

        return DeleteNodeResultSuccess()

    def on_get_node_resolution_state_request(self, request: GetNodeResolutionStateRequest) -> ResultPayload:
        node_name = request.node_name
        if node_name is None:
            # Get from the current context.
            if not GriptapeNodes.ContextManager().has_current_node():
                details = "Attempted to get resolution state for a Node from the Current Context. Failed because the Current Context is empty."
                logger.error(details)
                return GetNodeResolutionStateResultFailure()

            node_name = GriptapeNodes.ContextManager().get_current_node_name()

        # Does this node exist?
        obj_mgr = GriptapeNodes.ObjectManager()

        node = obj_mgr.attempt_get_object_by_name_as_type(node_name, BaseNode)
        if node is None:
            details = f"Attempted to get resolution state for a Node '{node_name}', but no such Node was found."
            logger.error(details)
            result = GetNodeResolutionStateResultFailure()
            return result

        node_state = node.state

        details = f"Successfully got resolution state for Node '{node_name}'."
        logger.debug(details)

        result = GetNodeResolutionStateResultSuccess(
            state=node_state.name,
        )
        return result

    def on_get_node_metadata_request(self, request: GetNodeMetadataRequest) -> ResultPayload:
        node_name = request.node_name
        if node_name is None:
            # Get from the current context.
            if not GriptapeNodes.ContextManager().has_current_node():
                details = "Attempted to get metadata for a Node from the Current Context. Failed because the Current Context is empty."
                logger.error(details)
                return GetNodeMetadataResultFailure()

            node_name = GriptapeNodes.ContextManager().get_current_node_name()

        # Does this node exist?
        obj_mgr = GriptapeNodes.ObjectManager()

        node = obj_mgr.attempt_get_object_by_name_as_type(node_name, BaseNode)
        if node is None:
            details = f"Attempted to get metadata for a Node '{node_name}', but no such Node was found."
            logger.error(details)

            result = GetNodeMetadataResultFailure()
            return result

        metadata = node.metadata
        details = f"Successfully retrieved metadata for a Node '{node_name}'."
        logger.debug(details)

        result = GetNodeMetadataResultSuccess(
            metadata=metadata,
        )
        return result

    def on_set_node_metadata_request(self, request: SetNodeMetadataRequest) -> ResultPayload:
        node_name = request.node_name
        if node_name is None:
            # Get from the current context.
            if not GriptapeNodes.ContextManager().has_current_node():
                details = "Attempted to set metadata for a Node from the Current Context. Failed because the Current Context is empty."
                logger.error(details)
                return SetNodeMetadataResultFailure()

            node_name = GriptapeNodes.ContextManager().get_current_node_name()

        # Does this node exist?
        obj_mgr = GriptapeNodes.ObjectManager()

        node = obj_mgr.attempt_get_object_by_name_as_type(node_name, BaseNode)
        if node is None:
            details = f"Attempted to set metadata for a Node '{node_name}', but no such Node was found."
            logger.error(details)

            result = SetNodeMetadataResultFailure()
            return result
        # We can't completely overwrite metadata.
        for key, value in request.metadata.items():
            node.metadata[key] = value
        details = f"Successfully set metadata for a Node '{node_name}'."
        logger.debug(details)

        result = SetNodeMetadataResultSuccess()
        return result

    def on_list_connections_for_node_request(self, request: ListConnectionsForNodeRequest) -> ResultPayload:
        node_name = request.node_name
        if node_name is None:
            # Get from the current context.
            if not GriptapeNodes.ContextManager().has_current_node():
                details = "Attempted to list Connections for a Node from the Current Context. Failed because the Current Context is empty."
                logger.error(details)
                return ListConnectionsForNodeResultFailure()

            node_name = GriptapeNodes.ContextManager().get_current_node_name()

        # Does this node exist?
        obj_mgr = GriptapeNodes.ObjectManager()

        node = obj_mgr.attempt_get_object_by_name_as_type(node_name, BaseNode)
        if node is None:
            details = f"Attempted to list Connections for a Node '{node_name}', but no such Node was found."
            logger.error(details)

            result = ListConnectionsForNodeResultFailure()
            return result

        parent_flow_name = self._name_to_parent_flow_name[node_name]
        try:
            parent_flow = GriptapeNodes.FlowManager().get_flow_by_name(parent_flow_name)
        except KeyError as err:
            details = f"Attempted to list Connections for a Node '{node_name}'. Error: {err}"
            logger.error(details)

            result = ListConnectionsForNodeResultFailure()
            return result

        # Kinda gross, but let's do it
        connection_mgr = parent_flow.connections
        # get outgoing connections
        outgoing_connections_list = []
        if node_name in connection_mgr.outgoing_index:
            outgoing_connections_list = [
                OutgoingConnection(
                    source_parameter_name=connection.source_parameter.name,
                    target_node_name=connection.target_node.name,
                    target_parameter_name=connection.target_parameter.name,
                )
                for connection_lists in connection_mgr.outgoing_index[node_name].values()
                for connection_id in connection_lists
                for connection in [connection_mgr.connections[connection_id]]
            ]
        # get incoming connections
        incoming_connections_list = []
        if node_name in connection_mgr.incoming_index:
            incoming_connections_list = [
                IncomingConnection(
                    source_node_name=connection.source_node.name,
                    source_parameter_name=connection.source_parameter.name,
                    target_parameter_name=connection.target_parameter.name,
                )
                for connection_lists in connection_mgr.incoming_index[node_name].values()
                for connection_id in connection_lists
                for connection in [
                    connection_mgr.connections[connection_id]
                ]  # This creates a temporary one-item list with the connection
            ]

        details = f"Successfully listed all Connections to and from Node '{node_name}'."
        logger.debug(details)

        result = ListConnectionsForNodeResultSuccess(
            incoming_connections=incoming_connections_list,
            outgoing_connections=outgoing_connections_list,
        )
        return result

    def on_list_parameters_on_node_request(self, request: ListParametersOnNodeRequest) -> ResultPayload:
        node_name = request.node_name

        if node_name is None:
            # Get from the current context.
            if not GriptapeNodes.ContextManager().has_current_node():
                details = "Attempted to list Parameters for a Node from the Current Context. Failed because the Current Context is empty."
                logger.error(details)
                return ListParametersOnNodeResultFailure()

            node_name = GriptapeNodes.ContextManager().get_current_node_name()

        # Does this node exist?
        obj_mgr = GriptapeNodes.ObjectManager()
        node = obj_mgr.attempt_get_object_by_name_as_type(node_name, BaseNode)
        if node is None:
            details = f"Attempted to list Parameters for a Node '{node_name}', but no such Node was found."
            logger.error(details)

            result = ListParametersOnNodeResultFailure()
            return result

        ret_list = [param.name for param in node.parameters]

        details = f"Successfully listed Parameters for Node '{node_name}'."
        logger.debug(details)

        result = ListParametersOnNodeResultSuccess(
            parameter_names=ret_list,
        )
        return result

    def on_add_parameter_to_node_request(self, request: AddParameterToNodeRequest) -> ResultPayload:  # noqa: C901, PLR0911, PLR0912, PLR0915
        node_name = request.node_name

        if node_name is None:
            # Get from the current context.
            if not GriptapeNodes.ContextManager().has_current_node():
                details = "Attempted to add Parameter to a Node from the Current Context. Failed because the Current Context is empty."
                logger.error(details)
                return AddParameterToNodeResultFailure()

            node_name = GriptapeNodes.ContextManager().get_current_node_name()

        # Does this node exist?
        obj_mgr = GriptapeNodes.ObjectManager()

        node = obj_mgr.attempt_get_object_by_name_as_type(node_name, BaseNode)
        if node is None:
            details = f"Attempted to add Parameter '{request.parameter_name}' to a Node '{node_name}', but no such Node was found."
            logger.error(details)

            result = AddParameterToNodeResultFailure()
            return result

        if request.parent_container_name and not request.initial_setup:
            parameter = node.get_parameter_by_name(request.parent_container_name)
            if parameter is None:
                details = f"Attempted to add Parameter to Container Parameter '{request.parent_container_name}' in node '{node_name}'. Failed because parameter didn't exist."
                logger.error(details)
                result = AddParameterToNodeResultFailure()
                return result
            if not isinstance(parameter, ParameterContainer):
                details = f"Attempted to add Parameter to Container Parameter '{request.parent_container_name}' in node '{node_name}'. Failed because parameter wasn't a container."
                logger.error(details)
                result = AddParameterToNodeResultFailure()
                return result
            try:
                new_param = parameter.add_child_parameter()
            except Exception as e:
                details = f"Attempted to add Parameter to Container Parameter '{request.parent_container_name}' in node '{node_name}'. Failed: {e}."
                logger.exception(details)
                result = AddParameterToNodeResultFailure()
                return result
            return AddParameterToNodeResultSuccess(
                parameter_name=new_param.name, type=new_param.type, node_name=node_name
            )
        if request.parameter_name is None or request.tooltip is None:
            details = f"Attempted to add Parameter to node '{node_name}'. Failed because default_value, tooltip, or parameter_name was not defined."
            logger.error(details)
            result = AddParameterToNodeResultFailure()
            return result
        # Does the Node already have a parameter by this name?
        if node.get_parameter_by_name(request.parameter_name) is not None:
            details = f"Attempted to add Parameter '{request.parameter_name}' to Node '{node_name}'. Failed because it already had a Parameter with that name on it. Parameter names must be unique within the Node."
            logger.error(details)

            result = AddParameterToNodeResultFailure()
            return result

        # Let's see if the Parameter is properly formed.
        # If a Parameter is intended for Control, it needs to have that be the exclusive type.
        # The 'type', 'types', and 'output_type' are a little weird to handle (see Parameter definition for details)
        has_control_type = False
        has_non_control_types = False
        if request.type is not None:
            if request.type.lower() == ParameterTypeBuiltin.CONTROL_TYPE.value.lower():
                has_control_type = True
            else:
                has_non_control_types = True
        if request.input_types is not None:
            for test_type in request.input_types:
                if test_type.lower == ParameterTypeBuiltin.CONTROL_TYPE.value.lower():
                    has_control_type = True
                else:
                    has_non_control_types = True
        if request.output_type is not None:
            if request.output_type.lower() == ParameterTypeBuiltin.CONTROL_TYPE.value.lower():
                has_control_type = True
            else:
                has_non_control_types = True

        if has_control_type and has_non_control_types:
            details = f"Attempted to add Parameter '{request.parameter_name}' to Node '{node_name}'. Failed because it had 'ParameterControlType' AND at least one other non-control type. If a Parameter is intended for control, it must only accept that type."
            logger.error(details)

            result = AddParameterToNodeResultFailure()
            return result

        allowed_modes = set()
        if request.mode_allowed_input:
            allowed_modes.add(ParameterMode.INPUT)
        if request.mode_allowed_property:
            allowed_modes.add(ParameterMode.PROPERTY)
        if request.mode_allowed_output:
            allowed_modes.add(ParameterMode.OUTPUT)

        # Let's roll, I guess.
        new_param = Parameter(
            name=request.parameter_name,
            type=request.type,
            input_types=request.input_types,
            output_type=request.output_type,
            default_value=request.default_value,
            user_defined=True,
            tooltip=request.tooltip,
            tooltip_as_input=request.tooltip_as_input,
            tooltip_as_property=request.tooltip_as_property,
            tooltip_as_output=request.tooltip_as_output,
            allowed_modes=allowed_modes,
            ui_options=request.ui_options,
            parent_container_name=request.parent_container_name,
        )
        try:
            if request.parent_container_name and request.initial_setup:
                parameter_parent = node.get_parameter_by_name(request.parent_container_name)
                if parameter_parent is not None:
                    parameter_parent.add_child(new_param)
            else:
                logger.info(new_param.name)
                node.add_parameter(new_param)
        except Exception as e:
            details = f"Couldn't add parameter with name {request.parameter_name} to node. Error: {e}"
            logger.error(details)
            return AddParameterToNodeResultFailure()

        details = f"Successfully added Parameter '{request.parameter_name}' to Node '{node_name}'."
        logger.debug(details)

        result = AddParameterToNodeResultSuccess(
            parameter_name=new_param.name, type=new_param.type, node_name=node_name
        )
        return result

    def on_remove_parameter_from_node_request(self, request: RemoveParameterFromNodeRequest) -> ResultPayload:  # noqa: C901, PLR0911, PLR0912, PLR0915
        node_name = request.node_name

        if node_name is None:
            # Get the Current Context
            if not GriptapeNodes.ContextManager().has_current_node():
                details = f"Attempted to remove Parameter '{request.parameter_name}' from a Node, but no Current Context was found."
                logger.error(details)

                result = RemoveParameterFromNodeResultFailure()
                return result

            node_name = GriptapeNodes.ContextManager().get_current_node_name()

        # Does this node exist?
        obj_mgr = GriptapeNodes.ObjectManager()

        node = obj_mgr.attempt_get_object_by_name_as_type(node_name, BaseNode)
        if node is None:
            details = f"Attempted to remove Parameter '{request.parameter_name}' from a Node '{node_name}', but no such Node was found."
            logger.error(details)

            result = RemoveParameterFromNodeResultFailure()
            return result

        # Does the Parameter actually exist on the Node?
        parameter = node.get_parameter_by_name(request.parameter_name)
        parameter_group = node.get_group_by_name_or_element_id(request.parameter_name)
        if parameter is None and parameter_group is None:
            details = f"Attempted to remove Parameter '{request.parameter_name}' from Node '{node_name}'. Failed because it didn't have a Parameter with that name on it."
            logger.error(details)

            result = RemoveParameterFromNodeResultFailure()
            return result
        if parameter_group is not None:
            for child in parameter_group.find_elements_by_type(Parameter):
                GriptapeNodes.handle_request(RemoveParameterFromNodeRequest(child.name, node_name))
            node.remove_group_by_name(request.parameter_name)
            return RemoveParameterFromNodeResultSuccess()

        # No tricky stuff, users!
        if parameter is not None and parameter.user_defined is False:
            details = f"Attempted to remove Parameter '{request.parameter_name}' from Node '{node_name}'. Failed because the Parameter was not user-defined (i.e., critical to the Node implementation). Only user-defined Parameters can be removed from a Node."
            logger.error(details)

            result = RemoveParameterFromNodeResultFailure()
            return result

        # Get all the connections to/from this Parameter.
        list_node_connections_request = ListConnectionsForNodeRequest(node_name=node_name)
        list_connections_result = GriptapeNodes.handle_request(request=list_node_connections_request)
        if not isinstance(list_connections_result, ListConnectionsForNodeResultSuccess):
            details = f"Attempted to remove Parameter '{request.parameter_name}' from Node '{node_name}'. Failed because we were unable to get a list of Connections for the Parameter's Node."
            logger.error(details)

            result = RemoveParameterFromNodeResultFailure()
            return result

        # We have a list of all connections to the NODE. Sift down to just those that are about this PARAMETER.

        # Destroy all the incoming Connections to this PARAMETER
        for incoming_connection in list_connections_result.incoming_connections:
            if incoming_connection.target_parameter_name == request.parameter_name:
                delete_request = DeleteConnectionRequest(
                    source_node_name=incoming_connection.source_node_name,
                    source_parameter_name=incoming_connection.source_parameter_name,
                    target_node_name=node_name,
                    target_parameter_name=incoming_connection.target_parameter_name,
                )
                delete_result = GriptapeNodes.handle_request(delete_request)
                if isinstance(delete_result, DeleteConnectionResultFailure):
                    details = f"Attempted to remove Parameter '{request.parameter_name}' from Node '{node_name}'. Failed because we were unable to delete a Connection for that Parameter."
                    logger.error(details)

                    result = RemoveParameterFromNodeResultFailure()

        # Destroy all the outgoing Connections from this PARAMETER
        for outgoing_connection in list_connections_result.outgoing_connections:
            if outgoing_connection.source_parameter_name == request.parameter_name:
                delete_request = DeleteConnectionRequest(
                    source_node_name=node_name,
                    source_parameter_name=outgoing_connection.source_parameter_name,
                    target_node_name=outgoing_connection.target_node_name,
                    target_parameter_name=outgoing_connection.target_parameter_name,
                )
                delete_result = GriptapeNodes.handle_request(delete_request)
                if isinstance(delete_result, DeleteConnectionResultFailure):
                    details = f"Attempted to remove Parameter '{request.parameter_name}' from Node '{node_name}'. Failed because we were unable to delete a Connection for that Parameter."
                    logger.error(details)

                    result = RemoveParameterFromNodeResultFailure()

        # Delete the Parameter itself.
        if parameter is not None:
            node.remove_parameter(parameter)
        else:
            details = f"Attempted to remove Parameter '{request.parameter_name}' from Node '{node_name}'. Failed because parameter didn't exist."
            logger.error(details)

            result = RemoveParameterFromNodeResultFailure()

        details = f"Successfully removed Parameter '{request.parameter_name}' from Node '{node_name}'."
        logger.debug(details)

        result = RemoveParameterFromNodeResultSuccess()
        return result

    def on_get_parameter_details_request(self, request: GetParameterDetailsRequest) -> ResultPayload:
        node_name = request.node_name
        if node_name is None:
            if not GriptapeNodes.ContextManager().has_current_node():
                details = f"Attempted to get details for Parameter '{request.parameter_name}' from a Node, but no Current Context was found."
                logger.error(details)

                result = GetParameterDetailsResultFailure()
                return result
            node_name = GriptapeNodes.ContextManager().get_current_node_name()

        # Does this node exist?
        obj_mgr = GriptapeNodes.ObjectManager()

        node = obj_mgr.attempt_get_object_by_name_as_type(node_name, BaseNode)
        if node is None:
            details = f"Attempted to get details for Parameter '{request.parameter_name}' from a Node '{node_name}', but no such Node was found."
            logger.error(details)

            result = GetParameterDetailsResultFailure()
            return result

        # Does the Parameter actually exist on the Node?
        parameter = node.get_parameter_by_name(request.parameter_name)
        if parameter is None:
            details = f"Attempted to get details for Parameter '{request.parameter_name}' from Node '{node_name}'. Failed because it didn't have a Parameter with that name on it."
            logger.error(details)

            result = GetParameterDetailsResultFailure()
            return result

        # Let's bundle up the details.
        modes_allowed = parameter.allowed_modes
        allows_input = ParameterMode.INPUT in modes_allowed
        allows_property = ParameterMode.PROPERTY in modes_allowed
        allows_output = ParameterMode.OUTPUT in modes_allowed

        details = f"Successfully got details for Parameter '{request.parameter_name}' from Node '{node_name}'."
        logger.debug(details)

        result = GetParameterDetailsResultSuccess(
            element_id=parameter.element_id,
            type=parameter.type,
            input_types=parameter.input_types,
            output_type=parameter.output_type,
            default_value=parameter.default_value,
            tooltip=parameter.tooltip,
            tooltip_as_input=parameter.tooltip_as_input,
            tooltip_as_property=parameter.tooltip_as_property,
            tooltip_as_output=parameter.tooltip_as_output,
            mode_allowed_input=allows_input,
            mode_allowed_property=allows_property,
            mode_allowed_output=allows_output,
            is_user_defined=parameter.user_defined,
            ui_options=parameter.ui_options,
        )
        return result

    def on_get_node_element_details_request(self, request: GetNodeElementDetailsRequest) -> ResultPayload:
        node_name = request.node_name
        if node_name is None:
            if not GriptapeNodes.ContextManager().has_current_node():
                details = f"Attempted to get element details for element '{request.specific_element_id}` from a Node, but no Current Context was found."
                logger.error(details)

                return GetNodeElementDetailsResultFailure()
            node_name = GriptapeNodes.ContextManager().get_current_node_name()

        # Does this node exist?
        obj_mgr = GriptapeNodes.ObjectManager()

        node = obj_mgr.attempt_get_object_by_name_as_type(node_name, BaseNode)
        if node is None:
            details = f"Attempted to get element details for Node '{node_name}', but no such Node was found."
            logger.error(details)

            return GetNodeElementDetailsResultFailure()

        # Did they ask for a specific element ID?
        if request.specific_element_id is None:
            # No? Use the node's root element to search from.
            element = node.root_ui_element
        else:
            element = node.root_ui_element.find_element_by_id(request.specific_element_id)
            if element is None:
                details = f"Attempted to get element details for element '{request.specific_element_id}' from Node '{node_name}'. Failed because it didn't have an element with that ID on it."
                logger.error(details)

                return GetNodeElementDetailsResultFailure()

        element_details = element.to_dict()
        # We need to get parameter values from here
        param_to_value = {}
        self._set_param_to_value(node, element, param_to_value)
        if param_to_value:
            element_details["element_id_to_value"] = param_to_value
        details = f"Successfully got element details for Node '{node_name}'."
        logger.debug(details)
        result = GetNodeElementDetailsResultSuccess(element_details=element_details)
        return result

    def _set_param_to_value(self, node: BaseNode, element: BaseNodeElement, param_to_value: dict) -> None:
        """This method builds our element_id_to_value mapping to eventually return in the Element Details Request."""
        # Get all parameters
        for parameter in element.find_elements_by_type(Parameter):
            # Check if they have an output value, that takes priority
            if parameter.name in node.parameter_output_values:
                value = node.parameter_output_values[parameter.name]
            else:
                # Otherwise grab the set value or default value
                value = node.get_parameter_value(parameter.name)
            if value is not None:
                element_id = parameter.element_id
                # Check if the value is in builtins. If it isn't we need to handle it specially.
                if value.__class__.__module__ != "builtins":
                    # Check if it has a to_dict method. Use that, if it's been implemented.
                    if hasattr(value, "to_dict"):
                        # If the object has a __dict__, use that
                        param_to_value[element_id] = value.to_dict()
                        continue
                    # Otherwise use __dict__.
                    if hasattr(value, "__dict__"):
                        param_to_value[element_id] = value.__dict__
                        continue
                # Otherwise, just set it here. It'll be handled in .json() when we send it over.
                param_to_value[element_id] = value

    def modify_alterable_fields(self, request: AlterParameterDetailsRequest, parameter: Parameter) -> None:
        if request.tooltip is not None:
            parameter.tooltip = request.tooltip
        if request.tooltip_as_input is not None:
            parameter.tooltip_as_input = request.tooltip_as_input
        if request.tooltip_as_property is not None:
            parameter.tooltip_as_property = request.tooltip_as_property
        if request.tooltip_as_output is not None:
            parameter.tooltip_as_output = request.tooltip_as_output
        if request.ui_options is not None:
            parameter.ui_options = request.ui_options

    def modify_key_parameter_fields(self, request: AlterParameterDetailsRequest, parameter: Parameter) -> None:
        if request.type is not None:
            parameter.type = request.type
        if request.input_types is not None:
            parameter.input_types = request.input_types
        if request.output_type is not None:
            parameter.output_type = request.output_type
        if request.mode_allowed_input is not None:
            # TODO: https://github.com/griptape-ai/griptape-nodes/issues/828
            if request.mode_allowed_input is True:
                parameter.allowed_modes.add(ParameterMode.INPUT)
            else:
                parameter.allowed_modes.discard(ParameterMode.INPUT)
        if request.mode_allowed_property is not None:
            # TODO: https://github.com/griptape-ai/griptape-nodes/issues/828
            if request.mode_allowed_property is True:
                parameter.allowed_modes.add(ParameterMode.PROPERTY)
            else:
                parameter.allowed_modes.discard(ParameterMode.PROPERTY)
        if request.mode_allowed_output is not None:
            # TODO: https://github.com/griptape-ai/griptape-nodes/issues/828
            if request.mode_allowed_output is True:
                parameter.allowed_modes.add(ParameterMode.OUTPUT)
            else:
                parameter.allowed_modes.discard(ParameterMode.OUTPUT)

    def on_alter_parameter_details_request(self, request: AlterParameterDetailsRequest) -> ResultPayload:
        node_name = request.node_name

        if node_name is None:
            if not GriptapeNodes.ContextManager().has_current_node():
                details = f"Attempted to alter details for Parameter '{request.parameter_name}' from node in the Current Context. Failed because there was no such Node."
                logger.error(details)

                return AlterParameterDetailsResultFailure()
            node_name = GriptapeNodes.ContextManager().get_current_node_name()

        # Does this node exist?
        obj_mgr = GriptapeNodes.ObjectManager()
        node = obj_mgr.attempt_get_object_by_name_as_type(node_name, BaseNode)
        if node is None:
            details = f"Attempted to alter details for Parameter '{request.parameter_name}' from Node '{node_name}', but no such Node was found."
            logger.error(details)

            return AlterParameterDetailsResultFailure()

        # Does the Parameter actually exist on the Node?
        parameter = node.get_parameter_by_name(request.parameter_name)
        parameter_group = node.get_group_by_name_or_element_id(request.parameter_name)
        if parameter is None:
            parameter_group = node.get_group_by_name_or_element_id(request.parameter_name)
            if parameter_group is None:
                details = f"Attempted to alter details for Parameter '{request.parameter_name}' from Node '{node_name}'. Failed because it didn't have a Parameter with that name on it."
                logger.error(details)

                return AlterParameterDetailsResultFailure()
            if request.ui_options is not None:
                parameter_group.ui_options = request.ui_options
            return AlterParameterDetailsResultSuccess()

        # TODO: https://github.com/griptape-ai/griptape-nodes/issues/827
        # Now change all the values on the Parameter.
        self.modify_alterable_fields(request, parameter)
        # The rest of these are not alterable
        if parameter.user_defined is False and request.request_id:
            # TODO: https://github.com/griptape-ai/griptape-nodes/issues/826
            details = f"Attempted to alter details for Parameter '{request.parameter_name}' from Node '{node_name}'. Could only alter some values because the Parameter was not user-defined (i.e., critical to the Node implementation). Only user-defined Parameters can be totally modified from a Node."
            logger.warning(details)
            return AlterParameterDetailsResultSuccess()
        self.modify_key_parameter_fields(request, parameter)
        # This field requires the node as well
        if request.default_value is not None:
            # TODO: https://github.com/griptape-ai/griptape-nodes/issues/825
            node.parameter_values[request.parameter_name] = request.default_value

        details = f"Successfully altered details for Parameter '{request.parameter_name}' from Node '{node_name}'."
        logger.debug(details)

        result = AlterParameterDetailsResultSuccess()
        return result

    # For C901 (too complex): Need to give customers explicit reasons for failure on each case.
    def on_get_parameter_value_request(self, request: GetParameterValueRequest) -> ResultPayload:
        node_name = request.node_name

        if node_name is None:
            if not GriptapeNodes.ContextManager().has_current_node():
                details = f"Attempted to get value for Parameter '{request.parameter_name}' from node in the Current Context. Failed because there was no such Node."
                logger.error(details)

                return GetParameterValueResultFailure()
            node_name = GriptapeNodes.ContextManager().get_current_node_name()

        # Does this node exist?
        obj_mgr = GriptapeNodes.ObjectManager()

        # Parse the parameter name to check for list indexing
        param_name = request.parameter_name

        # Get the node
        node = obj_mgr.attempt_get_object_by_name_as_type(node_name, BaseNode)
        if node is None:
            details = f'"{node_name}" not found'
            logger.error(details)
            return GetParameterValueResultFailure()

        # Does the Parameter actually exist on the Node?
        parameter = node.get_parameter_by_name(param_name)
        if parameter is None:
            details = f'"{node_name}.{param_name}" not found'
            logger.error(details)
            return GetParameterValueResultFailure()

        # Values are actually stored on the NODE, so let's ask them.
        if param_name not in node.parameter_values:
            # Check if it might be in output values (for output parameters)
            if param_name in node.parameter_output_values:
                data_value = node.parameter_output_values[param_name]
            else:
                # Use the default if not found in either place
                data_value = parameter.default_value
        else:
            data_value = node.parameter_values[param_name]

        # Cool.
        details = f"{node_name}.{request.parameter_name} = {data_value}"
        logger.debug(details)

        result = GetParameterValueResultSuccess(
            input_types=parameter.input_types,
            type=parameter.type,
            output_type=parameter.output_type,
            value=TypeValidator.safe_serialize(data_value),
        )
        return result

    # added ignoring C901 since this method is overly long because of granular error checking, not actual complexity.
    def on_set_parameter_value_request(self, request: SetParameterValueRequest) -> ResultPayload:  # noqa: C901, PLR0911, PLR0915
        node_name = request.node_name
        if node_name is None:
            if not GriptapeNodes.ContextManager().has_current_node():
                details = f"Attempted to set parameter '{request.parameter_name}' value. Failed because no Node was found in the Current Context."
                logger.error(details)
                return SetParameterValueResultFailure()
            node_name = GriptapeNodes.ContextManager().get_current_node_name()

        # Does this node exist?
        obj_mgr = GriptapeNodes.ObjectManager()

        # Parse the parameter name to check for list indexing
        param_name = request.parameter_name

        # Get the node
        node = obj_mgr.attempt_get_object_by_name_as_type(node_name, BaseNode)
        if node is None:
            details = f"Attempted to set parameter '{param_name}' value on node '{node_name}'. Failed because no such Node could be found."
            logger.error(details)
            return SetParameterValueResultFailure()

        # Does the Parameter actually exist on the Node?
        parameter = node.get_parameter_by_name(param_name)
        if parameter is None:
            details = f"Attempted to set parameter value for '{node_name}.{param_name}'. Failed because no parameter with that name could be found."
            logger.error(details)

            result = SetParameterValueResultFailure()
            return result

        # Validate that parameters can be set at all
        if not parameter.settable:
            details = f"Attempted to set parameter value for '{node_name}.{request.parameter_name}'. Failed because that Parameter was flagged as not settable."
            logger.error(details)
            result = SetParameterValueResultFailure()
            return result

        # Well this seems kind of stupid
        object_type = request.data_type if request.data_type else parameter.type
        # Is this value kosher for the types allowed?
        if not parameter.is_incoming_type_allowed(object_type):
            details = f"Attempted to set parameter value for '{node_name}.{request.parameter_name}'. Failed because the value's type of '{object_type}' was not in the Parameter's list of allowed types: {parameter.input_types}."
            logger.error(details)

            result = SetParameterValueResultFailure()
            return result

        try:
            parent_flow_name = self.get_node_parent_flow_by_name(node.name)
        except KeyError:
            details = f"Attempted to set parameter value for '{node_name}.{request.parameter_name}'. Failed because the node's parent flow does not exist. Could not unresolve future nodes."
            logger.error(details)
            return SetParameterValueResultFailure()
        parent_flow = obj_mgr.attempt_get_object_by_name_as_type(parent_flow_name, ControlFlow)
        if not parent_flow:
            details = f"Attempted to set parameter value for '{node_name}.{request.parameter_name}'. Failed because the node's parent flow does not exist. Could not unresolve future nodes."
            logger.error(details)
            return SetParameterValueResultFailure()
        try:
            parent_flow.connections.unresolve_future_nodes(node)
        except Exception as err:
            details = f"Attempted to set parameter value for '{node_name}.{request.parameter_name}'. Failed because Exception: {err}"
            logger.error(details)
            return SetParameterValueResultFailure()

        # Values are actually stored on the NODE.
        try:
            finalized_value = self._set_and_pass_through_values(request, node)
        except Exception as err:
            details = f"Attempted to set parameter value for '{node_name}.{request.parameter_name}'. Failed because Exception: {err}"
            logger.error(details)
            return SetParameterValueResultFailure()
        # Mark node as unresolved
        if request.initial_setup is False and not request.is_output:
            # Mark node as unresolved, broadcast an event
            node.make_node_unresolved(
                current_states_to_trigger_change_event=set(
                    {NodeResolutionState.RESOLVED, NodeResolutionState.RESOLVING}
                )
            )
            # Get the flow
            # Pass the value through!
            # Optional data_type parameter for internal handling!
            conn_output_nodes = parent_flow.get_connected_output_parameters(node, parameter)
            for target_node, target_parameter in conn_output_nodes:
                GriptapeNodes.handle_request(
                    SetParameterValueRequest(
                        parameter_name=target_parameter.name,
                        node_name=target_node.name,
                        value=finalized_value,
                        data_type=object_type,  # Do type instead of output type, because it hasn't been processed.
                    )
                )

        # Cool.
        details = f"Successfully set value on Node '{node_name}' Parameter '{request.parameter_name}'."
        logger.debug(details)

        result = SetParameterValueResultSuccess(finalized_value=finalized_value, data_type=parameter.type)
        return result

    def _set_and_pass_through_values(self, request: SetParameterValueRequest, node: BaseNode) -> Any:
        """Set the parameter value on the node according to the specifications."""
        object_created = request.value
        # If the value should be set on the output dictionary:
        if request.is_output:
            # set it to output values
            node.parameter_output_values[request.parameter_name] = object_created
            return object_created
        # Otherwise use set_parameter_value. This calls our converters and validators.
        modified_parameters = node.set_parameter_value(request.parameter_name, object_created)
        # Get the "converted" value here.
        finalized_value = node.get_parameter_value(request.parameter_name)
        # If any parameters were dependent on that value, we're calling this details request to emit the result to the editor.
        if modified_parameters:
            for modified_parameter_name in modified_parameters:
                modified_parameter = node.get_parameter_by_name(modified_parameter_name)
                if modified_parameter is not None:
                    modified_request = AlterParameterEvent.create(node_name=node.name, parameter=modified_parameter)
                    EventBus.publish_event(ExecutionGriptapeNodeEvent(ExecutionEvent(payload=modified_request)))
        return finalized_value

    # For C901 (too complex): Need to give customers explicit reasons for failure on each case.
    # For PLR0911 (too many return statements): don't want to do a ton of nested chains of success,
    # want to give clear reasoning for each failure.
    # For PLR0915 (too many statements): very little reusable code here, want to be explicit and
    # make debugger use friendly.
    def on_get_all_node_info_request(self, request: GetAllNodeInfoRequest) -> ResultPayload:  # noqa: C901, PLR0911, PLR0915
        node_name = request.node_name
        # Get from the current context.
        if node_name is None:
            if not GriptapeNodes.ContextManager().has_current_node():
                details = "Attempted to get all info for a Node from the Current Context. Failed because the Current Context is empty."
                logger.error(details)
                return GetAllNodeInfoResultFailure()

            node_name = GriptapeNodes.ContextManager().get_current_node_name()

        # Does this node exist?
        obj_mgr = GriptapeNodes.ObjectManager()

        node = obj_mgr.attempt_get_object_by_name_as_type(node_name, BaseNode)
        if node is None:
            details = f"Attempted to get all info for Node named '{node_name}', but no such Node was found."
            logger.error(details)

            result = GetAllNodeInfoResultFailure()
            return result

        get_metadata_request = GetNodeMetadataRequest(node_name=node_name)
        get_metadata_result = self.on_get_node_metadata_request(get_metadata_request)
        if not get_metadata_result.succeeded():
            details = f"Attempted to get all info for Node named '{node_name}', but failed getting the metadata."
            logger.error(details)

            result = GetAllNodeInfoResultFailure()
            return GetAllNodeInfoResultFailure()

        get_resolution_state_request = GetNodeResolutionStateRequest(node_name=node_name)
        get_resolution_state_result = self.on_get_node_resolution_state_request(get_resolution_state_request)
        if not get_resolution_state_result.succeeded():
            details = (
                f"Attempted to get all info for Node named '{node_name}', but failed getting the resolution state."
            )
            logger.error(details)

            return GetAllNodeInfoResultFailure()

        list_connections_request = ListConnectionsForNodeRequest(node_name=node_name)
        list_connections_result = self.on_list_connections_for_node_request(list_connections_request)
        if not list_connections_result.succeeded():
            details = (
                f"Attempted to get all info for Node named '{node_name}', but failed listing all connections for it."
            )
            logger.error(details)

            return GetAllNodeInfoResultFailure()
        # Cast everything to get the linter off our back.
        try:
            get_metadata_success = cast("GetNodeMetadataResultSuccess", get_metadata_result)
            get_resolution_state_success = cast("GetNodeResolutionStateResultSuccess", get_resolution_state_result)
            list_connections_success = cast("ListConnectionsForNodeResultSuccess", list_connections_result)
        except Exception as err:
            details = f"Attempted to get all info for Node named '{node_name}'. Failed due to error: {err}."
            logger.error(details)

            return GetAllNodeInfoResultFailure()
        get_node_elements_request = GetNodeElementDetailsRequest(node_name=node_name)
        get_node_elements_result = self.on_get_node_element_details_request(get_node_elements_request)
        if not get_node_elements_result.succeeded():
            details = (
                f"Attempted to get all info for Node named '{node_name}', but failed getting details for elements."
            )
            logger.error(details)
            return GetAllNodeInfoResultFailure()
        try:
            get_element_details_success = cast("GetNodeElementDetailsResultSuccess", get_node_elements_result)
        except Exception as err:
            details = f"Attempted to get all info for Node named '{node_name}'. Failed due to error: {err}."
            logger.exception(details)
            return GetAllNodeInfoResultFailure()

        # this will return the node element and the value
        element_details = get_element_details_success.element_details
        if "element_id_to_value" in element_details:
            element_id_to_value = element_details["element_id_to_value"].copy()
            del element_details["element_id_to_value"]
        else:
            element_id_to_value = {}
        details = f"Successfully got all node info for node '{node_name}'."
        logger.debug(details)
        result = GetAllNodeInfoResultSuccess(
            metadata=get_metadata_success.metadata,
            node_resolution_state=get_resolution_state_success.state,
            connections=list_connections_success,
            element_id_to_value=element_id_to_value,
            root_node_element=element_details,
        )
        return result

    def on_get_compatible_parameters_request(self, request: GetCompatibleParametersRequest) -> ResultPayload:  # noqa: C901, PLR0911, PLR0912, PLR0915
        node_name = request.node_name
        if node_name is None:
            if not GriptapeNodes.ContextManager().has_current_node():
                details = "Attempted to get compatible parameters for node, but no current node was found."
                logger.error(details)
                return GetCompatibleParametersResultFailure()
            node_name = GriptapeNodes.ContextManager().get_current_node_name()

        # Vet the node
        try:
            node = self.get_node_by_name(node_name)
        except ValueError as err:
            details = f"Attempted to get compatible parameters for node '{node_name}', but that node does not exist. Error: {err}."
            logger.error(details)
            return GetCompatibleParametersResultFailure()

        # Vet the parameter.
        request_param = node.get_parameter_by_name(request.parameter_name)
        if request_param is None:
            details = f"Attempted to get compatible parameters for '{node_name}.{request.parameter_name}', but that no Parameter with that name could not be found."
            logger.error(details)
            return GetCompatibleParametersResultFailure()

        # Figure out the mode we're going for, and if this parameter supports the mode.
        request_mode = ParameterMode.OUTPUT if request.is_output else ParameterMode.INPUT
        # Does this parameter support that?
        if request_mode not in request_param.allowed_modes:
            details = f"Attempted to get compatible parameters for '{node_name}.{request.parameter_name}' as '{request_mode}', but the Parameter didn't support that type of input/output."
            logger.error(details)
            return GetCompatibleParametersResultFailure()

        # Get the parent flows.
        try:
            flow_name = self.get_node_parent_flow_by_name(node_name)
        except KeyError as err:
            details = f"Attempted to get compatible parameters for '{node_name}.{request.parameter_name}', but the node's parent flow could not be found: {err}"
            logger.error(details)
            return GetCompatibleParametersResultFailure()

        # Iterate through all nodes in this Flow (yes, this restriction still sucks)
        list_nodes_in_flow_request = ListNodesInFlowRequest(flow_name=flow_name)
        list_nodes_in_flow_result = GriptapeNodes.FlowManager().on_list_nodes_in_flow_request(
            list_nodes_in_flow_request
        )
        if not list_nodes_in_flow_result.succeeded():
            details = f"Attempted to get compatible parameters for '{node_name}.{request.parameter_name}'. Failed due to inability to list nodes in parent flow '{flow_name}'."
            logger.error(details)
            return GetCompatibleParametersResultFailure()

        try:
            list_nodes_in_flow_success = cast("ListNodesInFlowResultSuccess", list_nodes_in_flow_result)
        except Exception as err:
            details = f"Attempted to get compatible parameters for '{node_name}.{request.parameter_name}'. Failed due to {err}"
            logger.error(details)
            return GetCompatibleParametersResultFailure()

        # Walk through all nodes that are NOT us to find compatible Parameters.
        valid_parameters_by_node = {}
        for test_node_name in list_nodes_in_flow_success.node_names:
            if test_node_name != request.node_name:
                # Get node by name
                try:
                    test_node = self.get_node_by_name(test_node_name)
                except ValueError as err:
                    details = f"Attempted to get compatible parameters for node '{node_name}', and sought to test against {test_node_name}, but that node does not exist. Error: {err}."
                    logger.error(details)
                    return GetCompatibleParametersResultFailure()

                # Get Parameters from Node
                for test_param in test_node.parameters:
                    # Are we compatible from an input/output perspective?
                    fits_mode = False
                    if request_mode == ParameterMode.INPUT:
                        fits_mode = ParameterMode.OUTPUT in test_param.allowed_modes
                    else:
                        fits_mode = ParameterMode.INPUT in test_param.allowed_modes

                    if fits_mode:
                        # Compare types for compatibility
                        types_compatible = False
                        if request_mode == ParameterMode.INPUT:
                            # See if THEIR inputs would accept MY output
                            types_compatible = test_param.is_incoming_type_allowed(request_param.output_type)
                        else:
                            # See if MY inputs would accept THEIR output
                            types_compatible = request_param.is_incoming_type_allowed(test_param.output_type)

                        if types_compatible:
                            param_and_mode = ParameterAndMode(
                                parameter_name=test_param.name, is_output=not request.is_output
                            )
                            # Add the test param to our dictionary.
                            if test_node_name in valid_parameters_by_node:
                                # Append this parameter to the list
                                compatible_list = valid_parameters_by_node[test_node_name]
                                compatible_list.append(param_and_mode)
                            else:
                                # Create new
                                compatible_list = [param_and_mode]
                                valid_parameters_by_node[test_node_name] = compatible_list

        details = f"Successfully got compatible parameters for '{node_name}.{request.parameter_name}'."
        logger.debug(details)
        return GetCompatibleParametersResultSuccess(valid_parameters_by_node=valid_parameters_by_node)

    def get_node_by_name(self, name: str) -> BaseNode:
        obj_mgr = GriptapeNodes.ObjectManager()

        node = obj_mgr.attempt_get_object_by_name_as_type(name, BaseNode)
        if node is None:
            msg = f"Node '{name}' not found."
            raise ValueError(msg)

        return node

    def get_node_parent_flow_by_name(self, node_name: str) -> str:
        if node_name not in self._name_to_parent_flow_name:
            msg = f"Node '{node_name}' could not be found."
            raise KeyError(msg)
        return self._name_to_parent_flow_name[node_name]

    def on_resolve_from_node_request(self, request: ResolveNodeRequest) -> ResultPayload:  # noqa: C901, PLR0911, PLR0915, PLR0912
        node_name = request.node_name
        debug_mode = request.debug_mode

        if node_name is None:
            details = "No Node name was provided. Failed to resolve node."
            logger.error(details)

            return ResolveNodeResultFailure(validation_exceptions=[])
        try:
            node = self.get_node_by_name(node_name)
        except ValueError as e:
            details = f'Resolve failure. "{node_name}" does not exist. {e}'
            logger.error(details)

            return ResolveNodeResultFailure(validation_exceptions=[e])
        # try to get the flow parent of this node
        try:
            flow_name = self._name_to_parent_flow_name[node_name]
        except KeyError as e:
            details = f'Failed to fetch parent flow for "{node_name}": {e}'
            logger.error(details)

            return ResolveNodeResultFailure(validation_exceptions=[e])
        try:
            obj_mgr = GriptapeNodes.ObjectManager()
            flow = obj_mgr.attempt_get_object_by_name_as_type(flow_name, ControlFlow)
        except KeyError as e:
            details = f'Failed to fetch parent flow for "{node_name}": {e}'
            logger.error(details)

            return ResolveNodeResultFailure(validation_exceptions=[e])

        if flow is None:
            details = f'Failed to fetch parent flow for "{node_name}"'
            logger.error(details)
            return ResolveNodeResultFailure(validation_exceptions=[])
        if flow.check_for_existing_running_flow():
            details = f"Failed to resolve from node '{node_name}'. Flow is already running."
            logger.error(details)
            return ResolveNodeResultFailure(validation_exceptions=[])
        try:
            flow.connections.unresolve_future_nodes(node)
        except Exception as e:
            details = f'Failed to mark future nodes dirty. Unable to kick off flow from "{node_name}": {e}'
            logger.error(details)
            return ResolveNodeResultFailure(validation_exceptions=[e])
        # Validate here.
        result = self.on_validate_node_dependencies_request(ValidateNodeDependenciesRequest(node_name=node_name))
        try:
            if not result.succeeded():
                details = f"Failed to resolve node '{node_name}'. Flow Validation Failed"
                logger.error(details)
                return StartFlowResultFailure(validation_exceptions=[])
            result = cast("ValidateNodeDependenciesResultSuccess", result)

            if not result.validation_succeeded:
                details = f"Failed to resolve node '{node_name}'. Flow Validation Failed."
                if len(result.exceptions) > 0:
                    for exception in result.exceptions:
                        details = f"{details}\n\t{exception}"
                logger.error(details)
                return StartFlowResultFailure(validation_exceptions=result.exceptions)
        except Exception as e:
            details = f"Failed to resolve node '{node_name}'. Flow Validation Failed. Error: {e}"
            logger.error(details)
            return StartFlowResultFailure(validation_exceptions=[e])
        try:
            flow.resolve_singular_node(node, debug_mode)
        except Exception as e:
            details = f'Failed to resolve "{node_name}".  Error: {e}'
            logger.error(details)
            return ResolveNodeResultFailure(validation_exceptions=[e])
        details = f'Starting to resolve "{node_name}" in "{flow_name}"'
        logger.debug(details)
        return ResolveNodeResultSuccess()

    def on_validate_node_dependencies_request(self, request: ValidateNodeDependenciesRequest) -> ResultPayload:
        node_name = request.node_name
        obj_manager = GriptapeNodes.ObjectManager()
        node = obj_manager.attempt_get_object_by_name_as_type(node_name, BaseNode)
        if node is None:
            details = f'Failed to validate node dependencies. Node with "{node_name}" does not exist.'
            logger.error(details)
            return ValidateNodeDependenciesResultFailure()
        try:
            flow_name = self.get_node_parent_flow_by_name(node_name)
        except Exception as e:
            details = f'Failed to validate node dependencies. Node with "{node_name}" has no parent flow. Error: {e}'
            logger.error(details)
            return ValidateNodeDependenciesResultFailure()
        flow = GriptapeNodes.ObjectManager().attempt_get_object_by_name_as_type(flow_name, ControlFlow)
        if not flow:
            details = f'Failed to validate node dependencies. Flow with "{flow_name}" does not exist.'
            logger.error(details)
            return ValidateNodeDependenciesResultFailure()
        # Gets all dependent nodes
        nodes = flow.get_node_dependencies(node)
        all_exceptions = []
        for dependent_node in nodes:
            exceptions = dependent_node.validate_before_workflow_run()
            if exceptions:
                all_exceptions = all_exceptions + exceptions
        return ValidateNodeDependenciesResultSuccess(
            validation_succeeded=(len(all_exceptions) == 0), exceptions=all_exceptions
        )

    def on_serialize_node_to_commands(self, request: SerializeNodeToCommandsRequest) -> ResultPayload:  # noqa: C901, PLR0912
        node_name = request.node_name
        if node_name is None:
            if GriptapeNodes.ContextManager().has_current_node():
                node_name = GriptapeNodes.ContextManager().get_current_node_name()
            else:
                details = "Attempted to serialize a Node to commands from the Current Context. Failed because the Current Context is empty."
                logger.error(details)
                return SerializeNodeToCommandsResultFailure()

        # Does this node exist?
        node = GriptapeNodes.ObjectManager().attempt_get_object_by_name_as_type(node_name, BaseNode)
        if node is None:
            details = f"Attempted to serialize Node '{node_name}' to commands. Failed because no Node with that name could be found."
            logger.error(details)
            return SerializeNodeToCommandsResultFailure()

        # This is our current dude.
        with GriptapeNodes.ContextManager().node(node_name=node_name):
            # Get the library and version details.
            library_used = node.metadata["library"]
            # Get the library metadata so we can get the version.
            library_metadata_request = GetLibraryMetadataRequest(library=library_used)
            library_metadata_result = GriptapeNodes().handle_request(library_metadata_request)
            if not isinstance(library_metadata_result, GetLibraryMetadataResultSuccess):
                details = f"Attempted to serialize Node '{node_name}' to commands. Failed to get metadata for library '{library_used}'."
                logger.error(details)
                return SerializeNodeToCommandsResultFailure()

            library_version = library_metadata_result.metadata.library_version
            library_details = LibraryNameAndVersion(library_name=library_used, library_version=library_version)

            # Get the creation details.
            create_node_request = CreateNodeRequest(
                node_type=node.__class__.__name__,
                node_name=node_name,
                specific_library_name=library_details.library_name,
                metadata=node.metadata,
            )

            # We're going to compare this node instance vs. a canonical one. Rez that one up.
            reference_node = type(node)(name="REFERENCE NODE")

            # Now creation or alteration of all of the elements.
            element_modification_commands = []
            for parameter in node.parameters:
                # Create the parameter, or alter it on the existing node
                if parameter.user_defined:
                    # Add a user-defined Parameter.
                    param_dict = parameter.to_dict()
                    param_dict["node_name"] = node.name
                    param_dict["initial_setup"] = True
                    add_param_request = AddParameterToNodeRequest.create(**param_dict)
                    element_modification_commands.append(add_param_request)
                else:
                    # Not user defined. Get any deltas from the values on the reference node.
                    diff = NodeManager._manage_alter_details(parameter, reference_node)
                    relevant = False
                    for key in diff:
                        if key in AlterParameterDetailsRequest.relevant_parameters():
                            relevant = True
                            break
                    if relevant:
                        diff["node_name"] = node.name
                        diff["parameter_name"] = parameter.name
                        diff["initial_setup"] = True
                        alter_param_request = AlterParameterDetailsRequest.create(**diff)
                        element_modification_commands.append(alter_param_request)

            # Now assignment of values to all of the parameters.
            set_value_commands = []
            for parameter in node.parameters:
                # SetParameterValueRequest event
                set_param_value_request = NodeManager._handle_parameter_value_saving(
                    parameter=parameter,
                    node=node,
                    value_hash_to_unique_value_index=request.value_hash_to_unique_value_index,
                    unique_values=request.unique_parameter_values_list,
                )
                if set_param_value_request is not None:
                    set_value_commands.append(set_param_value_request)

        # Hooray
        serialized_node_commands = SerializedNodeCommands(
            create_node_command=create_node_request,
            element_modification_commands=element_modification_commands,
            node_library_details=library_details,
        )
        details = f"Successfully serialized node '{node_name}' into commands."
        logger.debug(details)
        result = SerializeNodeToCommandsResultSuccess(
            serialized_node_commands=serialized_node_commands,  # How to serialize this node
            set_parameter_value_commands=set_value_commands,  # The commands to serialize it with
        )
        return result

    def on_deserialize_node_from_commands(self, request: DeserializeNodeFromCommandsRequest) -> ResultPayload:
        # Issue the creation command first.
        create_node_request = request.serialized_node_commands.create_node_command
        create_node_result = GriptapeNodes().handle_request(create_node_request)
        if not isinstance(create_node_result, CreateNodeResultSuccess):
            details = f"Attempted to deserialize a serialized set of Node Creation commands. Failed to create node '{create_node_request.node_name}'."
            logger.error(details)
            return DeserializeNodeFromCommandsResultFailure()

        # Adopt the newly-created node as our current context.
        node_name = create_node_result.node_name
        with GriptapeNodes.ContextManager().node(node_name=node_name):
            for element_command in request.serialized_node_commands.element_modification_commands:
                element_result = GriptapeNodes().handle_request(element_command)
                if element_result.failed():
                    details = f"Attempted to deserialize a serialized set of Node Creation commands. Failed to execute an element command for node '{node_name}'."
                    logger.error(details)
                    return DeserializeNodeFromCommandsResultFailure()

        details = f"Successfully deserialized a serialized set of Node Creation commands for node '{node_name}'."
        logger.debug(details)
        return DeserializeNodeFromCommandsResultSuccess(node_name=node_name)

    @staticmethod
    def _manage_alter_details(parameter: Parameter, base_node_obj: BaseNode) -> dict:
        base_param = base_node_obj.get_parameter_by_name(parameter.name)
        if base_param:
            diff = base_param.equals(parameter)
        else:
            return vars(parameter)
        return diff

    @staticmethod
    def _handle_parameter_value_saving(
        parameter: Parameter,
        node: BaseNode,
        value_hash_to_unique_value_index: dict[Any, int],
        unique_values: list[Any],
    ) -> SerializedNodeCommands.IndexedSetParameterValueCommand | None:
        """Generates code to save a parameter value for a node in a Griptape workflow.

        This function handles the process of creating commands that will reconstruct and set
        parameter values for nodes. It performs the following steps:
        1. Retrieves the parameter value from the node's parameter values or output values
        2. Checks if the value has already been created in our list of unique values
        3. If so, it records the index for later correlation.
        4. If not, it adds the value to the uniques list and records the new index.
        5. Creates a SetParameterValueRequest to reconstruct this for the node

        Args:
            parameter (Parameter): The parameter object containing metadata
            node (BaseNode): The node object that contains the parameter
            value_hash_to_unique_value_index (dict[Any, int]): Dictionary mapping value hashes to indices in unique_values list
            unique_values (list[Any]): List of unique values

        Returns:
            None (if no value to be serialized) or an IndexedSetParameterValueCommand linking the value to the unique value list

        Notes:
            - Parameter output values take precedence over regular parameter values
            - For values that can be hashed, the value itself is used as the key in values_created
            - For unhashable values, the object's id is used as the key
            - The function will reuse already created values to avoid duplication
        """
        if parameter.name in node.parameter_output_values:
            # Output values are more important.
            value = node.parameter_output_values[parameter.name]
            is_output = True
        elif parameter.name in node.parameter_values:
            # Check the internal parameter values
            value = node.get_parameter_value(parameter.name)
            is_output = False
        else:
            # No value set; bail.
            return None

        # We have a value. Attempt to get a hash for it to see if it matches one
        # we've already indexed.
        try:
            hash(value)
            value_id = value
        except TypeError:
            # Couldn't get a hash. Use the object's ID
            value_id = id(value)

        if value_id in value_hash_to_unique_value_index:
            # We have a match on this value. We're all good.
            unique_index = value_hash_to_unique_value_index[value_id]
        else:
            # This one is new for us. Append it to the list of uniques.
            unique_index = len(unique_values)
            value_hash_to_unique_value_index[value_id] = unique_index
            unique_values.append(value)

        # Serialize it
        set_value_command = SetParameterValueRequest(
            parameter_name=parameter.name,
            value=None,  # <- this will get overridden when instantiated
            is_output=is_output,
            initial_setup=True,
        )
        indexed_set_value_command = SerializedNodeCommands.IndexedSetParameterValueCommand(
            set_parameter_value_command=set_value_command,
            unique_value_index=unique_index,
        )
        return indexed_set_value_command
