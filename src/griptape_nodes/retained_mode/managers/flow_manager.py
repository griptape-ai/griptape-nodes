from __future__ import annotations

import logging
from enum import StrEnum
from queue import Queue
from typing import TYPE_CHECKING, Any, NamedTuple, cast
from uuid import uuid4

from griptape_nodes.common.node_executor import NodeExecutor
from griptape_nodes.exe_types.connections import Connections
from griptape_nodes.exe_types.core_types import (
    Parameter,
    ParameterContainer,
    ParameterMode,
    ParameterType,
    ParameterTypeBuiltin,
)
from griptape_nodes.exe_types.flow import ControlFlow
from griptape_nodes.exe_types.node_types import (
    LOCAL_EXECUTION,
    BaseNode,
    ErrorProxyNode,
    NodeDependencies,
    NodeGroupProxyNode,
    NodeResolutionState,
    StartLoopNode,
    StartNode,
)
from griptape_nodes.machines.control_flow import CompleteState, ControlFlowMachine
from griptape_nodes.machines.dag_builder import DagBuilder
from griptape_nodes.machines.parallel_resolution import ParallelResolutionMachine
from griptape_nodes.machines.sequential_resolution import SequentialResolutionMachine
from griptape_nodes.node_library.library_registry import LibraryNameAndVersion, LibraryRegistry
from griptape_nodes.node_library.workflow_registry import LibraryNameAndNodeType
from griptape_nodes.retained_mode.events.base_events import (
    ExecutionEvent,
    ExecutionGriptapeNodeEvent,
    FlushParameterChangesRequest,
    FlushParameterChangesResultSuccess,
    ResultDetails,
)
from griptape_nodes.retained_mode.events.connection_events import (
    CreateConnectionRequest,
    CreateConnectionResultFailure,
    CreateConnectionResultSuccess,
    DeleteConnectionRequest,
    DeleteConnectionResultFailure,
    DeleteConnectionResultSuccess,
    IncomingConnection,
    ListConnectionsForNodeRequest,
    ListConnectionsForNodeResultSuccess,
    OutgoingConnection,
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
    InvolvedNodesEvent,
    SingleExecutionStepRequest,
    SingleExecutionStepResultFailure,
    SingleExecutionStepResultSuccess,
    SingleNodeStepRequest,
    SingleNodeStepResultFailure,
    SingleNodeStepResultSuccess,
    StartFlowFromNodeRequest,
    StartFlowFromNodeResultFailure,
    StartFlowFromNodeResultSuccess,
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
    OriginalNodeParameter,
    PackageNodesAsSerializedFlowRequest,
    PackageNodesAsSerializedFlowResultFailure,
    PackageNodesAsSerializedFlowResultSuccess,
    SanitizedParameterName,
    SerializedFlowCommands,
    SerializeFlowToCommandsRequest,
    SerializeFlowToCommandsResultFailure,
    SerializeFlowToCommandsResultSuccess,
    SetFlowMetadataRequest,
    SetFlowMetadataResultFailure,
    SetFlowMetadataResultSuccess,
)
from griptape_nodes.retained_mode.events.node_events import (
    CreateNodeRequest,
    DeleteNodeRequest,
    DeleteNodeResultFailure,
    DeserializeNodeFromCommandsRequest,
    SerializedNodeCommands,
    SerializedParameterValueTracker,
    SerializeNodeToCommandsRequest,
    SerializeNodeToCommandsResultSuccess,
)
from griptape_nodes.retained_mode.events.parameter_events import (
    AddParameterToNodeRequest,
    AlterParameterDetailsRequest,
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
    from griptape_nodes.retained_mode.managers.workflow_manager import WorkflowShapeNodes

logger = logging.getLogger("griptape_nodes")


class DagExecutionType(StrEnum):
    START_NODE = "start_node"
    CONTROL_NODE = "control_node"
    DATA_NODE = "data_node"


class QueueItem(NamedTuple):
    """Represents an item in the flow execution queue."""

    node: BaseNode
    dag_execution_type: DagExecutionType


class ConnectionAnalysis(NamedTuple):
    """Analysis of connections separated by type (data vs control) when packaging nodes."""

    incoming_data_connections: list[IncomingConnection]
    incoming_control_connections: list[IncomingConnection]
    outgoing_data_connections: list[OutgoingConnection]
    outgoing_control_connections: list[OutgoingConnection]


class PackageNodeInfo(NamedTuple):
    """Information about the node being packaged."""

    package_node: BaseNode
    package_flow_name: str


class StartNodeIncomingDataResult(NamedTuple):
    """Result of processing incoming data connections for a start node."""

    parameter_commands: list[AddParameterToNodeRequest]
    data_connections: list[SerializedFlowCommands.IndirectConnectionSerialization]
    input_shape_data: WorkflowShapeNodes
    parameter_value_commands: list[SerializedNodeCommands.IndirectSetParameterValueCommand]


class PackagingStartNodeResult(NamedTuple):
    """Result of creating start node commands and connections for flow packaging."""

    start_node_commands: SerializedNodeCommands
    start_to_package_connections: list[SerializedFlowCommands.IndirectConnectionSerialization]
    input_shape_data: WorkflowShapeNodes
    start_node_parameter_value_commands: list[SerializedNodeCommands.IndirectSetParameterValueCommand]


class PackagingEndNodeResult(NamedTuple):
    """Result of creating end node commands and data connections for flow packaging."""

    end_node_commands: SerializedNodeCommands
    package_to_end_connections: list[SerializedFlowCommands.IndirectConnectionSerialization]
    output_shape_data: WorkflowShapeNodes


class MultiNodeEndNodeResult(NamedTuple):
    """Result of creating end node commands and parameter mappings for multi-node packaging."""

    packaging_result: PackagingEndNodeResult
    parameter_name_mappings: dict[SanitizedParameterName, OriginalNodeParameter]
    alter_parameter_commands: list[AlterParameterDetailsRequest]


class FlowManager:
    _name_to_parent_name: dict[str, str | None]
    _flow_to_referenced_workflow_name: dict[ControlFlow, str]
    _connections: Connections

    # Global execution state (moved from individual ControlFlows)
    _global_flow_queue: Queue[QueueItem]
    _global_control_flow_machine: ControlFlowMachine | None
    _global_single_node_resolution: bool
    _global_dag_builder: DagBuilder
    _node_executor: NodeExecutor

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
        event_manager.assign_manager_to_request_type(StartFlowFromNodeRequest, self.on_start_flow_from_node_request)
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
        event_manager.assign_manager_to_request_type(
            PackageNodesAsSerializedFlowRequest, self.on_package_nodes_as_serialized_flow_request
        )
        event_manager.assign_manager_to_request_type(FlushParameterChangesRequest, self.on_flush_request)

        self._name_to_parent_name = {}
        self._flow_to_referenced_workflow_name = {}
        self._connections = Connections()

        # Initialize global execution state
        self._global_flow_queue = Queue[QueueItem]()
        self._global_control_flow_machine = None  # Track the current control flow machine
        self._global_single_node_resolution = False
        self._global_dag_builder = DagBuilder()
        self._node_executor = NodeExecutor()

    @property
    def global_single_node_resolution(self) -> bool:
        return self._global_single_node_resolution

    @property
    def global_flow_queue(self) -> Queue[QueueItem]:
        return self._global_flow_queue

    @property
    def global_dag_builder(self) -> DagBuilder:
        return self._global_dag_builder

    @property
    def node_executor(self) -> NodeExecutor:
        return self._node_executor

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
                return GetTopLevelFlowResultSuccess(
                    flow_name=flow_name, result_details=f"Successfully found top level flow: '{flow_name}'"
                )
        msg = "Attempted to get top level flow, but no such flow exists"
        logger.debug(msg)
        return GetTopLevelFlowResultSuccess(flow_name=None, result_details=msg)

    def on_get_flow_details_request(self, request: GetFlowDetailsRequest) -> ResultPayload:
        flow_name = request.flow_name
        flow = None

        if flow_name is None:
            # We want to get details for whatever is at the top of the Current Context.
            if not GriptapeNodes.ContextManager().has_current_flow():
                details = "Attempted to get Flow details from the Current Context. Failed because the Current Context was empty."
                return GetFlowDetailsResultFailure(result_details=details)
            flow = GriptapeNodes.ContextManager().get_current_flow()
            flow_name = flow.name
        else:
            flow = GriptapeNodes.ObjectManager().attempt_get_object_by_name_as_type(flow_name, ControlFlow)
            if flow is None:
                details = (
                    f"Attempted to get Flow details for '{flow_name}'. Failed because no Flow with that name exists."
                )
                return GetFlowDetailsResultFailure(result_details=details)

        try:
            parent_flow_name = self.get_parent_flow(flow_name)
        except ValueError:
            details = f"Attempted to get Flow details for '{flow_name}'. Failed because Flow does not exist in parent mapping."
            return GetFlowDetailsResultFailure(result_details=details)

        referenced_workflow_name = None
        if self.is_referenced_workflow(flow):
            referenced_workflow_name = self.get_referenced_workflow_name(flow)

        details = f"Successfully retrieved Flow details for '{flow_name}'."
        return GetFlowDetailsResultSuccess(
            referenced_workflow_name=referenced_workflow_name, parent_flow_name=parent_flow_name, result_details=details
        )

    def on_get_flow_metadata_request(self, request: GetFlowMetadataRequest) -> ResultPayload:
        flow_name = request.flow_name
        flow = None
        if flow_name is None:
            # Get from the current context.
            if not GriptapeNodes.ContextManager().has_current_flow():
                details = "Attempted to get metadata for a Flow from the Current Context. Failed because the Current Context is empty."
                return GetFlowMetadataResultFailure(result_details=details)

            flow = GriptapeNodes.ContextManager().get_current_flow()
            flow_name = flow.name

        # Does this flow exist?
        if flow is None:
            obj_mgr = GriptapeNodes.ObjectManager()
            flow = obj_mgr.attempt_get_object_by_name_as_type(flow_name, ControlFlow)
            if flow is None:
                details = f"Attempted to get metadata for a Flow '{flow_name}', but no such Flow was found."
                return GetFlowMetadataResultFailure(result_details=details)

        metadata = flow.metadata
        details = f"Successfully retrieved metadata for a Flow '{flow_name}'."

        return GetFlowMetadataResultSuccess(metadata=metadata, result_details=details)

    def on_set_flow_metadata_request(self, request: SetFlowMetadataRequest) -> ResultPayload:
        flow_name = request.flow_name
        flow = None
        if flow_name is None:
            # Get from the current context.
            if not GriptapeNodes.ContextManager().has_current_flow():
                details = "Attempted to set metadata for a Flow from the Current Context. Failed because the Current Context is empty."
                return SetFlowMetadataResultFailure(result_details=details)

            flow = GriptapeNodes.ContextManager().get_current_flow()
            flow_name = flow.name

        # Does this flow exist?
        if flow is None:
            obj_mgr = GriptapeNodes.ObjectManager()
            flow = obj_mgr.attempt_get_object_by_name_as_type(flow_name, ControlFlow)
            if flow is None:
                details = f"Attempted to set metadata for a Flow '{flow_name}', but no such Flow was found."
                return SetFlowMetadataResultFailure(result_details=details)

        # We can't completely overwrite metadata.
        for key, value in request.metadata.items():
            flow.metadata[key] = value
        details = f"Successfully set metadata for a Flow '{flow_name}'."

        return SetFlowMetadataResultSuccess(result_details=details)

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
                result = CreateFlowResultFailure(result_details=details)
                return result
        # Now our parent exists, right?
        elif parent is None:
            details = f"Attempted to create a Flow with a parent '{request.parent_flow_name}', but no parent with that name could be found."

            result = CreateFlowResultFailure(result_details=details)

            return result

        # We need to have a current workflow context to proceed.
        if not GriptapeNodes.ContextManager().has_current_workflow():
            details = "Attempted to create a Flow, but no Workflow was active in the Current Context."
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

        result = CreateFlowResultSuccess(
            flow_name=final_flow_name, result_details=ResultDetails(message=details, level=log_level)
        )
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
            result = DeleteFlowResultFailure(result_details=details)
            return result
        if self.check_for_existing_running_flow():
            result = GriptapeNodes.handle_request(CancelFlowRequest(flow_name=flow.name))
            if not result.succeeded():
                details = f"Attempted to delete flow '{flow_name}'. Failed because running flow could not cancel."
                return DeleteFlowResultFailure(result_details=details)

        # Let this Flow assume the Current Context while we delete everything within it.
        with GriptapeNodes.ContextManager().flow(flow=flow):
            # Delete all child nodes in this Flow.
            list_nodes_request = ListNodesInFlowRequest()
            list_nodes_result = GriptapeNodes.handle_request(list_nodes_request)
            if not isinstance(list_nodes_result, ListNodesInFlowResultSuccess):
                details = f"Attempted to delete Flow '{flow.name}', but failed while attempting to get the list of Nodes owned by this Flow."
                result = DeleteFlowResultFailure(result_details=details)
                return result
            node_names = list_nodes_result.node_names
            for node_name in node_names:
                delete_node_request = DeleteNodeRequest(node_name=node_name)
                delete_node_result = GriptapeNodes.handle_request(delete_node_request)
                if isinstance(delete_node_result, DeleteNodeResultFailure):
                    details = f"Attempted to delete Flow '{flow.name}', but failed while attempting to delete child Node '{node_name}'."
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
                    result = DeleteFlowResultFailure(result_details=details)
                    return result
                with GriptapeNodes.ContextManager().flow(flow=child_flow):
                    # Delete them.
                    delete_flow_request = DeleteFlowRequest()
                    delete_flow_result = GriptapeNodes.handle_request(delete_flow_request)
                    if isinstance(delete_flow_result, DeleteFlowResultFailure):
                        details = f"Attempted to delete Flow '{flow.name}', but failed while attempting to delete child Flow '{child_flow.name}'."
                        result = DeleteFlowResultFailure(result_details=details)
                        return result

            # If we've made it this far, we have deleted all the children Flows and their nodes.
            # Remove the flow from our map.
            obj_mgr.del_obj_by_name(flow.name)
            del self._name_to_parent_name[flow.name]

            # Clean up referenced workflow tracking
            if flow in self._flow_to_referenced_workflow_name:
                del self._flow_to_referenced_workflow_name[flow]

            # Clean up ControlFlowMachine and DAG orchestrator for this flow
            self._global_control_flow_machine = None
            self._global_dag_builder.clear()

        details = f"Successfully deleted Flow '{flow_name}'."
        result = DeleteFlowResultSuccess(result_details=details)
        return result

    def on_get_is_flow_running_request(self, request: GetIsFlowRunningRequest) -> ResultPayload:
        obj_mgr = GriptapeNodes.ObjectManager()
        if request.flow_name is None:
            details = "Attempted to get Flow, but no flow name was provided."
            return GetIsFlowRunningResultFailure(result_details=details)
        flow = obj_mgr.attempt_get_object_by_name_as_type(request.flow_name, ControlFlow)
        if flow is None:
            details = f"Attempted to get Flow '{request.flow_name}', but no Flow with that name could be found."
            result = GetIsFlowRunningResultFailure(result_details=details)
            return result
        try:
            is_running = self.check_for_existing_running_flow()
        except Exception:
            details = f"Error while trying to get status of '{request.flow_name}'."
            result = GetIsFlowRunningResultFailure(result_details=details)
            return result
        return GetIsFlowRunningResultSuccess(
            is_running=is_running, result_details=f"Successfully checked if flow is running: {is_running}"
        )

    def on_list_nodes_in_flow_request(self, request: ListNodesInFlowRequest) -> ResultPayload:
        flow_name = request.flow_name
        flow = None
        if flow_name is None:
            # First check if we have a current flow
            if not GriptapeNodes.ContextManager().has_current_flow():
                details = "Attempted to list Nodes in a Flow in the Current Context. Failed because the Current Context was empty."
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
            result = ListNodesInFlowResultFailure(result_details=details)
            return result

        ret_list = list(flow.nodes.keys())
        details = f"Successfully got the list of Nodes within Flow '{flow_name}'."

        result = ListNodesInFlowResultSuccess(node_names=ret_list, result_details=details)
        return result

    def on_list_flows_in_flow_request(self, request: ListFlowsInFlowRequest) -> ResultPayload:
        if request.parent_flow_name is not None:
            # Does this Flow even exist?
            obj_mgr = GriptapeNodes.ObjectManager()
            flow = obj_mgr.attempt_get_object_by_name_as_type(request.parent_flow_name, ControlFlow)
            if flow is None:
                details = f"Attempted to list Flows that are children of Flow '{request.parent_flow_name}', but no Flow with that name could be found."
                result = ListFlowsInFlowResultFailure(result_details=details)
                return result

        # Create a list of all child flow names that point DIRECTLY to us.
        ret_list = []
        for flow_name, parent_name in self._name_to_parent_name.items():
            if parent_name == request.parent_flow_name:
                ret_list.append(flow_name)

        details = f"Successfully got the list of Flows that are direct children of Flow '{request.parent_flow_name}'."

        result = ListFlowsInFlowResultSuccess(flow_names=ret_list, result_details=details)
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
                return CreateConnectionResultFailure(result_details=details)

            # Get the current node from context
            source_node = GriptapeNodes.ContextManager().get_current_node()
            source_node_name = source_node.name
        if source_node is None:
            try:
                source_node = GriptapeNodes.NodeManager().get_node_by_name(source_node_name)
            except ValueError as err:
                details = f'Connection failed: "{source_node_name}" does not exist. Error: {err}.'

                return CreateConnectionResultFailure(result_details=details)

        target_node_name = request.target_node_name
        target_node = None
        if target_node_name is None:
            # First check if we have a current node
            if not GriptapeNodes.ContextManager().has_current_node():
                details = "Attempted to create a Connection with the target node from the Current Context. Failed because the Current Context was empty."
                return CreateConnectionResultFailure(result_details=details)

            # Get the current node from context
            target_node = GriptapeNodes.ContextManager().get_current_node()
            target_node_name = target_node.name
        if target_node is None:
            try:
                target_node = GriptapeNodes.NodeManager().get_node_by_name(target_node_name)
            except ValueError as err:
                details = f'Connection failed: "{target_node_name}" does not exist. Error: {err}.'
                return CreateConnectionResultFailure(result_details=details)

        # The two nodes exist.
        # Get the parent flows.
        source_flow_name = None
        try:
            source_flow_name = GriptapeNodes.NodeManager().get_node_parent_flow_by_name(source_node_name)
            self.get_flow_by_name(flow_name=source_flow_name)
        except KeyError as err:
            details = f'Connection "{source_node_name}.{request.source_parameter_name}" to "{target_node_name}.{request.target_parameter_name}" failed: {err}.'
            return CreateConnectionResultFailure(result_details=details)

        target_flow_name = None
        try:
            target_flow_name = GriptapeNodes.NodeManager().get_node_parent_flow_by_name(target_node_name)
            self.get_flow_by_name(flow_name=target_flow_name)
        except KeyError as err:
            details = f'Connection "{source_node_name}.{request.source_parameter_name}" to "{target_node_name}.{request.target_parameter_name}" failed: {err}.'
            return CreateConnectionResultFailure(result_details=details)

        # Cross-flow connections are now supported via global connection storage

        # Call before_connection callbacks to allow nodes to prepare parameters
        source_node.before_outgoing_connection(
            source_parameter_name=request.source_parameter_name,
            target_node=target_node,
            target_parameter_name=request.target_parameter_name,
        )
        target_node.before_incoming_connection(
            source_node=source_node,
            source_parameter_name=request.source_parameter_name,
            target_parameter_name=request.target_parameter_name,
        )

        # Now validate the parameters.
        source_param = source_node.get_parameter_by_name(request.source_parameter_name)
        if source_param is None:
            details = f'Connection failed: "{source_node_name}.{request.source_parameter_name}" not found'
            return CreateConnectionResultFailure(result_details=details)

        target_param = target_node.get_parameter_by_name(request.target_parameter_name)
        if target_param is None:
            # TODO: https://github.com/griptape-ai/griptape-nodes/issues/860
            details = f'Connection failed: "{target_node_name}.{request.target_parameter_name}" not found'
            return CreateConnectionResultFailure(result_details=details)
        # Validate parameter modes accept this type of connection.
        source_modes_allowed = source_param.allowed_modes
        if ParameterMode.OUTPUT not in source_modes_allowed:
            details = (
                f'Connection failed: "{source_node_name}.{request.source_parameter_name}" is not an allowed OUTPUT'
            )
            return CreateConnectionResultFailure(result_details=details)

        target_modes_allowed = target_param.allowed_modes
        if ParameterMode.INPUT not in target_modes_allowed:
            details = f'Connection failed: "{target_node_name}.{request.target_parameter_name}" is not an allowed INPUT'
            return CreateConnectionResultFailure(result_details=details)

        # Validate that the data type from the source is allowed by the target.
        if not target_param.is_incoming_type_allowed(source_param.output_type):
            details = f'Connection failed on type mismatch "{source_node_name}.{request.source_parameter_name}" type({source_param.output_type}) to "{target_node_name}.{request.target_parameter_name}" types({target_param.input_types}) '
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
            return CreateConnectionResultFailure(result_details=details)

        if not target_node.allow_incoming_connection(
            source_node=source_node,
            source_parameter=source_param,
            target_parameter=target_param,
        ):
            details = (
                f'Connection failed : "{target_node_name}.{request.target_parameter_name}" rejected the connection '
            )
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
                return CreateConnectionResultFailure(result_details=details)

            details = f"Deleted the previous connection from '{old_source_node_name}.{old_source_param_name}' to '{old_target_node_name}.{old_target_param_name}' to make room for the new connection."
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
        # Set the parameter value (including None/empty values) unless we're in initial setup
        # Skip propagation for:
        # 1. Control Parameters as they should not receive values
        # 2. Locked nodes
        # 3. Initial Setup (this is used during deserialization; the downstream node may not be created yet)
        is_control_parameter = (
            ParameterType.attempt_get_builtin(source_param.output_type) == ParameterTypeBuiltin.CONTROL_TYPE
        )
        is_dest_node_locked = target_node.lock
        if (not is_control_parameter) and (not is_dest_node_locked) and (not request.initial_setup):
            # When creating a connection, pass the initial value from source to target parameter
            # Set incoming_connection_source fields to identify this as legitimate connection value passing
            # (not manual property setting) so it bypasses the INPUT+PROPERTY connection blocking logic
            GriptapeNodes.handle_request(
                SetParameterValueRequest(
                    parameter_name=target_param.name,
                    node_name=target_node.name,
                    value=value,
                    data_type=source_param.type,
                    incoming_connection_source_node_name=source_node.name,
                    incoming_connection_source_parameter_name=source_param.name,
                )
            )

        # Check if either node is ErrorProxyNode and mark connection modification if not initial_setup
        if not request.initial_setup:
            if isinstance(source_node, ErrorProxyNode):
                source_node.set_post_init_connections_modified()
            if isinstance(target_node, ErrorProxyNode):
                target_node.set_post_init_connections_modified()

        result = CreateConnectionResultSuccess(result_details=details)

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
                return DeleteConnectionResultFailure(result_details=details)

            # Get the current node from context
            source_node = GriptapeNodes.ContextManager().get_current_node()
            source_node_name = source_node.name
        if source_node is None:
            try:
                source_node = GriptapeNodes.NodeManager().get_node_by_name(source_node_name)
            except ValueError as err:
                details = f'Connection not deleted "{source_node_name}.{request.source_parameter_name}" to "{target_node_name}.{request.target_parameter_name}". Error: {err}'

                return DeleteConnectionResultFailure(result_details=details)

        target_node_name = request.target_node_name
        if target_node_name is None:
            # First check if we have a current node
            if not GriptapeNodes.ContextManager().has_current_node():
                details = "Attempted to delete a Connection with a target node from the Current Context. Failed because the Current Context was empty."
                return DeleteConnectionResultFailure(result_details=details)

            # Get the current node from context
            target_node = GriptapeNodes.ContextManager().get_current_node()
            target_node_name = target_node.name
        if target_node is None:
            try:
                target_node = GriptapeNodes.NodeManager().get_node_by_name(target_node_name)
            except ValueError as err:
                details = f'Connection not deleted "{source_node_name}.{request.source_parameter_name}" to "{target_node_name}.{request.target_parameter_name}". Error: {err}'

                return DeleteConnectionResultFailure(result_details=details)

        # The two nodes exist.
        # Get the parent flows.
        source_flow_name = None
        try:
            source_flow_name = GriptapeNodes.NodeManager().get_node_parent_flow_by_name(source_node_name)
            self.get_flow_by_name(flow_name=source_flow_name)
        except KeyError as err:
            details = f'Connection not deleted "{source_node_name}.{request.source_parameter_name}" to "{target_node_name}.{request.target_parameter_name}". Error: {err}'

            return DeleteConnectionResultFailure(result_details=details)

        target_flow_name = None
        try:
            target_flow_name = GriptapeNodes.NodeManager().get_node_parent_flow_by_name(target_node_name)
            self.get_flow_by_name(flow_name=target_flow_name)
        except KeyError as err:
            details = f'Connection not deleted "{source_node_name}.{request.source_parameter_name}" to "{target_node_name}.{request.target_parameter_name}". Error: {err}'

            return DeleteConnectionResultFailure(result_details=details)

        # Cross-flow connections are now supported via global connection storage

        # Now validate the parameters.
        source_param = source_node.get_parameter_by_name(request.source_parameter_name)
        if source_param is None:
            details = f'Connection not deleted "{source_node_name}.{request.source_parameter_name}" Not found.'

            return DeleteConnectionResultFailure(result_details=details)

        target_param = target_node.get_parameter_by_name(request.target_parameter_name)
        if target_param is None:
            details = f'Connection not deleted "{target_node_name}.{request.target_parameter_name}" Not found.'

            return DeleteConnectionResultFailure(result_details=details)

        # Vet that a Connection actually exists between them already.
        if not self._has_connection(
            source_node=source_node,
            source_parameter=source_param,
            target_node=target_node,
            target_parameter=target_param,
        ):
            details = f'Connection does not exist: "{source_node_name}.{request.source_parameter_name}" to "{target_node_name}.{request.target_parameter_name}"'

            return DeleteConnectionResultFailure(result_details=details)

        # Remove the connection.
        if not self._connections.remove_connection(
            source_node=source_node.name,
            source_parameter=source_param.name,
            target_node=target_node.name,
            target_parameter=target_param.name,
        ):
            details = f'Connection not deleted "{source_node_name}.{request.source_parameter_name}" to "{target_node_name}.{request.target_parameter_name}". Unknown failure.'

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

        # Check if either node is ErrorProxyNode and mark connection modification (deletes are always user-initiated)
        if isinstance(source_node, ErrorProxyNode):
            source_node.set_post_init_connections_modified()
        if isinstance(target_node, ErrorProxyNode):
            target_node.set_post_init_connections_modified()

        result = DeleteConnectionResultSuccess(result_details=details)
        return result

    def on_package_nodes_as_serialized_flow_request(  # noqa: C901, PLR0911, PLR0912
        self, request: PackageNodesAsSerializedFlowRequest
    ) -> ResultPayload:
        """Handle request to package multiple nodes as a serialized flow.

        Creates a self-contained flow with Start → [Selected Nodes] → End structure,
        where artificial start/end nodes interface with external connections only.
        """
        # Step 0: Apply defaults for None values
        if request.start_node_type is None:
            request.start_node_type = "StartFlow"
        if request.end_node_type is None:
            request.end_node_type = "EndFlow"

        # Step 1: Reject empty node list
        if not request.node_names:
            return PackageNodesAsSerializedFlowResultFailure(
                result_details="Attempted to package nodes as serialized flow. Failed because no nodes were specified in the node_names list."
            )

        # Step 2: Validate library and get version
        library_version = self._validate_and_get_multi_node_library_info(request=request)
        if isinstance(library_version, PackageNodesAsSerializedFlowResultFailure):
            return library_version

        # Step 3: Validate all nodes exist
        validation_result = self._validate_multi_node_request(request)
        if validation_result is not None:
            return validation_result

        # Get the actual node objects for processing
        nodes_to_package = []
        for node_name in request.node_names:
            node = GriptapeNodes.NodeManager().get_node_by_name(node_name)
            nodes_to_package.append(node)

        # Step 4: Initialize tracking variables and mappings (moved up so package node serialization can use them)
        unique_parameter_uuid_to_values = {}
        serialized_parameter_value_tracker = SerializedParameterValueTracker()
        node_name_to_uuid: dict[str, SerializedNodeCommands.NodeUUID] = {}
        packaged_nodes_set_parameter_value_commands: dict[
            SerializedNodeCommands.NodeUUID, list[SerializedNodeCommands.IndirectSetParameterValueCommand]
        ] = {}
        packaged_nodes_internal_connections: list[SerializedFlowCommands.IndirectConnectionSerialization] = []

        # Step 5: Serialize nodes with local execution environment to prevent recursive loops
        serialized_package_nodes = self._serialize_package_nodes_for_local_execution(
            nodes_to_package=nodes_to_package,
            unique_parameter_uuid_to_values=unique_parameter_uuid_to_values,
            serialized_parameter_value_tracker=serialized_parameter_value_tracker,
            node_name_to_uuid=node_name_to_uuid,
            set_parameter_value_commands=packaged_nodes_set_parameter_value_commands,
            internal_connections=packaged_nodes_internal_connections,
            proxy_node=request.proxy_node,
        )
        if isinstance(serialized_package_nodes, PackageNodesAsSerializedFlowResultFailure):
            return serialized_package_nodes

        # Step 6: Inject OUTPUT mode changes for PROPERTY-only parameters to enable value reconciliation after the
        # packaged workflow is run.
        # Example: Nodes A -> B -> C. If B has property-only parameters, those values may change during execution,
        # so we need to send the value back after the packaged flow has run. We do this by making connections from
        # B's property-only parameters to the End Node, ensuring they're reflected when the packaged flow returns.
        # Since connections require an OUTPUT parameter mode, we inject that here.
        self._inject_output_mode_for_property_parameters(nodes_to_package, serialized_package_nodes)

        # Step 7: Analyze external connections (connections from/to nodes outside our selection)
        node_connections_dict = self._analyze_multi_node_external_connections(
            package_nodes=nodes_to_package, proxy_node=request.proxy_node
        )
        if isinstance(node_connections_dict, PackageNodesAsSerializedFlowResultFailure):
            return node_connections_dict

        # Step 8: Create start node with parameters for external incoming connections
        start_node_result = self._create_multi_node_start_node_with_connections(
            request=request,
            library_version=library_version,
            unique_parameter_uuid_to_values=unique_parameter_uuid_to_values,
            serialized_parameter_value_tracker=serialized_parameter_value_tracker,
            node_name_to_uuid=node_name_to_uuid,
            external_connections_dict=node_connections_dict,
        )
        if isinstance(start_node_result, PackageNodesAsSerializedFlowResultFailure):
            return start_node_result

        # Step 9: Create end node with parameters for external outgoing connections and parameter mappings
        end_node_result = self._create_multi_node_end_node_with_connections(
            request=request,
            package_nodes=nodes_to_package,
            node_name_to_uuid=node_name_to_uuid,
            library_version=library_version,
            node_connections_dict=node_connections_dict,
        )
        if isinstance(end_node_result, PackageNodesAsSerializedFlowResultFailure):
            return end_node_result

        end_node_packaging_result = end_node_result.packaging_result
        parameter_name_mappings = end_node_result.parameter_name_mappings

        # Step 10: Assemble final SerializedFlowCommands
        # Collect all connections from start/end nodes and internal package connections
        all_connections = self._collect_all_connections_for_multi_node_package(
            start_node_result=start_node_result,
            end_node_packaging_result=end_node_packaging_result,
            packaged_nodes_internal_connections=packaged_nodes_internal_connections,
        )

        # Build WorkflowShape from collected parameter shape data
        workflow_shape = GriptapeNodes.WorkflowManager().build_workflow_shape_from_parameter_info(
            input_node_params=start_node_result.input_shape_data,
            output_node_params=end_node_packaging_result.output_shape_data,
        )

        # Create set parameter value commands dict
        set_parameter_value_commands = {
            start_node_result.start_node_commands.node_uuid: start_node_result.start_node_parameter_value_commands,
            **packaged_nodes_set_parameter_value_commands,
        }

        # Collect all serialized nodes
        all_serialized_nodes = [
            start_node_result.start_node_commands,
            *serialized_package_nodes,
            end_node_packaging_result.end_node_commands,
        ]

        # Create comprehensive dependencies from all nodes
        combined_dependencies = NodeDependencies()
        for serialized_node in all_serialized_nodes:
            combined_dependencies.aggregate_from(serialized_node.node_dependencies)

        # Extract lock commands from serialized nodes (they're embedded in SerializedNodeCommands)
        set_lock_commands_per_node = {}
        for serialized_node in all_serialized_nodes:
            if serialized_node.lock_node_command:
                set_lock_commands_per_node[serialized_node.node_uuid] = serialized_node.lock_node_command

        # Create a CreateFlowRequest for the packaged flow so that it can
        # run as a standalone workflow
        packaged_flow_metadata = {}  # Keep it simple until we have reason to populate it

        create_packaged_flow_request = CreateFlowRequest(
            parent_flow_name=None,  # Standalone flow
            set_as_new_context=False,  # Let deserializer decide
            metadata=packaged_flow_metadata,
        )

        # Aggregate node types used
        combined_node_types_used = self._aggregate_node_types_used(
            serialized_node_commands=all_serialized_nodes, sub_flows_commands=[]
        )

        # Build the complete serialized flow
        final_serialized_flow = SerializedFlowCommands(
            flow_initialization_command=create_packaged_flow_request,
            serialized_node_commands=all_serialized_nodes,
            serialized_connections=all_connections,
            unique_parameter_uuid_to_values=unique_parameter_uuid_to_values,
            set_parameter_value_commands=set_parameter_value_commands,
            set_lock_commands_per_node=set_lock_commands_per_node,
            sub_flows_commands=[],
            node_dependencies=combined_dependencies,
            node_types_used=combined_node_types_used,
        )

        return PackageNodesAsSerializedFlowResultSuccess(
            serialized_flow_commands=final_serialized_flow,
            workflow_shape=workflow_shape,
            packaged_node_names=request.node_names,
            parameter_name_mappings=parameter_name_mappings,
            result_details=f"Successfully packaged {len(request.node_names)} nodes as serialized flow.",
        )

    def _validate_and_get_multi_node_library_info(
        self, request: PackageNodesAsSerializedFlowRequest
    ) -> str | PackageNodesAsSerializedFlowResultFailure:
        """Validate start/end node types exist in library and return library version."""
        # Early validation - ensure both start and end node types exist in the specified library
        try:
            start_end_library = LibraryRegistry.get_library_for_node_type(
                node_type=request.start_node_type,  # type: ignore[arg-type]  # Guaranteed non-None by handler
                specific_library_name=request.start_end_specific_library_name,
            )
        except KeyError as err:
            details = f"Attempted to package nodes with start node type '{request.start_node_type}' from library '{request.start_end_specific_library_name}'. Failed because start node type was not found in library. Error: {err}."
            return PackageNodesAsSerializedFlowResultFailure(result_details=details)

        try:
            LibraryRegistry.get_library_for_node_type(
                node_type=request.end_node_type,  # type: ignore[arg-type]  # Guaranteed non-None by handler
                specific_library_name=request.start_end_specific_library_name,
            )
        except KeyError as err:
            details = f"Attempted to package nodes with end node type '{request.end_node_type}' from library '{request.start_end_specific_library_name}'. Failed because end node type was not found in library. Error: {err}."
            return PackageNodesAsSerializedFlowResultFailure(result_details=details)

        # Get the actual library version
        start_end_library_metadata = start_end_library.get_metadata()
        return start_end_library_metadata.library_version

    def _validate_multi_node_request(
        self, request: PackageNodesAsSerializedFlowRequest
    ) -> None | PackageNodesAsSerializedFlowResultFailure:
        """Validate that all requested nodes exist and control flow configuration is valid."""
        # Validate all nodes exist
        missing_nodes = []
        for node_name in request.node_names:
            try:
                GriptapeNodes.NodeManager().get_node_by_name(node_name)
            except Exception:
                missing_nodes.append(node_name)

        if missing_nodes:
            return PackageNodesAsSerializedFlowResultFailure(
                result_details=f"Attempted to package nodes as serialized flow. Failed because the following nodes were not found: {', '.join(missing_nodes)}."
            )

        # Validate control flow configuration for non-empty node lists
        if request.node_names and request.entry_control_parameter_name and not request.entry_control_node_name:
            return PackageNodesAsSerializedFlowResultFailure(
                result_details="Attempted to package nodes as serialized flow. Failed because entry_control_parameter_name was specified but entry_control_node_name was not. For multi-node packaging with a non-empty node list, both must be specified to avoid ambiguity about which node should receive the control connection."
            )

        # Validate entry_control_node_name exists and is in our package list
        if request.entry_control_node_name and request.entry_control_node_name not in request.node_names:
            return PackageNodesAsSerializedFlowResultFailure(
                result_details=f"Attempted to package nodes as serialized flow. Failed because entry_control_node_name '{request.entry_control_node_name}' is not in the list of nodes to package: {request.node_names}."
            )

        return None

    def _serialize_package_nodes_for_local_execution(  # noqa: PLR0913
        self,
        nodes_to_package: list[BaseNode],
        unique_parameter_uuid_to_values: dict[SerializedNodeCommands.UniqueParameterValueUUID, Any],
        serialized_parameter_value_tracker: SerializedParameterValueTracker,
        node_name_to_uuid: dict[str, SerializedNodeCommands.NodeUUID],  # OUTPUT: will be populated
        set_parameter_value_commands: dict[  # OUTPUT: will be populated
            SerializedNodeCommands.NodeUUID, list[SerializedNodeCommands.IndirectSetParameterValueCommand]
        ],
        internal_connections: list[SerializedFlowCommands.IndirectConnectionSerialization],  # OUTPUT: will be populated
        proxy_node: NodeGroupProxyNode | None = None,  # NodeGroupProxyNode if packaging nodes from a proxy
    ) -> list[SerializedNodeCommands] | PackageNodesAsSerializedFlowResultFailure:
        """Serialize package nodes while temporarily setting execution environment to local to prevent recursive loops.

        This method temporarily overrides each node's execution_environment parameter to LOCAL_EXECUTION
        during serialization, then restores the original values. This prevents recursive packaging loops
        that could occur if nodes were configured for remote execution environments.

        Args:
            nodes_to_package: List of nodes to serialize
            unique_parameter_uuid_to_values: Shared dictionary for deduplicating parameter values across all nodes
            serialized_parameter_value_tracker: Tracker for serialized parameter values
            node_name_to_uuid: OUTPUT - Dictionary mapping node names to UUIDs (populated by this method)
            set_parameter_value_commands: OUTPUT - Dict mapping node UUIDs to parameter value commands (populated by this method)
            internal_connections: OUTPUT - List of connections between package nodes (populated by this method)
            proxy_node: NodeGroupProxyNode if packaging nodes from a proxy, provides access to original connections
                       stored before they were redirected to the proxy

        Returns:
            List of SerializedNodeCommands on success, or PackageNodesAsSerializedFlowResultFailure on failure
        """
        # Intercept execution_environment and job_group for all nodes before serialization
        original_execution_environments = {}
        original_job_groups = {}
        for node in nodes_to_package:
            # Save and override execution_environment to prevent recursive packaging loops
            original_exec_value = node.get_parameter_value("execution_environment")
            original_execution_environments[node.name] = original_exec_value
            node.set_parameter_value("execution_environment", LOCAL_EXECUTION)

            # Save and clear job_group to prevent group processing in packaged flow
            original_job_group_value = node.get_parameter_value("job_group")
            original_job_groups[node.name] = original_job_group_value
            node.set_parameter_value("job_group", "")

        try:
            # Serialize each node using shared unique_parameter_uuid_to_values dictionary for deduplication
            serialized_node_commands = []

            for node in nodes_to_package:
                # Serialize this node using shared dictionaries for value deduplication
                serialize_request = SerializeNodeToCommandsRequest(
                    node_name=node.name,
                    unique_parameter_uuid_to_values=unique_parameter_uuid_to_values,
                    serialized_parameter_value_tracker=serialized_parameter_value_tracker,
                )
                serialize_result = GriptapeNodes.NodeManager().on_serialize_node_to_commands(serialize_request)

                if not isinstance(serialize_result, SerializeNodeToCommandsResultSuccess):
                    return PackageNodesAsSerializedFlowResultFailure(
                        result_details=f"Attempted to package nodes as serialized flow. Failed to serialize node '{node.name}': {serialize_result.result_details}"
                    )

                # Collect serialized node
                serialized_node_commands.append(serialize_result.serialized_node_commands)

                # Populate the shared node_name_to_uuid mapping
                if serialize_result.serialized_node_commands.create_node_command.node_name is not None:
                    node_name_to_uuid[serialize_result.serialized_node_commands.create_node_command.node_name] = (
                        serialize_result.serialized_node_commands.node_uuid
                    )

                # Collect set parameter value commands (references to unique_parameter_uuid_to_values)
                if serialize_result.set_parameter_value_commands:
                    set_parameter_value_commands[serialize_result.serialized_node_commands.node_uuid] = (
                        serialize_result.set_parameter_value_commands
                    )

            # Build internal connections between package nodes
            package_node_names_set = {n.name for n in nodes_to_package}

            # Get connections using appropriate method based on whether we have a proxy node
            connections_result = self._get_internal_connections_for_package(
                nodes_to_package=nodes_to_package,
                package_node_names_set=package_node_names_set,
                node_name_to_uuid=node_name_to_uuid,
                proxy_node=proxy_node,
            )

            if isinstance(connections_result, PackageNodesAsSerializedFlowResultFailure):
                return connections_result

            internal_connections.extend(connections_result)
        finally:
            # Always restore original execution_environment and job_group values, even on failure
            for node_name, original_value in original_execution_environments.items():
                restore_node = GriptapeNodes.NodeManager().get_node_by_name(node_name)
                restore_node.set_parameter_value("execution_environment", original_value)

            for node_name, original_job_group in original_job_groups.items():
                restore_node = GriptapeNodes.NodeManager().get_node_by_name(node_name)
                restore_node.set_parameter_value("job_group", original_job_group)

        return serialized_node_commands

    def _get_internal_connections_for_package(  # noqa: C901, PLR0912
        self,
        nodes_to_package: list[BaseNode],
        package_node_names_set: set[str],
        node_name_to_uuid: dict[str, SerializedNodeCommands.NodeUUID],
        proxy_node: NodeGroupProxyNode | None,
    ) -> list[SerializedFlowCommands.IndirectConnectionSerialization] | PackageNodesAsSerializedFlowResultFailure:
        """Get internal connections between package nodes.

        If a proxy_node is provided, uses the stored internal_connections from the NodeGroup
        which preserve the original connection structure before redirection to the proxy.
        Otherwise, queries connections from the connection manager.

        Args:
            nodes_to_package: List of nodes being packaged
            package_node_names_set: Set of node names in the package for O(1) lookup
            node_name_to_uuid: Mapping of node names to their UUIDs in the serialization
            proxy_node: Optional proxy node containing the original connection structure

        Returns:
            List of serialized connections, or PackageNodesAsSerializedFlowResultFailure on error
        """
        internal_connections: list[SerializedFlowCommands.IndirectConnectionSerialization] = []

        if proxy_node is not None and hasattr(proxy_node, "node_group_data"):
            # Use stored connections from NodeGroup which have the original node references
            node_group = proxy_node.node_group_data

            # 1. Add internal connections (between nodes inside the group)
            for conn in node_group.internal_connections:
                source_node_name = conn.source_node.name
                target_node_name = conn.target_node.name

                # Only include connections where BOTH nodes are in our package
                if source_node_name in package_node_names_set and target_node_name in package_node_names_set:
                    source_uuid = node_name_to_uuid[source_node_name]
                    target_uuid = node_name_to_uuid[target_node_name]
                    internal_connections.append(
                        SerializedFlowCommands.IndirectConnectionSerialization(
                            source_node_uuid=source_uuid,
                            source_parameter_name=conn.source_parameter.name,
                            target_node_uuid=target_uuid,
                            target_parameter_name=conn.target_parameter.name,
                        )
                    )

            # 2. Add external incoming connections (from outside into the group)
            # These connections have been redirected to point TO the proxy, but we want the original targets
            for conn in node_group.external_incoming_connections:
                conn_id = id(conn)
                original_target = node_group.original_incoming_targets.get(conn_id)

                if original_target and original_target.name in package_node_names_set:
                    # The source is outside the package, target is inside
                    # We include these because the source will be external (like StartFlow)
                    source_node_name = conn.source_node.name
                    target_node_name = original_target.name

                    # Only include if source is NOT in package (external) and target IS in package
                    if source_node_name not in package_node_names_set:
                        source_uuid = node_name_to_uuid.get(source_node_name)
                        target_uuid = node_name_to_uuid[target_node_name]

                        # Source might not have a UUID if it's external to the package
                        if source_uuid:
                            internal_connections.append(
                                SerializedFlowCommands.IndirectConnectionSerialization(
                                    source_node_uuid=source_uuid,
                                    source_parameter_name=conn.source_parameter.name,
                                    target_node_uuid=target_uuid,
                                    target_parameter_name=conn.target_parameter.name,
                                )
                            )

            # 3. Add external outgoing connections (from the group to outside)
            # These connections have been redirected to point FROM the proxy, but we want the original sources
            for conn in node_group.external_outgoing_connections:
                conn_id = id(conn)
                original_source = node_group.original_outgoing_sources.get(conn_id)

                if original_source and original_source.name in package_node_names_set:
                    # The source is inside the package, target is outside
                    source_node_name = original_source.name
                    target_node_name = conn.target_node.name

                    # Only include if source IS in package and target is NOT in package (external)
                    if target_node_name not in package_node_names_set:
                        source_uuid = node_name_to_uuid[source_node_name]
                        target_uuid = node_name_to_uuid.get(target_node_name)

                        # Target might not have a UUID if it's external to the package
                        if target_uuid:
                            internal_connections.append(
                                SerializedFlowCommands.IndirectConnectionSerialization(
                                    source_node_uuid=source_uuid,
                                    source_parameter_name=conn.source_parameter.name,
                                    target_node_uuid=target_uuid,
                                    target_parameter_name=conn.target_parameter.name,
                                )
                            )
        else:
            # No proxy node - query connections from connection manager
            for node in nodes_to_package:
                list_connections_request = ListConnectionsForNodeRequest(node_name=node.name)
                list_connections_result = GriptapeNodes.NodeManager().on_list_connections_for_node_request(
                    list_connections_request
                )

                if not isinstance(list_connections_result, ListConnectionsForNodeResultSuccess):
                    return PackageNodesAsSerializedFlowResultFailure(
                        result_details=f"Attempted to package nodes as serialized flow. Failed to list connections for node '{node.name}': {list_connections_result.result_details}"
                    )

                # Only include connections where BOTH source and target are in the package
                for outgoing_conn in list_connections_result.outgoing_connections:
                    if outgoing_conn.target_node_name in package_node_names_set:
                        source_uuid = node_name_to_uuid[node.name]
                        target_uuid = node_name_to_uuid[outgoing_conn.target_node_name]
                        internal_connections.append(
                            SerializedFlowCommands.IndirectConnectionSerialization(
                                source_node_uuid=source_uuid,
                                source_parameter_name=outgoing_conn.source_parameter_name,
                                target_node_uuid=target_uuid,
                                target_parameter_name=outgoing_conn.target_parameter_name,
                            )
                        )

        return internal_connections

    def _inject_output_mode_for_property_parameters(
        self, nodes_to_package: list[BaseNode], serialized_package_nodes: list[SerializedNodeCommands]
    ) -> None:
        """Inject OUTPUT mode for PROPERTY-only parameters to enable value reconciliation.

        This method adds ALTER parameter commands to serialized nodes for parameters that have
        PROPERTY mode but not OUTPUT mode. This allows the orchestrator/caller to reconcile
        the packaged node's values after execution.

        Args:
            nodes_to_package: List of nodes being packaged
            serialized_package_nodes: The serialized node commands to modify
        """
        # Apply ALTER parameter commands for PROPERTY-only parameters to enable OUTPUT mode
        # We need these to emit their values back so that the orchestrator/caller
        # can reconcile the packaged node's values after it is executed.
        for package_node in nodes_to_package:
            # Find the corresponding serialized node
            serialized_node = None
            for serialized_node_command in serialized_package_nodes:
                if serialized_node_command.create_node_command.node_name == package_node.name:
                    serialized_node = serialized_node_command
                    break

            if serialized_node is None:
                error_msg = f"Data integrity error: Could not find serialized node for package node '{package_node.name}'. This indicates a logic error in the serialization process."
                logger.error(error_msg)
                raise RuntimeError(error_msg)

            package_alter_parameter_commands = []
            for package_param in package_node.parameters:
                has_output_mode = ParameterMode.OUTPUT in package_param.allowed_modes
                has_property_mode = ParameterMode.PROPERTY in package_param.allowed_modes
                # If has PROPERTY but not OUTPUT, add ALTER command to enable OUTPUT
                if has_property_mode and not has_output_mode:
                    alter_param_request = AlterParameterDetailsRequest(
                        parameter_name=package_param.name,
                        node_name=package_node.name,
                        mode_allowed_output=True,
                    )
                    package_alter_parameter_commands.append(alter_param_request)

            # If we have alter parameter commands, append them to the existing element_modification_commands
            if package_alter_parameter_commands:
                serialized_node.element_modification_commands.extend(package_alter_parameter_commands)

    def _analyze_multi_node_external_connections(
        self, package_nodes: list[BaseNode], proxy_node: NodeGroupProxyNode | None = None
    ) -> dict[str, ConnectionAnalysis] | PackageNodesAsSerializedFlowResultFailure:
        """Analyze external connections for each package node using filtered single-node analysis.

        This method reuses the existing single-node connection analysis method but applies filtering
        to only capture "external" connections - those that cross the package boundary.

        External connections are:
        - Incoming connections where the source node is NOT in the package
        - Outgoing connections where the target node is NOT in the package

        Internal connections (between nodes within the package) are filtered out by passing
        the set of package node names to the single-node analysis method.

        Args:
            package_nodes: List of nodes being packaged together
            proxy_node: Optional proxy node containing the original connection structure

        Returns:
            Dictionary mapping node_name -> ConnectionAnalysis, where each ConnectionAnalysis
            contains only the external connections for that node, or failure result on error
        """
        package_node_names_set = {node.name for node in package_nodes}
        node_connections = {}

        for package_node in package_nodes:
            # Perform a single node analysis, filtering out internal connections
            connection_analysis = self._analyze_package_node_connections(
                package_node=package_node,
                node_name=package_node.name,
                package_node_names=package_node_names_set,
                proxy_node=proxy_node,
            )
            if isinstance(connection_analysis, PackageNodesAsSerializedFlowResultFailure):
                return PackageNodesAsSerializedFlowResultFailure(result_details=connection_analysis.result_details)

            node_connections[package_node.name] = connection_analysis

        return node_connections

    def _get_node_connections_from_proxy(
        self, node_name: str, proxy_node: NodeGroupProxyNode
    ) -> tuple[list[IncomingConnection], list[OutgoingConnection]]:
        """Extract incoming and outgoing connections for a specific node from the proxy node's stored data.

        Returns connections in the same format as ListConnectionsForNodeRequest would return them,
        using the original node references from before proxy redirection.

        Args:
            node_name: Name of the node to get connections for
            proxy_node: The proxy node containing the NodeGroup data with stored connections

        Returns:
            Tuple of (incoming_connections, outgoing_connections) matching the ListConnectionsForNodeResultSuccess format
        """
        node_group = proxy_node.node_group_data
        incoming_connections: list[IncomingConnection] = []
        outgoing_connections: list[OutgoingConnection] = []

        # Get incoming connections: check internal_connections and external_incoming_connections
        # Internal connections where this node is the target
        incoming_connections.extend(
            IncomingConnection(
                source_node_name=conn.source_node.name,
                source_parameter_name=conn.source_parameter.name,
                target_parameter_name=conn.target_parameter.name,
            )
            for conn in node_group.internal_connections
            if conn.target_node.name == node_name
        )

        # External incoming connections where this node is the original target
        incoming_connections.extend(
            IncomingConnection(
                source_node_name=conn.source_node.name,
                source_parameter_name=conn.source_parameter.name,
                target_parameter_name=conn.target_parameter.name,
            )
            for conn in node_group.external_incoming_connections
            if (original_target := node_group.original_incoming_targets.get(id(conn)))
            and original_target.name == node_name
        )

        # Get outgoing connections: check internal_connections and external_outgoing_connections
        # Internal connections where this node is the source
        outgoing_connections.extend(
            OutgoingConnection(
                source_parameter_name=conn.source_parameter.name,
                target_node_name=conn.target_node.name,
                target_parameter_name=conn.target_parameter.name,
            )
            for conn in node_group.internal_connections
            if conn.source_node.name == node_name
        )

        # External outgoing connections where this node is the original source
        outgoing_connections.extend(
            OutgoingConnection(
                source_parameter_name=conn.source_parameter.name,
                target_node_name=conn.target_node.name,
                target_parameter_name=conn.target_parameter.name,
            )
            for conn in node_group.external_outgoing_connections
            if (original_source := node_group.original_outgoing_sources.get(id(conn)))
            and original_source.name == node_name
        )

        return incoming_connections, outgoing_connections

    def _analyze_package_node_connections(
        self,
        package_node: BaseNode,
        node_name: str,
        package_node_names: set[str] | None = None,
        proxy_node: NodeGroupProxyNode | None = None,
    ) -> ConnectionAnalysis | PackageNodesAsSerializedFlowResultFailure:
        """Analyze package node connections and separate control from data connections.

        If a proxy_node is provided, uses the stored connections from the NodeGroup which preserve
        the original connection structure before proxy redirection.

        Args:
            package_node: The node being analyzed
            node_name: Name of the node
            package_node_names: Set of node names in the package for filtering internal connections
            proxy_node: Optional proxy node containing original connection structure
        """
        # Get incoming and outgoing connections for this node
        if proxy_node is not None and hasattr(proxy_node, "node_group_data"):
            # Use stored connections from proxy which have the original node references
            incoming_connections, outgoing_connections = self._get_node_connections_from_proxy(
                node_name=node_name, proxy_node=proxy_node
            )
        else:
            # Get connection details using the standard approach
            list_connections_request = ListConnectionsForNodeRequest(node_name=node_name)
            list_connections_result = GriptapeNodes.NodeManager().on_list_connections_for_node_request(
                list_connections_request
            )

            if not isinstance(list_connections_result, ListConnectionsForNodeResultSuccess):
                details = f"Attempted to analyze connections for package node '{node_name}'. Failed because connection listing failed."
                return PackageNodesAsSerializedFlowResultFailure(result_details=details)

            incoming_connections = list_connections_result.incoming_connections
            outgoing_connections = list_connections_result.outgoing_connections

        # Separate control connections from data connections based on package node's parameter types
        incoming_data_connections = []
        incoming_control_connections = []
        for incoming_conn in incoming_connections:
            # Filter out internal connections if package_node_names is provided
            if package_node_names is not None and incoming_conn.source_node_name in package_node_names:
                continue

            # Get the package node's parameter to check if it's a control type
            package_param = package_node.get_parameter_by_name(incoming_conn.target_parameter_name)
            if package_param and ParameterTypeBuiltin.CONTROL_TYPE.value in package_param.input_types:
                incoming_control_connections.append(incoming_conn)
            else:
                incoming_data_connections.append(incoming_conn)

        outgoing_data_connections = []
        outgoing_control_connections = []
        for outgoing_conn in outgoing_connections:
            # Filter out internal connections if package_node_names is provided
            if package_node_names is not None and outgoing_conn.target_node_name in package_node_names:
                continue

            # Get the package node's parameter to check if it's a control type
            package_param = package_node.get_parameter_by_name(outgoing_conn.source_parameter_name)
            if package_param and ParameterTypeBuiltin.CONTROL_TYPE.value == package_param.output_type:
                outgoing_control_connections.append(outgoing_conn)
            else:
                outgoing_data_connections.append(outgoing_conn)

        return ConnectionAnalysis(
            incoming_data_connections=incoming_data_connections,
            incoming_control_connections=incoming_control_connections,
            outgoing_data_connections=outgoing_data_connections,
            outgoing_control_connections=outgoing_control_connections,
        )

    def _create_multi_node_end_node_with_connections(
        self,
        request: PackageNodesAsSerializedFlowRequest,
        package_nodes: list[BaseNode],
        node_name_to_uuid: dict[str, SerializedNodeCommands.NodeUUID],
        library_version: str,
        node_connections_dict: dict[str, ConnectionAnalysis],
    ) -> MultiNodeEndNodeResult | PackageNodesAsSerializedFlowResultFailure:
        """Create end node commands and connections for ALL package parameters that meet criteria (copied from single-node)."""
        # Generate UUID and name for end node
        end_node_uuid = SerializedNodeCommands.NodeUUID(str(uuid4()))
        end_node_name = "End_Multi_Package"

        # Build end node CreateNodeRequest
        end_create_node_command = CreateNodeRequest(
            node_type=request.end_node_type,  # type: ignore[arg-type]  # Guaranteed non-None by handler
            specific_library_name=request.start_end_specific_library_name,
            node_name=end_node_name,
            metadata={},
            initial_setup=True,
            create_error_proxy_on_failure=False,
        )

        # Create library details
        end_node_library_details = LibraryNameAndVersion(
            library_name=request.start_end_specific_library_name,
            library_version=library_version,
        )

        # Initialize collections for building the end node
        end_node_parameter_commands = []
        package_to_end_connections = []
        output_shape_data: WorkflowShapeNodes = {}
        # Parameter name mappings (rosetta stone): maps mangled end node parameter names back to original (node_name, parameter_name)
        # This is essential for callers to understand which end node outputs correspond to which original node parameters
        parameter_name_mappings: dict[SanitizedParameterName, OriginalNodeParameter] = {}

        # Handle external control connections first
        self._create_end_node_control_connections(
            request=request,
            package_nodes=package_nodes,
            node_connections_dict=node_connections_dict,
            node_name_to_uuid=node_name_to_uuid,
            end_node_uuid=end_node_uuid,
            end_node_name=end_node_name,
            end_node_parameter_commands=end_node_parameter_commands,
            package_to_end_connections=package_to_end_connections,
            parameter_name_mappings=parameter_name_mappings,
            output_shape_data=output_shape_data,
        )

        # Process ALL parameters with OUTPUT or PROPERTY modes for comprehensive coverage
        self._create_end_node_data_parameters_and_connections(
            request=request,
            package_nodes=package_nodes,
            node_name_to_uuid=node_name_to_uuid,
            end_node_uuid=end_node_uuid,
            end_node_name=end_node_name,
            end_node_parameter_commands=end_node_parameter_commands,
            package_to_end_connections=package_to_end_connections,
            parameter_name_mappings=parameter_name_mappings,
            output_shape_data=output_shape_data,
        )

        # Build complete SerializedNodeCommands for end node
        end_node_dependencies = NodeDependencies()
        end_node_dependencies.libraries.add(end_node_library_details)

        end_node_commands = SerializedNodeCommands(
            create_node_command=end_create_node_command,
            element_modification_commands=end_node_parameter_commands,
            node_dependencies=end_node_dependencies,
            node_uuid=end_node_uuid,
        )

        end_node_result = PackagingEndNodeResult(
            end_node_commands=end_node_commands,
            package_to_end_connections=package_to_end_connections,
            output_shape_data=output_shape_data,
        )

        return MultiNodeEndNodeResult(
            packaging_result=end_node_result,
            parameter_name_mappings=parameter_name_mappings,
            alter_parameter_commands=[],
        )

    def _create_end_node_control_connections(  # noqa: PLR0913
        self,
        request: PackageNodesAsSerializedFlowRequest,
        package_nodes: list[BaseNode],
        node_connections_dict: dict[str, ConnectionAnalysis],  # Contains only EXTERNAL connections
        node_name_to_uuid: dict[
            str, SerializedNodeCommands.NodeUUID
        ],  # Map node names to UUIDs for connection creation
        end_node_uuid: SerializedNodeCommands.NodeUUID,
        end_node_name: str,
        end_node_parameter_commands: list[
            AddParameterToNodeRequest
        ],  # OUTPUT: Will populate with parameters to add to end node
        package_to_end_connections: list[
            SerializedFlowCommands.IndirectConnectionSerialization
        ],  # OUTPUT: Will populate with connections to add
        parameter_name_mappings: dict[
            SanitizedParameterName, OriginalNodeParameter
        ],  # OUTPUT: Will populate rosetta stone for parameter names so customer knows how to map mangled names back to original nodes.
        output_shape_data: WorkflowShapeNodes,  # OUTPUT: Will populate with workflow shape data
    ) -> None:
        """Create control connections and parameters on end node for EXTERNAL control flow connections."""
        for package_node in package_nodes:
            node_connection_analysis = node_connections_dict.get(package_node.name)
            if node_connection_analysis is None:
                # This node has no external connections (neither incoming nor outgoing), skip it
                continue

            # Handle external outgoing control connections
            for control_conn in node_connection_analysis.outgoing_control_connections:
                # Get the source parameter for validation and processing
                source_param = package_node.get_parameter_by_name(control_conn.source_parameter_name)
                if source_param is None:
                    msg = f"External control connection references parameter '{control_conn.source_parameter_name}' on node '{package_node.name}' which does not exist. This indicates a data consistency issue."
                    raise ValueError(msg)

                # Use comprehensive helper to process this control parameter
                self._process_parameter_for_end_node(
                    request=request,
                    parameter=source_param,
                    node_name=package_node.name,
                    node_uuid=node_name_to_uuid[package_node.name],
                    end_node_name=end_node_name,
                    end_node_uuid=end_node_uuid,
                    tooltip=f"Control output {control_conn.source_parameter_name} from packaged node {package_node.name}",
                    end_node_parameter_commands=end_node_parameter_commands,
                    package_to_end_connections=package_to_end_connections,
                    parameter_name_mappings=parameter_name_mappings,
                    output_shape_data=output_shape_data,
                )

    def _create_end_node_data_parameters_and_connections(  # noqa: PLR0913
        self,
        request: PackageNodesAsSerializedFlowRequest,
        package_nodes: list[BaseNode],
        node_name_to_uuid: dict[str, SerializedNodeCommands.NodeUUID],
        end_node_uuid: SerializedNodeCommands.NodeUUID,
        end_node_name: str,
        end_node_parameter_commands: list[
            AddParameterToNodeRequest
        ],  # OUTPUT: Will populate with parameters to add to end node
        package_to_end_connections: list[
            SerializedFlowCommands.IndirectConnectionSerialization
        ],  # OUTPUT: Will populate with connections to add
        parameter_name_mappings: dict[
            SanitizedParameterName, OriginalNodeParameter
        ],  # OUTPUT: Will populate rosetta stone for parameter names
        output_shape_data: WorkflowShapeNodes,  # OUTPUT: Will populate with workflow shape data
    ) -> None:
        """Create data parameters and connections on end node for all OUTPUT/PROPERTY parameters from packaged nodes."""
        for package_node in package_nodes:
            package_node_uuid = node_name_to_uuid[package_node.name]

            for package_param in package_node.parameters:
                # Only process parameters with OUTPUT or PROPERTY mode
                has_output_mode = ParameterMode.OUTPUT in package_param.allowed_modes
                has_property_mode = ParameterMode.PROPERTY in package_param.allowed_modes

                if not has_output_mode and not has_property_mode:
                    continue

                # Skip control parameters - those are handled by the control connections helper
                if package_param.output_type == ParameterTypeBuiltin.CONTROL_TYPE.value:
                    continue

                # Use comprehensive helper to process this data parameter
                self._process_parameter_for_end_node(
                    request=request,
                    parameter=package_param,
                    node_name=package_node.name,
                    node_uuid=package_node_uuid,
                    end_node_name=end_node_name,
                    end_node_uuid=end_node_uuid,
                    tooltip=f"Output parameter {package_param.name} from packaged node {package_node.name}",
                    end_node_parameter_commands=end_node_parameter_commands,
                    package_to_end_connections=package_to_end_connections,
                    parameter_name_mappings=parameter_name_mappings,
                    output_shape_data=output_shape_data,
                )

    def _process_parameter_for_end_node(  # noqa: PLR0913
        self,
        request: PackageNodesAsSerializedFlowRequest,
        parameter: Parameter,
        node_name: str,
        node_uuid: SerializedNodeCommands.NodeUUID,
        end_node_name: str,
        end_node_uuid: SerializedNodeCommands.NodeUUID,
        tooltip: str,
        end_node_parameter_commands: list[
            AddParameterToNodeRequest
        ],  # OUTPUT: Will populate with parameters to add to end node
        package_to_end_connections: list[
            SerializedFlowCommands.IndirectConnectionSerialization
        ],  # OUTPUT: Will populate with connections to add
        parameter_name_mappings: dict[
            SanitizedParameterName, OriginalNodeParameter
        ],  # OUTPUT: Will populate rosetta stone for parameter names
        output_shape_data: WorkflowShapeNodes,  # OUTPUT: Will populate with workflow shape data
    ) -> None:
        """Process a single parameter for inclusion in the end node, handling all aspects of parameter creation and connection."""
        # Create sanitized parameter name with collision avoidance
        sanitized_param_name = self._generate_sanitized_parameter_name(
            prefix=request.output_parameter_prefix,
            node_name=node_name,
            parameter_name=parameter.name,
        )

        # Build parameter name mapping for rosetta stone
        parameter_name_mappings[sanitized_param_name] = OriginalNodeParameter(
            node_name=node_name,
            parameter_name=parameter.name,
        )

        # Extract parameter shape info for workflow shape (outputs to external consumers)
        param_shape_info = GriptapeNodes.WorkflowManager().extract_parameter_shape_info(
            parameter, include_control_params=True
        )
        if param_shape_info is not None:
            if end_node_name not in output_shape_data:
                output_shape_data[end_node_name] = {}
            output_shape_data[end_node_name][sanitized_param_name] = param_shape_info

        # Create parameter command for end node
        add_param_request = AddParameterToNodeRequest(
            node_name=end_node_name,
            parameter_name=sanitized_param_name,
            type=parameter.output_type,
            default_value=None,
            tooltip=tooltip,
            initial_setup=True,
        )
        end_node_parameter_commands.append(add_param_request)

        # Create connection from package node to end node
        package_to_end_connection = SerializedFlowCommands.IndirectConnectionSerialization(
            source_node_uuid=node_uuid,
            source_parameter_name=parameter.name,
            target_node_uuid=end_node_uuid,
            target_parameter_name=sanitized_param_name,
        )
        package_to_end_connections.append(package_to_end_connection)

    def _create_multi_node_start_node_with_connections(  # noqa: PLR0913
        self,
        request: PackageNodesAsSerializedFlowRequest,
        library_version: str,
        unique_parameter_uuid_to_values: dict[SerializedNodeCommands.UniqueParameterValueUUID, Any],
        serialized_parameter_value_tracker: SerializedParameterValueTracker,
        node_name_to_uuid: dict[str, SerializedNodeCommands.NodeUUID],
        external_connections_dict: dict[
            str, ConnectionAnalysis
        ],  # Contains EXTERNAL connections only - used to determine which parameters need start node inputs
    ) -> PackagingStartNodeResult | PackageNodesAsSerializedFlowResultFailure:
        """Create start node commands and connections for external incoming connections."""
        # Generate UUID and name for start node
        start_node_uuid = SerializedNodeCommands.NodeUUID(str(uuid4()))
        start_node_name = "Start_Package_MultiNode"

        # Build start node CreateNodeRequest
        start_create_node_command = CreateNodeRequest(
            node_type=request.start_node_type,  # type: ignore[arg-type]  # Guaranteed non-None by handler
            specific_library_name=request.start_end_specific_library_name,
            node_name=start_node_name,
            metadata={},
            initial_setup=True,
            create_error_proxy_on_failure=False,
        )

        # Create library details
        start_node_library_details = LibraryNameAndVersion(
            library_name=request.start_end_specific_library_name,
            library_version=library_version,
        )

        # Create parameter modification commands and connection mappings for the start node
        start_node_parameter_commands = []
        start_to_package_connections = []
        start_node_parameter_value_commands = []
        input_shape_data: WorkflowShapeNodes = {}

        # Iterate through all EXTERNAL, INCOMING, DATA connections.
        # We will then, for each connection:
        #  1. Generate a mangled name
        #  2. Add parameter with the mangled name for each connection source on the Start Node object
        #  3. Extract the value from the source node and have it assigned to the Start Node so that it can be propagated
        #  4. Create a connection from the Start Node to the package node
        for target_node_name, connection_analysis in external_connections_dict.items():
            result = self._create_start_node_parameters_and_connections_for_incoming_data(
                target_node_name=target_node_name,
                incoming_data_connections=connection_analysis.incoming_data_connections,
                output_parameter_prefix=request.output_parameter_prefix,
                start_node_name=start_node_name,
                start_node_uuid=start_node_uuid,
                start_create_node_command=start_create_node_command,
                node_name_to_uuid=node_name_to_uuid,
                unique_parameter_uuid_to_values=unique_parameter_uuid_to_values,
                serialized_parameter_value_tracker=serialized_parameter_value_tracker,
            )
            if isinstance(result, PackageNodesAsSerializedFlowResultFailure):
                return result

            # Accumulate results from helper
            start_node_parameter_commands.extend(result.parameter_commands)
            start_to_package_connections.extend(result.data_connections)
            start_node_parameter_value_commands.extend(result.parameter_value_commands)
            # Merge input shape data
            for node_name, params in result.input_shape_data.items():
                if node_name not in input_shape_data:
                    input_shape_data[node_name] = {}
                input_shape_data[node_name].update(params)

        # Create all control connections
        control_connections = self._create_start_node_control_connections(
            request=request,
            start_node_uuid=start_node_uuid,
            node_name_to_uuid=node_name_to_uuid,
        )
        if isinstance(control_connections, PackageNodesAsSerializedFlowResultFailure):
            return control_connections

        # Add control connections to the same list as data connections
        start_to_package_connections.extend(control_connections)

        # Build complete SerializedNodeCommands for start node
        start_node_dependencies = NodeDependencies()
        start_node_dependencies.libraries.add(start_node_library_details)

        start_node_commands = SerializedNodeCommands(
            create_node_command=start_create_node_command,
            element_modification_commands=start_node_parameter_commands,
            node_dependencies=start_node_dependencies,
            node_uuid=start_node_uuid,
        )

        return PackagingStartNodeResult(
            start_node_commands=start_node_commands,
            start_to_package_connections=start_to_package_connections,
            input_shape_data=input_shape_data,
            start_node_parameter_value_commands=start_node_parameter_value_commands,
        )

    def _create_start_node_parameters_and_connections_for_incoming_data(  # noqa: PLR0913
        self,
        target_node_name: str,
        incoming_data_connections: list[IncomingConnection],
        output_parameter_prefix: str,
        start_node_name: str,
        start_node_uuid: SerializedNodeCommands.NodeUUID,
        start_create_node_command: CreateNodeRequest,
        node_name_to_uuid: dict[str, SerializedNodeCommands.NodeUUID],
        unique_parameter_uuid_to_values: dict[SerializedNodeCommands.UniqueParameterValueUUID, Any],
        serialized_parameter_value_tracker: SerializedParameterValueTracker,
    ) -> StartNodeIncomingDataResult | PackageNodesAsSerializedFlowResultFailure:
        """Create parameters and connections for incoming data connections to a specific target node."""
        start_node_parameter_commands = []
        start_to_package_connections = []
        start_node_parameter_value_commands = []
        input_shape_data: WorkflowShapeNodes = {}

        for connection in incoming_data_connections:
            target_parameter_name = connection.target_parameter_name

            # Create sanitized parameter name with prefix + node + parameter
            param_name = self._generate_sanitized_parameter_name(
                prefix=output_parameter_prefix,
                node_name=target_node_name,
                parameter_name=target_parameter_name,
            )

            # Get the source node to determine parameter type (from the external connection)
            try:
                source_node = GriptapeNodes.NodeManager().get_node_by_name(connection.source_node_name)
            except ValueError as err:
                details = f"Attempted to package nodes as serialized flow. Failed because source node '{connection.source_node_name}' from incoming connection could not be found. Error: {err}."
                return PackageNodesAsSerializedFlowResultFailure(result_details=details)

            # Get the source parameter
            source_param = source_node.get_parameter_by_name(connection.source_parameter_name)
            if not source_param:
                details = f"Attempted to package nodes as serialized flow. Failed because source parameter '{connection.source_parameter_name}' on node '{connection.source_node_name}' from incoming connection could not be found."
                return PackageNodesAsSerializedFlowResultFailure(result_details=details)

            # Extract parameter shape info for workflow shape (inputs from external sources)
            param_shape_info = GriptapeNodes.WorkflowManager().extract_parameter_shape_info(
                source_param, include_control_params=True
            )
            if param_shape_info is not None:
                if start_node_name not in input_shape_data:
                    input_shape_data[start_node_name] = {}
                input_shape_data[start_node_name][param_name] = param_shape_info

            # Extract parameter value from source node to set on start node
            param_value_commands = GriptapeNodes.NodeManager().handle_parameter_value_saving(
                parameter=source_param,
                node=source_node,
                unique_parameter_uuid_to_values=unique_parameter_uuid_to_values,
                serialized_parameter_value_tracker=serialized_parameter_value_tracker,
                create_node_request=start_create_node_command,
            )
            if param_value_commands is not None:
                # Modify each command to target the start node parameter instead
                for param_value_command in param_value_commands:
                    param_value_command.set_parameter_value_command.node_name = start_node_name
                    param_value_command.set_parameter_value_command.parameter_name = param_name
                    start_node_parameter_value_commands.append(param_value_command)

            # Create parameter command for start node (following single-node pattern exactly)
            add_param_request = AddParameterToNodeRequest(
                node_name=start_node_name,
                parameter_name=param_name,
                type=source_param.output_type,
                default_value=None,
                tooltip=f"Parameter {target_parameter_name} from node {target_node_name} in packaged flow",
                initial_setup=True,
            )
            start_node_parameter_commands.append(add_param_request)

            # Get target node UUID from mapping
            target_node_uuid = node_name_to_uuid.get(target_node_name)
            if target_node_uuid is None:
                details = f"Attempted to package nodes as serialized flow. Failed because target node '{target_node_name}' UUID not found in mapping."
                return PackageNodesAsSerializedFlowResultFailure(result_details=details)

            # Create connection from start node to target node
            start_to_package_connections.append(
                SerializedFlowCommands.IndirectConnectionSerialization(
                    source_node_uuid=start_node_uuid,
                    source_parameter_name=param_name,
                    target_node_uuid=target_node_uuid,
                    target_parameter_name=target_parameter_name,
                )
            )

        return StartNodeIncomingDataResult(
            parameter_commands=start_node_parameter_commands,
            data_connections=start_to_package_connections,
            input_shape_data=input_shape_data,
            parameter_value_commands=start_node_parameter_value_commands,
        )

    def _create_start_node_control_connections(
        self,
        request: PackageNodesAsSerializedFlowRequest,
        start_node_uuid: SerializedNodeCommands.NodeUUID,
        node_name_to_uuid: dict[str, SerializedNodeCommands.NodeUUID],
    ) -> list[SerializedFlowCommands.IndirectConnectionSerialization] | PackageNodesAsSerializedFlowResultFailure:
        """Create control connection from start node to entry control node.

        Args:
            request: The packaging request with control flow configuration
            start_node_uuid: UUID of the start node
            node_name_to_uuid: Mapping of node names to UUIDs for lookup

        Returns:
            List of control connections or failure result
        """
        control_connections = []

        # Connect start node to specified entry control node (if specified)
        if request.entry_control_node_name:
            # Get the entry node (already validated to exist)
            entry_node = GriptapeNodes.NodeManager().get_node_by_name(request.entry_control_node_name)
            entry_node_uuid = node_name_to_uuid[request.entry_control_node_name]

            # Connect start node to specified entry control node
            control_connection_result = self._create_start_node_control_connection(
                entry_control_parameter_name=request.entry_control_parameter_name,
                start_node_uuid=start_node_uuid,
                package_node_uuid=entry_node_uuid,
                package_node=entry_node,
            )
            if isinstance(control_connection_result, PackageNodesAsSerializedFlowResultFailure):
                return PackageNodesAsSerializedFlowResultFailure(
                    result_details=control_connection_result.result_details
                )

            control_connections.append(control_connection_result)

        return control_connections

    def _create_start_node_control_connection(
        self,
        entry_control_parameter_name: str | None,
        start_node_uuid: SerializedNodeCommands.NodeUUID,
        package_node_uuid: SerializedNodeCommands.NodeUUID,
        package_node: BaseNode,
    ) -> SerializedFlowCommands.IndirectConnectionSerialization | PackageNodesAsSerializedFlowResultFailure:
        """Create control flow connection from start node to package node.

        Connects the start node's first control output to the specified or first available package node control input.
        """
        if entry_control_parameter_name is not None:
            # Case 1: Specific entry parameter name provided
            package_control_input_name = entry_control_parameter_name
        else:
            # Case 2: Find the first available control input parameter
            package_control_input_name = None
            for param in package_node.parameters:
                if ParameterTypeBuiltin.CONTROL_TYPE.value in param.input_types:
                    package_control_input_name = param.name
                    logger.warning(
                        "No entry_control_parameter_name specified for packaging node '%s'. "
                        "Using first available control input parameter: '%s'",
                        package_node.name,
                        package_control_input_name,
                    )
                    break

            if package_control_input_name is None:
                details = f"Attempted to package node '{package_node.name}'. Failed because no control input parameters found on the node, so cannot create control flow connection."
                return PackageNodesAsSerializedFlowResultFailure(result_details=details)

        # StartNode always has a control output parameter with name "exec_out"
        source_control_parameter_name = "exec_out"

        # Create the connection
        control_connection = SerializedFlowCommands.IndirectConnectionSerialization(
            source_node_uuid=start_node_uuid,
            source_parameter_name=source_control_parameter_name,
            target_node_uuid=package_node_uuid,
            target_parameter_name=package_control_input_name,
        )
        return control_connection

    def _collect_all_connections_for_multi_node_package(
        self,
        start_node_result: PackagingStartNodeResult,
        end_node_packaging_result: PackagingEndNodeResult,
        packaged_nodes_internal_connections: list[SerializedFlowCommands.IndirectConnectionSerialization],
    ) -> list[SerializedFlowCommands.IndirectConnectionSerialization]:
        """Collect all connections for the multi-node packaged flow.

        Returns a list containing:
        1. Start node connections (data + control)
        2. End node connections (data)
        3. Internal package node connections

        Args:
            start_node_result: Result containing start node and its connections
            end_node_packaging_result: Result containing end node and its connections
            packaged_nodes_internal_connections: Internal connections between package nodes

        Returns:
            List of all connections for the packaged flow
        """
        all_connections = []

        # Add start and end node connections
        all_connections.extend(start_node_result.start_to_package_connections)
        all_connections.extend(end_node_packaging_result.package_to_end_connections)

        # Add internal package node connections
        all_connections.extend(packaged_nodes_internal_connections)

        return all_connections

    def _generate_sanitized_parameter_name(self, prefix: str, node_name: str, parameter_name: str) -> str:
        """Generate a sanitized parameter name for multi-node packaging.

        Creates a parameter name in the format: prefix + sanitized_node_name + _ + parameter_name
        Node names are sanitized by replacing spaces and dots with underscores.

        Args:
            prefix: Prefix for the parameter name (e.g., "packaged_node_")
            node_name: Original node name (may contain spaces, dots, etc.)
            parameter_name: Original parameter name

        Returns:
            Sanitized parameter name safe for use (e.g., "packaged_node_Merge_Texts_merge_string")
        """
        sanitized_node_name = node_name.replace(" ", "_").replace(".", "_")
        return f"{prefix}{sanitized_node_name}_{parameter_name}"

    async def on_start_flow_request(self, request: StartFlowRequest) -> ResultPayload:  # noqa: C901, PLR0911, PLR0912
        # which flow
        flow_name = request.flow_name
        if not flow_name:
            details = "Must provide flow name to start a flow."

            return StartFlowResultFailure(validation_exceptions=[], result_details=details)
        # get the flow by ID
        try:
            flow = self.get_flow_by_name(flow_name)
        except KeyError as err:
            details = f"Cannot start flow. Error: {err}"
            return StartFlowResultFailure(validation_exceptions=[err], result_details=details)
        # Check to see if the flow is already running.
        if self.check_for_existing_running_flow():
            details = "Cannot start flow. Flow is already running."
            return StartFlowResultFailure(validation_exceptions=[], result_details=details)
        # A node has been provided to either start or to run up to.
        if request.flow_node_name:
            flow_node_name = request.flow_node_name
            flow_node = GriptapeNodes.ObjectManager().attempt_get_object_by_name_as_type(flow_node_name, BaseNode)
            if not flow_node:
                details = f"Provided node with name {flow_node_name} does not exist"
                return StartFlowResultFailure(validation_exceptions=[], result_details=details)
            # lets get the first control node in the flow!
            start_node = self.get_start_node_from_node(flow, flow_node)
            # if the start is not the node provided, set a breakpoint at the stop (we're running up until there)
            if not start_node:
                details = f"Start node for node with name {flow_node_name} does not exist"
                return StartFlowResultFailure(validation_exceptions=[], result_details=details)
            if start_node != flow_node:
                flow_node.stop_flow = True
        else:
            # we wont hit this if we dont have a request id, our requests always have nodes
            # If there is a request, reinitialize the queue
            self.get_start_node_queue()  # initialize the start flow queue!
            start_node = None
        # Run Validation before starting a flow
        result = await self.on_validate_flow_dependencies_request(
            ValidateFlowDependenciesRequest(flow_name=flow_name, flow_node_name=start_node.name if start_node else None)
        )
        try:
            if not result.succeeded():
                details = f"Couldn't start flow with name {flow_name}. Flow Validation Failed"
                return StartFlowResultFailure(validation_exceptions=[], result_details=details)
            result = cast("ValidateFlowDependenciesResultSuccess", result)

            if not result.validation_succeeded:
                details = f"Couldn't start flow with name {flow_name}. Flow Validation Failed."
                if len(result.exceptions) > 0:
                    for exception in result.exceptions:
                        details = f"{details}\n\t{exception}"
                return StartFlowResultFailure(validation_exceptions=result.exceptions, result_details=details)
        except Exception as e:
            details = f"Couldn't start flow with name {flow_name}. Flow Validation Failed: {e}"
            return StartFlowResultFailure(validation_exceptions=[e], result_details=details)
        # By now, it has been validated with no exceptions.
        try:
            await self.start_flow(
                flow,
                start_node,
                debug_mode=request.debug_mode,
                pickle_control_flow_result=request.pickle_control_flow_result,
            )
        except Exception as e:
            details = f"Failed to kick off flow with name {flow_name}. Exception occurred: {e} "
            return StartFlowResultFailure(validation_exceptions=[e], result_details=details)

        details = f"Successfully kicked off flow with name {flow_name}"

        return StartFlowResultSuccess(result_details=details)

    async def on_start_flow_from_node_request(self, request: StartFlowFromNodeRequest) -> ResultPayload:  # noqa: C901, PLR0911
        # which flow
        flow_name = request.flow_name
        if not flow_name:
            details = "Must provide flow name to start a flow."

            return StartFlowResultFailure(validation_exceptions=[], result_details=details)
        # get the flow by ID
        try:
            flow = self.get_flow_by_name(flow_name)
        except KeyError as err:
            details = f"Cannot start flow. Error: {err}"
            return StartFlowFromNodeResultFailure(validation_exceptions=[err], result_details=details)
        # Check to see if the flow is already running.
        if self.check_for_existing_running_flow():
            details = "Cannot start flow. Flow is already running."
            return StartFlowFromNodeResultFailure(validation_exceptions=[], result_details=details)
        node_name = request.node_name
        if node_name is None:
            details = "Must provide node name to start a flow."
            return StartFlowFromNodeResultFailure(validation_exceptions=[], result_details=details)
        start_node = GriptapeNodes.ObjectManager().attempt_get_object_by_name_as_type(node_name, BaseNode)
        if not start_node:
            details = f"Provided node with name {node_name} does not exist"
            return StartFlowResultFailure(validation_exceptions=[], result_details=details)
        result = await self.on_validate_flow_dependencies_request(
            ValidateFlowDependenciesRequest(flow_name=flow_name, flow_node_name=start_node.name if start_node else None)
        )
        try:
            if not result.succeeded():
                details = f"Couldn't start flow with name {flow_name}. Flow Validation Failed"
                return StartFlowFromNodeResultFailure(validation_exceptions=[], result_details=details)
            result = cast("ValidateFlowDependenciesResultSuccess", result)

            if not result.validation_succeeded:
                details = f"Couldn't start flow with name {flow_name}. Flow Validation Failed."
                if len(result.exceptions) > 0:
                    for exception in result.exceptions:
                        details = f"{details}\n\t{exception}"
                return StartFlowFromNodeResultFailure(validation_exceptions=result.exceptions, result_details=details)
        except Exception as e:
            details = f"Couldn't start flow with name {flow_name}. Flow Validation Failed: {e}"
            return StartFlowFromNodeResultFailure(validation_exceptions=[e], result_details=details)
        # By now, it has been validated with no exceptions.
        try:
            await self.start_flow(
                flow,
                start_node,
                debug_mode=request.debug_mode,
                pickle_control_flow_result=request.pickle_control_flow_result,
            )
        except Exception as e:
            details = f"Failed to kick off flow with name {flow_name}. Exception occurred: {e} "
            return StartFlowFromNodeResultFailure(validation_exceptions=[e], result_details=details)

        details = f"Successfully kicked off flow with name {flow_name}"

        return StartFlowFromNodeResultSuccess(result_details=details)

    def on_get_flow_state_request(self, event: GetFlowStateRequest) -> ResultPayload:
        flow_name = event.flow_name
        if not flow_name:
            details = "Could not get flow state. No flow name was provided."
            return GetFlowStateResultFailure(result_details=details)
        try:
            flow = self.get_flow_by_name(flow_name)
        except KeyError as err:
            details = f"Could not get flow state. Error: {err}"
            return GetFlowStateResultFailure(result_details=details)
        try:
            control_nodes, resolving_nodes, involved_nodes = self.flow_state(flow)
        except Exception as e:
            details = f"Failed to get flow state of flow with name {flow_name}. Exception occurred: {e} "
            logger.exception(details)
            return GetFlowStateResultFailure(result_details=details)
        details = f"Successfully got flow state for flow with name {flow_name}."
        return GetFlowStateResultSuccess(
            control_nodes=control_nodes,
            resolving_nodes=resolving_nodes,
            involved_nodes=involved_nodes,
            result_details=details,
        )

    async def on_cancel_flow_request(self, request: CancelFlowRequest) -> ResultPayload:
        flow_name = request.flow_name
        if not flow_name:
            details = "Could not cancel flow execution. No flow name was provided."

            return CancelFlowResultFailure(result_details=details)
        try:
            self.get_flow_by_name(flow_name)
        except KeyError as err:
            details = f"Could not cancel flow execution. Error: {err}"

            return CancelFlowResultFailure(result_details=details)
        try:
            await self.cancel_flow_run()
        except Exception as e:
            details = f"Could not cancel flow execution. Exception: {e}"

            return CancelFlowResultFailure(result_details=details)
        details = f"Successfully cancelled flow execution with name {flow_name}"

        return CancelFlowResultSuccess(result_details=details)

    async def on_single_node_step_request(self, request: SingleNodeStepRequest) -> ResultPayload:
        flow_name = request.flow_name
        if not flow_name:
            details = "Could not advance to the next step of a running workflow. No flow name was provided."

            return SingleNodeStepResultFailure(validation_exceptions=[], result_details=details)
        try:
            self.get_flow_by_name(flow_name)
        except KeyError as err:
            details = f"Could not advance to the next step of a running workflow. No flow with name {flow_name} exists. Error: {err}"

            return SingleNodeStepResultFailure(validation_exceptions=[err], result_details=details)
        try:
            flow = self.get_flow_by_name(flow_name)
            await self.single_node_step(flow)
        except Exception as e:
            details = f"Could not advance to the next step of a running workflow. Exception: {e}"
            return SingleNodeStepResultFailure(validation_exceptions=[], result_details=details)

        # All completed happily
        details = f"Successfully advanced to the next step of a running workflow with name {flow_name}"

        return SingleNodeStepResultSuccess(result_details=details)

    async def on_single_execution_step_request(self, request: SingleExecutionStepRequest) -> ResultPayload:
        flow_name = request.flow_name
        if not flow_name:
            details = "Could not advance to the next step of a running workflow. No flow name was provided."

            return SingleExecutionStepResultFailure(result_details=details)
        try:
            flow = self.get_flow_by_name(flow_name)
        except KeyError as err:
            details = f"Could not advance to the next step of a running workflow. Error: {err}."

            return SingleExecutionStepResultFailure(result_details=details)
        change_debug_mode = request.request_id is not None
        try:
            await self.single_execution_step(flow, change_debug_mode)
        except Exception as e:
            # We REALLY don't want to fail here, else we'll take the whole engine down
            try:
                if self.check_for_existing_running_flow():
                    await self.cancel_flow_run()
            except Exception as e_inner:
                details = f"Could not cancel flow execution. Exception: {e_inner}"

            details = f"Could not advance to the next step of a running workflow. Exception: {e}"
            return SingleNodeStepResultFailure(validation_exceptions=[e], result_details=details)
        details = f"Successfully advanced to the next step of a running workflow with name {flow_name}"

        return SingleExecutionStepResultSuccess(result_details=details)

    async def on_continue_execution_step_request(self, request: ContinueExecutionStepRequest) -> ResultPayload:
        flow_name = request.flow_name
        if not flow_name:
            details = "Failed to continue execution step because no flow name was provided"

            return ContinueExecutionStepResultFailure(result_details=details)
        try:
            flow = self.get_flow_by_name(flow_name)
        except KeyError as err:
            details = f"Failed to continue execution step. Error: {err}"

            return ContinueExecutionStepResultFailure(result_details=details)
        try:
            await self.continue_executing(flow)
        except Exception as e:
            details = f"Failed to continue execution step. An exception occurred: {e}."
            return ContinueExecutionStepResultFailure(result_details=details)
        details = f"Successfully continued flow with name {flow_name}"
        return ContinueExecutionStepResultSuccess(result_details=details)

    def on_unresolve_flow_request(self, request: UnresolveFlowRequest) -> ResultPayload:
        flow_name = request.flow_name
        if not flow_name:
            details = "Failed to unresolve flow because no flow name was provided"
            return UnresolveFlowResultFailure(result_details=details)
        try:
            flow = self.get_flow_by_name(flow_name)
        except KeyError as err:
            details = f"Failed to unresolve flow. Error: {err}"
            return UnresolveFlowResultFailure(result_details=details)
        try:
            self.unresolve_whole_flow(flow)
        except Exception as e:
            details = f"Failed to unresolve flow. An exception occurred: {e}."
            return UnresolveFlowResultFailure(result_details=details)
        details = f"Unresolved flow with name {flow_name}"
        return UnresolveFlowResultSuccess(result_details=details)

    async def on_validate_flow_dependencies_request(self, request: ValidateFlowDependenciesRequest) -> ResultPayload:
        flow_name = request.flow_name
        # get the flow name
        try:
            flow = self.get_flow_by_name(flow_name)
        except KeyError as err:
            details = f"Failed to validate flow. Error: {err}"
            return ValidateFlowDependenciesResultFailure(result_details=details)
        if request.flow_node_name:
            flow_node_name = request.flow_node_name
            flow_node = GriptapeNodes.ObjectManager().attempt_get_object_by_name_as_type(flow_node_name, BaseNode)
            if not flow_node:
                details = f"Provided node with name {flow_node_name} does not exist"
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
            validation_succeeded=len(all_exceptions) == 0,
            exceptions=all_exceptions,
            result_details=f"Validated flow dependencies: {len(all_exceptions)} exceptions found",
        )

    def on_list_flows_in_current_context_request(self, request: ListFlowsInCurrentContextRequest) -> ResultPayload:  # noqa: ARG002 (request isn't actually used)
        if not GriptapeNodes.ContextManager().has_current_flow():
            details = "Attempted to list Flows in the Current Context. Failed because the Current Context was empty."
            return ListFlowsInCurrentContextResultFailure(result_details=details)

        parent_flow = GriptapeNodes.ContextManager().get_current_flow()
        parent_flow_name = parent_flow.name

        # Create a list of all child flow names that point DIRECTLY to us.
        ret_list = []
        for flow_name, parent_name in self._name_to_parent_name.items():
            if parent_name == parent_flow_name:
                ret_list.append(flow_name)

        details = f"Successfully got the list of Flows in the Current Context (Flow '{parent_flow_name}')."

        return ListFlowsInCurrentContextResultSuccess(flow_names=ret_list, result_details=details)

    def _aggregate_flow_dependencies(
        self, serialized_node_commands: list[SerializedNodeCommands], sub_flows_commands: list[SerializedFlowCommands]
    ) -> NodeDependencies:
        """Aggregate dependencies from nodes and sub-flows into a single NodeDependencies object.

        Args:
            serialized_node_commands: List of serialized node commands to aggregate from
            sub_flows_commands: List of sub-flow commands to aggregate from

        Returns:
            NodeDependencies object with all dependencies merged
        """
        # Start with empty dependencies and aggregate into it
        aggregated_deps = NodeDependencies()

        # Aggregate dependencies from all nodes
        for node_cmd in serialized_node_commands:
            aggregated_deps.aggregate_from(node_cmd.node_dependencies)

        # Aggregate dependencies from all sub-flows
        for sub_flow_cmd in sub_flows_commands:
            aggregated_deps.aggregate_from(sub_flow_cmd.node_dependencies)

        return aggregated_deps

    def _aggregate_node_types_used(
        self, serialized_node_commands: list[SerializedNodeCommands], sub_flows_commands: list[SerializedFlowCommands]
    ) -> set[LibraryNameAndNodeType]:
        """Aggregate node types used from nodes and sub-flows.

        Args:
            serialized_node_commands: List of serialized node commands to aggregate from
            sub_flows_commands: List of sub-flow commands to aggregate from

        Returns:
            Set of LibraryNameAndNodeType with all node types used

        Raises:
            ValueError: If a node command has no library name specified
        """
        node_types_used: set[LibraryNameAndNodeType] = set()

        # Collect node types from all nodes in this flow
        for node_cmd in serialized_node_commands:
            node_type = node_cmd.create_node_command.node_type
            library_name = node_cmd.create_node_command.specific_library_name
            if library_name is None:
                msg = f"Node type '{node_type}' has no library name specified during serialization"
                raise ValueError(msg)
            node_types_used.add(LibraryNameAndNodeType(library_name=library_name, node_type=node_type))

        # Aggregate node types from all sub-flows
        for sub_flow_cmd in sub_flows_commands:
            node_types_used.update(sub_flow_cmd.node_types_used)

        return node_types_used

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
                return SerializeFlowToCommandsResultFailure(result_details=details)
        if flow is None:
            # Does this flow exist?
            flow = GriptapeNodes.ObjectManager().attempt_get_object_by_name_as_type(flow_name, ControlFlow)
            if flow is None:
                details = (
                    f"Attempted to serialize Flow '{flow_name}' to commands, but no Flow with that name could be found."
                )
                return SerializeFlowToCommandsResultFailure(result_details=details)

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
                return SerializeFlowToCommandsResultFailure(result_details=details)

            # Serialize each node
            for node_name in nodes_in_flow_result.node_names:
                node = GriptapeNodes.ObjectManager().attempt_get_object_by_name_as_type(node_name, BaseNode)
                if node is None:
                    details = f"Attempted to serialize Flow '{flow_name}'. Failed while attempting to serialize Node '{node_name}' within the Flow."
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
                        return SerializeFlowToCommandsResultFailure(result_details=details)

                    serialized_node = serialize_node_result.serialized_node_commands

                    # Store the serialized node's UUID for correlation to connections and setting parameter values later.
                    node_name_to_uuid[node_name] = serialized_node.node_uuid

                    serialized_node_commands.append(serialized_node)
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
                return SerializeFlowToCommandsResultFailure(result_details=details)

            sub_flow_commands = []
            for child_flow in flows_in_flow_result.flow_names:
                flow = GriptapeNodes.ObjectManager().attempt_get_object_by_name_as_type(child_flow, ControlFlow)
                if flow is None:
                    details = f"Attempted to serialize Flow '{flow_name}', but no Flow with that name could be found."
                    return SerializeFlowToCommandsResultFailure(result_details=details)

                # Check if this is a referenced workflow
                if self.is_referenced_workflow(flow):
                    # For referenced workflows, create a minimal SerializedFlowCommands with just the import command
                    referenced_workflow_name = self.get_referenced_workflow_name(flow)
                    import_command = ImportWorkflowAsReferencedSubFlowRequest(
                        workflow_name=referenced_workflow_name,  # type: ignore[arg-type] # is_referenced_workflow() guarantees this is not None
                        imported_flow_metadata=flow.metadata,
                    )

                    # Create NodeDependencies with just the referenced workflow
                    sub_flow_dependencies = NodeDependencies(
                        referenced_workflows={referenced_workflow_name}  # type: ignore[arg-type] # is_referenced_workflow() guarantees this is not None
                    )

                    serialized_flow = SerializedFlowCommands(
                        flow_initialization_command=import_command,
                        serialized_node_commands=[],
                        serialized_connections=[],
                        unique_parameter_uuid_to_values={},
                        set_parameter_value_commands={},
                        set_lock_commands_per_node={},
                        sub_flows_commands=[],
                        node_dependencies=sub_flow_dependencies,
                        node_types_used=set(),
                    )
                    sub_flow_commands.append(serialized_flow)
                else:
                    # For standalone sub-flows, use the existing recursive serialization
                    with GriptapeNodes.ContextManager().flow(flow=flow):
                        child_flow_request = SerializeFlowToCommandsRequest()
                        child_flow_result = GriptapeNodes().handle_request(child_flow_request)
                        if not isinstance(child_flow_result, SerializeFlowToCommandsResultSuccess):
                            details = f"Attempted to serialize parent flow '{flow_name}'. Failed while serializing child flow '{child_flow}'."
                            return SerializeFlowToCommandsResultFailure(result_details=details)
                        serialized_flow = child_flow_result.serialized_flow_commands
                        sub_flow_commands.append(serialized_flow)

        # Aggregate all dependencies from nodes and sub-flows
        aggregated_dependencies = self._aggregate_flow_dependencies(serialized_node_commands, sub_flow_commands)

        # Aggregate all node types used from nodes and sub-flows
        try:
            aggregated_node_types_used = self._aggregate_node_types_used(serialized_node_commands, sub_flow_commands)
        except ValueError as e:
            details = f"Attempted to serialize Flow '{flow_name}' to commands. Failed while aggregating node types: {e}"
            return SerializeFlowToCommandsResultFailure(result_details=details)

        serialized_flow = SerializedFlowCommands(
            flow_initialization_command=create_flow_request,
            serialized_node_commands=serialized_node_commands,
            serialized_connections=create_connection_commands,
            unique_parameter_uuid_to_values=unique_parameter_uuid_to_values,
            set_parameter_value_commands=set_parameter_value_commands_per_node,
            set_lock_commands_per_node=set_lock_commands_per_node,
            sub_flows_commands=sub_flow_commands,
            node_dependencies=aggregated_dependencies,
            node_types_used=aggregated_node_types_used,
        )
        details = f"Successfully serialized Flow '{flow_name}' into commands."
        result = SerializeFlowToCommandsResultSuccess(serialized_flow_commands=serialized_flow, result_details=details)
        return result

    def on_deserialize_flow_from_commands(self, request: DeserializeFlowFromCommandsRequest) -> ResultPayload:  # noqa: C901, PLR0911, PLR0912, PLR0915 (I am big and complicated and have a lot of negative edge-cases)
        # Do we want to create a NEW Flow to deserialize into, or use the one in the Current Context?
        if request.serialized_flow_commands.flow_initialization_command is None:
            if GriptapeNodes.ContextManager().has_current_flow():
                flow = GriptapeNodes.ContextManager().get_current_flow()
                flow_name = flow.name
            else:
                details = "Attempted to deserialize a set of Flow Creation commands into the Current Context. Failed because the Current Context was empty."
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
                        return DeserializeFlowFromCommandsResultFailure(result_details=details)
                    flow_name = flow_initialization_result.flow_name
                case ImportWorkflowAsReferencedSubFlowRequest():
                    if not isinstance(flow_initialization_result, ImportWorkflowAsReferencedSubFlowResultSuccess):
                        details = f"Attempted to deserialize a serialized set of Flow Creation commands. Failed to import workflow '{flow_initialization_command.workflow_name}'."
                        return DeserializeFlowFromCommandsResultFailure(result_details=details)
                    flow_name = flow_initialization_result.created_flow_name
                case _:
                    details = f"Attempted to deserialize Flow Creation commands with unknown command type: {type(flow_initialization_command).__name__}."
                    return DeserializeFlowFromCommandsResultFailure(result_details=details)

            # Adopt the newly-created flow as our current context.
            flow = GriptapeNodes.ObjectManager().attempt_get_object_by_name_as_type(flow_name, ControlFlow)
            if flow is None:
                details = f"Attempted to deserialize a serialized set of Flow Creation commands. Failed to find created flow '{flow_name}'."
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
                return DeserializeFlowFromCommandsResultFailure(result_details=details)
            target_node_uuid = indirect_connection.target_node_uuid
            if target_node_uuid not in node_uuid_to_deserialized_node_result:
                details = f"Attempted to deserialize a Flow '{flow_name}'. Failed while attempting to create a Connection for a target node that did not exist within the flow."
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
                        return DeserializeFlowFromCommandsResultFailure(result_details=details)

                    # Call the SetParameterValueRequest, subbing in the value from our unique value list.
                    indirect_set_value_command.set_parameter_value_command.value = value
                    set_parameter_value_result = GriptapeNodes.handle_request(
                        indirect_set_value_command.set_parameter_value_command
                    )
                    if set_parameter_value_result.failed():
                        details = f"Attempted to deserialize a Flow '{flow_name}'. Failed while deserializing a value assignment for node '{node.name}.{parameter_name}'."
                        return DeserializeFlowFromCommandsResultFailure(result_details=details)

        # Now the child flows.
        for sub_flow_command in request.serialized_flow_commands.sub_flows_commands:
            sub_flow_request = DeserializeFlowFromCommandsRequest(serialized_flow_commands=sub_flow_command)
            sub_flow_result = GriptapeNodes.handle_request(sub_flow_request)
            if sub_flow_result.failed():
                details = f"Attempted to deserialize a Flow '{flow_name}'. Failed while deserializing a sub-flow within the Flow."
                return DeserializeFlowFromCommandsResultFailure(result_details=details)

        details = f"Successfully deserialized Flow '{flow_name}'."
        return DeserializeFlowFromCommandsResultSuccess(flow_name=flow_name, result_details=details)

    def on_flush_request(self, request: FlushParameterChangesRequest) -> ResultPayload:  # noqa: ARG002
        obj_manager = GriptapeNodes.ObjectManager()
        GriptapeNodes.EventManager().clear_flush_in_queue()
        # Get all flows and their nodes
        nodes = obj_manager.get_filtered_subset(type=BaseNode)
        for node in nodes.values():
            # Only flush if there are actually tracked parameters
            if node._tracked_parameters:
                node.emit_parameter_changes()
        return FlushParameterChangesResultSuccess(result_details="Parameter changes flushed successfully.")

    async def start_flow(
        self,
        flow: ControlFlow,
        start_node: BaseNode | None = None,
        *,
        debug_mode: bool = False,
        pickle_control_flow_result: bool = False,
    ) -> None:
        if self.check_for_existing_running_flow():
            # If flow already exists, throw an error
            errormsg = "This workflow is already in progress. Please wait for the current process to finish before starting again."
            raise RuntimeError(errormsg)

        if start_node is None:
            if self._global_flow_queue.empty():
                errormsg = "No Flow exists. You must create at least one control connection."
                raise RuntimeError(errormsg)
            queue_item = self._global_flow_queue.get()
            start_node = queue_item.node
            self._global_flow_queue.task_done()

        # Initialize global control flow machine and DAG builder

        self._global_control_flow_machine = ControlFlowMachine(
            flow.name, pickle_control_flow_result=pickle_control_flow_result
        )
        # Set off the request here.
        try:
            await self._global_control_flow_machine.start_flow(start_node, debug_mode=debug_mode)
        except Exception:
            if self.check_for_existing_running_flow():
                # Cleanup proxy nodes before canceling flow
                self._global_control_flow_machine.cleanup_proxy_nodes()
                await self.cancel_flow_run()
            raise
        GriptapeNodes.EventManager().put_event(
            ExecutionGriptapeNodeEvent(wrapped_event=ExecutionEvent(payload=InvolvedNodesEvent(involved_nodes=[])))
        )

    def check_for_existing_running_flow(self) -> bool:
        if self._global_control_flow_machine is None:
            return False
        current_state = self._global_control_flow_machine.current_state
        if current_state and current_state is not CompleteState:
            # Flow already exists in progress
            return True
        return bool(
            not self._global_control_flow_machine.context.resolution_machine.is_complete()
            and self._global_control_flow_machine.context.resolution_machine.is_started()
        )

    async def cancel_flow_run(self) -> None:
        if not self.check_for_existing_running_flow():
            errormsg = "Flow has not yet been started. Cannot cancel flow that hasn't begun."
            raise RuntimeError(errormsg)
        self._global_flow_queue.queue.clear()

        # Request cancellation on all nodes and wait for them to complete
        if self._global_control_flow_machine is not None:
            await self._global_control_flow_machine.cancel_flow()

        # Cleanup proxy nodes and restore connections
        if self._global_control_flow_machine is not None:
            self._global_control_flow_machine.cleanup_proxy_nodes()

        # Reset control flow machine
        if self._global_control_flow_machine is not None:
            self._global_control_flow_machine.reset_machine(cancel=True)
        self._global_single_node_resolution = False
        self._global_dag_builder.clear()
        logger.debug("Cancelling flow run")

        GriptapeNodes.EventManager().put_event(
            ExecutionGriptapeNodeEvent(wrapped_event=ExecutionEvent(payload=InvolvedNodesEvent(involved_nodes=[])))
        )
        GriptapeNodes.EventManager().put_event(
            ExecutionGriptapeNodeEvent(wrapped_event=ExecutionEvent(payload=ControlFlowCancelledEvent()))
        )

    def reset_global_execution_state(self) -> None:
        """Reset all global execution state - useful when clearing all workflows."""
        self._global_flow_queue.queue.clear()

        # Cleanup proxy nodes and restore connections before resetting machine
        if self._global_control_flow_machine is not None:
            self._global_control_flow_machine.cleanup_proxy_nodes()
            self._global_control_flow_machine.reset_machine()

        # Reset control flow machine
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
        queue_item = self._global_flow_queue.get()
        self._global_flow_queue.task_done()
        return queue_item.node

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
    async def _handle_flow_start_if_not_running(
        self,
        flow: ControlFlow,
        *,
        debug_mode: bool,
        error_message: str,
    ) -> None:
        """Common logic for starting flow execution if not already running."""
        if not self.check_for_existing_running_flow():
            if self._global_flow_queue.empty():
                raise RuntimeError(error_message)
            queue_item = self._global_flow_queue.get()
            start_node = queue_item.node
            self._global_flow_queue.task_done()
            # Get or create machine
            if self._global_control_flow_machine is None:
                self._global_control_flow_machine = ControlFlowMachine(flow.name)
            await self._global_control_flow_machine.start_flow(start_node, debug_mode=debug_mode)

    async def _handle_post_execution_queue_processing(self, *, debug_mode: bool) -> None:
        """Handle execution queue processing after execution completes."""
        if not self.check_for_existing_running_flow() and not self._global_flow_queue.empty():
            queue_item = self._global_flow_queue.get()
            start_node = queue_item.node
            self._global_flow_queue.task_done()
            machine = self._global_control_flow_machine
            if machine is not None:
                await machine.start_flow(start_node, debug_mode=debug_mode)

    async def resolve_singular_node(self, flow: ControlFlow, node: BaseNode, *, debug_mode: bool = False) -> None:
        # We are now going to have different behavior depending on how the node is behaving.
        if self.check_for_existing_running_flow():
            # Now we know something is running, it's ParallelResolutionMachine, and that we are in single_node_resolution.
            self._global_dag_builder.add_node_with_dependencies(node, node.name)
            # Emit involved nodes update after adding node to DAG
            involved_nodes = list(self._global_dag_builder.node_to_reference.keys())
            GriptapeNodes.EventManager().put_event(
                ExecutionGriptapeNodeEvent(
                    wrapped_event=ExecutionEvent(payload=InvolvedNodesEvent(involved_nodes=involved_nodes))
                )
            )
        else:
            # Set that we are only working on one node right now!
            self._global_single_node_resolution = True
            # Get or create machine
            self._global_control_flow_machine = ControlFlowMachine(flow.name)
            self._global_control_flow_machine.context.current_nodes = [node]
            resolution_machine = self._global_control_flow_machine.resolution_machine
            resolution_machine.change_debug_mode(debug_mode=debug_mode)
            node.state = NodeResolutionState.UNRESOLVED
            # Build the DAG for the node
            if isinstance(resolution_machine, ParallelResolutionMachine):
                self._global_dag_builder.add_node_with_dependencies(node)
                resolution_machine.context.dag_builder = self._global_dag_builder
                involved_nodes = list(self._global_dag_builder.node_to_reference.keys())
            else:
                involved_nodes = list(flow.nodes.keys())
            # Send a InvolvedNodesRequest

            GriptapeNodes.EventManager().put_event(
                ExecutionGriptapeNodeEvent(
                    wrapped_event=ExecutionEvent(payload=InvolvedNodesEvent(involved_nodes=involved_nodes))
                )
            )
            try:
                await self._global_control_flow_machine.start_flow(
                    start_node=node, end_node=node, debug_mode=debug_mode
                )
            except Exception as e:
                logger.exception("Exception during single node resolution")
                if self.check_for_existing_running_flow():
                    if self._global_control_flow_machine is not None:
                        self._global_control_flow_machine.cleanup_proxy_nodes()
                    await self.cancel_flow_run()
                raise RuntimeError(e) from e
            if resolution_machine.is_complete():
                self._global_single_node_resolution = False
                self._global_control_flow_machine.context.current_nodes = []
            GriptapeNodes.EventManager().put_event(
                ExecutionGriptapeNodeEvent(wrapped_event=ExecutionEvent(payload=InvolvedNodesEvent(involved_nodes=[])))
            )

    async def single_execution_step(self, flow: ControlFlow, change_debug_mode: bool) -> None:  # noqa: FBT001
        # do a granular step
        await self._handle_flow_start_if_not_running(
            flow, debug_mode=True, error_message="Flow has not yet been started. Cannot step while no flow has begun."
        )
        if not self.check_for_existing_running_flow():
            return
        if self._global_control_flow_machine is not None:
            await self._global_control_flow_machine.granular_step(change_debug_mode)
            resolution_machine = self._global_control_flow_machine.resolution_machine
            if self._global_single_node_resolution:
                resolution_machine = self._global_control_flow_machine.resolution_machine
            if resolution_machine.is_complete():
                self._global_single_node_resolution = False

    async def single_node_step(self, flow: ControlFlow) -> None:
        # It won't call single_node_step without an existing flow running from US.
        await self._handle_flow_start_if_not_running(
            flow, debug_mode=True, error_message="Flow has not yet been started. Cannot step while no flow has begun."
        )
        if not self.check_for_existing_running_flow():
            return
        # Step over a whole node
        if self._global_single_node_resolution:
            msg = "Cannot step through the Control Flow in Single Node Execution"
            raise RuntimeError(msg)
        if self._global_control_flow_machine is not None:
            await self._global_control_flow_machine.node_step()
        # Start the next resolution step now please.
        await self._handle_post_execution_queue_processing(debug_mode=True)

    async def continue_executing(self, flow: ControlFlow) -> None:
        await self._handle_flow_start_if_not_running(
            flow, debug_mode=False, error_message="Flow has not yet been started. Cannot step while no flow has begun."
        )
        if not self.check_for_existing_running_flow():
            return
        # Turn all debugging to false and continue on
        if self._global_control_flow_machine is not None and self._global_control_flow_machine is not None:
            self._global_control_flow_machine.change_debug_mode(False)
            if self._global_single_node_resolution:
                if self._global_control_flow_machine.resolution_machine.is_complete():
                    self._global_single_node_resolution = False
                else:
                    await self._global_control_flow_machine.resolution_machine.update()
            else:
                await self._global_control_flow_machine.node_step()
        # Now it is done executing. make sure it's actually done?
        await self._handle_post_execution_queue_processing(debug_mode=False)

    def unresolve_whole_flow(self, flow: ControlFlow) -> None:
        for node in flow.nodes.values():
            node.make_node_unresolved(current_states_to_trigger_change_event=None)
            # Clear entry control parameter for new execution
            node.set_entry_control_parameter(None)

    def flow_state(self, flow: ControlFlow) -> tuple[list[str], list[str], list[str]]:
        if not self.check_for_existing_running_flow():
            return [], [], []
        if self._global_control_flow_machine is None:
            return [], [], []
        control_flow_context = self._global_control_flow_machine.context
        current_control_nodes = (
            [control_flow_node.name for control_flow_node in control_flow_context.current_nodes]
            if control_flow_context.current_nodes is not None
            else []
        )
        if self._global_single_node_resolution and isinstance(
            control_flow_context.resolution_machine, ParallelResolutionMachine
        ):
            involved_nodes = list(self._global_dag_builder.node_to_reference.keys())
        else:
            involved_nodes = list(flow.nodes.keys())
        # focus_stack is no longer available in the new architecture
        if isinstance(control_flow_context.resolution_machine, ParallelResolutionMachine):
            current_resolving_nodes = [
                node.node_reference.name
                for node in control_flow_context.resolution_machine.context.task_to_node.values()
            ]
            return current_control_nodes, current_resolving_nodes, involved_nodes
        if isinstance(control_flow_context.resolution_machine, SequentialResolutionMachine):
            focus_stack_for_node = control_flow_context.resolution_machine.context.focus_stack
            current_resolving_node = focus_stack_for_node[-1].node.name if len(focus_stack_for_node) else None
            return current_control_nodes, [current_resolving_node] if current_resolving_node else [], involved_nodes
        return current_control_nodes, [], involved_nodes

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
        cn_mgr = self.get_connections()
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
                    # Check if the control parameters are being used at all. If they are not, treat it as a data node.
                    incoming_control = (
                        node.name in cn_mgr.incoming_index and parameter.name in cn_mgr.incoming_index[node.name]
                    )
                    outgoing_control = (
                        node.name in cn_mgr.outgoing_index and parameter.name in cn_mgr.outgoing_index[node.name]
                    )
                    if incoming_control or outgoing_control:
                        control_param = True
                        break
            if not control_param:
                # saving this for later
                data_nodes.append(node)
                # If this node doesn't have a control connection..
                continue
            # check if it has an incoming connection. If it does, it's not a start node
            has_control_connection = False
            if node.name in cn_mgr.incoming_index:
                for param_name in cn_mgr.incoming_index[node.name]:
                    param = node.get_parameter_by_name(param_name)
                    if param and ParameterTypeBuiltin.CONTROL_TYPE.value == param.output_type:
                        # there is a control connection coming in
                        # If the node is a StartLoopNode, it may have an incoming hidden connection from it's EndLoopNode for iteration.
                        if isinstance(node, StartLoopNode):
                            connection_id = cn_mgr.incoming_index[node.name][param_name][0]
                            connection = cn_mgr.connections[connection_id]
                            connected_node = connection.get_source_node()
                            # Check if the source node is the end loop node associated with this StartLoopNode.
                            # If it is, then this could still be the first node in the control flow.
                            if connected_node == node.end_node:
                                continue
                        has_control_connection = True
                        break
            # if there is a connection coming in, isn't a start.
            if has_control_connection:
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
        # ok now - populate the global flow queue with node type information
        for node in start_nodes:
            self._global_flow_queue.put(QueueItem(node=node, dag_execution_type=DagExecutionType.START_NODE))
        for node in control_nodes:
            self._global_flow_queue.put(QueueItem(node=node, dag_execution_type=DagExecutionType.CONTROL_NODE))
        for node in valid_data_nodes:
            self._global_flow_queue.put(QueueItem(node=node, dag_execution_type=DagExecutionType.DATA_NODE))

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
