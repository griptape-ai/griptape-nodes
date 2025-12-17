from __future__ import annotations

from typing import Any

from griptape_nodes.exe_types.core_types import (
    Parameter,
    ParameterMode,
)
from griptape_nodes.exe_types.node_types import (
    LOCAL_EXECUTION,
    PRIVATE_EXECUTION,
    BaseNode,
)


class BaseNodeGroup(BaseNode):
    """Base class for node group implementations.

    Node groups are collections of nodes that are treated as a single unit.
    This base class provides the core functionality for managing a group of
    nodes, which may itself include other node groups.
    """

    nodes: dict[str, BaseNode]

    def __init__(
        self,
        name: str,
        metadata: dict[Any, Any] | None = None,
    ) -> None:
        """Initialize the node group base.

        Args:
            name: The name of this node group
            metadata: Optional metadata dictionary
        """
        super().__init__(name, metadata)
        self.nodes = {}
        self.metadata["is_node_group"] = True
        self.metadata["executable"] = False

    def add_parameter_to_group_settings(self, parameter: Parameter) -> None:
        """Add a parameter to the Group settings panel.

        Group settings parameters are determined by metadata in the frontend.

        Args:
            parameter: The parameter to add to settings
        """
        if ParameterMode.PROPERTY not in parameter.allowed_modes:
            msg = f"Parameter '{parameter.name}' must allow PROPERTY mode to be added to settings."
            raise ValueError(msg)

        if "execution_environment" not in self.metadata:
            self.metadata["execution_environment"] = {}

        execution_environment: dict = self.metadata.get("execution_environment", {})
        if LOCAL_EXECUTION not in execution_environment:
            execution_environment[LOCAL_EXECUTION] = {"parameter_names": []}
        if PRIVATE_EXECUTION not in execution_environment:
            execution_environment[PRIVATE_EXECUTION] = {"parameter_names": []}

        for library in execution_environment:
            parameter_names = self.metadata["execution_environment"][library].get("parameter_names", [])
            self.metadata["execution_environment"][library]["parameter_names"] = [parameter.name, *parameter_names]

    def add_nodes_to_group(self, nodes: list[BaseNode]) -> None:
        """Add nodes to this group.

        Args:
            nodes: A list of nodes to add to this group
        """
        for node in nodes:
            self.nodes[node.name] = node

        node_names_in_group = set(self.nodes.keys())
        self.metadata["node_names_in_group"] = list(node_names_in_group)

    def remove_nodes_from_group(self, nodes: list[BaseNode]) -> None:
        """Remove nodes from this group.

        Args:
            nodes: A list of nodes to remove from this group
        """
        for node in nodes:
            if node.name in self.nodes:
                del self.nodes[node.name]

    def _add_nodes_to_group_dict(self, nodes: list[BaseNode]) -> None:
        """Add nodes to the group's node dictionary."""
        for node in nodes:
            node.parent_group = self
            self.nodes[node.name] = node

    def _validate_nodes_in_group(self, nodes: list[BaseNode]) -> None:
        """Validate that all nodes are in the group."""
        for node in nodes:
            if node.name not in self.nodes:
                msg = f"Node {node.name} is not in node group {self.name}"
                raise ValueError(msg)
