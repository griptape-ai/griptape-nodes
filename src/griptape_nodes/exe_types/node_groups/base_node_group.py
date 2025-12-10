from __future__ import annotations

from typing import Any

from griptape_nodes.exe_types.node_types import BaseNode


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
