from __future__ import annotations

from queue import Queue
from typing import TYPE_CHECKING

from griptape_nodes.exe_types.connections import Connections
from griptape_nodes.exe_types.core_types import ParameterControlType
from griptape_nodes.exe_types.node_types import NodeResolutionState, StartNode
from griptape_nodes.machines.control_flow import CompleteState, ControlFlowMachine

if TYPE_CHECKING:
    from griptape_nodes.exe_types.core_types import Parameter
    from griptape_nodes.exe_types.node_types import NodeBase


# The flow will own all of the nodes and the connections
class ControlFlow:
    connections: Connections
    nodes: dict[str, NodeBase]
    control_flow_machine: ControlFlowMachine
    single_node_resolution: bool
    flow_queue: Queue[NodeBase]

    def __init__(self) -> None:
        self.connections = Connections()
        self.nodes = {}
        self.control_flow_machine = ControlFlowMachine(self)
        self.single_node_resolution = False
        self.flow_queue = Queue()

    def add_node(self, node: NodeBase) -> None:
        self.nodes[node.name] = node

    def remove_node(self, node_name: str) -> None:
        del self.nodes[node_name]

    def add_connection(
        self,
        source_node: NodeBase,
        source_parameter: Parameter,
        target_node: NodeBase,
        target_parameter: Parameter,
    ) -> bool:
        if source_node.name in self.nodes and target_node.name in self.nodes:
            return self.connections.add_connection(source_node, source_parameter, target_node, target_parameter)
        return False

    def remove_connection(
        self, source_node: NodeBase, source_parameter: Parameter, target_node: NodeBase, target_parameter: Parameter
    ) -> bool:
        if source_node.name in self.nodes and target_node.name in self.nodes:
            return self.connections.remove_connection(
                source_node.name, source_parameter.name, target_node.name, target_parameter.name
            )
        return False

    def has_connection(
        self,
        source_node: NodeBase,
        source_parameter: Parameter,
        target_node: NodeBase,
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

    def start_flow(self, start_node: NodeBase | None = None, debug_mode: bool = False) -> None:  # noqa: FBT001, FBT002
        if self.check_for_existing_running_flow():
            # If flow already exists, throw an error
            errormsg = "Flow already has been started. Cannot start flow when it has already been started."
            raise Exception(errormsg)
        if start_node:
            print(f"start with {start_node.name}")
            self.control_flow_machine.start_flow(start_node, debug_mode)
        elif not self.flow_queue.empty():
            start_node = self.flow_queue.get()
            self.control_flow_machine.start_flow(start_node, debug_mode)
            self.flow_queue.task_done()
            if not debug_mode:
                while not self.flow_queue.empty():
                    if not self.check_for_existing_running_flow():
                        start_node = self.flow_queue.get()
                        self.control_flow_machine.start_flow(start_node, debug_mode)
                        self.flow_queue.task_done()
        else:
            errormsg = "No Flow exists. You must create at least one control connection."
            raise Exception(errormsg)

    def check_for_existing_running_flow(self) -> bool:
        if self.control_flow_machine._current_state is not CompleteState and self.control_flow_machine._current_state:
            # Flow already exists in progress
            return True
        return bool(
            not self.control_flow_machine._context.resolution_machine.is_complete()
            and self.control_flow_machine._context.resolution_machine.is_started()
        )

    def resolve_singular_node(self, node: NodeBase, debug_mode: bool = False) -> None:  # noqa: FBT001, FBT002
        # Set that we are only working on one node right now! no other stepping allowed
        if self.check_for_existing_running_flow():
            # If flow already exists, throw an error
            errormsg = f"Flow already has been started. Cannot resolve node {node.name} while existing flow has begun."
            raise Exception(errormsg)
        self.single_node_resolution = True
        # Get the node resolution machine for the current flow!
        resolution_machine = self.control_flow_machine._context.resolution_machine
        # Set debug mode
        resolution_machine.change_debug_mode(debug_mode)
        # Resolve the node.
        node.state = NodeResolutionState.UNRESOLVED
        resolution_machine.resolve_node(node)
        # decide if we can change it back to normal flow mode!
        if resolution_machine.is_complete():
            self.single_node_resolution = False

    def single_execution_step(self) -> None:
        # do a granular step
        if not self.check_for_existing_running_flow():
            if self.flow_queue.empty():
                errormsg = "Flow has not yet been started. Cannot step while no flow has begun."
                raise Exception(errormsg)
            start_node = self.flow_queue.get()
            self.control_flow_machine.start_flow(start_node, debug_mode=True)
            start_node = self.flow_queue.task_done()
            return
        self.control_flow_machine.granular_step()
        resolution_machine = self.control_flow_machine._context.resolution_machine
        if self.single_node_resolution:
            resolution_machine = self.control_flow_machine._context.resolution_machine
            if resolution_machine.is_complete():
                self.single_node_resolution = False

    def single_node_step(self) -> None:
        if not self.check_for_existing_running_flow():
            if self.flow_queue.empty():
                errormsg = "Flow has not yet been started. Cannot step while no flow has begun."
                raise Exception(errormsg)
            start_node = self.flow_queue.get()
            self.control_flow_machine.start_flow(start_node, debug_mode=True)
            start_node = self.flow_queue.task_done()
            return
        # Step over a whole node
        if self.single_node_resolution:
            msg = "Cannot step through the Control Flow in Single Node Execution"
            raise Exception(msg)
        self.control_flow_machine.node_step()

    def continue_executing(self) -> None:
        if not self.check_for_existing_running_flow():
            if self.flow_queue.empty():
                errormsg = "Flow has not yet been started. Cannot step while no flow has begun."
                raise Exception(errormsg)
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
            raise Exception(errormsg)
        del self.control_flow_machine
        # Create a new control flow machine
        # Cancel all future runs
        del self.flow_queue
        self.flow_queue = Queue()
        # Reset control flow machine
        self.control_flow_machine = ControlFlowMachine(self)
        self.single_node_resolution = False

    def unresolve_whole_flow(self) -> None:
        for node in self.nodes.values():
            node.make_node_unresolved()

    def flow_state(self) -> tuple:
        if not self.check_for_existing_running_flow():
            msg = "Flow hasn't started."
            raise Exception(msg)
        current_control_node = self.control_flow_machine._context.current_node.name
        focus_stack_for_node = self.control_flow_machine._context.resolution_machine._context.focus_stack
        if len(focus_stack_for_node):
            current_resolving_node = focus_stack_for_node[-1].name
        else:
            current_resolving_node = None
        return current_control_node, current_resolving_node

    def get_connected_output_parameters(self, node: NodeBase, param: Parameter) -> list[tuple[NodeBase, Parameter]]:
        connections = []
        if node.name in self.connections.outgoing_index:
            outgoing_params = self.connections.outgoing_index[node.name]
            if param.name in outgoing_params:
                for connection_id in outgoing_params[param.name]:
                    connection = self.connections.connections[connection_id]
                    connections.append((connection.target_node, connection.target_parameter))
        return connections

    def get_connected_input_parameters(self, node: NodeBase, param: Parameter) -> list[tuple[NodeBase, Parameter]]:
        connections = []
        if node.name in self.connections.incoming_index:
            incoming_params = self.connections.incoming_index[node.name]
            if param.name in incoming_params:
                for connection_id in incoming_params[param.name]:
                    connection = self.connections.connections[connection_id]
                    connections.append((connection.source_node, connection.source_parameter))
        return connections

    def get_connected_output_from_node(self, node: NodeBase) -> list[tuple[NodeBase, Parameter]] | None:
        connections = []
        if node.name in self.connections.outgoing_index:
            connection_ids = [
                item for value_list in self.connections.outgoing_index[node.name].values() for item in value_list
            ]
            for connection_id in connection_ids:
                connection = self.connections.connections[connection_id]
                connections.append((connection.target_node, connection.target_parameter))
        return connections if connections else None

    def get_connected_input_from_node(self, node: NodeBase) -> list[tuple[NodeBase, Parameter]] | None:
        connections = []
        if node.name in self.connections.incoming_index:
            connection_ids = [
                item for value_list in self.connections.incoming_index[node.name].values() for item in value_list
            ]
            for connection_id in connection_ids:
                connection = self.connections.connections[connection_id]
                connections.append((connection.source_node, connection.source_parameter))
        return connections if connections else None

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
                if ParameterControlType.__name__ in parameter.allowed_types:
                    control_param = True
                    break
            if not control_param:
                # saving this for later
                data_nodes.append(node)
                # If this node doesn't have a control connection..
                continue
            cn_mgr = self.connections
            # check if it has an incoming connection. If it does, it's not a start node
            if node.name in cn_mgr.incoming_index:
                has_control_connection = False
                for param_name in cn_mgr.incoming_index[node.name]:
                    param = node.get_parameter_by_name(param_name)
                    if param and ParameterControlType.__name__ in param.allowed_types:
                        # there is a control connection coming in
                        has_control_connection = True
                        break
                # if there is a connection coming in, isn't a start.
                if has_control_connection:
                    # let's look at the next node.
                    continue
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

    def get_start_node_from_node(self, node: NodeBase) -> NodeBase | None:
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

    def get_prev_node(self, node: NodeBase) -> NodeBase | None:
        if node.name in self.connections.incoming_index:
            parameters = self.connections.incoming_index[node.name]
            for parameter_name in parameters:
                parameter = node.get_parameter_by_name(parameter_name)
                if parameter and ParameterControlType.__name__ in parameter.allowed_types:
                    # this is a control connection
                    connection_ids = self.connections.incoming_index[node.name][parameter_name]
                    for connection_id in connection_ids:
                        connection = self.connections.connections[connection_id]
                        return connection.get_source_node()
        return None

    def stop_flow_breakpoint(self, node: NodeBase) -> None:
        # This will prevent the flow from continuing on.
        node.stop_flow = True

    def get_connections_on_node(self, node: NodeBase) -> list[NodeBase] | None:
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

    def get_all_connected_nodes(self, node: NodeBase) -> list[NodeBase]:
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

    def get_node_dependencies(self, node: NodeBase) -> list[NodeBase]:
        node_list = [node]
        node_queue = Queue()
        node_queue.put(node)
        while not node_queue.empty():
            curr_node = node_queue.get()
            input_connections = self.get_connected_input_from_node(curr_node)
            if input_connections:
                for input_node, input_parameter in input_connections:
                    if not isinstance(input_parameter, ParameterControlType) and input_node not in node_list:
                        node_list.append(input_node)
                        node_queue.put(input_node)
        return node_list
