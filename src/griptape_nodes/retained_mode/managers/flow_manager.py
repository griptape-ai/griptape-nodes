from __future__ import annotations

import logging
from queue import Queue
from typing import TYPE_CHECKING, cast

from griptape.events import EventBus

from griptape_nodes.exe_types.connections import Connections
from griptape_nodes.exe_types.core_types import (
    Parameter,
    ParameterContainer,
    ParameterMode,
    ParameterTypeBuiltin,
)
from griptape_nodes.exe_types.flow import ControlFlow
from griptape_nodes.exe_types.node_types import BaseNode, NodeResolutionState, StartLoopNode, StartNode
from griptape_nodes.machines.control_flow import CompleteState, ControlFlowMachine
from griptape_nodes.retained_mode.events.base_events import (
    ExecutionEvent,
    ExecutionGriptapeNodeEvent,
    FlushParameterChangesRequest,
    FlushParameterChangesResultSuccess,
)
from griptape_nodes.retained_mode.events.connection_events import (
    CreateConnectionRequest,
    CreateConnectionResultFailure,
    CreateConnectionResultSuccess,
    DeleteConnectionRequest,
    DeleteConnectionResultFailure,
    DeleteConnectionResultSuccess,
)
from griptape_nodes.retained_mode.events.execution_events import (
    CancelFlowRequest,
    CancelFlowResultFailure,
    CancelFlowResultSuccess,
    ContinueExecutionStepRequest,
    ContinueExecutionStepResultFailure,
    ContinueExecutionStepResultSuccess,
    ControlFlowCancelledEvent,
    GetFlowStateRequest,
    GetFlowStateResultFailure,
    GetFlowStateResultSuccess,
    GetIsFlowRunningRequest,
    GetIsFlowRunningResultFailure,
    GetIsFlowRunningResultSuccess,
    SingleExecutionStepRequest,
    SingleExecutionStepResultFailure,
    SingleExecutionStepResultSuccess,
    SingleNodeStepRequest,
    SingleNodeStepResultFailure,
    SingleNodeStepResultSuccess,
    StartFlowRequest,
    StartFlowResultFailure,
    StartFlowResultSuccess,
    UnresolveFlowRequest,
    UnresolveFlowResultFailure,
    UnresolveFlowResultSuccess,
)
from griptape_nodes.retained_mode.events.flow_events import (
    CreateFlowRequest,
    CreateFlowResultFailure,
    CreateFlowResultSuccess,
    DeleteFlowRequest,
    DeleteFlowResultFailure,
    DeleteFlowResultSuccess,
    DeserializeFlowFromCommandsRequest,
    DeserializeFlowFromCommandsResultFailure,
    DeserializeFlowFromCommandsResultSuccess,
    GetFlowDetailsRequest,
    GetFlowDetailsResultFailure,
    GetFlowDetailsResultSuccess,
    GetFlowMetadataRequest,
    GetFlowMetadataResultFailure,
    GetFlowMetadataResultSuccess,
    GetTopLevelFlowRequest,
    GetTopLevelFlowResultSuccess,
    ListFlowsInCurrentContextRequest,
    ListFlowsInCurrentContextResultFailure,
    ListFlowsInCurrentContextResultSuccess,
    ListFlowsInFlowRequest,
    ListFlowsInFlowResultFailure,
    ListFlowsInFlowResultSuccess,
    ListNodesInFlowRequest,
    ListNodesInFlowResultFailure,
    ListNodesInFlowResultSuccess,
    SerializedFlowCommands,
    SerializeFlowToCommandsRequest,
    SerializeFlowToCommandsResultFailure,
    SerializeFlowToCommandsResultSuccess,
    SetFlowMetadataRequest,
    SetFlowMetadataResultFailure,
    SetFlowMetadataResultSuccess,
)
from griptape_nodes.retained_mode.events.node_events import (
    DeleteNodeRequest,
    DeleteNodeResultFailure,
    DeserializeNodeFromCommandsRequest,
    SerializedParameterValueTracker,
    SerializeNodeToCommandsRequest,
    SerializeNodeToCommandsResultSuccess,
)
from griptape_nodes.retained_mode.events.parameter_events import (
    SetParameterValueRequest,
)
from griptape_nodes.retained_mode.events.validation_events import (
    ValidateFlowDependenciesRequest,
    ValidateFlowDependenciesResultFailure,
    ValidateFlowDependenciesResultSuccess,
)
from griptape_nodes.retained_mode.events.workflow_events import (
    ImportWorkflowAsReferencedSubFlowRequest,
    ImportWorkflowAsReferencedSubFlowResultSuccess,
)
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

if TYPE_CHECKING:
    from griptape_nodes.retained_mode.events.base_events import ResultPayload
    from griptape_nodes.retained_mode.managers.event_manager import EventManager

logger = logging.getLogger("griptape_nodes")


class FlowManager:
    _name_to_parent_name: dict[str, str | None]
    _flow_to_referenced_workflow_name: dict[ControlFlow, str]
    _connections: Connections

    # Global execution state (moved from individual ControlFlows)
    _global_flow_queue: Queue[BaseNode]
    _global_control_flow_machine: ControlFlowMachine | None
    _global_single_node_resolution: bool

    def __init__(self, event_manager: EventManager) -> None:
        event_manager.assign_manager_to_request_type(CreateFlowRequest, self.on_create_flow_request)
        event_manager.assign_manager_to_request_type(DeleteFlowRequest, self.on_delete_flow_request)
        event_manager.assign_manager_to_request_type(ListNodesInFlowRequest, self.on_list_nodes_in_flow_request)
        event_manager.assign_manager_to_request_type(ListFlowsInFlowRequest, self.on_list_flows_in_flow_request)
        event_manager.assign_manager_to_request_type(
            ListFlowsInCurrentContextRequest, self.on_list_flows_in_current_context_request
        )
        event_manager.assign_manager_to_request_type(CreateConnectionRequest, self.on_create_connection_request)
        event_manager.assign_manager_to_request_type(DeleteConnectionRequest, self.on_delete_connection_request)
        event_manager.assign_manager_to_request_type(StartFlowRequest, self.on_start_flow_request)
        event_manager.assign_manager_to_request_type(SingleNodeStepRequest, self.on_single_node_step_request)
        event_manager.assign_manager_to_request_type(SingleExecutionStepRequest, self.on_single_execution_step_request)
        event_manager.assign_manager_to_request_type(
            ContinueExecutionStepRequest, self.on_continue_execution_step_request
        )
        event_manager.assign_manager_to_request_type(CancelFlowRequest, self.on_cancel_flow_request)
        event_manager.assign_manager_to_request_type(UnresolveFlowRequest, self.on_unresolve_flow_request)

        event_manager.assign_manager_to_request_type(GetFlowStateRequest, self.on_get_flow_state_request)
        event_manager.assign_manager_to_request_type(GetIsFlowRunningRequest, self.on_get_is_flow_running_request)
        event_manager.assign_manager_to_request_type(
            ValidateFlowDependenciesRequest, self.on_validate_flow_dependencies_request
        )
        event_manager.assign_manager_to_request_type(GetTopLevelFlowRequest, self.on_get_top_level_flow_request)
        event_manager.assign_manager_to_request_type(GetFlowDetailsRequest, self.on_get_flow_details_request)
        event_manager.assign_manager_to_request_type(GetFlowMetadataRequest, self.on_get_flow_metadata_request)
        event_manager.assign_manager_to_request_type(SetFlowMetadataRequest, self.on_set_flow_metadata_request)
        event_manager.assign_manager_to_request_type(SerializeFlowToCommandsRequest, self.on_serialize_flow_to_commands)
        event_manager.assign_manager_to_request_type(
            DeserializeFlowFromCommandsRequest, self.on_deserialize_flow_from_commands
        )
        event_manager.assign_manager_to_request_type(FlushParameterChangesRequest, self.on_flush_request)

        self._name_to_parent_name = {}
        self._flow_to_referenced_workflow_name = {}
        self._connections = Connections()

        # Initialize global execution state
        self._global_flow_queue = Queue[BaseNode]()
        self._global_control_flow_machine = None  # Will be initialized when first flow starts
        self._global_single_node_resolution = False

    def get_connections(self) -> Connections:
        """Get the connections instance."""
        return self._connections

    def _has_connection(
        self,
        source_node: BaseNode,
        source_parameter: Parameter,
        target_node: BaseNode,
        target_parameter: Parameter,
    ) -> bool:
        """Check if a connection exists."""
        connected_outputs = self.get_connected_output_parameters(source_node, source_parameter)
        for connected_node, connected_param in connected_outputs:
            if connected_node is target_node and connected_param is target_parameter:
                return True
        return False

    def get_connected_output_parameters(self, node: BaseNode, param: Parameter) -> list[tuple[BaseNode, Parameter]]:
        """Get connected output parameters."""
        connections = []
        if node.name in self._connections.outgoing_index:
            outgoing_params = self._connections.outgoing_index[node.name]
            if param.name in outgoing_params:
                for connection_id in outgoing_params[param.name]:
                    connection = self._connections.connections[connection_id]
                    connections.append((connection.target_node, connection.target_parameter))
        return connections

    def _get_connections_for_flow(self, flow: ControlFlow) -> list:
        """Get connections where both nodes are in the specified flow."""
        flow_connections = []
        for connection in self._connections.connections.values():
            source_in_flow = connection.source_node.name in flow.nodes
            target_in_flow = connection.target_node.name in flow.nodes
            # Only include connection if BOTH nodes are in this flow (for serialization)
            if source_in_flow and target_in_flow:
                flow_connections.append(connection)
        return flow_connections

    def get_parent_flow(self, flow_name: str) -> str | None:
        if flow_name in self._name_to_parent_name:
            return self._name_to_parent_name[flow_name]
        msg = f"Flow with name {flow_name} doesn't exist"
        raise ValueError(msg)

    def is_referenced_workflow(self, flow: ControlFlow) -> bool:
        """Check if this flow was created by importing a referenced workflow.

        Returns True if this flow originated from a workflow import operation,
        False if it was created standalone.
        """
        return flow in self._flow_to_referenced_workflow_name

    def get_referenced_workflow_name(self, flow: ControlFlow) -> str | None:
        """Get the name of the referenced workflow, if any.

        Returns the workflow name that was imported to create this flow,
        or None if this flow was created standalone.
        """
        return self._flow_to_referenced_workflow_name.get(flow)

    def on_get_top_level_flow_request(self, request: GetTopLevelFlowRequest) -> ResultPayload:  # noqa: ARG002 (the request has to be assigned to the method)
        for flow_name, parent in self._name_to_parent_name.items():
            if parent is None:
                return GetTopLevelFlowResultSuccess(flow_name=flow_name)
        msg = "Attempted to get top level flow, but no such flow exists"
        logger.debug(msg)
        return GetTopLevelFlowResultSuccess(flow_name=None)

    def on_get_flow_details_request(self, request: GetFlowDetailsRequest) -> ResultPayload:
        flow_name = request.flow_name
        flow = None

        if flow_name is None:
            # We want to get details for whatever is at the top of the Current Context.
            if not GriptapeNodes.ContextManager().has_current_flow():
                details = "Attempted to get Flow details from the Current Context. Failed because the Current Context was empty."
                logger.error(details)
                return GetFlowDetailsResultFailure(result_details=details)
            flow = GriptapeNodes.ContextManager().get_current_flow()
            flow_name = flow.name
        else:
            flow = GriptapeNodes.ObjectManager().attempt_get_object_by_name_as_type(flow_name, ControlFlow)
            if flow is None:
                details = (
                    f"Attempted to get Flow details for '{flow_name}'. Failed because no Flow with that name exists."
                )
                logger.error(details)
                return GetFlowDetailsResultFailure(result_details=details)

        try:
            parent_flow_name = self.get_parent_flow(flow_name)
        except ValueError:
            details = f"Attempted to get Flow details for '{flow_name}'. Failed because Flow does not exist in parent mapping."
            logger.error(details)
            return GetFlowDetailsResultFailure(result_details=details)

        referenced_workflow_name = None
        if self.is_referenced_workflow(flow):
            referenced_workflow_name = self.get_referenced_workflow_name(flow)

        details = f"Successfully retrieved Flow details for '{flow_name}'."
        logger.debug(details)
        return GetFlowDetailsResultSuccess(
            referenced_workflow_name=referenced_workflow_name,
            parent_flow_name=parent_flow_name,
        )

    def on_get_flow_metadata_request(self, request: GetFlowMetadataRequest) -> ResultPayload:
        flow_name = request.flow_name
        flow = None
        if flow_name is None:
            # Get from the current context.
            if not GriptapeNodes.ContextManager().has_current_flow():
                details = "Attempted to get metadata for a Flow from the Current Context. Failed because the Current Context is empty."
                logger.error(details)
                return GetFlowMetadataResultFailure(result_details=details)

            flow = GriptapeNodes.ContextManager().get_current_flow()
            flow_name = flow.name

        # Does this flow exist?
        if flow is None:
            obj_mgr = GriptapeNodes.ObjectManager()
            flow = obj_mgr.attempt_get_object_by_name_as_type(flow_name, ControlFlow)
            if flow is None:
                details = f"Attempted to get metadata for a Flow '{flow_name}', but no such Flow was found."
                logger.error(details)
                return GetFlowMetadataResultFailure(result_details=details)

        metadata = flow.metadata
        details = f"Successfully retrieved metadata for a Flow '{flow_name}'."
        logger.debug(details)

        return GetFlowMetadataResultSuccess(metadata=metadata)

    def on_set_flow_metadata_request(self, request: SetFlowMetadataRequest) -> ResultPayload:
        flow_name = request.flow_name
        flow = None
        if flow_name is None:
            # Get from the current context.
            if not GriptapeNodes.ContextManager().has_current_flow():
                details = "Attempted to set metadata for a Flow from the Current Context. Failed because the Current Context is empty."
                logger.error(details)
                return SetFlowMetadataResultFailure(result_details=details)

            flow = GriptapeNodes.ContextManager().get_current_flow()
            flow_name = flow.name

        # Does this flow exist?
        if flow is None:
            obj_mgr = GriptapeNodes.ObjectManager()
            flow = obj_mgr.attempt_get_object_by_name_as_type(flow_name, ControlFlow)
            if flow is None:
                details = f"Attempted to set metadata for a Flow '{flow_name}', but no such Flow was found."
                logger.error(details)
                return SetFlowMetadataResultFailure(result_details=details)

        # We can't completely overwrite metadata.
        for key, value in request.metadata.items():
            flow.metadata[key] = value
        details = f"Successfully set metadata for a Flow '{flow_name}'."
        logger.debug(details)

        return SetFlowMetadataResultSuccess()

    def does_canvas_exist(self) -> bool:
        """Determines if there is already an existing flow with no parent flow.Returns True if there is an existing flow with no parent flow.Return False if there is no existing flow with no parent flow."""
        return any([parent is None for parent in self._name_to_parent_name.values()])  # noqa: C419

    def on_create_flow_request(self, request: CreateFlowRequest) -> ResultPayload:
        # Who is the parent?
        parent_name = request.parent_flow_name

        # This one's tricky. If they said "None" for the parent, they could either be saying:
        # 1. Use whatever the current context is to be the parent.
        # 2. Create me as the canvas (i.e., the top-level flow, of which there can be only one)

        # We'll explore #1 first by seeing if the Context Manager already has a current flow,
        # which would mean the canvas is already established:
        parent = None
        if (parent_name is None) and (GriptapeNodes.ContextManager().has_current_flow()):
            # Aha! Just use that.
            parent = GriptapeNodes.ContextManager().get_current_flow()
            parent_name = parent.name

        # TODO: FIX THIS LOGIC MESS https://github.com/griptape-ai/griptape-nodes/issues/616

        if parent_name is not None and parent is None:
            parent = GriptapeNodes.ObjectManager().attempt_get_object_by_name_as_type(parent_name, ControlFlow)
        if parent_name is None:
            if self.does_canvas_exist():
                # We're trying to create the canvas. Ensure that parent does NOT already exist.
                details = "Attempted to create a Flow as the Canvas (top-level Flow with no parents), but the Canvas already exists."
                logger.error(details)
                result = CreateFlowResultFailure(result_details=details)
                return result
        # Now our parent exists, right?
        elif parent is None:
            details = f"Attempted to create a Flow with a parent '{request.parent_flow_name}', but no parent with that name could be found."
            logger.error(details)

            result = CreateFlowResultFailure(result_details=details)

            return result

        # We need to have a current workflow context to proceed.
        if not GriptapeNodes.ContextManager().has_current_workflow():
            details = "Attempted to create a Flow, but no Workflow was active in the Current Context."
            logger.error(details)
            return CreateFlowResultFailure(result_details=details)

        # Create it.
        final_flow_name = GriptapeNodes.ObjectManager().generate_name_for_object(
            type_name="ControlFlow", requested_name=request.flow_name
        )
        # Check if we're creating this flow within a referenced workflow context
        # This will inform the engine to maintain a reference to the workflow
        # when serializing it. It may inform the editor to render it differently.
        workflow_manager = GriptapeNodes.WorkflowManager()
        flow = ControlFlow(name=final_flow_name, metadata=request.metadata)
        GriptapeNodes.ObjectManager().add_object_by_name(name=final_flow_name, obj=flow)
        self._name_to_parent_name[final_flow_name] = parent_name

        # Track referenced workflow if this flow was created within a referenced workflow context
        if workflow_manager.has_current_referenced_workflow():
            referenced_workflow_name = workflow_manager.get_current_referenced_workflow()
            self._flow_to_referenced_workflow_name[flow] = referenced_workflow_name

        # See if we need to push it as the current context.
        if request.set_as_new_context:
            GriptapeNodes.ContextManager().push_flow(flow)

        # Success
        details = f"Successfully created Flow '{final_flow_name}'."
        log_level = logging.DEBUG
        if (request.flow_name is not None) and (final_flow_name != request.flow_name):
            details = f"{details} WARNING: Had to rename from original Flow requested '{request.flow_name}' as an object with this name already existed."
            log_level = logging.WARNING

        logger.log(level=log_level, msg=details)
        result = CreateFlowResultSuccess(flow_name=final_flow_name)
        return result

    # This needs to have a lot of branches to check the flow in all possible situations. In Current Context, or when the name is passed in.
    def on_delete_flow_request(self, request: DeleteFlowRequest) -> ResultPayload:  # noqa: C901, PLR0911, PLR0912, PLR0915
        flow_name = request.flow_name
        flow = None
        if flow_name is None:
            # We want to delete whatever is at the top of the Current Context.
            if not GriptapeNodes.ContextManager().has_current_flow():
                details = (
                    "Attempted to delete a Flow from the Current Context. Failed because the Current Context was empty."
                )
                logger.error(details)
                result = DeleteFlowResultFailure(result_details=details)
                return result
            # We pop it off here, but we'll re-add it using context in a moment.
            flow = GriptapeNodes.ContextManager().pop_flow()

        # Does this Flow even exist?
        if flow is None and flow_name is not None:
            obj_mgr = GriptapeNodes.ObjectManager()
            flow = obj_mgr.attempt_get_object_by_name_as_type(flow_name, ControlFlow)
        if flow is None:
            details = f"Attempted to delete Flow '{flow_name}', but no Flow with that name could be found."
            logger.error(details)
            result = DeleteFlowResultFailure(result_details=details)
            return result
        if self.check_for_existing_running_flow():
            result = GriptapeNodes.handle_request(CancelFlowRequest(flow_name=flow.name))
            if not result.succeeded():
                details = f"Attempted to delete flow '{flow_name}'. Failed because running flow could not cancel."
                logger.error(details)
                return DeleteFlowResultFailure(result_details=details)

        # Let this Flow assume the Current Context while we delete everything within it.
        with GriptapeNodes.ContextManager().flow(flow=flow):
            # Delete all child nodes in this Flow.
            list_nodes_request = ListNodesInFlowRequest()
            list_nodes_result = GriptapeNodes.handle_request(list_nodes_request)
            if not isinstance(list_nodes_result, ListNodesInFlowResultSuccess):
                details = f"Attempted to delete Flow '{flow.name}', but failed while attempting to get the list of Nodes owned by this Flow."
                logger.error(details)
                result = DeleteFlowResultFailure(result_details=details)
                return result
            node_names = list_nodes_result.node_names
            for node_name in node_names:
                delete_node_request = DeleteNodeRequest(node_name=node_name)
                delete_node_result = GriptapeNodes.handle_request(delete_node_request)
                if isinstance(delete_node_result, DeleteNodeResultFailure):
                    details = f"Attempted to delete Flow '{flow.name}', but failed while attempting to delete child Node '{node_name}'."
                    logger.error(details)
                    result = DeleteFlowResultFailure(result_details=details)
                    return result

            # Delete all child Flows of this Flow.
            # Note: We use ListFlowsInCurrentContextRequest here instead of ListFlowsInFlowRequest(parent_flow_name=None)
            # because None in ListFlowsInFlowRequest means "get canvas/top-level flows". We want the flows in the
            # current context, which is the flow we're deleting.
            list_flows_request = ListFlowsInCurrentContextRequest()
            list_flows_result = GriptapeNodes.handle_request(list_flows_request)
            if not isinstance(list_flows_result, ListFlowsInCurrentContextResultSuccess):
                details = f"Attempted to delete Flow '{flow_name}', but failed while attempting to get the list of Flows owned by this Flow."
                logger.error(details)
                result = DeleteFlowResultFailure(result_details=details)
                return result
            flow_names = list_flows_result.flow_names
            obj_mgr = GriptapeNodes.ObjectManager()
            for child_flow_name in flow_names:
                child_flow = obj_mgr.attempt_get_object_by_name_as_type(child_flow_name, ControlFlow)
                if child_flow is None:
                    details = (
                        f"Attempted to delete Flow '{child_flow_name}', but no Flow with that name could be found."
                    )
                    logger.error(details)
                    result = DeleteFlowResultFailure(result_details=details)
                    return result
                with GriptapeNodes.ContextManager().flow(flow=child_flow):
                    # Delete them.
                    delete_flow_request = DeleteFlowRequest()
                    delete_flow_result = GriptapeNodes.handle_request(delete_flow_request)
                    if isinstance(delete_flow_result, DeleteFlowResultFailure):
                        details = f"Attempted to delete Flow '{flow.name}', but failed while attempting to delete child Flow '{child_flow.name}'."
                        logger.error(details)
                        result = DeleteFlowResultFailure(result_details=details)
                        return result

            # If we've made it this far, we have deleted all the children Flows and their nodes.
            # Remove the flow from our map.
            obj_mgr.del_obj_by_name(flow.name)
            del self._name_to_parent_name[flow.name]

            # Clean up referenced workflow tracking
            if flow in self._flow_to_referenced_workflow_name:
                del self._flow_to_referenced_workflow_name[flow]

        details = f"Successfully deleted Flow '{flow_name}'."
        logger.debug(details)
        result = DeleteFlowResultSuccess()
        return result

    def on_get_is_flow_running_request(self, request: GetIsFlowRunningRequest) -> ResultPayload:
        obj_mgr = GriptapeNodes.ObjectManager()
        if request.flow_name is None:
            details = "Attempted to get Flow, but no flow name was provided."
            logger.error(details)
            return GetIsFlowRunningResultFailure(result_details=details)
        flow = obj_mgr.attempt_get_object_by_name_as_type(request.flow_name, ControlFlow)
        if flow is None:
            details = f"Attempted to get Flow '{request.flow_name}', but no Flow with that name could be found."
            logger.error(details)
            result = GetIsFlowRunningResultFailure(result_details=details)
            return result
        try:
            is_running = self.check_for_existing_running_flow()
        except Exception:
            details = f"Error while trying to get status of '{request.flow_name}'."
            logger.error(details)
            result = GetIsFlowRunningResultFailure(result_details=details)
            return result
        return GetIsFlowRunningResultSuccess(is_running=is_running)

    def on_list_nodes_in_flow_request(self, request: ListNodesInFlowRequest) -> ResultPayload:
        flow_name = request.flow_name
        flow = None
        if flow_name is None:
            # First check if we have a current flow
            if not GriptapeNodes.ContextManager().has_current_flow():
                details = "Attempted to list Nodes in a Flow in the Current Context. Failed because the Current Context was empty."
                logger.error(details)
                result = ListNodesInFlowResultFailure(result_details=details)
                return result
            # Get the current flow from context
            flow = GriptapeNodes.ContextManager().get_current_flow()
            flow_name = flow.name
        # Does this Flow even exist?
        if flow is None:
            obj_mgr = GriptapeNodes.ObjectManager()
            flow = obj_mgr.attempt_get_object_by_name_as_type(flow_name, ControlFlow)
        if flow is None:
            details = (
                f"Attempted to list Nodes in Flow '{flow_name}'. Failed because no Flow with that name could be found."
            )
            logger.error(details)
            result = ListNodesInFlowResultFailure(result_details=details)
            return result

        ret_list = list(flow.nodes.keys())
        details = f"Successfully got the list of Nodes within Flow '{flow_name}'."
        logger.debug(details)

        result = ListNodesInFlowResultSuccess(node_names=ret_list)
        return result

    def on_list_flows_in_flow_request(self, request: ListFlowsInFlowRequest) -> ResultPayload:
        if request.parent_flow_name is not None:
            # Does this Flow even exist?
            obj_mgr = GriptapeNodes.ObjectManager()
            flow = obj_mgr.attempt_get_object_by_name_as_type(request.parent_flow_name, ControlFlow)
            if flow is None:
                details = f"Attempted to list Flows that are children of Flow '{request.parent_flow_name}', but no Flow with that name could be found."
                logger.error(details)
                result = ListFlowsInFlowResultFailure(result_details=details)
                return result

        # Create a list of all child flow names that point DIRECTLY to us.
        ret_list = []
        for flow_name, parent_name in self._name_to_parent_name.items():
            if parent_name == request.parent_flow_name:
                ret_list.append(flow_name)

        details = f"Successfully got the list of Flows that are direct children of Flow '{request.parent_flow_name}'."
        logger.debug(details)

        result = ListFlowsInFlowResultSuccess(flow_names=ret_list)
        return result

    def get_flow_by_name(self, flow_name: str) -> ControlFlow:
        obj_mgr = GriptapeNodes.ObjectManager()
        flow = obj_mgr.attempt_get_object_by_name_as_type(flow_name, ControlFlow)
        if flow is None:
            msg = f"Flow with name {flow_name} doesn't exist"
            raise KeyError(msg)

        return flow

    def handle_flow_rename(self, old_name: str, new_name: str) -> None:
        # Replace the old flow name and its parent first.
        parent = self._name_to_parent_name[old_name]
        self._name_to_parent_name[new_name] = parent
        del self._name_to_parent_name[old_name]

        # Now iterate through everyone who pointed to the old one as a parent and update it.
        for flow_name, parent_name in self._name_to_parent_name.items():
            if parent_name == old_name:
                self._name_to_parent_name[flow_name] = new_name

        # Let the Node Manager know about the change, too.
        GriptapeNodes.NodeManager().handle_flow_rename(old_name=old_name, new_name=new_name)

    def on_create_connection_request(self, request: CreateConnectionRequest) -> ResultPayload:  # noqa: PLR0911, PLR0912, PLR0915, C901
        # Vet the two nodes first.
        source_node_name = request.source_node_name
        source_node = None
        if source_node_name is None:
            # First check if we have a current node
            if not GriptapeNodes.ContextManager().has_current_node():
                details = "Attempted to create a Connection with a source node from the Current Context. Failed because the Current Context was empty."
                logger.error(details)
                return CreateConnectionResultFailure(result_details=details)

            # Get the current node from context
            source_node = GriptapeNodes.ContextManager().get_current_node()
            source_node_name = source_node.name
        if source_node is None:
            try:
                source_node = GriptapeNodes.NodeManager().get_node_by_name(source_node_name)
            except ValueError as err:
                details = f'Connection failed: "{source_node_name}" does not exist. Error: {err}.'
                logger.error(details)

                return CreateConnectionResultFailure(result_details=details)

        target_node_name = request.target_node_name
        target_node = None
        if target_node_name is None:
            # First check if we have a current node
            if not GriptapeNodes.ContextManager().has_current_node():
                details = "Attempted to create a Connection with the target node from the Current Context. Failed because the Current Context was empty."
                logger.error(details)
                return CreateConnectionResultFailure(result_details=details)

            # Get the current node from context
            target_node = GriptapeNodes.ContextManager().get_current_node()
            target_node_name = target_node.name
        if target_node is None:
            try:
                target_node = GriptapeNodes.NodeManager().get_node_by_name(target_node_name)
            except ValueError as err:
                details = f'Connection failed: "{target_node_name}" does not exist. Error: {err}.'
                logger.error(details)
                return CreateConnectionResultFailure(result_details=details)

        # The two nodes exist.
        # Get the parent flows.
        source_flow_name = None
        try:
            source_flow_name = GriptapeNodes.NodeManager().get_node_parent_flow_by_name(source_node_name)
            self.get_flow_by_name(flow_name=source_flow_name)
        except KeyError as err:
            details = f'Connection "{source_node_name}.{request.source_parameter_name}" to "{target_node_name}.{request.target_parameter_name}" failed: {err}.'
            logger.error(details)
            return CreateConnectionResultFailure(result_details=details)

        target_flow_name = None
        try:
            target_flow_name = GriptapeNodes.NodeManager().get_node_parent_flow_by_name(target_node_name)
            self.get_flow_by_name(flow_name=target_flow_name)
        except KeyError as err:
            details = f'Connection "{source_node_name}.{request.source_parameter_name}" to "{target_node_name}.{request.target_parameter_name}" failed: {err}.'
            logger.error(details)
            return CreateConnectionResultFailure(result_details=details)

        # Cross-flow connections are now supported via global connection storage

        # Now validate the parameters.
        source_param = source_node.get_parameter_by_name(request.source_parameter_name)
        if source_param is None:
            details = f'Connection failed: "{source_node_name}.{request.source_parameter_name}" not found'
            logger.error(details)
            return CreateConnectionResultFailure(result_details=details)

        target_param = target_node.get_parameter_by_name(request.target_parameter_name)
        if target_param is None:
            # TODO: https://github.com/griptape-ai/griptape-nodes/issues/860
            details = f'Connection failed: "{target_node_name}.{request.target_parameter_name}" not found'
            logger.error(details)
            return CreateConnectionResultFailure(result_details=details)
        # Validate parameter modes accept this type of connection.
        source_modes_allowed = source_param.allowed_modes
        if ParameterMode.OUTPUT not in source_modes_allowed:
            details = (
                f'Connection failed: "{source_node_name}.{request.source_parameter_name}" is not an allowed OUTPUT'
            )
            logger.error(details)
            return CreateConnectionResultFailure(result_details=details)

        target_modes_allowed = target_param.allowed_modes
        if ParameterMode.INPUT not in target_modes_allowed:
            details = f'Connection failed: "{target_node_name}.{request.target_parameter_name}" is not an allowed INPUT'
            logger.error(details)
            return CreateConnectionResultFailure(result_details=details)

        # Validate that the data type from the source is allowed by the target.
        if not target_param.is_incoming_type_allowed(source_param.output_type):
            details = f'Connection failed on type mismatch "{source_node_name}.{request.source_parameter_name}" type({source_param.output_type}) to "{target_node_name}.{request.target_parameter_name}" types({target_param.input_types}) '
            logger.error(details)
            return CreateConnectionResultFailure(result_details=details)

        # Ask each node involved to bless this union.
        if not source_node.allow_outgoing_connection(
            source_parameter=source_param,
            target_node=target_node,
            target_parameter=target_param,
        ):
            details = (
                f'Connection failed : "{source_node_name}.{request.source_parameter_name}" rejected the connection '
            )
            logger.error(details)
            return CreateConnectionResultFailure(result_details=details)

        if not target_node.allow_incoming_connection(
            source_node=source_node,
            source_parameter=source_param,
            target_parameter=target_param,
        ):
            details = (
                f'Connection failed : "{target_node_name}.{request.target_parameter_name}" rejected the connection '
            )
            logger.error(details)
            return CreateConnectionResultFailure(result_details=details)

        # Based on user feedback, if a connection already exists in a scenario where only ONE such connection can exist
        # (e.g., connecting to a data input that already has a connection, or from a control output that is already wired up),
        # delete the old connection and replace it with this one.
        old_source_node_name = None
        old_source_param_name = None
        old_target_node_name = None
        old_target_param_name = None

        # Some scenarios restrict when we can have more than one connection. See if we're in such a scenario and replace the
        # existing connection instead of adding a new one.
        connection_mgr = self._connections
        # Try the OUTGOING restricted scenario first.
        restricted_scenario_connection = connection_mgr.get_existing_connection_for_restricted_scenario(
            node=source_node, parameter=source_param, is_source=True
        )
        if not restricted_scenario_connection:
            # Check the INCOMING scenario.
            restricted_scenario_connection = connection_mgr.get_existing_connection_for_restricted_scenario(
                node=target_node, parameter=target_param, is_source=False
            )

        if restricted_scenario_connection:
            # Record the original data in case we need to back out of this.
            old_source_node_name = restricted_scenario_connection.source_node.name
            old_source_param_name = restricted_scenario_connection.source_parameter.name
            old_target_node_name = restricted_scenario_connection.target_node.name
            old_target_param_name = restricted_scenario_connection.target_parameter.name

            delete_old_request = DeleteConnectionRequest(
                source_node_name=old_source_node_name,
                source_parameter_name=old_source_param_name,
                target_node_name=old_target_node_name,
                target_parameter_name=old_target_param_name,
            )
            delete_old_result = GriptapeNodes.handle_request(delete_old_request)
            if delete_old_result.failed():
                details = f"Attempted to connect '{source_node_name}.{request.source_parameter_name}'. Failed because there was a previous connection from '{old_source_node_name}.{old_source_param_name}' to '{old_target_node_name}.{old_target_param_name}' that could not be deleted."
                logger.error(details)
                return CreateConnectionResultFailure(result_details=details)

            details = f"Deleted the previous connection from '{old_source_node_name}.{old_source_param_name}' to '{old_target_node_name}.{old_target_param_name}' to make room for the new connection."
            logger.debug(details)
        try:
            # Actually create the Connection.
            self._connections.add_connection(
                source_node=source_node,
                source_parameter=source_param,
                target_node=target_node,
                target_parameter=target_param,
            )
        except ValueError as e:
            details = f'Connection failed: "{e}"'
            logger.error(details)

            # Attempt to restore any old connection that may have been present.
            if (
                (old_source_node_name is not None)
                and (old_source_param_name is not None)
                and (old_target_node_name is not None)
                and (old_target_param_name is not None)
            ):
                create_old_connection_request = CreateConnectionRequest(
                    source_node_name=old_source_node_name,
                    source_parameter_name=old_source_param_name,
                    target_node_name=old_target_node_name,
                    target_parameter_name=old_target_param_name,
                    initial_setup=request.initial_setup,
                )
                create_old_connection_result = GriptapeNodes.handle_request(create_old_connection_request)
                if create_old_connection_result.failed():
                    details = "Failed attempting to restore the old Connection after failing the replacement. A thousand pardons."
                    logger.error(details)
            return CreateConnectionResultFailure(result_details=details)

        # Let the source make any internal handling decisions now that the Connection has been made.
        source_node.after_outgoing_connection(
            source_parameter=source_param, target_node=target_node, target_parameter=target_param
        )

        # And target.
        target_node.after_incoming_connection(
            source_node=source_node,
            source_parameter=source_param,
            target_parameter=target_param,
        )

        details = f'Connected "{source_node_name}.{request.source_parameter_name}" to "{target_node_name}.{request.target_parameter_name}"'
        logger.debug(details)

        # Now update the parameter values if it exists.
        # check if it's been resolved/has a value in parameter_output_values
        if source_param.name in source_node.parameter_output_values:
            value = source_node.parameter_output_values[source_param.name]
        # if it doesn't let's use the one in parameter_values! that's the most updated.
        elif source_param.name in source_node.parameter_values:
            value = source_node.get_parameter_value(source_param.name)
        # if not even that.. then does it have a default value?
        elif source_param.default_value:
            value = source_param.default_value
        else:
            value = None
            if isinstance(target_param, ParameterContainer):
                target_node.kill_parameter_children(target_param)
        # if it existed somewhere and actually has a value - Set the parameter!
        if value and request.initial_setup is False:
            GriptapeNodes.handle_request(
                SetParameterValueRequest(
                    parameter_name=target_param.name,
                    node_name=target_node.name,
                    value=value,
                    data_type=source_param.type,
                )
            )

        result = CreateConnectionResultSuccess()

        return result

    def on_delete_connection_request(self, request: DeleteConnectionRequest) -> ResultPayload:  # noqa: C901, PLR0911, PLR0912, PLR0915 (complex logic, multiple edge cases)
        # Vet the two nodes first.
        source_node_name = request.source_node_name
        target_node_name = request.target_node_name
        source_node = None
        target_node = None
        if source_node_name is None:
            # First check if we have a current node
            if not GriptapeNodes.ContextManager().has_current_node():
                details = "Attempted to delete a Connection with a source node from the Current Context. Failed because the Current Context was empty."
                logger.error(details)
                return DeleteConnectionResultFailure(result_details=details)

            # Get the current node from context
            source_node = GriptapeNodes.ContextManager().get_current_node()
            source_node_name = source_node.name
        if source_node is None:
            try:
                source_node = GriptapeNodes.NodeManager().get_node_by_name(source_node_name)
            except ValueError as err:
                details = f'Connection not deleted "{source_node_name}.{request.source_parameter_name}" to "{target_node_name}.{request.target_parameter_name}". Error: {err}'
                logger.error(details)

                return DeleteConnectionResultFailure(result_details=details)

        target_node_name = request.target_node_name
        if target_node_name is None:
            # First check if we have a current node
            if not GriptapeNodes.ContextManager().has_current_node():
                details = "Attempted to delete a Connection with a target node from the Current Context. Failed because the Current Context was empty."
                logger.error(details)
                return DeleteConnectionResultFailure(result_details=details)

            # Get the current node from context
            target_node = GriptapeNodes.ContextManager().get_current_node()
            target_node_name = target_node.name
        if target_node is None:
            try:
                target_node = GriptapeNodes.NodeManager().get_node_by_name(target_node_name)
            except ValueError as err:
                details = f'Connection not deleted "{source_node_name}.{request.source_parameter_name}" to "{target_node_name}.{request.target_parameter_name}". Error: {err}'
                logger.error(details)

                return DeleteConnectionResultFailure(result_details=details)

        # The two nodes exist.
        # Get the parent flows.
        source_flow_name = None
        try:
            source_flow_name = GriptapeNodes.NodeManager().get_node_parent_flow_by_name(source_node_name)
            self.get_flow_by_name(flow_name=source_flow_name)
        except KeyError as err:
            details = f'Connection not deleted "{source_node_name}.{request.source_parameter_name}" to "{target_node_name}.{request.target_parameter_name}". Error: {err}'
            logger.error(details)

            return DeleteConnectionResultFailure(result_details=details)

        target_flow_name = None
        try:
            target_flow_name = GriptapeNodes.NodeManager().get_node_parent_flow_by_name(target_node_name)
            self.get_flow_by_name(flow_name=target_flow_name)
        except KeyError as err:
            details = f'Connection not deleted "{source_node_name}.{request.source_parameter_name}" to "{target_node_name}.{request.target_parameter_name}". Error: {err}'
            logger.error(details)

            return DeleteConnectionResultFailure(result_details=details)

        # Cross-flow connections are now supported via global connection storage

        # Now validate the parameters.
        source_param = source_node.get_parameter_by_name(request.source_parameter_name)
        if source_param is None:
            details = f'Connection not deleted "{source_node_name}.{request.source_parameter_name}" Not found.'
            logger.error(details)

            return DeleteConnectionResultFailure(result_details=details)

        target_param = target_node.get_parameter_by_name(request.target_parameter_name)
        if target_param is None:
            details = f'Connection not deleted "{target_node_name}.{request.target_parameter_name}" Not found.'
            logger.error(details)

            return DeleteConnectionResultFailure(result_details=details)

        # Vet that a Connection actually exists between them already.
        if not self._has_connection(
            source_node=source_node,
            source_parameter=source_param,
            target_node=target_node,
            target_parameter=target_param,
        ):
            details = f'Connection does not exist: "{source_node_name}.{request.source_parameter_name}" to "{target_node_name}.{request.target_parameter_name}"'
            logger.error(details)

            return DeleteConnectionResultFailure(result_details=details)

        # Remove the connection.
        if not self._connections.remove_connection(
            source_node=source_node.name,
            source_parameter=source_param.name,
            target_node=target_node.name,
            target_parameter=target_param.name,
        ):
            details = f'Connection not deleted "{source_node_name}.{request.source_parameter_name}" to "{target_node_name}.{request.target_parameter_name}". Unknown failure.'
            logger.error(details)

            return DeleteConnectionResultFailure(result_details=details)

        # After the connection has been removed, if it doesn't have PROPERTY as a type, wipe the set parameter value and unresolve future nodes
        if ParameterMode.PROPERTY not in target_param.allowed_modes:
            try:
                # Only try to remove a value where one exists, otherwise it will generate errant warnings.
                if target_param.name in target_node.parameter_values:
                    target_node.remove_parameter_value(target_param.name)
                # It removed it accurately
                # Unresolve future nodes that depended on that value
                self._connections.unresolve_future_nodes(target_node)
                target_node.make_node_unresolved(
                    current_states_to_trigger_change_event=set(
                        {NodeResolutionState.RESOLVED, NodeResolutionState.RESOLVING}
                    )
                )
            except KeyError as e:
                logger.warning(e)
        # Let the source make any internal handling decisions now that the Connection has been REMOVED.
        source_node.after_outgoing_connection_removed(
            source_parameter=source_param, target_node=target_node, target_parameter=target_param
        )

        # And target.
        target_node.after_incoming_connection_removed(
            source_node=source_node,
            source_parameter=source_param,
            target_parameter=target_param,
        )

        details = f'Connection "{source_node_name}.{request.source_parameter_name}" to "{target_node_name}.{request.target_parameter_name}" deleted.'
        logger.debug(details)

        result = DeleteConnectionResultSuccess()
        return result

    def on_start_flow_request(self, request: StartFlowRequest) -> ResultPayload:  # noqa: C901, PLR0911, PLR0912
        # which flow
        flow_name = request.flow_name
        debug_mode = request.debug_mode
        if not flow_name:
            details = "Must provide flow name to start a flow."
            logger.error(details)

            return StartFlowResultFailure(validation_exceptions=[], result_details=details)
        # get the flow by ID
        try:
            flow = self.get_flow_by_name(flow_name)
        except KeyError as err:
            details = f"Cannot start flow. Error: {err}"
            logger.error(details)
            return StartFlowResultFailure(validation_exceptions=[err], result_details=details)
        # Check to see if the flow is already running.
        if self.check_for_existing_running_flow():
            details = "Cannot start flow. Flow is already running."
            logger.error(details)
            return StartFlowResultFailure(validation_exceptions=[], result_details=details)
        # A node has been provided to either start or to run up to.
        if request.flow_node_name:
            flow_node_name = request.flow_node_name
            flow_node = GriptapeNodes.ObjectManager().attempt_get_object_by_name_as_type(flow_node_name, BaseNode)
            if not flow_node:
                details = f"Provided node with name {flow_node_name} does not exist"
                logger.error(details)
                return StartFlowResultFailure(validation_exceptions=[], result_details=details)
            # lets get the first control node in the flow!
            start_node = self.get_start_node_from_node(flow, flow_node)
            # if the start is not the node provided, set a breakpoint at the stop (we're running up until there)
            if not start_node:
                details = f"Start node for node with name {flow_node_name} does not exist"
                logger.error(details)
                return StartFlowResultFailure(validation_exceptions=[], result_details=details)
            if start_node != flow_node:
                flow_node.stop_flow = True
        else:
            # we wont hit this if we dont have a request id, our requests always have nodes
            # If there is a request, reinitialize the queue
            self.get_start_node_queue()  # initialize the start flow queue!
            start_node = None
        # Run Validation before starting a flow
        result = self.on_validate_flow_dependencies_request(
            ValidateFlowDependenciesRequest(flow_name=flow_name, flow_node_name=start_node.name if start_node else None)
        )
        try:
            if not result.succeeded():
                details = f"Couldn't start flow with name {flow_name}. Flow Validation Failed"
                logger.error(details)
                return StartFlowResultFailure(validation_exceptions=[])
            result = cast("ValidateFlowDependenciesResultSuccess", result)

            if not result.validation_succeeded:
                details = f"Couldn't start flow with name {flow_name}. Flow Validation Failed."
                if len(result.exceptions) > 0:
                    for exception in result.exceptions:
                        details = f"{details}\n\t{exception}"
                logger.error(details)
                return StartFlowResultFailure(validation_exceptions=result.exceptions, result_details=details)
        except Exception as e:
            details = f"Couldn't start flow with name {flow_name}. Flow Validation Failed: {e}"
            logger.error(details)
            return StartFlowResultFailure(validation_exceptions=[e], result_details=details)
        # By now, it has been validated with no exceptions.
        try:
            self.start_flow(flow, start_node, debug_mode)
        except Exception as e:
            details = f"Failed to kick off flow with name {flow_name}. Exception occurred: {e} "
            logger.error(details)
            return StartFlowResultFailure(validation_exceptions=[e], result_details=details)

        details = f"Successfully kicked off flow with name {flow_name}"
        logger.debug(details)

        return StartFlowResultSuccess()

    def on_get_flow_state_request(self, event: GetFlowStateRequest) -> ResultPayload:
        flow_name = event.flow_name
        if not flow_name:
            details = "Could not get flow state. No flow name was provided."
            logger.error(details)
            return GetFlowStateResultFailure(result_details=details)
        try:
            flow = self.get_flow_by_name(flow_name)
        except KeyError as err:
            details = f"Could not get flow state. Error: {err}"
            logger.error(details)
            return GetFlowStateResultFailure(result_details=details)
        try:
            control_node, resolving_node = self.flow_state(flow)
        except Exception as e:
            details = f"Failed to get flow state of flow with name {flow_name}. Exception occurred: {e} "
            logger.exception(details)
            return GetFlowStateResultFailure(result_details=details)
        details = f"Successfully got flow state for flow with name {flow_name}."
        logger.debug(details)
        return GetFlowStateResultSuccess(control_node=control_node, resolving_node=resolving_node)

    def on_cancel_flow_request(self, request: CancelFlowRequest) -> ResultPayload:
        flow_name = request.flow_name
        if not flow_name:
            details = "Could not cancel flow execution. No flow name was provided."
            logger.error(details)

            return CancelFlowResultFailure(result_details=details)
        try:
            self.get_flow_by_name(flow_name)
        except KeyError as err:
            details = f"Could not cancel flow execution. Error: {err}"
            logger.error(details)

            return CancelFlowResultFailure(result_details=details)
        try:
            self.cancel_flow_run()
        except Exception as e:
            details = f"Could not cancel flow execution. Exception: {e}"
            logger.error(details)

            return CancelFlowResultFailure(result_details=details)
        details = f"Successfully cancelled flow execution with name {flow_name}"
        logger.debug(details)

        return CancelFlowResultSuccess()

    def on_single_node_step_request(self, request: SingleNodeStepRequest) -> ResultPayload:
        flow_name = request.flow_name
        if not flow_name:
            details = "Could not advance to the next step of a running workflow. No flow name was provided."
            logger.error(details)

            return SingleNodeStepResultFailure(validation_exceptions=[], result_details=details)
        try:
            self.get_flow_by_name(flow_name)
        except KeyError as err:
            details = f"Could not advance to the next step of a running workflow. No flow with name {flow_name} exists. Error: {err}"
            logger.error(details)

            return SingleNodeStepResultFailure(validation_exceptions=[err], result_details=details)
        try:
            flow = self.get_flow_by_name(flow_name)
            self.single_node_step(flow)
        except Exception as e:
            details = f"Could not advance to the next step of a running workflow. Exception: {e}"
            logger.error(details)
            return SingleNodeStepResultFailure(validation_exceptions=[], result_details=details)

        # All completed happily
        details = f"Successfully advanced to the next step of a running workflow with name {flow_name}"
        logger.debug(details)

        return SingleNodeStepResultSuccess()

    def on_single_execution_step_request(self, request: SingleExecutionStepRequest) -> ResultPayload:
        flow_name = request.flow_name
        if not flow_name:
            details = "Could not advance to the next step of a running workflow. No flow name was provided."
            logger.error(details)

            return SingleExecutionStepResultFailure(result_details=details)
        try:
            flow = self.get_flow_by_name(flow_name)
        except KeyError as err:
            details = f"Could not advance to the next step of a running workflow. Error: {err}."
            logger.error(details)

            return SingleExecutionStepResultFailure(result_details=details)
        change_debug_mode = request.request_id is not None
        try:
            self.single_execution_step(flow, change_debug_mode)
        except Exception as e:
            # We REALLY don't want to fail here, else we'll take the whole engine down
            try:
                if self.check_for_existing_running_flow():
                    self.cancel_flow_run()
            except Exception as e_inner:
                details = f"Could not cancel flow execution. Exception: {e_inner}"
                logger.error(details)

            details = f"Could not advance to the next step of a running workflow. Exception: {e}"
            logger.error(details)
            return SingleNodeStepResultFailure(validation_exceptions=[e], result_details=details)
        details = f"Successfully advanced to the next step of a running workflow with name {flow_name}"
        logger.debug(details)

        return SingleExecutionStepResultSuccess()

    def on_continue_execution_step_request(self, request: ContinueExecutionStepRequest) -> ResultPayload:
        flow_name = request.flow_name
        if not flow_name:
            details = "Failed to continue execution step because no flow name was provided"
            logger.error(details)

            return ContinueExecutionStepResultFailure(result_details=details)
        try:
            flow = self.get_flow_by_name(flow_name)
        except KeyError as err:
            details = f"Failed to continue execution step. Error: {err}"
            logger.error(details)

            return ContinueExecutionStepResultFailure(result_details=details)
        try:
            self.continue_executing(flow)
        except Exception as e:
            details = f"Failed to continue execution step. An exception occurred: {e}."
            logger.error(details)
            return ContinueExecutionStepResultFailure(result_details=details)
        details = f"Successfully continued flow with name {flow_name}"
        logger.debug(details)
        return ContinueExecutionStepResultSuccess()

    def on_unresolve_flow_request(self, request: UnresolveFlowRequest) -> ResultPayload:
        flow_name = request.flow_name
        if not flow_name:
            details = "Failed to unresolve flow because no flow name was provided"
            logger.error(details)
            return UnresolveFlowResultFailure(result_details=details)
        try:
            flow = self.get_flow_by_name(flow_name)
        except KeyError as err:
            details = f"Failed to unresolve flow. Error: {err}"
            logger.error(details)
            return UnresolveFlowResultFailure(result_details=details)
        try:
            self.unresolve_whole_flow(flow)
        except Exception as e:
            details = f"Failed to unresolve flow. An exception occurred: {e}."
            logger.error(details)
            return UnresolveFlowResultFailure(result_details=details)
        details = f"Unresolved flow with name {flow_name}"
        logger.debug(details)
        return UnresolveFlowResultSuccess()

    def on_validate_flow_dependencies_request(self, request: ValidateFlowDependenciesRequest) -> ResultPayload:
        flow_name = request.flow_name
        # get the flow name
        try:
            flow = self.get_flow_by_name(flow_name)
        except KeyError as err:
            details = f"Failed to validate flow. Error: {err}"
            logger.error(details)
            return ValidateFlowDependenciesResultFailure(result_details=details)
        if request.flow_node_name:
            flow_node_name = request.flow_node_name
            flow_node = GriptapeNodes.ObjectManager().attempt_get_object_by_name_as_type(flow_node_name, BaseNode)
            if not flow_node:
                details = f"Provided node with name {flow_node_name} does not exist"
                logger.error(details)
                return ValidateFlowDependenciesResultFailure(result_details=details)
            # Gets all nodes in that connected group to be ran
            nodes = flow.get_all_connected_nodes(flow_node)
        else:
            nodes = flow.nodes.values()
        # If we're just running the whole flow
        all_exceptions = []
        for node in nodes:
            exceptions = node.validate_before_workflow_run()
            if exceptions:
                all_exceptions = all_exceptions + exceptions
        return ValidateFlowDependenciesResultSuccess(
            validation_succeeded=len(all_exceptions) == 0, exceptions=all_exceptions
        )

    def on_list_flows_in_current_context_request(self, request: ListFlowsInCurrentContextRequest) -> ResultPayload:  # noqa: ARG002 (request isn't actually used)
        if not GriptapeNodes.ContextManager().has_current_flow():
            details = "Attempted to list Flows in the Current Context. Failed because the Current Context was empty."
            logger.error(details)
            return ListFlowsInCurrentContextResultFailure(result_details=details)

        parent_flow = GriptapeNodes.ContextManager().get_current_flow()
        parent_flow_name = parent_flow.name

        # Create a list of all child flow names that point DIRECTLY to us.
        ret_list = []
        for flow_name, parent_name in self._name_to_parent_name.items():
            if parent_name == parent_flow_name:
                ret_list.append(flow_name)

        details = f"Successfully got the list of Flows in the Current Context (Flow '{parent_flow_name}')."
        logger.debug(details)

        return ListFlowsInCurrentContextResultSuccess(flow_names=ret_list)

    # TODO: https://github.com/griptape-ai/griptape-nodes/issues/861
    # similar manager refactors: https://github.com/griptape-ai/griptape-nodes/issues/806
    def on_serialize_flow_to_commands(self, request: SerializeFlowToCommandsRequest) -> ResultPayload:  # noqa: C901, PLR0911, PLR0912, PLR0915
        flow_name = request.flow_name
        flow = None
        if flow_name is None:
            if GriptapeNodes.ContextManager().has_current_flow():
                flow = GriptapeNodes.ContextManager().get_current_flow()
                flow_name = flow.name
            else:
                details = "Attempted to serialize a Flow to commands from the Current Context. Failed because the Current Context was empty."
                logger.error(details)
                return SerializeFlowToCommandsResultFailure(result_details=details)
        if flow is None:
            # Does this flow exist?
            flow = GriptapeNodes.ObjectManager().attempt_get_object_by_name_as_type(flow_name, ControlFlow)
            if flow is None:
                details = (
                    f"Attempted to serialize Flow '{flow_name}' to commands, but no Flow with that name could be found."
                )
                logger.error(details)
                return SerializeFlowToCommandsResultFailure(result_details=details)

        # Track all node libraries that were in use by these Nodes
        node_libraries_in_use = set()

        # Track all referenced workflows used by this flow and its sub-flows
        referenced_workflows_in_use = set()

        # Track all parameter values that were in use by these Nodes (maps UUID to Parameter value)
        unique_parameter_uuid_to_values = {}
        # And track how values map into that map.
        serialized_parameter_value_tracker = SerializedParameterValueTracker()

        with GriptapeNodes.ContextManager().flow(flow):
            # The base flow creation, if desired.
            if request.include_create_flow_command:
                # Check if this flow is a referenced workflow
                if self.is_referenced_workflow(flow):
                    referenced_workflow_name = self.get_referenced_workflow_name(flow)
                    create_flow_request = ImportWorkflowAsReferencedSubFlowRequest(
                        workflow_name=referenced_workflow_name,  # type: ignore[arg-type] # is_referenced_workflow() guarantees this is not None
                        imported_flow_metadata=flow.metadata,
                    )
                    referenced_workflows_in_use.add(referenced_workflow_name)  # type: ignore[arg-type] # is_referenced_workflow() guarantees this is not None
                else:
                    # Always set set_as_new_context=False during serialization - let the workflow manager
                    # that loads this serialized flow decide whether to push it to context or not
                    create_flow_request = CreateFlowRequest(
                        parent_flow_name=None, set_as_new_context=False, metadata=flow.metadata
                    )
            else:
                create_flow_request = None

            serialized_node_commands = []
            set_parameter_value_commands_per_node = {}  # Maps a node UUID to a list of set parameter value commands
            set_lock_commands_per_node = {}  # Maps a node UUID to a set Lock command, if it exists.

            # Now each of the child nodes in the flow.
            node_name_to_uuid = {}
            nodes_in_flow_request = ListNodesInFlowRequest()
            nodes_in_flow_result = GriptapeNodes().handle_request(nodes_in_flow_request)
            if not isinstance(nodes_in_flow_result, ListNodesInFlowResultSuccess):
                details = (
                    f"Attempted to serialize Flow '{flow_name}'. Failed while attempting to list Nodes in the Flow."
                )
                logger.error(details)
                return SerializeFlowToCommandsResultFailure(result_details=details)

            # Serialize each node
            for node_name in nodes_in_flow_result.node_names:
                node = GriptapeNodes.ObjectManager().attempt_get_object_by_name_as_type(node_name, BaseNode)
                if node is None:
                    details = f"Attempted to serialize Flow '{flow_name}'. Failed while attempting to serialize Node '{node_name}' within the Flow."
                    logger.error(details)
                    return SerializeFlowToCommandsResultFailure(result_details=details)
                with GriptapeNodes.ContextManager().node(node):
                    # Note: the parameter value stuff is pass-by-reference, and we expect the values to be modified in place.
                    # This might be dangerous if done over the wire.
                    serialize_node_request = SerializeNodeToCommandsRequest(
                        unique_parameter_uuid_to_values=unique_parameter_uuid_to_values,  # Unique values
                        serialized_parameter_value_tracker=serialized_parameter_value_tracker,  # Mapping values to UUIDs
                    )
                    serialize_node_result = GriptapeNodes.handle_request(serialize_node_request)
                    if not isinstance(serialize_node_result, SerializeNodeToCommandsResultSuccess):
                        details = f"Attempted to serialize Flow '{flow_name}'. Failed while attempting to serialize Node '{node_name}' within the Flow."
                        logger.error(details)
                        return SerializeFlowToCommandsResultFailure(result_details=details)

                    serialized_node = serialize_node_result.serialized_node_commands

                    # Store the serialized node's UUID for correlation to connections and setting parameter values later.
                    node_name_to_uuid[node_name] = serialized_node.node_uuid

                    serialized_node_commands.append(serialized_node)
                    node_libraries_in_use.add(serialized_node.node_library_details)
                    # Get the list of set value commands for THIS node.
                    set_value_commands_list = serialize_node_result.set_parameter_value_commands
                    if serialize_node_result.serialized_node_commands.lock_node_command is not None:
                        set_lock_commands_per_node[serialized_node.node_uuid] = (
                            serialize_node_result.serialized_node_commands.lock_node_command
                        )
                    set_parameter_value_commands_per_node[serialized_node.node_uuid] = set_value_commands_list

            # We'll have to do a patch-up of all the connections, since we can't predict all of the node names being accurate
            # when we're restored.
            # Create all of the connections
            create_connection_commands = []
            for connection in self._get_connections_for_flow(flow):
                source_node_uuid = node_name_to_uuid[connection.source_node.name]
                target_node_uuid = node_name_to_uuid[connection.target_node.name]
                create_connection_command = SerializedFlowCommands.IndirectConnectionSerialization(
                    source_node_uuid=source_node_uuid,
                    source_parameter_name=connection.source_parameter.name,
                    target_node_uuid=target_node_uuid,
                    target_parameter_name=connection.target_parameter.name,
                )
                create_connection_commands.append(create_connection_command)

            # Now sub-flows.
            parent_flow = GriptapeNodes.ContextManager().get_current_flow()
            parent_flow_name = parent_flow.name
            flows_in_flow_request = ListFlowsInFlowRequest(parent_flow_name=parent_flow_name)
            flows_in_flow_result = GriptapeNodes().handle_request(flows_in_flow_request)
            if not isinstance(flows_in_flow_result, ListFlowsInFlowResultSuccess):
                details = f"Attempted to serialize Flow '{flow_name}'. Failed while attempting to list child Flows in the Flow."
                logger.error(details)
                return SerializeFlowToCommandsResultFailure(result_details=details)

            sub_flow_commands = []
            for child_flow in flows_in_flow_result.flow_names:
                flow = GriptapeNodes.ObjectManager().attempt_get_object_by_name_as_type(child_flow, ControlFlow)
                if flow is None:
                    details = f"Attempted to serialize Flow '{flow_name}', but no Flow with that name could be found."
                    logger.error(details)
                    return SerializeFlowToCommandsResultFailure(result_details=details)

                # Check if this is a referenced workflow
                if self.is_referenced_workflow(flow):
                    # For referenced workflows, create a minimal SerializedFlowCommands with just the import command
                    referenced_workflow_name = self.get_referenced_workflow_name(flow)
                    import_command = ImportWorkflowAsReferencedSubFlowRequest(
                        workflow_name=referenced_workflow_name,  # type: ignore[arg-type] # is_referenced_workflow() guarantees this is not None
                        imported_flow_metadata=flow.metadata,
                    )

                    serialized_flow = SerializedFlowCommands(
                        node_libraries_used=set(),
                        flow_initialization_command=import_command,
                        serialized_node_commands=[],
                        serialized_connections=[],
                        unique_parameter_uuid_to_values={},
                        set_parameter_value_commands={},
                        sub_flows_commands=[],
                        referenced_workflows={referenced_workflow_name},  # type: ignore[arg-type] # is_referenced_workflow() guarantees this is not None
                    )
                    sub_flow_commands.append(serialized_flow)

                    # Add this referenced workflow to our accumulation
                    referenced_workflows_in_use.add(referenced_workflow_name)  # type: ignore[arg-type] # is_referenced_workflow() guarantees this is not None
                else:
                    # For standalone sub-flows, use the existing recursive serialization
                    with GriptapeNodes.ContextManager().flow(flow=flow):
                        child_flow_request = SerializeFlowToCommandsRequest()
                        child_flow_result = GriptapeNodes().handle_request(child_flow_request)
                        if not isinstance(child_flow_result, SerializeFlowToCommandsResultSuccess):
                            details = f"Attempted to serialize parent flow '{flow_name}'. Failed while serializing child flow '{child_flow}'."
                            logger.error(details)
                            return SerializeFlowToCommandsResultFailure()
                        serialized_flow = child_flow_result.serialized_flow_commands
                        sub_flow_commands.append(serialized_flow)

                        # Merge in all child flow library details.
                        node_libraries_in_use.union(serialized_flow.node_libraries_used)

                        # Merge in all child flow referenced workflows.
                        referenced_workflows_in_use.union(serialized_flow.referenced_workflows)

        serialized_flow = SerializedFlowCommands(
            flow_initialization_command=create_flow_request,
            serialized_node_commands=serialized_node_commands,
            serialized_connections=create_connection_commands,
            unique_parameter_uuid_to_values=unique_parameter_uuid_to_values,
            set_parameter_value_commands=set_parameter_value_commands_per_node,
            set_lock_commands_per_node=set_lock_commands_per_node,
            sub_flows_commands=sub_flow_commands,
            node_libraries_used=node_libraries_in_use,
            referenced_workflows=referenced_workflows_in_use,
        )
        details = f"Successfully serialized Flow '{flow_name}' into commands."
        result = SerializeFlowToCommandsResultSuccess(serialized_flow_commands=serialized_flow)
        return result

    def on_deserialize_flow_from_commands(self, request: DeserializeFlowFromCommandsRequest) -> ResultPayload:  # noqa: C901, PLR0911, PLR0912, PLR0915 (I am big and complicated and have a lot of negative edge-cases)
        # Do we want to create a NEW Flow to deserialize into, or use the one in the Current Context?
        if request.serialized_flow_commands.flow_initialization_command is None:
            if GriptapeNodes.ContextManager().has_current_flow():
                flow = GriptapeNodes.ContextManager().get_current_flow()
                flow_name = flow.name
            else:
                details = "Attempted to deserialize a set of Flow Creation commands into the Current Context. Failed because the Current Context was empty."
                logger.error(details)
                return DeserializeFlowFromCommandsResultFailure(result_details=details)
        else:
            # Issue the creation command first.
            flow_initialization_command = request.serialized_flow_commands.flow_initialization_command
            flow_initialization_result = GriptapeNodes.handle_request(flow_initialization_command)

            # Handle different types of creation commands
            match flow_initialization_command:
                case CreateFlowRequest():
                    if not isinstance(flow_initialization_result, CreateFlowResultSuccess):
                        details = f"Attempted to deserialize a serialized set of Flow Creation commands. Failed to create flow '{flow_initialization_command.flow_name}'."
                        logger.error(details)
                        return DeserializeFlowFromCommandsResultFailure(result_details=details)
                    flow_name = flow_initialization_result.flow_name
                case ImportWorkflowAsReferencedSubFlowRequest():
                    if not isinstance(flow_initialization_result, ImportWorkflowAsReferencedSubFlowResultSuccess):
                        details = f"Attempted to deserialize a serialized set of Flow Creation commands. Failed to import workflow '{flow_initialization_command.workflow_name}'."
                        logger.error(details)
                        return DeserializeFlowFromCommandsResultFailure(result_details=details)
                    flow_name = flow_initialization_result.created_flow_name
                case _:
                    details = f"Attempted to deserialize Flow Creation commands with unknown command type: {type(flow_initialization_command).__name__}."
                    logger.error(details)
                    return DeserializeFlowFromCommandsResultFailure(result_details=details)

            # Adopt the newly-created flow as our current context.
            flow = GriptapeNodes.ObjectManager().attempt_get_object_by_name_as_type(flow_name, ControlFlow)
            if flow is None:
                details = f"Attempted to deserialize a serialized set of Flow Creation commands. Failed to find created flow '{flow_name}'."
                logger.error(details)
                return DeserializeFlowFromCommandsResultFailure(result_details=details)
            GriptapeNodes.ContextManager().push_flow(flow=flow)

        # Deserializing a flow goes in a specific order.

        # Create the nodes.
        # Preserve the node UUIDs because we will need to tie these back together with the Connections later.
        node_uuid_to_deserialized_node_result = {}
        for serialized_node in request.serialized_flow_commands.serialized_node_commands:
            deserialize_node_request = DeserializeNodeFromCommandsRequest(serialized_node_commands=serialized_node)
            deserialized_node_result = GriptapeNodes.handle_request(deserialize_node_request)
            if deserialized_node_result.failed():
                details = (
                    f"Attempted to deserialize a Flow '{flow_name}'. Failed while deserializing a node within the flow."
                )
                logger.error(details)
                return DeserializeFlowFromCommandsResultFailure(result_details=details)
            node_uuid_to_deserialized_node_result[serialized_node.node_uuid] = deserialized_node_result

        # Now apply the connections.
        # We didn't know the exact name that would be used for the nodes, but we knew the node's creation UUID.
        # Tie the UUID back to the node names.
        for indirect_connection in request.serialized_flow_commands.serialized_connections:
            # Validate the source and target node UUIDs.
            source_node_uuid = indirect_connection.source_node_uuid
            if source_node_uuid not in node_uuid_to_deserialized_node_result:
                details = f"Attempted to deserialize a Flow '{flow_name}'. Failed while attempting to create a Connection for a source node that did not exist within the flow."
                logger.error(details)
                return DeserializeFlowFromCommandsResultFailure(result_details=details)
            target_node_uuid = indirect_connection.target_node_uuid
            if target_node_uuid not in node_uuid_to_deserialized_node_result:
                details = f"Attempted to deserialize a Flow '{flow_name}'. Failed while attempting to create a Connection for a target node that did not exist within the flow."
                logger.error(details)
                return DeserializeFlowFromCommandsResultFailure(result_details=details)

            source_node_result = node_uuid_to_deserialized_node_result[source_node_uuid]
            source_node_name = source_node_result.node_name
            target_node_result = node_uuid_to_deserialized_node_result[indirect_connection.target_node_uuid]
            target_node_name = target_node_result.node_name

            create_connection_request = CreateConnectionRequest(
                source_node_name=source_node_name,
                source_parameter_name=indirect_connection.source_parameter_name,
                target_node_name=target_node_name,
                target_parameter_name=indirect_connection.target_parameter_name,
            )
            create_connection_result = GriptapeNodes.handle_request(create_connection_request)
            if create_connection_result.failed():
                details = f"Attempted to deserialize a Flow '{flow_name}'. Failed while deserializing a Connection from '{source_node_name}.{indirect_connection.source_parameter_name}' to '{target_node_name}.{indirect_connection.target_parameter_name}' within the flow."
                logger.error(details)
                return DeserializeFlowFromCommandsResultFailure(result_details=details)

        # Now assign the values.
        # This is the same issue that we handle for Connections:
        # we don't know the exact node name that would be used, but we do know the UUIDs.
        # Similarly, we need to wire up the value UUIDs back to the unique values.
        # We maintain one map of set value commands per node in the Flow.
        for node_uuid, set_value_command_list in request.serialized_flow_commands.set_parameter_value_commands.items():
            node_name = node_uuid_to_deserialized_node_result[node_uuid].node_name
            # Make this node the current context.
            node = GriptapeNodes.ObjectManager().attempt_get_object_by_name_as_type(node_name, BaseNode)
            if node is None:
                details = f"Attempted to deserialize a Flow '{flow_name}'. Failed while deserializing a value assignment for node '{node_name}'."
                logger.error(details)
                return DeserializeFlowFromCommandsResultFailure(result_details=details)
            with GriptapeNodes.ContextManager().node(node=node):
                # Iterate through each set value command in the list for this node.
                for indirect_set_value_command in set_value_command_list:
                    parameter_name = indirect_set_value_command.set_parameter_value_command.parameter_name
                    unique_value_uuid = indirect_set_value_command.unique_value_uuid
                    try:
                        value = request.serialized_flow_commands.unique_parameter_uuid_to_values[unique_value_uuid]
                    except IndexError as err:
                        details = f"Attempted to deserialize a Flow '{flow_name}'. Failed while deserializing a value assignment for node '{node.name}.{parameter_name}': {err}"
                        logger.error(details)
                        return DeserializeFlowFromCommandsResultFailure(result_details=details)

                    # Call the SetParameterValueRequest, subbing in the value from our unique value list.
                    indirect_set_value_command.set_parameter_value_command.value = value
                    set_parameter_value_result = GriptapeNodes.handle_request(
                        indirect_set_value_command.set_parameter_value_command
                    )
                    if set_parameter_value_result.failed():
                        details = f"Attempted to deserialize a Flow '{flow_name}'. Failed while deserializing a value assignment for node '{node.name}.{parameter_name}'."
                        logger.error(details)
                        return DeserializeFlowFromCommandsResultFailure(result_details=details)

        # Now the child flows.
        for sub_flow_command in request.serialized_flow_commands.sub_flows_commands:
            sub_flow_request = DeserializeFlowFromCommandsRequest(serialized_flow_commands=sub_flow_command)
            sub_flow_result = GriptapeNodes.handle_request(sub_flow_request)
            if sub_flow_result.failed():
                details = f"Attempted to deserialize a Flow '{flow_name}'. Failed while deserializing a sub-flow within the Flow."
                logger.error(details)
                return DeserializeFlowFromCommandsResultFailure(result_details=details)

        details = f"Successfully deserialized Flow '{flow_name}'."
        logger.debug(details)
        return DeserializeFlowFromCommandsResultSuccess(flow_name=flow_name)

    def on_flush_request(self, request: FlushParameterChangesRequest) -> ResultPayload:  # noqa: ARG002
        obj_manager = GriptapeNodes.ObjectManager()
        GriptapeNodes.EventManager().clear_flush_in_queue()
        # Get all flows and their nodes
        nodes = obj_manager.get_filtered_subset(type=BaseNode)
        for node in nodes.values():
            # Only flush if there are actually tracked parameters
            if node._tracked_parameters:
                node.emit_parameter_changes()
        return FlushParameterChangesResultSuccess()

    def start_flow(self, flow: ControlFlow, start_node: BaseNode | None = None, debug_mode: bool = False) -> None:  # noqa: FBT001, FBT002, ARG002
        if self.check_for_existing_running_flow():
            # If flow already exists, throw an error
            errormsg = "This workflow is already in progress. Please wait for the current process to finish before starting again."
            raise RuntimeError(errormsg)

        if start_node is None:
            if self._global_flow_queue.empty():
                errormsg = "No Flow exists. You must create at least one control connection."
                raise RuntimeError(errormsg)
            start_node = self._global_flow_queue.get()
            self._global_flow_queue.task_done()

        # Initialize global control flow machine if needed
        if self._global_control_flow_machine is None:
            self._global_control_flow_machine = ControlFlowMachine()

        try:
            self._global_control_flow_machine.start_flow(start_node, debug_mode)
        except Exception:
            if self.check_for_existing_running_flow():
                self.cancel_flow_run()
            raise

    def check_for_existing_running_flow(self) -> bool:
        if self._global_control_flow_machine is None:
            return False
        if (
            self._global_control_flow_machine._current_state is not CompleteState
            and self._global_control_flow_machine._current_state
        ):
            # Flow already exists in progress
            return True
        return bool(
            not self._global_control_flow_machine._context.resolution_machine.is_complete()
            and self._global_control_flow_machine._context.resolution_machine.is_started()
        )

    def cancel_flow_run(self) -> None:
        if not self.check_for_existing_running_flow():
            errormsg = "Flow has not yet been started. Cannot cancel flow that hasn't begun."
            raise RuntimeError(errormsg)
        self._global_flow_queue.queue.clear()
        if self._global_control_flow_machine is not None:
            self._global_control_flow_machine.reset_machine()
        # Reset control flow machine
        self._global_single_node_resolution = False
        logger.debug("Cancelling flow run")

        EventBus.publish_event(
            ExecutionGriptapeNodeEvent(wrapped_event=ExecutionEvent(payload=ControlFlowCancelledEvent()))
        )

    def reset_global_execution_state(self) -> None:
        """Reset all global execution state - useful when clearing all workflows."""
        self._global_flow_queue.queue.clear()
        if self._global_control_flow_machine is not None:
            self._global_control_flow_machine.reset_machine()
        self._global_control_flow_machine = None
        self._global_single_node_resolution = False

        # Clear all connections to prevent memory leaks and stale references
        self._connections.connections.clear()
        self._connections.outgoing_index.clear()
        self._connections.incoming_index.clear()

        logger.debug("Reset global execution state")

    # Public methods to replace private variable access from external classes
    def is_execution_queue_empty(self) -> bool:
        """Check if the global execution queue is empty."""
        return self._global_flow_queue.empty()

    def get_next_node_from_execution_queue(self) -> BaseNode | None:
        """Get the next node from the global execution queue, or None if empty."""
        if self._global_flow_queue.empty():
            return None
        node = self._global_flow_queue.get()
        self._global_flow_queue.task_done()
        return node

    def clear_execution_queue(self) -> None:
        """Clear all nodes from the global execution queue."""
        self._global_flow_queue.queue.clear()

    def has_connection(
        self,
        source_node: BaseNode,
        source_parameter: Parameter,
        target_node: BaseNode,
        target_parameter: Parameter,
    ) -> bool:
        """Check if a connection exists between the specified nodes and parameters."""
        return self._has_connection(source_node, source_parameter, target_node, target_parameter)

    # Internal execution queue helper methods to consolidate redundant operations
    def _handle_flow_start_if_not_running(self, flow: ControlFlow, *, debug_mode: bool, error_message: str) -> None:  # noqa: ARG002
        """Common logic for starting flow execution if not already running."""
        if not self.check_for_existing_running_flow():
            if self._global_flow_queue.empty():
                raise RuntimeError(error_message)
            start_node = self._global_flow_queue.get()
            self._global_flow_queue.task_done()
            if self._global_control_flow_machine is None:
                self._global_control_flow_machine = ControlFlowMachine()
            self._global_control_flow_machine.start_flow(start_node, debug_mode)

    def _handle_post_execution_queue_processing(self, *, debug_mode: bool) -> None:
        """Handle execution queue processing after execution completes."""
        if not self.check_for_existing_running_flow() and not self._global_flow_queue.empty():
            start_node = self._global_flow_queue.get()
            self._global_flow_queue.task_done()
            if self._global_control_flow_machine is not None:
                self._global_control_flow_machine.start_flow(start_node, debug_mode)

    def resolve_singular_node(self, flow: ControlFlow, node: BaseNode, debug_mode: bool = False) -> None:  # noqa: FBT001, FBT002, ARG002
        # Set that we are only working on one node right now! no other stepping allowed
        if self.check_for_existing_running_flow():
            # If flow already exists, throw an error
            errormsg = f"This workflow is already in progress. Please wait for the current process to finish before starting {node.name} again."
            raise RuntimeError(errormsg)
        self._global_single_node_resolution = True
        # Initialize global control flow machine if needed
        if self._global_control_flow_machine is None:
            self._global_control_flow_machine = ControlFlowMachine()
        # Get the node resolution machine for the current flow!
        self._global_control_flow_machine._context.current_node = node
        resolution_machine = self._global_control_flow_machine._context.resolution_machine
        # Set debug mode
        resolution_machine.change_debug_mode(debug_mode)
        # Resolve the node.
        node.state = NodeResolutionState.UNRESOLVED
        resolution_machine.resolve_node(node)
        # decide if we can change it back to normal flow mode!
        if resolution_machine.is_complete():
            self._global_single_node_resolution = False
            self._global_control_flow_machine._context.current_node = None

    def single_execution_step(self, flow: ControlFlow, change_debug_mode: bool) -> None:  # noqa: FBT001
        # do a granular step
        self._handle_flow_start_if_not_running(
            flow, debug_mode=True, error_message="Flow has not yet been started. Cannot step while no flow has begun."
        )
        if not self.check_for_existing_running_flow():
            return
        if self._global_control_flow_machine is not None:
            self._global_control_flow_machine.granular_step(change_debug_mode)
            resolution_machine = self._global_control_flow_machine._context.resolution_machine
            if self._global_single_node_resolution:
                resolution_machine = self._global_control_flow_machine._context.resolution_machine
                if resolution_machine.is_complete():
                    self._global_single_node_resolution = False

    def single_node_step(self, flow: ControlFlow) -> None:
        # It won't call single_node_step without an existing flow running from US.
        self._handle_flow_start_if_not_running(
            flow, debug_mode=True, error_message="Flow has not yet been started. Cannot step while no flow has begun."
        )
        if not self.check_for_existing_running_flow():
            return
        # Step over a whole node
        if self._global_single_node_resolution:
            msg = "Cannot step through the Control Flow in Single Node Execution"
            raise RuntimeError(msg)
        if self._global_control_flow_machine is not None:
            self._global_control_flow_machine.node_step()
        # Start the next resolution step now please.
        self._handle_post_execution_queue_processing(debug_mode=True)

    def continue_executing(self, flow: ControlFlow) -> None:
        self._handle_flow_start_if_not_running(
            flow, debug_mode=False, error_message="Flow has not yet been started. Cannot step while no flow has begun."
        )
        if not self.check_for_existing_running_flow():
            return
        # Turn all debugging to false and continue on
        if self._global_control_flow_machine is not None:
            self._global_control_flow_machine.change_debug_mode(False)
            if self._global_single_node_resolution:
                if self._global_control_flow_machine._context.resolution_machine.is_complete():
                    self._global_single_node_resolution = False
                else:
                    self._global_control_flow_machine._context.resolution_machine.update()
            else:
                self._global_control_flow_machine.node_step()
        # Now it is done executing. make sure it's actually done?
        self._handle_post_execution_queue_processing(debug_mode=False)

    def unresolve_whole_flow(self, flow: ControlFlow) -> None:
        for node in flow.nodes.values():
            node.make_node_unresolved(current_states_to_trigger_change_event=None)
            # Clear entry control parameter for new execution
            node.set_entry_control_parameter(None)

    def flow_state(self, flow: ControlFlow) -> tuple[str | None, str | None]:  # noqa: ARG002
        if not self.check_for_existing_running_flow():
            msg = "Flow hasn't started."
            raise RuntimeError(msg)
        if self._global_control_flow_machine is None:
            return None, None
        current_control_node = (
            self._global_control_flow_machine._context.current_node.name
            if self._global_control_flow_machine._context.current_node is not None
            else None
        )
        focus_stack_for_node = self._global_control_flow_machine._context.resolution_machine._context.focus_stack
        current_resolving_node = focus_stack_for_node[-1].node.name if len(focus_stack_for_node) else None
        return current_control_node, current_resolving_node

    def get_start_node_from_node(self, flow: ControlFlow, node: BaseNode) -> BaseNode | None:
        # backwards chain in control outputs.
        if node not in flow.nodes.values():
            return None
        # Go back through incoming control connections to get the start node
        curr_node = node
        prev_node = self.get_prev_node(flow, curr_node)
        # Fencepost loop - get the first previous node name and then we go
        while prev_node:
            curr_node = prev_node
            prev_node = self.get_prev_node(flow, prev_node)
        return curr_node

    def get_prev_node(self, flow: ControlFlow, node: BaseNode) -> BaseNode | None:  # noqa: ARG002
        connections = self.get_connections()
        if node.name in connections.incoming_index:
            parameters = connections.incoming_index[node.name]
            for parameter_name in parameters:
                parameter = node.get_parameter_by_name(parameter_name)
                if parameter and ParameterTypeBuiltin.CONTROL_TYPE.value == parameter.output_type:
                    # this is a control connection
                    connection_ids = connections.incoming_index[node.name][parameter_name]
                    for connection_id in connection_ids:
                        connection = connections.connections[connection_id]
                        return connection.get_source_node()
        return None

    def get_start_node_queue(self) -> Queue | None:  # noqa: C901, PLR0912
        # For cross-flow execution, we need to consider ALL nodes across ALL flows
        # Clear and use the global execution queue
        self._global_flow_queue.queue.clear()

        # Get all flows and collect all nodes across all flows
        all_flows = GriptapeNodes.ObjectManager().get_filtered_subset(type=ControlFlow)
        all_nodes = []
        for current_flow in all_flows.values():
            all_nodes.extend(current_flow.nodes.values())

        # if no nodes across all flows, no execution possible
        if not all_nodes:
            return None

        data_nodes = []
        valid_data_nodes = []
        start_nodes = []
        control_nodes = []
        for node in all_nodes:
            # if it's a start node, start here! Return the first one!
            if isinstance(node, StartNode):
                start_nodes.append(node)
                continue
            # no start nodes. let's find the first control node.
            # if it's a control node, there could be a flow.
            control_param = False
            for parameter in node.parameters:
                if ParameterTypeBuiltin.CONTROL_TYPE.value == parameter.output_type:
                    control_param = True
                    break
            if not control_param:
                # saving this for later
                data_nodes.append(node)
                # If this node doesn't have a control connection..
                continue

            cn_mgr = self.get_connections()
            # check if it has an incoming connection. If it does, it's not a start node
            has_control_connection = False
            if node.name in cn_mgr.incoming_index:
                for param_name in cn_mgr.incoming_index[node.name]:
                    param = node.get_parameter_by_name(param_name)
                    if param and ParameterTypeBuiltin.CONTROL_TYPE.value == param.output_type:
                        # there is a control connection coming in
                        has_control_connection = True
                        break
            # if there is a connection coming in, isn't a start.
            if has_control_connection and not isinstance(node, StartLoopNode):
                continue
            # Does it have an outgoing connection?
            if node.name in cn_mgr.outgoing_index:
                # If one of the outgoing connections is control, add it. otherwise don't.
                for param_name in cn_mgr.outgoing_index[node.name]:
                    param = node.get_parameter_by_name(param_name)
                    if param and ParameterTypeBuiltin.CONTROL_TYPE.value == param.output_type:
                        control_nodes.append(node)
                        break
            else:
                control_nodes.append(node)

        # If we've gotten to this point, there are no control parameters
        # Let's return a data node that has no OUTGOING data connections!
        for node in data_nodes:
            cn_mgr = self.get_connections()
            # check if it has an outgoing connection. We don't want it to (that means we get the most resolution)
            if node.name not in cn_mgr.outgoing_index:
                valid_data_nodes.append(node)
        # ok now - populate the global flow queue
        for node in start_nodes:
            self._global_flow_queue.put(node)
        for node in control_nodes:
            self._global_flow_queue.put(node)
        for node in valid_data_nodes:
            self._global_flow_queue.put(node)

        return self._global_flow_queue

    def get_connected_input_from_node(self, flow: ControlFlow, node: BaseNode) -> list[tuple[BaseNode, Parameter]]:  # noqa: ARG002
        global_connections = self.get_connections()
        connections = []
        if node.name in global_connections.incoming_index:
            connection_ids = [
                item for value_list in global_connections.incoming_index[node.name].values() for item in value_list
            ]
            for connection_id in connection_ids:
                connection = global_connections.connections[connection_id]
                connections.append((connection.source_node, connection.source_parameter))
        return connections

    def get_connected_output_from_node(self, flow: ControlFlow, node: BaseNode) -> list[tuple[BaseNode, Parameter]]:  # noqa: ARG002
        global_connections = self.get_connections()
        connections = []
        if node.name in global_connections.outgoing_index:
            connection_ids = [
                item for value_list in global_connections.outgoing_index[node.name].values() for item in value_list
            ]
            for connection_id in connection_ids:
                connection = global_connections.connections[connection_id]
                connections.append((connection.target_node, connection.target_parameter))
        return connections

    def get_connected_input_parameters(
        self,
        flow: ControlFlow,  # noqa: ARG002
        node: BaseNode,
        param: Parameter,
    ) -> list[tuple[BaseNode, Parameter]]:
        global_connections = self.get_connections()
        connections = []
        if node.name in global_connections.incoming_index:
            incoming_params = global_connections.incoming_index[node.name]
            if param.name in incoming_params:
                for connection_id in incoming_params[param.name]:
                    connection = global_connections.connections[connection_id]
                    connections.append((connection.source_node, connection.source_parameter))
        return connections

    def get_connections_on_node(self, flow: ControlFlow, node: BaseNode) -> list[BaseNode] | None:  # noqa: ARG002
        connections = self.get_connections()
        # get all of the connection ids
        connected_nodes = []
        # Handle outgoing connections
        if node.name in connections.outgoing_index:
            outgoing_params = connections.outgoing_index[node.name]
            outgoing_connection_ids = []
            for connection_ids in outgoing_params.values():
                outgoing_connection_ids = outgoing_connection_ids + connection_ids
            for connection_id in outgoing_connection_ids:
                connection = connections.connections[connection_id]
                if connection.source_node not in connected_nodes:
                    connected_nodes.append(connection.target_node)
        # Handle incoming connections
        if node.name in connections.incoming_index:
            incoming_params = connections.incoming_index[node.name]
            incoming_connection_ids = []
            for connection_ids in incoming_params.values():
                incoming_connection_ids = incoming_connection_ids + connection_ids
            for connection_id in incoming_connection_ids:
                connection = connections.connections[connection_id]
                if connection.source_node not in connected_nodes:
                    connected_nodes.append(connection.source_node)
        # Return all connected nodes. No duplicates
        return connected_nodes

    def get_all_connected_nodes(self, flow: ControlFlow, node: BaseNode) -> list[BaseNode]:
        discovered = {}
        processed = {}
        queue = Queue()
        queue.put(node)
        discovered[node] = True
        while not queue.empty():
            curr_node = queue.get()
            processed[curr_node] = True
            next_nodes = self.get_connections_on_node(flow, curr_node)
            if next_nodes:
                for next_node in next_nodes:
                    if next_node not in discovered:
                        discovered[next_node] = True
                        queue.put(next_node)
        return list(processed.keys())

    def get_node_dependencies(self, flow: ControlFlow, node: BaseNode) -> list[BaseNode]:
        """Get all upstream nodes that the given node depends on.

        This method performs a breadth-first search starting from the given node and working backwards through its non-control input connections to identify all nodes that must run before this node can be resolved.
        It ignores control connections, since we're only focusing on node dependencies.

        Args:
            flow (ControlFlow): The flow containing the node
            node (BaseNode): The node to find dependencies for

        Returns:
            list[BaseNode]: A list of all nodes that the given node depends on, including the node itself (as the first element)
        """
        node_list = [node]
        node_queue = Queue()
        node_queue.put(node)
        while not node_queue.empty():
            curr_node = node_queue.get()
            input_connections = self.get_connected_input_from_node(flow, curr_node)
            if input_connections:
                for input_node, input_parameter in input_connections:
                    if (
                        ParameterTypeBuiltin.CONTROL_TYPE.value != input_parameter.output_type
                        and input_node not in node_list
                    ):
                        node_list.append(input_node)
                        node_queue.put(input_node)
        return node_list
