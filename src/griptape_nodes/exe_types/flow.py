from __future__ import annotations

import logging
from typing import TYPE_CHECKING, NamedTuple

if TYPE_CHECKING:
    from queue import Queue

    from griptape_nodes.exe_types.core_types import Parameter
    from griptape_nodes.exe_types.node_types import BaseNode, Connection
    from griptape_nodes.retained_mode.engine import Engine
    from griptape_nodes.retained_mode.runtime.workflow_runtime import WorkflowRuntime


logger = logging.getLogger("griptape_nodes")


class CurrentNodes(NamedTuple):
    """The two relevant nodes during flow execution."""

    current_control_node: str | None
    current_resolving_node: str | None


# The flow will own all of the nodes
class ControlFlow:
    """A flow of one open workflow. Its connection queries answer from that workflow's flows."""

    name: str
    nodes: dict[str, BaseNode]
    metadata: dict
    engine: Engine
    workflow: WorkflowRuntime

    def __init__(self, name: str, engine: Engine, workflow: WorkflowRuntime, metadata: dict | None = None) -> None:
        self.name = name
        self.nodes = {}
        self.metadata = metadata or {}
        self.engine = engine
        self.workflow = workflow

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
    ) -> Connection | None:
        if source_node.name in self.nodes and target_node.name in self.nodes:
            return self.workflow.flows.connections.add_connection(
                source_node, source_parameter, target_node, target_parameter
            )
        return None

    def remove_connection(
        self, source_node: BaseNode, source_parameter: Parameter, target_node: BaseNode, target_parameter: Parameter
    ) -> bool:
        if source_node.name in self.nodes and target_node.name in self.nodes:
            return self.workflow.flows.connections.remove_connection(
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
        return self.workflow.flows.has_connection(source_node, source_parameter, target_node, target_parameter)

    def clear_execution_queue(self) -> None:
        self.workflow.flows.clear_queue_for_flow(self.name)

    def get_connections_on_node(self, node: BaseNode) -> list[BaseNode] | None:
        return self.workflow.flows.connections_on_node(node)

    def get_all_connected_nodes(self, node: BaseNode) -> list[BaseNode]:
        return self.workflow.flows.all_connected_nodes(node)

    def get_node_dependencies(self, node: BaseNode) -> list[BaseNode]:
        """Get all upstream nodes that the given node depends on.

        This method performs a breadth-first search starting from the given node and working backwards through its non-control input connections to identify all nodes that must run before this node can be resolved.
        It ignores control connections, since we're only focusing on node dependencies.

        Args:
            node (BaseNode): The node to find dependencies for

        Returns:
            list[BaseNode]: A list of all nodes that the given node depends on, including the node itself (as the first element)
        """
        return self.workflow.flows.node_dependencies(node)

    def get_connected_output_parameters(self, node: BaseNode, param: Parameter) -> list[tuple[BaseNode, Parameter]]:
        return self.workflow.flows.connected_output_parameters(node, param)

    def get_connected_input_parameters(self, node: BaseNode, param: Parameter) -> list[tuple[BaseNode, Parameter]]:
        return self.workflow.flows.connected_input_parameters(node, param)

    def get_connected_output_from_node(self, node: BaseNode) -> list[tuple[BaseNode, Parameter]]:
        return self.workflow.flows.connected_output_from_node(node)

    def get_connected_input_from_node(self, node: BaseNode) -> list[tuple[BaseNode, Parameter]]:
        return self.workflow.flows.connected_input_from_node(node)

    def get_start_node_queue(self) -> Queue | None:
        return self.engine.flow_manager.start_node_queue(self.workflow)

    def get_start_node_from_node(self, node: BaseNode) -> BaseNode | None:
        return self.engine.flow_manager.start_node_from_node(self.workflow, self, node)

    def get_prev_node(self, node: BaseNode) -> BaseNode | None:
        return self.workflow.flows.prev_control_node(node)
