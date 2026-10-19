"""The flow hierarchy, connections, and execution state of one open workflow.

`WorkflowFlows` is the state a `WorkflowRuntime` keeps as `flows`. `FlowManager` is the behavior that
creates, connects, serializes, and runs flows against it.
"""

from __future__ import annotations

from enum import StrEnum
from queue import Queue
from typing import TYPE_CHECKING, NamedTuple

from griptape_nodes.exe_types.connections import Connections
from griptape_nodes.exe_types.core_types import ParameterTypeBuiltin
from griptape_nodes.machines.dag_builder import DagBuilder

if TYPE_CHECKING:
    from griptape_nodes.exe_types.core_types import Parameter
    from griptape_nodes.exe_types.flow import ControlFlow
    from griptape_nodes.exe_types.node_types import BaseNode
    from griptape_nodes.machines.control_flow import ControlFlowMachine


class DagExecutionType(StrEnum):
    START_NODE = "start_node"
    CONTROL_NODE = "control_node"
    DATA_NODE = "data_node"


class QueueItem(NamedTuple):
    """Represents an item in the flow execution queue."""

    node: BaseNode
    dag_execution_type: DagExecutionType


class WorkflowFlows:
    """The flows of one open workflow, how they nest, how their nodes connect, and the run in progress."""

    def __init__(self) -> None:
        self.name_to_parent_name: dict[str, str | None] = {}
        self.flow_to_referenced_workflow_name: dict[ControlFlow, str] = {}
        self.connections = Connections()
        self.global_flow_queue = Queue[QueueItem]()
        # The control flow machine of the current run, if any.
        self.global_control_flow_machine: ControlFlowMachine | None = None
        self.global_single_node_resolution = False
        self.global_dag_builder = DagBuilder(self.connections)

    def parent_flow_name(self, flow_name: str) -> str | None:
        """The name of the flow the flow belongs to, None for the top-level flow.

        Raises:
            ValueError: No flow of that name is in this workflow.
        """
        if flow_name not in self.name_to_parent_name:
            msg = f"Flow with name {flow_name} doesn't exist"
            raise ValueError(msg)
        return self.name_to_parent_name[flow_name]

    def child_flow_names(self, parent_flow_name: str | None) -> list[str]:
        """The names of the flows that sit directly under the flow, or of the top-level flows for None."""
        return [
            flow_name for flow_name, parent_name in self.name_to_parent_name.items() if parent_name == parent_flow_name
        ]

    def flow_hierarchy(self, starting_flow: str) -> list[str]:
        """The flow and each of its ancestors, innermost first, ending at the top-level flow."""
        hierarchy: list[str] = []
        current_flow: str | None = starting_flow
        while current_flow:
            hierarchy.append(current_flow)
            if current_flow not in self.name_to_parent_name:
                break
            current_flow = self.name_to_parent_name[current_flow]
        return hierarchy

    def top_level_flow_name(self) -> str | None:
        """The name of the flow with no parent, None when there is none."""
        for flow_name, parent_name in self.name_to_parent_name.items():
            if parent_name is None:
                return flow_name
        return None

    def reparent_flow(self, flow_name: str, new_parent_flow_name: str) -> None:
        """Move a flow under a different parent flow.

        Raises:
            ValueError: Either flow is unknown, or the move would create a cycle.
        """
        if flow_name not in self.name_to_parent_name:
            msg = f"Flow with name {flow_name} doesn't exist"
            raise ValueError(msg)
        if new_parent_flow_name not in self.name_to_parent_name:
            msg = f"Flow with name {new_parent_flow_name} doesn't exist"
            raise ValueError(msg)
        if flow_name == new_parent_flow_name:
            msg = f"Attempted to make Flow '{flow_name}' its own parent."
            raise ValueError(msg)

        # Walk up from the proposed parent: if we meet the flow being moved, the move would
        # detach that branch from the tree and make the ancestor walk loop forever.
        ancestor = self.name_to_parent_name[new_parent_flow_name]
        while ancestor is not None:
            if ancestor == flow_name:
                msg = (
                    f"Attempted to move Flow '{flow_name}' under '{new_parent_flow_name}', which is already inside it."
                )
                raise ValueError(msg)
            ancestor = self.name_to_parent_name.get(ancestor)

        self.name_to_parent_name[flow_name] = new_parent_flow_name

    def rename_flow(self, old_name: str, new_name: str) -> None:
        """Record that the flow `old_name` is now called `new_name`, under the same parent."""
        self.name_to_parent_name[new_name] = self.name_to_parent_name.pop(old_name)

        # Everyone who pointed to the old name as a parent now points to the new one.
        for flow_name, parent_name in self.name_to_parent_name.items():
            if parent_name == old_name:
                self.name_to_parent_name[flow_name] = new_name

    def is_referenced_workflow(self, flow: ControlFlow) -> bool:
        """Whether the flow was created by importing a referenced workflow, not created standalone."""
        return flow in self.flow_to_referenced_workflow_name

    def referenced_workflow_name(self, flow: ControlFlow) -> str | None:
        """The name of the workflow imported to create the flow, None if it was created standalone."""
        return self.flow_to_referenced_workflow_name.get(flow)

    def connected_output_parameters(self, node: BaseNode, param: Parameter) -> list[tuple[BaseNode, Parameter]]:
        """The target node and parameter of each connection leaving the parameter."""
        found = []
        outgoing_params = self.connections.outgoing_index.get(node.name)
        if outgoing_params is None or param.name not in outgoing_params:
            return found
        for connection_id in outgoing_params[param.name]:
            connection = self.connections.connections[connection_id]
            found.append((connection.target_node, connection.target_parameter))
        return found

    def connected_input_parameters(self, node: BaseNode, param: Parameter) -> list[tuple[BaseNode, Parameter]]:
        """The source node and parameter of each connection entering the parameter."""
        found = []
        incoming_params = self.connections.incoming_index.get(node.name)
        if incoming_params is None or param.name not in incoming_params:
            return found
        for connection_id in incoming_params[param.name]:
            connection = self.connections.connections[connection_id]
            found.append((connection.source_node, connection.source_parameter))
        return found

    def connected_input_from_node(self, node: BaseNode) -> list[tuple[BaseNode, Parameter]]:
        """The source node and parameter of every connection entering any parameter of the node."""
        found = []
        incoming_params = self.connections.incoming_index.get(node.name)
        if incoming_params is None:
            return found
        for connection_ids in incoming_params.values():
            for connection_id in connection_ids:
                connection = self.connections.connections[connection_id]
                found.append((connection.source_node, connection.source_parameter))
        return found

    def connected_output_from_node(self, node: BaseNode) -> list[tuple[BaseNode, Parameter]]:
        """The target node and parameter of every connection leaving any parameter of the node."""
        found = []
        outgoing_params = self.connections.outgoing_index.get(node.name)
        if outgoing_params is None:
            return found
        for connection_ids in outgoing_params.values():
            for connection_id in connection_ids:
                connection = self.connections.connections[connection_id]
                found.append((connection.target_node, connection.target_parameter))
        return found

    def has_connection(
        self,
        source_node: BaseNode,
        source_parameter: Parameter,
        target_node: BaseNode,
        target_parameter: Parameter,
    ) -> bool:
        """Whether a connection exists between the two parameters."""
        for connected_node, connected_param in self.connected_output_parameters(source_node, source_parameter):
            if connected_node is target_node and connected_param is target_parameter:
                return True
        return False

    def connections_on_node(self, node: BaseNode) -> list[BaseNode]:
        """The nodes at the other end of the node's connections, without duplicates."""
        connected_nodes: list[BaseNode] = []
        outgoing_params = self.connections.outgoing_index.get(node.name)
        if outgoing_params is not None:
            for connection_ids in outgoing_params.values():
                for connection_id in connection_ids:
                    connection = self.connections.connections[connection_id]
                    if connection.source_node not in connected_nodes:
                        connected_nodes.append(connection.target_node)
        incoming_params = self.connections.incoming_index.get(node.name)
        if incoming_params is not None:
            for connection_ids in incoming_params.values():
                for connection_id in connection_ids:
                    connection = self.connections.connections[connection_id]
                    if connection.source_node not in connected_nodes:
                        connected_nodes.append(connection.source_node)
        return connected_nodes

    def all_connected_nodes(self, node: BaseNode) -> list[BaseNode]:
        """The node and every node reachable from it through connections in either direction."""
        discovered = {node: True}
        processed: dict[BaseNode, bool] = {}
        queue: Queue[BaseNode] = Queue()
        queue.put(node)
        while not queue.empty():
            current_node = queue.get()
            processed[current_node] = True
            for next_node in self.connections_on_node(current_node):
                if next_node not in discovered:
                    discovered[next_node] = True
                    queue.put(next_node)
        return list(processed.keys())

    def prev_control_node(self, node: BaseNode) -> BaseNode | None:
        """The node whose control output leads into `node`, skipping connections internal to a node group."""
        incoming_params = self.connections.incoming_index.get(node.name)
        if incoming_params is None:
            return None
        for parameter_name, connection_ids in incoming_params.items():
            parameter = node.get_parameter_by_name(parameter_name)
            if parameter is None or parameter.output_type != ParameterTypeBuiltin.CONTROL_TYPE.value:
                continue
            for connection_id in connection_ids:
                connection = self.connections.connections[connection_id]
                if connection.is_node_group_internal:
                    continue
                return connection.get_source_node()
        return None

    def node_dependencies(self, node: BaseNode) -> list[BaseNode]:
        """The node, then every node upstream of it through data connections, breadth first.

        Control connections are ignored: they order a run, they don't feed values.
        """
        node_list = [node]
        node_queue: Queue[BaseNode] = Queue()
        node_queue.put(node)
        while not node_queue.empty():
            current_node = node_queue.get()
            for input_node, input_parameter in self.connected_input_from_node(current_node):
                if input_parameter.output_type == ParameterTypeBuiltin.CONTROL_TYPE.value:
                    continue
                if input_node in node_list:
                    continue
                node_list.append(input_node)
                node_queue.put(input_node)
        return node_list

    def clear_queue_for_flow(self, flow_name: str) -> None:
        """Empty the execution queue, when the run in progress is of `flow_name`."""
        machine = self.global_control_flow_machine
        if machine is not None and machine.context.flow_name == flow_name:
            self.global_flow_queue.queue.clear()
