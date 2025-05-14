from __future__ import annotations

import logging
from typing import TYPE_CHECKING, cast

from griptape.events import EventBus

from griptape_nodes.exe_types.core_types import (
    ParameterContainer,
    ParameterMode,
)
from griptape_nodes.exe_types.flow import ControlFlow
from griptape_nodes.exe_types.node_types import BaseNode, NodeResolutionState
from griptape_nodes.retained_mode.events.base_events import ExecutionEvent, ExecutionGriptapeNodeEvent
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
)
from griptape_nodes.retained_mode.events.node_events import (
    DeleteNodeRequest,
    DeleteNodeResultFailure,
    DeserializeNodeFromCommandsRequest,
    SerializeNodeToCommandsRequest,
    SerializeNodeToCommandsResultSuccess,
)
from griptape_nodes.retained_mode.events.parameter_events import (
    AlterParameterEvent,
    SetParameterValueRequest,
)
from griptape_nodes.retained_mode.events.validation_events import (
    ValidateFlowDependenciesRequest,
    ValidateFlowDependenciesResultFailure,
    ValidateFlowDependenciesResultSuccess,
)
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

if TYPE_CHECKING:
    from griptape_nodes.retained_mode.events.base_events import ResultPayload
    from griptape_nodes.retained_mode.managers.event_manager import EventManager

logger = logging.getLogger("griptape_nodes")


class FlowManager:
    _name_to_parent_name: dict[str, str | None]

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
        event_manager.assign_manager_to_request_type(SerializeFlowToCommandsRequest, self.on_serialize_flow_to_commands)
        event_manager.assign_manager_to_request_type(
            DeserializeFlowFromCommandsRequest, self.on_deserialize_flow_from_commands
        )

        self._name_to_parent_name = {}

    def get_parent_flow(self, flow_name: str) -> str | None:
        if flow_name in self._name_to_parent_name:
            return self._name_to_parent_name[flow_name]
        msg = f"Flow with name {flow_name} doesn't exist"
        raise ValueError(msg)

    def on_get_top_level_flow_request(self, request: GetTopLevelFlowRequest) -> ResultPayload:  # noqa: ARG002 (the request has to be assigned to the method)
        for flow_name, parent in self._name_to_parent_name.items():
            if parent is None:
                return GetTopLevelFlowResultSuccess(flow_name=flow_name)
        msg = "Attempted to get top level flow, but no such flow exists"
        logger.debug(msg)
        return GetTopLevelFlowResultSuccess(flow_name=None)

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
        if (parent_name is None) and (GriptapeNodes.ContextManager().has_current_flow()):
            # Aha! Just use that.
            parent_name = GriptapeNodes.ContextManager().get_current_flow_name()

        # TODO: FIX THIS LOGIC MESS https://github.com/griptape-ai/griptape-nodes/issues/616

        parent = None
        if parent_name is not None:
            parent = GriptapeNodes.ObjectManager().attempt_get_object_by_name_as_type(parent_name, ControlFlow)
        if parent_name is None:
            if self.does_canvas_exist():
                # We're trying to create the canvas. Ensure that parent does NOT already exist.
                details = "Attempted to create a Flow as the Canvas (top-level Flow with no parents), but the Canvas already exists."
                logger.error(details)
                result = CreateFlowResultFailure()
                return result
        # Now our parent exists, right?
        elif parent is None:
            details = f"Attempted to create a Flow with a parent '{request.parent_flow_name}', but no parent with that name could be found."
            logger.error(details)

            result = CreateFlowResultFailure()

            return result

        # We need to have a current workflow context to proceed.
        if not GriptapeNodes.ContextManager().has_current_workflow():
            details = "Attempted to create a Flow, but no Workflow was active in the Current Context."
            logger.error(details)
            return CreateFlowResultFailure()

        # Create it.
        final_flow_name = GriptapeNodes.ObjectManager().generate_name_for_object(
            type_name="ControlFlow", requested_name=request.flow_name
        )
        flow = ControlFlow()
        GriptapeNodes.ObjectManager().add_object_by_name(name=final_flow_name, obj=flow)
        self._name_to_parent_name[final_flow_name] = parent_name

        # See if we need to push it as the current context.
        if request.set_as_new_context:
            GriptapeNodes.ContextManager().push_flow(final_flow_name)

        # Success
        details = f"Successfully created Flow '{final_flow_name}'."
        log_level = logging.DEBUG
        if (request.flow_name is not None) and (final_flow_name != request.flow_name):
            details = f"{details} WARNING: Had to rename from original Flow requested '{request.flow_name}' as an object with this name already existed."
            log_level = logging.WARNING

        logger.log(level=log_level, msg=details)
        result = CreateFlowResultSuccess(flow_name=final_flow_name)
        return result

    def on_delete_flow_request(self, request: DeleteFlowRequest) -> ResultPayload:  # noqa: C901, PLR0911, PLR0915
        flow_name = request.flow_name
        if flow_name is None:
            # We want to delete whatever is at the top of the Current Context.
            if not GriptapeNodes.ContextManager().has_current_flow():
                details = (
                    "Attempted to delete a Flow from the Current Context. Failed because the Current Context was empty."
                )
                logger.error(details)
                result = DeleteFlowResultFailure()
                return result
            # We pop it off here, but we'll re-add it using context in a moment.
            flow_name = GriptapeNodes.ContextManager().pop_flow()

        # Does this Flow even exist?
        obj_mgr = GriptapeNodes.ObjectManager()
        flow = obj_mgr.attempt_get_object_by_name_as_type(flow_name, ControlFlow)
        if flow is None:
            details = f"Attempted to delete Flow '{flow_name}', but no Flow with that name could be found."
            logger.error(details)
            result = DeleteFlowResultFailure()
            return result
        if flow.check_for_existing_running_flow():
            result = GriptapeNodes.handle_request(CancelFlowRequest(flow_name=flow_name))
            if not result.succeeded():
                details = f"Attempted to delete flow '{flow_name}'. Failed because running flow could not cancel."
                logger.error(details)
                return DeleteFlowResultFailure()

        # Let this Flow assume the Current Context while we delete everything within it.
        with GriptapeNodes.ContextManager().flow(flow_name=flow_name):
            # Delete all child nodes in this Flow.
            list_nodes_request = ListNodesInFlowRequest()
            list_nodes_result = GriptapeNodes.handle_request(list_nodes_request)
            if not isinstance(list_nodes_result, ListNodesInFlowResultSuccess):
                details = f"Attempted to delete Flow '{flow_name}', but failed while attempting to get the list of Nodes owned by this Flow."
                logger.error(details)
                result = DeleteFlowResultFailure()
                return result
            node_names = list_nodes_result.node_names
            for node_name in node_names:
                delete_node_request = DeleteNodeRequest(node_name=node_name)
                delete_node_result = GriptapeNodes.handle_request(delete_node_request)
                if isinstance(delete_node_result, DeleteNodeResultFailure):
                    details = f"Attempted to delete Flow '{flow_name}', but failed while attempting to delete child Node '{node_name}'."
                    logger.error(details)
                    result = DeleteFlowResultFailure()
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
                result = DeleteFlowResultFailure()
                return result
            flow_names = list_flows_result.flow_names
            for child_flow_name in flow_names:
                with GriptapeNodes.ContextManager().flow(flow_name=child_flow_name):
                    # Delete them.
                    delete_flow_request = DeleteFlowRequest()
                    delete_flow_result = GriptapeNodes.handle_request(delete_flow_request)
                    if isinstance(delete_flow_result, DeleteFlowResultFailure):
                        details = f"Attempted to delete Flow '{flow_name}', but failed while attempting to delete child Flow '{child_flow_name}'."
                        logger.error(details)
                        result = DeleteFlowResultFailure()
                        return result

            # If we've made it this far, we have deleted all the children Flows and their nodes.
            # Remove the flow from our map.
            obj_mgr.del_obj_by_name(flow_name)
            del self._name_to_parent_name[flow_name]

        details = f"Successfully deleted Flow '{flow_name}'."
        logger.debug(details)
        result = DeleteFlowResultSuccess()
        return result

    def on_get_is_flow_running_request(self, request: GetIsFlowRunningRequest) -> ResultPayload:
        obj_mgr = GriptapeNodes.ObjectManager()
        flow = obj_mgr.attempt_get_object_by_name_as_type(request.flow_name, ControlFlow)
        if flow is None:
            details = f"Attempted to get Flow '{request.flow_name}', but no Flow with that name could be found."
            logger.error(details)
            result = GetIsFlowRunningResultFailure()
            return result
        try:
            is_running = flow.check_for_existing_running_flow()
        except Exception:
            details = f"Error while trying to get status of '{request.flow_name}'."
            logger.error(details)
            result = GetIsFlowRunningResultFailure()
            return result
        return GetIsFlowRunningResultSuccess(is_running=is_running)

    def on_list_nodes_in_flow_request(self, request: ListNodesInFlowRequest) -> ResultPayload:
        flow_name = request.flow_name
        if flow_name is None:
            # First check if we have a current flow
            if not GriptapeNodes.ContextManager().has_current_flow():
                details = "Attempted to list Nodes in a Flow in the Current Context. Failed because the Current Context was empty."
                logger.error(details)
                result = ListNodesInFlowResultFailure()
                return result
            # Get the current flow from context
            flow_name = GriptapeNodes.ContextManager().get_current_flow_name()

        # Does this Flow even exist?
        obj_mgr = GriptapeNodes.ObjectManager()
        flow = obj_mgr.attempt_get_object_by_name_as_type(flow_name, ControlFlow)
        if flow is None:
            details = (
                f"Attempted to list Nodes in Flow '{flow_name}'. Failed because no Flow with that name could be found."
            )
            logger.error(details)
            result = ListNodesInFlowResultFailure()
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
                result = ListFlowsInFlowResultFailure()
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
        if source_node_name is None:
            # First check if we have a current node
            if not GriptapeNodes.ContextManager().has_current_node():
                details = "Attempted to create a Connection with a source node from the Current Context. Failed because the Current Context was empty."
                logger.error(details)
                return CreateConnectionResultFailure()

            # Get the current node from context
            source_node_name = GriptapeNodes.ContextManager().get_current_node_name()

        try:
            source_node = GriptapeNodes.NodeManager().get_node_by_name(source_node_name)
        except ValueError as err:
            details = f'Connection failed: "{source_node_name}" does not exist. Error: {err}.'
            logger.error(details)

            return CreateConnectionResultFailure()

        target_node_name = request.target_node_name
        if target_node_name is None:
            # First check if we have a current node
            if not GriptapeNodes.ContextManager().has_current_node():
                details = "Attempted to create a Connection with the target node from the Current Context. Failed because the Current Context was empty."
                logger.error(details)
                return CreateConnectionResultFailure()

            # Get the current node from context
            target_node_name = GriptapeNodes.ContextManager().get_current_node_name()

        try:
            target_node = GriptapeNodes.NodeManager().get_node_by_name(target_node_name)
        except ValueError as err:
            details = f'Connection failed: "{target_node_name}" does not exist. Error: {err}.'
            logger.error(details)
            return CreateConnectionResultFailure()

        # The two nodes exist.
        # Get the parent flows.
        source_flow_name = None
        source_flow = None
        try:
            source_flow_name = GriptapeNodes.NodeManager().get_node_parent_flow_by_name(source_node_name)
            source_flow = self.get_flow_by_name(flow_name=source_flow_name)
        except KeyError as err:
            details = f'Connection "{source_node_name}.{request.source_parameter_name}" to "{target_node_name}.{request.target_parameter_name}" failed: {err}.'
            logger.error(details)
            return CreateConnectionResultFailure()

        target_flow_name = None
        try:
            target_flow_name = GriptapeNodes.NodeManager().get_node_parent_flow_by_name(target_node_name)
            self.get_flow_by_name(flow_name=target_flow_name)
        except KeyError as err:
            details = f'Connection "{source_node_name}.{request.source_parameter_name}" to "{target_node_name}.{request.target_parameter_name}" failed: {err}.'
            logger.error(details)
            return CreateConnectionResultFailure()

        # CURRENT RESTRICTION: Now vet the parents are in the same Flow (yes this sucks)
        if target_flow_name != source_flow_name:
            details = f'Connection "{source_node_name}.{request.source_parameter_name}" to "{target_node_name}.{request.target_parameter_name}" failed: Different flows.'
            logger.error(details)
            return CreateConnectionResultFailure()

        # Now validate the parameters.
        source_param = source_node.get_parameter_by_name(request.source_parameter_name)
        if source_param is None:
            details = f'Connection failed: "{source_node_name}.{request.source_parameter_name}" not found'
            logger.error(details)
            return CreateConnectionResultFailure()

        target_param = target_node.get_parameter_by_name(request.target_parameter_name)
        if target_param is None:
            # TODO: https://github.com/griptape-ai/griptape-nodes/issues/860
            details = f'Connection failed: "{target_node_name}.{request.target_parameter_name}" not found'
            logger.error(details)
            return CreateConnectionResultFailure()
        # Validate parameter modes accept this type of connection.
        source_modes_allowed = source_param.allowed_modes
        if ParameterMode.OUTPUT not in source_modes_allowed:
            details = (
                f'Connection failed: "{source_node_name}.{request.source_parameter_name}" is not an allowed OUTPUT'
            )
            logger.error(details)
            return CreateConnectionResultFailure()

        target_modes_allowed = target_param.allowed_modes
        if ParameterMode.INPUT not in target_modes_allowed:
            details = f'Connection failed: "{target_node_name}.{request.target_parameter_name}" is not an allowed INPUT'
            logger.error(details)
            return CreateConnectionResultFailure()

        # Validate that the data type from the source is allowed by the target.
        if not target_param.is_incoming_type_allowed(source_param.output_type):
            details = f'Connection failed on type mismatch "{source_node_name}.{request.source_parameter_name}" type({source_param.output_type}) to "{target_node_name}.{request.target_parameter_name}" types({target_param.input_types}) '
            logger.error(details)
            return CreateConnectionResultFailure()

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
            return CreateConnectionResultFailure()

        if not target_node.allow_incoming_connection(
            source_node=source_node,
            source_parameter=source_param,
            target_parameter=target_param,
        ):
            details = (
                f'Connection failed : "{target_node_name}.{request.target_parameter_name}" rejected the connection '
            )
            logger.error(details)
            return CreateConnectionResultFailure()

        # Based on user feedback, if a connection already exists in a scenario where only ONE such connection can exist
        # (e.g., connecting to a data input that already has a connection, or from a control output that is already wired up),
        # delete the old connection and replace it with this one.
        old_source_node_name = None
        old_source_param_name = None
        old_target_node_name = None
        old_target_param_name = None

        # Some scenarios restrict when we can have more than one connection. See if we're in such a scenario and replace the
        # existing connection instead of adding a new one.
        connection_mgr = source_flow.connections
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
                return CreateConnectionResultFailure()

            details = f"Deleted the previous connection from '{old_source_node_name}.{old_source_param_name}' to '{old_target_node_name}.{old_target_param_name}' to make room for the new connection."
            logger.debug(details)
        try:
            # Actually create the Connection.
            source_flow.add_connection(
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
            return CreateConnectionResultFailure()

        # Let the source make any internal handling decisions now that the Connection has been made.
        modified_source_parameters = set()
        source_node.after_outgoing_connection(
            source_parameter=source_param,
            target_node=target_node,
            target_parameter=target_param,
            modified_parameters_set=modified_source_parameters,
        )

        # And target.
        modified_target_parameters = set()
        target_node.after_incoming_connection(
            source_node=source_node,
            source_parameter=source_param,
            target_parameter=target_param,
            modified_parameters_set=modified_target_parameters,
        )

        if modified_source_parameters:
            for modified_parameter_name in modified_source_parameters:
                # TODO: https://github.com/griptape-ai/griptape-nodes/issues/865
                modified_parameter = source_node.get_parameter_by_name(modified_parameter_name)
                if modified_parameter is not None:
                    modified_request = AlterParameterEvent.create(
                        node_name=source_node.name, parameter=modified_parameter
                    )
                    EventBus.publish_event(ExecutionGriptapeNodeEvent(ExecutionEvent(payload=modified_request)))
        if modified_target_parameters:
            for modified_parameter_name in modified_target_parameters:
                # TODO: https://github.com/griptape-ai/griptape-nodes/issues/865
                modified_parameter = target_node.get_parameter_by_name(modified_parameter_name)
                if modified_parameter is not None:
                    modified_request = AlterParameterEvent.create(
                        node_name=target_node.name, parameter=modified_parameter
                    )
                    EventBus.publish_event(ExecutionGriptapeNodeEvent(ExecutionEvent(payload=modified_request)))

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

        if source_node_name is None:
            # First check if we have a current node
            if not GriptapeNodes.ContextManager().has_current_node():
                details = "Attempted to delete a Connection with a source node from the Current Context. Failed because the Current Context was empty."
                logger.error(details)
                return DeleteConnectionResultFailure()

            # Get the current node from context
            source_node_name = GriptapeNodes.ContextManager().get_current_node_name()

        try:
            source_node = GriptapeNodes.NodeManager().get_node_by_name(source_node_name)
        except ValueError as err:
            details = f'Connection not deleted "{source_node_name}.{request.source_parameter_name}" to "{target_node_name}.{request.target_parameter_name}". Error: {err}'
            logger.error(details)

            return DeleteConnectionResultFailure()

        target_node_name = request.target_node_name
        if target_node_name is None:
            # First check if we have a current node
            if not GriptapeNodes.ContextManager().has_current_node():
                details = "Attempted to delete a Connection with a target node from the Current Context. Failed because the Current Context was empty."
                logger.error(details)
                return DeleteConnectionResultFailure()

            # Get the current node from context
            target_node_name = GriptapeNodes.ContextManager().get_current_node_name()
        try:
            target_node = GriptapeNodes.NodeManager().get_node_by_name(target_node_name)
        except ValueError as err:
            details = f'Connection not deleted "{source_node_name}.{request.source_parameter_name}" to "{target_node_name}.{request.target_parameter_name}". Error: {err}'
            logger.error(details)

            return DeleteConnectionResultFailure()

        # The two nodes exist.
        # Get the parent flows.
        source_flow_name = None
        source_flow = None
        try:
            source_flow_name = GriptapeNodes.NodeManager().get_node_parent_flow_by_name(source_node_name)
            source_flow = self.get_flow_by_name(flow_name=source_flow_name)
        except KeyError as err:
            details = f'Connection not deleted "{source_node_name}.{request.source_parameter_name}" to "{target_node_name}.{request.target_parameter_name}". Error: {err}'
            logger.error(details)

            return DeleteConnectionResultFailure()

        target_flow_name = None
        try:
            target_flow_name = GriptapeNodes.NodeManager().get_node_parent_flow_by_name(target_node_name)
            self.get_flow_by_name(flow_name=target_flow_name)
        except KeyError as err:
            details = f'Connection not deleted "{source_node_name}.{request.source_parameter_name}" to "{target_node_name}.{request.target_parameter_name}". Error: {err}'
            logger.error(details)

            return DeleteConnectionResultFailure()

        # CURRENT RESTRICTION: Now vet the parents are in the same Flow (yes this sucks)
        if target_flow_name != source_flow_name:
            details = f'Connection not deleted "{source_node_name}.{request.source_parameter_name}" to "{target_node_name}.{request.target_parameter_name}". They are in different Flows (TEMPORARY RESTRICTION).'
            logger.error(details)

            return DeleteConnectionResultFailure()

        # Now validate the parameters.
        source_param = source_node.get_parameter_by_name(request.source_parameter_name)
        if source_param is None:
            details = f'Connection not deleted "{source_node_name}.{request.source_parameter_name}" Not found.'
            logger.error(details)

            return DeleteConnectionResultFailure()

        target_param = target_node.get_parameter_by_name(request.target_parameter_name)
        if target_param is None:
            details = f'Connection not deleted "{target_node_name}.{request.target_parameter_name}" Not found.'
            logger.error(details)

            return DeleteConnectionResultFailure()

        # Vet that a Connection actually exists between them already.
        if not source_flow.has_connection(
            source_node=source_node,
            source_parameter=source_param,
            target_node=target_node,
            target_parameter=target_param,
        ):
            details = f'Connection does not exist: "{source_node_name}.{request.source_parameter_name}" to "{target_node_name}.{request.target_parameter_name}"'
            logger.error(details)

            return DeleteConnectionResultFailure()

        # Remove the connection.
        if not source_flow.remove_connection(
            source_node=source_node,
            source_parameter=source_param,
            target_node=target_node,
            target_parameter=target_param,
        ):
            details = f'Connection not deleted "{source_node_name}.{request.source_parameter_name}" to "{target_node_name}.{request.target_parameter_name}". Unknown failure.'
            logger.error(details)

            return DeleteConnectionResultFailure()

        # After the connection has been removed, if it doesn't have PROPERTY as a type, wipe the set parameter value and unresolve future nodes
        if ParameterMode.PROPERTY not in target_param.allowed_modes:
            try:
                # Only try to remove a value where one exists, otherwise it will generate errant warnings.
                if target_param.name in target_node.parameter_values:
                    target_node.remove_parameter_value(target_param.name)
                # It removed it accurately
                # Unresolve future nodes that depended on that value
                source_flow.connections.unresolve_future_nodes(target_node)
                target_node.make_node_unresolved(
                    current_states_to_trigger_change_event=set(
                        {NodeResolutionState.RESOLVED, NodeResolutionState.RESOLVING}
                    )
                )
            except KeyError as e:
                logger.warning(e)
        modified_source_parameters = set()
        # Let the source make any internal handling decisions now that the Connection has been REMOVED.
        source_node.after_outgoing_connection_removed(
            source_parameter=source_param,
            target_node=target_node,
            target_parameter=target_param,
            modified_parameters_set=modified_source_parameters,
        )

        # And target.
        modified_target_parameters = set()
        target_node.after_incoming_connection_removed(
            source_node=source_node,
            source_parameter=source_param,
            target_parameter=target_param,
            modified_parameters_set=modified_target_parameters,
        )
        if modified_source_parameters:
            for modified_parameter_name in modified_source_parameters:
                # TODO: https://github.com/griptape-ai/griptape-nodes/issues/865
                modified_parameter = source_node.get_parameter_by_name(modified_parameter_name)
                if modified_parameter is not None:
                    modified_request = AlterParameterEvent.create(
                        node_name=source_node_name, parameter=modified_parameter
                    )
                    EventBus.publish_event(ExecutionGriptapeNodeEvent(ExecutionEvent(payload=modified_request)))
        if modified_target_parameters:
            for modified_parameter_name in modified_target_parameters:
                # TODO: https://github.com/griptape-ai/griptape-nodes/issues/865
                modified_parameter = target_node.get_parameter_by_name(modified_parameter_name)
                if modified_parameter is not None:
                    modified_request = AlterParameterEvent.create(
                        node_name=target_node_name, parameter=modified_parameter
                    )
                    EventBus.publish_event(ExecutionGriptapeNodeEvent(ExecutionEvent(payload=modified_request)))

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

            return StartFlowResultFailure(validation_exceptions=[])
        # get the flow by ID
        try:
            flow = self.get_flow_by_name(flow_name)
        except KeyError as err:
            details = f"Cannot start flow. Error: {err}"
            logger.error(details)
            return StartFlowResultFailure(validation_exceptions=[err])
        # Check to see if the flow is already running.
        if flow.check_for_existing_running_flow():
            details = "Cannot start flow. Flow is already running."
            logger.error(details)
            return StartFlowResultFailure(validation_exceptions=[])
        # A node has been provided to either start or to run up to.
        if request.flow_node_name:
            flow_node_name = request.flow_node_name
            flow_node = GriptapeNodes.ObjectManager().attempt_get_object_by_name_as_type(flow_node_name, BaseNode)
            if not flow_node:
                details = f"Provided node with name {flow_node_name} does not exist"
                logger.error(details)
                return StartFlowResultFailure(validation_exceptions=[])
            # lets get the first control node in the flow!
            start_node = flow.get_start_node_from_node(flow_node)
            # if the start is not the node provided, set a breakpoint at the stop (we're running up until there)
            if not start_node:
                details = f"Start node for node with name {flow_node_name} does not exist"
                logger.error(details)
                return StartFlowResultFailure(validation_exceptions=[])
            if start_node != flow_node:
                flow_node.stop_flow = True
        else:
            # we wont hit this if we dont have a request id, our requests always have nodes
            # If there is a request, reinitialize the queue
            flow.get_start_node_queue()  # initialize the start flow queue!
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
                return StartFlowResultFailure(validation_exceptions=result.exceptions)
        except Exception as e:
            details = f"Couldn't start flow with name {flow_name}. Flow Validation Failed: {e}"
            logger.error(details)
            return StartFlowResultFailure(validation_exceptions=[e])
        # By now, it has been validated with no exceptions.
        try:
            flow.start_flow(start_node, debug_mode)
        except Exception as e:
            details = f"Failed to kick off flow with name {flow_name}. Exception occurred: {e} "
            logger.error(details)
            return StartFlowResultFailure(validation_exceptions=[e])

        details = f"Successfully kicked off flow with name {flow_name}"
        logger.debug(details)

        return StartFlowResultSuccess()

    def on_get_flow_state_request(self, event: GetFlowStateRequest) -> ResultPayload:
        flow_name = event.flow_name
        if not flow_name:
            details = "Could not get flow state. No flow name was provided."
            logger.error(details)
            return GetFlowStateResultFailure()
        try:
            flow = self.get_flow_by_name(flow_name)
        except KeyError as err:
            details = f"Could not get flow state. Error: {err}"
            logger.error(details)
            return GetFlowStateResultFailure()
        try:
            control_node, resolving_node = flow.flow_state()
        except Exception as e:
            details = f"Failed to get flow state of flow with name {flow_name}. Exception occurred: {e} "
            logger.exception(details)
            return GetFlowStateResultFailure()
        details = f"Successfully got flow state for flow with name {flow_name}."
        logger.debug(details)
        return GetFlowStateResultSuccess(control_node=control_node, resolving_node=resolving_node)

    def on_cancel_flow_request(self, request: CancelFlowRequest) -> ResultPayload:
        flow_name = request.flow_name
        if not flow_name:
            details = "Could not cancel flow execution. No flow name was provided."
            logger.error(details)

            return CancelFlowResultFailure()
        try:
            flow = self.get_flow_by_name(flow_name)
        except KeyError as err:
            details = f"Could not cancel flow execution. Error: {err}"
            logger.error(details)

            return CancelFlowResultFailure()
        try:
            flow.cancel_flow_run()
        except Exception as e:
            details = f"Could not cancel flow execution. Exception: {e}"
            logger.error(details)

            return CancelFlowResultFailure()
        details = f"Successfully cancelled flow execution with name {flow_name}"
        logger.debug(details)

        return CancelFlowResultSuccess()

    def on_single_node_step_request(self, request: SingleNodeStepRequest) -> ResultPayload:
        flow_name = request.flow_name
        if not flow_name:
            details = "Could not advance to the next step of a running workflow. No flow name was provided."
            logger.error(details)

            return SingleNodeStepResultFailure(validation_exceptions=[])
        try:
            flow = self.get_flow_by_name(flow_name)
        except KeyError as err:
            details = f"Could not advance to the next step of a running workflow. No flow with name {flow_name} exists. Error: {err}"
            logger.error(details)

            return SingleNodeStepResultFailure(validation_exceptions=[err])
        try:
            flow.single_node_step()
        except Exception as e:
            details = f"Could not advance to the next step of a running workflow. Exception: {e}"
            logger.error(details)
            return SingleNodeStepResultFailure(validation_exceptions=[])

        # All completed happily
        details = f"Successfully advanced to the next step of a running workflow with name {flow_name}"
        logger.debug(details)

        return SingleNodeStepResultSuccess()

    def on_single_execution_step_request(self, request: SingleExecutionStepRequest) -> ResultPayload:
        flow_name = request.flow_name
        if not flow_name:
            details = "Could not advance to the next step of a running workflow. No flow name was provided."
            logger.error(details)

            return SingleExecutionStepResultFailure()
        try:
            flow = self.get_flow_by_name(flow_name)
        except KeyError as err:
            details = f"Could not advance to the next step of a running workflow. Error: {err}."
            logger.error(details)

            return SingleExecutionStepResultFailure()
        change_debug_mode = request.request_id is not None
        try:
            flow.single_execution_step(change_debug_mode)
        except Exception as e:
            # We REALLY don't want to fail here, else we'll take the whole engine down
            try:
                if flow.check_for_existing_running_flow():
                    flow.cancel_flow_run()
            except Exception as e_inner:
                details = f"Could not cancel flow execution. Exception: {e_inner}"
                logger.error(details)

            details = f"Could not advance to the next step of a running workflow. Exception: {e}"
            logger.error(details)
            return SingleNodeStepResultFailure(validation_exceptions=[e])
        details = f"Successfully advanced to the next step of a running workflow with name {flow_name}"
        logger.debug(details)

        return SingleExecutionStepResultSuccess()

    def on_continue_execution_step_request(self, request: ContinueExecutionStepRequest) -> ResultPayload:
        flow_name = request.flow_name
        if not flow_name:
            details = "Failed to continue execution step because no flow name was provided"
            logger.error(details)

            return ContinueExecutionStepResultFailure()
        try:
            flow = self.get_flow_by_name(flow_name)
        except KeyError as err:
            details = f"Failed to continue execution step. Error: {err}"
            logger.error(details)

            return ContinueExecutionStepResultFailure()
        try:
            flow.continue_executing()
        except Exception as e:
            details = f"Failed to continue execution step. An exception occurred: {e}."
            logger.error(details)
            return ContinueExecutionStepResultFailure()
        details = f"Successfully continued flow with name {flow_name}"
        logger.debug(details)
        return ContinueExecutionStepResultSuccess()

    def on_unresolve_flow_request(self, request: UnresolveFlowRequest) -> ResultPayload:
        flow_name = request.flow_name
        if not flow_name:
            details = "Failed to unresolve flow because no flow name was provided"
            logger.error(details)
            return UnresolveFlowResultFailure()
        try:
            flow = self.get_flow_by_name(flow_name)
        except KeyError as err:
            details = f"Failed to unresolve flow. Error: {err}"
            logger.error(details)
            return UnresolveFlowResultFailure()
        try:
            flow.unresolve_whole_flow()
        except Exception as e:
            details = f"Failed to unresolve flow. An exception occurred: {e}."
            logger.error(details)
            return UnresolveFlowResultFailure()
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
            return ValidateFlowDependenciesResultFailure()
        if request.flow_node_name:
            flow_node_name = request.flow_node_name
            flow_node = GriptapeNodes.ObjectManager().attempt_get_object_by_name_as_type(flow_node_name, BaseNode)
            if not flow_node:
                details = f"Provided node with name {flow_node_name} does not exist"
                logger.error(details)
                return ValidateFlowDependenciesResultFailure()
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
            return ListFlowsInCurrentContextResultFailure()

        parent_flow_name = GriptapeNodes.ContextManager().get_current_flow_name()

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
        if flow_name is None:
            if GriptapeNodes.ContextManager().has_current_flow():
                flow_name = GriptapeNodes.ContextManager().get_current_flow_name()
            else:
                details = "Attempted to serialize a Flow to commands from the Current Context. Failed because the Current Context was empty."
                logger.error(details)
                return SerializeFlowToCommandsResultFailure()

        # Does this flow exist?
        flow = GriptapeNodes.ObjectManager().attempt_get_object_by_name_as_type(flow_name, ControlFlow)
        if flow is None:
            details = (
                f"Attempted to serialize Flow '{flow_name}' to commands, but no Flow with that name could be found."
            )
            logger.error(details)
            return SerializeFlowToCommandsResultFailure()

        # Track all node libraries that were in use by these Nodes
        node_libraries_in_use = set()

        # Track all parameter values that were in use by these Nodes
        unique_parameter_values = []
        # And track how values map into that list.
        value_hash_to_unique_value_index = {}

        with GriptapeNodes.ContextManager().flow(flow_name):
            # The base flow creation, if desired.
            if request.include_create_flow_command:
                create_flow_request = CreateFlowRequest(parent_flow_name=None)
            else:
                create_flow_request = None

            serialized_node_commands = []
            set_parameter_value_commands_per_node = []  # We're actually a list of lists.

            # Now each of the child nodes in the flow.
            node_name_to_index = {}
            nodes_in_flow_request = ListNodesInFlowRequest()
            nodes_in_flow_result = GriptapeNodes().handle_request(nodes_in_flow_request)
            if not isinstance(nodes_in_flow_result, ListNodesInFlowResultSuccess):
                details = (
                    f"Attempted to serialize Flow '{flow_name}'. Failed while attempting to list Nodes in the Flow."
                )
                logger.error(details)
                return SerializeFlowToCommandsResultFailure()

            # Serialize each node
            for node_index, node_name in enumerate(nodes_in_flow_result.node_names):
                node_name_to_index[node_name] = node_index

                with GriptapeNodes.ContextManager().node(node_name):
                    # Note: the parameter value stuff is pass-by-reference, and we expect the values to be modified in place.
                    # This might be dangerous if done over the wire.
                    serialize_node_request = SerializeNodeToCommandsRequest(
                        unique_parameter_values_list=unique_parameter_values,  # Unique values
                        value_hash_to_unique_value_index=value_hash_to_unique_value_index,  # Mapping values to indices
                    )
                    serialize_node_result = GriptapeNodes().handle_request(serialize_node_request)
                    if not isinstance(serialize_node_result, SerializeNodeToCommandsResultSuccess):
                        details = f"Attempted to serialize Flow '{flow_name}'. Failed while attempting to serialize Node '{node_name}' within the Flow."
                        logger.error(details)
                        return SerializeFlowToCommandsResultFailure()

                    serialized_node = serialize_node_result.serialized_node_commands
                    serialized_node_commands.append(serialized_node)
                    node_libraries_in_use.add(serialized_node.node_library_details)
                    # Get the list of set value commands for THIS node.
                    set_value_commands_list = serialize_node_result.set_parameter_value_commands
                    set_parameter_value_commands_per_node.append(set_value_commands_list)

            # We'll have to do a patch-up of all the connections, since we can't predict all of the node names being accurate
            # when we're restored.
            # Create all of the connections
            create_connection_commands = []
            for connection in flow.connections.connections.values():
                source_node_index = node_name_to_index[connection.source_node.name]
                target_node_index = node_name_to_index[connection.target_node.name]
                create_connection_command = SerializedFlowCommands.IndexedConnectionSerialization(
                    source_node_index=source_node_index,
                    source_parameter_name=connection.source_parameter.name,
                    target_node_index=target_node_index,
                    target_parameter_name=connection.target_parameter.name,
                )
                create_connection_commands.append(create_connection_command)

            # Now sub-flows.
            parent_flow_name = GriptapeNodes.ContextManager().get_current_flow_name()
            flows_in_flow_request = ListFlowsInFlowRequest(parent_flow_name=parent_flow_name)
            flows_in_flow_result = GriptapeNodes().handle_request(flows_in_flow_request)
            if not isinstance(flows_in_flow_result, ListFlowsInFlowResultSuccess):
                details = f"Attempted to serialize Flow '{flow_name}'. Failed while attempting to list child Flows in the Flow."
                logger.error(details)
                return SerializeFlowToCommandsResultFailure()

            sub_flow_commands = []
            for child_flow in flows_in_flow_result.flow_names:
                with GriptapeNodes.ContextManager().flow(flow_name=child_flow):
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

        serialized_flow = SerializedFlowCommands(
            create_flow_command=create_flow_request,
            serialized_node_commands=serialized_node_commands,
            serialized_connections=create_connection_commands,
            unique_parameter_values=unique_parameter_values,
            set_parameter_value_commands=set_parameter_value_commands_per_node,
            sub_flows_commands=sub_flow_commands,
            node_libraries_used=node_libraries_in_use,
        )
        details = f"Successfully serialized Flow '{flow_name}' into commands."
        result = SerializeFlowToCommandsResultSuccess(serialized_flow_commands=serialized_flow)
        return result

    def on_deserialize_flow_from_commands(self, request: DeserializeFlowFromCommandsRequest) -> ResultPayload:  # noqa: C901, PLR0911, PLR0912, PLR0915 (I am big and complicated and have a lot of negative edge-cases)
        # Do we want to create a NEW Flow to deserialize into, or use the one in the Current Context?
        if request.serialized_flow_commands.create_flow_command is None:
            if GriptapeNodes.ContextManager().has_current_flow():
                flow_name = GriptapeNodes.ContextManager().get_current_flow_name()
            else:
                details = "Attempted to deserialize a set of Flow Creation commands into the Current Context. Failed because the Current Context was empty."
                logger.error(details)
                return DeserializeFlowFromCommandsResultFailure()
        else:
            # Issue the creation command first.
            create_flow_request = request.serialized_flow_commands.create_flow_command
            create_flow_result = GriptapeNodes().handle_request(create_flow_request)
            if not isinstance(create_flow_result, CreateFlowResultSuccess):
                details = f"Attempted to deserialize a serialized set of Flow Creation commands. Failed to create flow '{create_flow_request.flow_name}'."
                logger.error(details)
                return DeserializeFlowFromCommandsResultFailure()

            # Adopt the newly-created flow as our current context.
            flow_name = create_flow_result.flow_name
            GriptapeNodes.ContextManager().push_flow(flow_name=flow_name)

        # Deserializing a flow goes in a specific order.

        # Create the nodes.
        # Preserve the indices because we will need to tie these back together with the Connections later.
        deserialized_node_results = []
        for serialized_node in request.serialized_flow_commands.serialized_node_commands:
            deserialize_node_request = DeserializeNodeFromCommandsRequest(serialized_node_commands=serialized_node)
            deserialized_node_result = GriptapeNodes.handle_request(deserialize_node_request)
            if deserialized_node_result.failed():
                details = (
                    f"Attempted to deserialize a Flow '{flow_name}'. Failed while deserializing a node within the flow."
                )
                logger.error(details)
                return DeserializeFlowFromCommandsResultFailure()
            deserialized_node_results.append(deserialized_node_result)

        # Now apply the connections.
        # We didn't know the exact name that would be used for the nodes, but we knew the indices.
        # Tie the indices back to the node names.
        for indexed_connection in request.serialized_flow_commands.serialized_connections:
            source_node_result = deserialized_node_results[indexed_connection.source_node_index]
            source_node_name = source_node_result.node_name
            target_node_result = deserialized_node_results[indexed_connection.target_node_index]
            target_node_name = target_node_result.node_name

            create_connection_request = CreateConnectionRequest(
                source_node_name=source_node_name,
                source_parameter_name=indexed_connection.source_parameter_name,
                target_node_name=target_node_name,
                target_parameter_name=indexed_connection.target_parameter_name,
            )
            create_connection_result = GriptapeNodes.handle_request(create_connection_request)
            if create_connection_result.failed():
                details = f"Attempted to deserialize a Flow '{flow_name}'. Failed while deserializing a Connection from '{source_node_name}.{indexed_connection.source_parameter_name}' to '{target_node_name}.{indexed_connection.target_parameter_name}' within the flow."
                logger.error(details)
                return DeserializeFlowFromCommandsResultFailure()

        # Now assign the values.
        # This is the same issue that we handle for Connections:
        # we don't know the exact node name that would be used, but know the indices.
        # Similarly, we need to wire up the value indices back to the unique values.
        # We maintain one list of set value commands per node in the Flow.
        for node_index, set_value_command_list in enumerate(
            request.serialized_flow_commands.set_parameter_value_commands
        ):
            node_name = deserialized_node_results[node_index].node_name
            # Make this node the current context.
            with GriptapeNodes.ContextManager().node(node_name=node_name):
                # Iterate through each set value command in the list for this node.
                for indexed_set_value_command in set_value_command_list:
                    parameter_name = indexed_set_value_command.set_parameter_value_command.parameter_name
                    unique_value_index = indexed_set_value_command.unique_value_index
                    try:
                        value = request.serialized_flow_commands.unique_parameter_values[unique_value_index]
                    except IndexError as err:
                        details = f"Attempted to deserialize a Flow '{flow_name}'. Failed while deserializing a value assignment for node '{node_name}.{parameter_name}': {err}"
                        logger.error(details)
                        return DeserializeFlowFromCommandsResultFailure()

                    # Call the SetParameterValueRequest, subbing in the value from our unique value list.
                    indexed_set_value_command.set_parameter_value_command.value = value
                    set_parameter_value_result = GriptapeNodes.handle_request(
                        indexed_set_value_command.set_parameter_value_command
                    )
                    if set_parameter_value_result.failed():
                        details = f"Attempted to deserialize a Flow '{flow_name}'. Failed while deserializing a value assignment for node '{node_name}.{parameter_name}'."
                        logger.error(details)
                        return DeserializeFlowFromCommandsResultFailure()

        # Now the child flows.
        for sub_flow_command in request.serialized_flow_commands.sub_flows_commands:
            sub_flow_request = DeserializeFlowFromCommandsRequest(serialized_flow_commands=sub_flow_command)
            sub_flow_result = GriptapeNodes.handle_request(sub_flow_request)
            if sub_flow_result.failed():
                details = f"Attempted to deserialize a Flow '{flow_name}'. Failed while deserializing a sub-flow within the Flow."
                logger.error(details)
                return DeserializeFlowFromCommandsResultFailure()

        details = f"Successfully deserialized Flow '{flow_name}'."
        logger.debug(details)
        return DeserializeFlowFromCommandsResultSuccess(flow_name=flow_name)
