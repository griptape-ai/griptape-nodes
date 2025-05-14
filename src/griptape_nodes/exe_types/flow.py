from __future__ import annotations

import logging
from queue import Queue
from typing import TYPE_CHECKING, NamedTuple

from griptape.events import EventBus

from griptape_nodes.exe_types.connections import Connections
from griptape_nodes.exe_types.core_types import ParameterTypeBuiltin
from griptape_nodes.exe_types.node_types import NodeResolutionState, StartNode
from griptape_nodes.machines.control_flow import CompleteState, ControlFlowMachine
from griptape_nodes.retained_mode.events.base_events import ExecutionEvent, ExecutionGriptapeNodeEvent
from griptape_nodes.retained_mode.events.execution_events import ControlFlowCancelledEvent

if TYPE_CHECKING:
    from griptape_nodes.exe_types.core_types import Parameter
    from griptape_nodes.exe_types.node_types import BaseNode


logger = logging.getLogger("griptape_nodes")


class CurrentNodes(NamedTuple):
    """The two relevant nodes during flow execution."""

    current_control_node: str | None
    current_resolving_node: str | None


# The flow will own all of the nodes and the connections
class ControlFlow:
    connections: Connections
    nodes: dict[str, BaseNode]
    control_flow_machine: ControlFlowMachine
    single_node_resolution: bool
    flow_queue: Queue[BaseNode]

    def __init__(self) -> None:
        self.connections = Connections()
        self.nodes = {}
        self.control_flow_machine = ControlFlowMachine(self)
        self.single_node_resolution = False
        self.flow_queue = Queue()

    def add_node(self, node: BaseNode) -> None:
        self.nodes[node.name] = node

    def remove_node(self, node_name: str) -> None:
        del self.nodes[node_name]

    def add_connection(
        self,
        source_node: BaseNode,
        source_parameter: Parameter,
        target_node: BaseNode,
        target_parameter: Parameter,
    ) -> bool:
        if source_node.name in self.nodes and target_node.name in self.nodes:
            return self.connections.add_connection(source_node, source_parameter, target_node, target_parameter)
        return False

    def remove_connection(
        self, source_node: BaseNode, source_parameter: Parameter, target_node: BaseNode, target_parameter: Parameter
    ) -> bool:
        if source_node.name in self.nodes and target_node.name in self.nodes:
            return self.connections.remove_connection(
                source_node.name, source_parameter.name, target_node.name, target_parameter.name
            )
        return False

    def has_connection(
        self,
        source_node: BaseNode,
        source_parameter: Parameter,
        target_node: BaseNode,
        target_parameter: Parameter,
    ) -> bool:
        if source_node.name in self.nodes and target_node.name in self.nodes:
            connected_node_tuple = self.get_connected_output_parameters(node=source_node, param=source_parameter)
            if connected_node_tuple is not None:
                for connected_node_values in connected_node_tuple:
                    connected_node, connected_param = connected_node_values
                    if connected_node is target_node and connected_param is target_parameter:
                        return True
        return False

    def start_flow(self, start_node: BaseNode | None = None, debug_mode: bool = False) -> None:  # noqa: FBT001, FBT002
        if self.check_for_existing_running_flow():
            # If flow already exists, throw an error
            errormsg = "This workflow is already in progress. Please wait for the current process to finish before starting again."
            raise RuntimeError(errormsg)

        if start_node is None:
            if self.flow_queue.empty():
                errormsg = "No Flow exists. You must create at least one control connection."
                raise RuntimeError(errormsg)
            start_node = self.flow_queue.get()

        try:
            self.control_flow_machine.start_flow(start_node, debug_mode)
            self.flow_queue.task_done()
        except Exception:
            if self.check_for_existing_running_flow():
                self.cancel_flow_run()
            raise

    def check_for_existing_running_flow(self) -> bool:
        if self.control_flow_machine._current_state is not CompleteState and self.control_flow_machine._current_state:
            # Flow already exists in progress
            return True
        return bool(
            not self.control_flow_machine._context.resolution_machine.is_complete()
            and self.control_flow_machine._context.resolution_machine.is_started()
        )

    def resolve_singular_node(self, node: BaseNode, debug_mode: bool = False) -> None:  # noqa: FBT001, FBT002
        # Set that we are only working on one node right now! no other stepping allowed
        if self.check_for_existing_running_flow():
            # If flow already exists, throw an error
            errormsg = f"This workflow is already in progress. Please wait for the current process to finish before starting {node.name} again."
            raise RuntimeError(errormsg)
        self.single_node_resolution = True
        # Get the node resolution machine for the current flow!
        self.control_flow_machine._context.current_node = node
        resolution_machine = self.control_flow_machine._context.resolution_machine
        # Set debug mode
        resolution_machine.change_debug_mode(debug_mode)
        # Resolve the node.
        node.state = NodeResolutionState.UNRESOLVED
        resolution_machine.resolve_node(node)
        # decide if we can change it back to normal flow mode!
        if resolution_machine.is_complete():
            self.single_node_resolution = False
            self.control_flow_machine._context.current_node = None

    def single_execution_step(self, change_debug_mode: bool) -> None:  # noqa: FBT001
        # do a granular step
        if not self.check_for_existing_running_flow():
            if self.flow_queue.empty():
                errormsg = "Flow has not yet been started. Cannot step while no flow has begun."
                raise RuntimeError(errormsg)
            start_node = self.flow_queue.get()
            self.control_flow_machine.start_flow(start_node, debug_mode=True)
            start_node = self.flow_queue.task_done()
            return
        self.control_flow_machine.granular_step(change_debug_mode)
        resolution_machine = self.control_flow_machine._context.resolution_machine
        if self.single_node_resolution:
            resolution_machine = self.control_flow_machine._context.resolution_machine
            if resolution_machine.is_complete():
                self.single_node_resolution = False

    def single_node_step(self) -> None:
        # It won't call single_node_step without an existing flow running from US.
        if not self.check_for_existing_running_flow():
            if self.flow_queue.empty():
                errormsg = "Flow has not yet been started. Cannot step while no flow has begun."
                raise RuntimeError(errormsg)
            start_node = self.flow_queue.get()
            self.control_flow_machine.start_flow(start_node, debug_mode=True)
            start_node = self.flow_queue.task_done()
            return
        # Step over a whole node
        if self.single_node_resolution:
            msg = "Cannot step through the Control Flow in Single Node Execution"
            raise RuntimeError(msg)
        self.control_flow_machine.node_step()
        # Start the next resolution step now please.
        if not self.check_for_existing_running_flow() and not self.flow_queue.empty():
            start_node = self.flow_queue.get()
            self.flow_queue.task_done()
            self.control_flow_machine.start_flow(start_node, debug_mode=True)

    def continue_executing(self) -> None:
        if not self.check_for_existing_running_flow():
            if self.flow_queue.empty():
                errormsg = "Flow has not yet been started. Cannot step while no flow has begun."
                raise RuntimeError(errormsg)
            start_node = self.flow_queue.get()
            self.flow_queue.task_done()
            self.control_flow_machine.start_flow(start_node, debug_mode=False)
            return
        # Turn all debugging to false and continue on
        self.control_flow_machine.change_debug_mode(False)
        if self.single_node_resolution:
            if self.control_flow_machine._context.resolution_machine.is_complete():
                self.single_node_resolution = False
            else:
                self.control_flow_machine._context.resolution_machine.update()
        else:
            self.control_flow_machine.node_step()
        # Now it is done executing. make sure it's actually done?
        if not self.check_for_existing_running_flow() and not self.flow_queue.empty():
            start_node = self.flow_queue.get()
            self.flow_queue.task_done()
            self.control_flow_machine.start_flow(start_node, debug_mode=False)

    def cancel_flow_run(self) -> None:
        if not self.check_for_existing_running_flow():
            errormsg = "Flow has not yet been started. Cannot cancel flow that hasn't begun."
            raise RuntimeError(errormsg)
        self.clear_flow_queue()
        self.control_flow_machine.reset_machine()
        # Reset control flow machine
        self.single_node_resolution = False
        logger.debug("Cancelling flow run")

        EventBus.publish_event(
            ExecutionGriptapeNodeEvent(wrapped_event=ExecutionEvent(payload=ControlFlowCancelledEvent()))
        )

    def unresolve_whole_flow(self) -> None:
        for node in self.nodes.values():
            node.make_node_unresolved(current_states_to_trigger_change_event=None)

    def flow_state(self) -> CurrentNodes:
        if not self.check_for_existing_running_flow():
            msg = "Flow hasn't started."
            raise RuntimeError(msg)
        current_control_node = (
            self.control_flow_machine._context.current_node.name
            if self.control_flow_machine._context.current_node is not None
            else None
        )
        focus_stack_for_node = self.control_flow_machine._context.resolution_machine._context.focus_stack
        current_resolving_node = focus_stack_for_node[-1].node.name if len(focus_stack_for_node) else None
        return CurrentNodes(current_control_node, current_resolving_node)

    def clear_flow_queue(self) -> None:
        self.flow_queue.queue.clear()

    def get_connected_output_parameters(self, node: BaseNode, param: Parameter) -> list[tuple[BaseNode, Parameter]]:
        connections = []
        if node.name in self.connections.outgoing_index:
            outgoing_params = self.connections.outgoing_index[node.name]
            if param.name in outgoing_params:
                for connection_id in outgoing_params[param.name]:
                    connection = self.connections.connections[connection_id]
                    connections.append((connection.target_node, connection.target_parameter))
        return connections

    def get_connected_input_parameters(self, node: BaseNode, param: Parameter) -> list[tuple[BaseNode, Parameter]]:
        connections = []
        if node.name in self.connections.incoming_index:
            incoming_params = self.connections.incoming_index[node.name]
            if param.name in incoming_params:
                for connection_id in incoming_params[param.name]:
                    connection = self.connections.connections[connection_id]
                    connections.append((connection.source_node, connection.source_parameter))
        return connections

    def get_connected_output_from_node(self, node: BaseNode) -> list[tuple[BaseNode, Parameter]]:
        connections = []
        if node.name in self.connections.outgoing_index:
            connection_ids = [
                item for value_list in self.connections.outgoing_index[node.name].values() for item in value_list
            ]
            for connection_id in connection_ids:
                connection = self.connections.connections[connection_id]
                connections.append((connection.target_node, connection.target_parameter))
        return connections

    def get_connected_input_from_node(self, node: BaseNode) -> list[tuple[BaseNode, Parameter]]:
        connections = []
        if node.name in self.connections.incoming_index:
            connection_ids = [
                item for value_list in self.connections.incoming_index[node.name].values() for item in value_list
            ]
            for connection_id in connection_ids:
                connection = self.connections.connections[connection_id]
                connections.append((connection.source_node, connection.source_parameter))
        return connections

    def get_start_node_queue(self) -> Queue | None:  # noqa: C901, PLR0912
        # check all nodes in flow
        # add them all to a stack. We're calling this only if no flow was specified, so we're running them all.
        self.flow_queue = Queue()
        # if no nodes, no flow.
        if not len(self.nodes):
            return None
        data_nodes = []
        valid_data_nodes = []
        start_nodes = []
        control_nodes = []
        for node in self.nodes.values():
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
            cn_mgr = self.connections
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
            cn_mgr = self.connections
            # check if it has an outgoing connection. We don't want it to (that means we get the most resolution)
            if node.name not in cn_mgr.outgoing_index:
                valid_data_nodes.append(node)
        # ok now
        for node in start_nodes:
            self.flow_queue.put(node)
        for node in control_nodes:
            self.flow_queue.put(node)
        for node in valid_data_nodes:
            self.flow_queue.put(node)

        return self.flow_queue

    def get_start_node_from_node(self, node: BaseNode) -> BaseNode | None:
        # backwards chain in control outputs.
        if node not in self.nodes.values():
            return None
        # Go back through incoming control connections to get the start node
        curr_node = node
        prev_node = self.get_prev_node(curr_node)
        # Fencepost loop - get the first previous node name and then we go
        while prev_node:
            curr_node = prev_node
            prev_node = self.get_prev_node(prev_node)
        return curr_node

    def get_prev_node(self, node: BaseNode) -> BaseNode | None:
        if node.name in self.connections.incoming_index:
            parameters = self.connections.incoming_index[node.name]
            for parameter_name in parameters:
                parameter = node.get_parameter_by_name(parameter_name)
                if parameter and ParameterTypeBuiltin.CONTROL_TYPE.value == parameter.output_type:
                    # this is a control connection
                    connection_ids = self.connections.incoming_index[node.name][parameter_name]
                    for connection_id in connection_ids:
                        connection = self.connections.connections[connection_id]
                        return connection.get_source_node()
        return None

    def stop_flow_breakpoint(self, node: BaseNode) -> None:
        # This will prevent the flow from continuing on.
        node.stop_flow = True

    def get_connections_on_node(self, node: BaseNode) -> list[BaseNode] | None:
        # get all of the connection ids
        connected_nodes = []
        # Handle outgoing connections
        if node.name in self.connections.outgoing_index:
            outgoing_params = self.connections.outgoing_index[node.name]
            outgoing_connection_ids = []
            for connection_ids in outgoing_params.values():
                outgoing_connection_ids = outgoing_connection_ids + connection_ids
            for connection_id in outgoing_connection_ids:
                connection = self.connections.connections[connection_id]
                if connection.source_node not in connected_nodes:
                    connected_nodes.append(connection.target_node)
        # Handle incoming connections
        if node.name in self.connections.incoming_index:
            incoming_params = self.connections.incoming_index[node.name]
            incoming_connection_ids = []
            for connection_ids in incoming_params.values():
                incoming_connection_ids = incoming_connection_ids + connection_ids
            for connection_id in incoming_connection_ids:
                connection = self.connections.connections[connection_id]
                if connection.source_node not in connected_nodes:
                    connected_nodes.append(connection.source_node)
        # Return all connected nodes. No duplicates
        return connected_nodes

    def get_all_connected_nodes(self, node: BaseNode) -> list[BaseNode]:
        discovered = {}
        processed = {}
        queue = Queue()
        queue.put(node)
        discovered[node] = True
        while not queue.empty():
            curr_node = queue.get()
            processed[curr_node] = True
            next_nodes = self.get_connections_on_node(curr_node)
            if next_nodes:
                for next_node in next_nodes:
                    if next_node not in discovered:
                        discovered[next_node] = True
                        queue.put(next_node)
        return list(processed.keys())

    def get_node_dependencies(self, node: BaseNode) -> list[BaseNode]:
        """Get all upstream nodes that the given node depends on.

        This method performs a breadth-first search starting from the given node and working backwards through its non-control input connections to identify all nodes that must run before this node can be resolved.
        It ignores control connections, since we're only focusing on node dependencies.

        Args:
            node (BaseNode): The node to find dependencies for

        Returns:
            list[BaseNode]: A list of all nodes that the given node depends on, including the node itself (as the first element)
        """
        node_list = [node]
        node_queue = Queue()
        node_queue.put(node)
        while not node_queue.empty():
            curr_node = node_queue.get()
            input_connections = self.get_connected_input_from_node(curr_node)
            if input_connections:
                for input_node, input_parameter in input_connections:
                    if (
                        ParameterTypeBuiltin.CONTROL_TYPE.value != input_parameter.output_type
                        and input_node not in node_list
                    ):
                        node_list.append(input_node)
                        node_queue.put(input_node)
        return node_list
