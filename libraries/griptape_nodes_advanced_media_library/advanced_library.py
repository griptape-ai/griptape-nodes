from __future__ import annotations

from typing import TYPE_CHECKING

from griptape_nodes.node_library.advanced_node_library import AdvancedNodeLibrary
from griptape_nodes.retained_mode.griptape_nodes import logger

if TYPE_CHECKING:
    from griptape_nodes.exe_types.node_types import BaseNode


class AdvancedMediaLibrary(AdvancedNodeLibrary):
    """Advanced library for media processing with executor methods."""

    async def execute(self, node: BaseNode) -> None:
        """Execute a media processing node with enhanced functionality.

        Args:
            node: The BaseNode to execute with media library enhancements
        """
        await node.aprocess()
        logger.info("Media processing node executed with media library enhancements")

