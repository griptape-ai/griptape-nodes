from __future__ import annotations

from typing import Any

from griptape_nodes.exe_types.node_groups.subflow_node_group import SubflowNodeGroup


class StandardSubflowNodeGroup(SubflowNodeGroup):
    """Standard implementation of a subflow node group.

    This concrete implementation executes all nodes in the group in parallel
    by running the subflow and propagating output values through proxy parameters.
    """

    async def aprocess(self) -> None:
        """Execute all nodes in the group in parallel.

        This method is called by the DAG executor. It executes all nodes in the
        group concurrently by delegating to the execute_subflow helper method.
        """
        await self.execute_subflow()

    def process(self) -> Any:
        """Synchronous process method - not used for node groups."""
