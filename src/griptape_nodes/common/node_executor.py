from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from griptape_nodes.node_library.library_registry import LibraryRegistry

if TYPE_CHECKING:
    from griptape_nodes.exe_types.node_types import BaseNode

logger = logging.getLogger("griptape_nodes")


class NodeExecutor:
    """Simple class for executing nodes with library registry integration."""

    def __init__(self) -> None:
        self._registry = LibraryRegistry()

    async def execute(self, node: BaseNode) -> None:
        """Execute the given node.

        Args:
            node: The BaseNode to execute
        """
            # Execute the node's process method
        await node.aprocess()
        