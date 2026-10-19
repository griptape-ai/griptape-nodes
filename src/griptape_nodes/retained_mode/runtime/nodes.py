"""The node bookkeeping of one open workflow.

`WorkflowNodes` is the state a `WorkflowRuntime` keeps as `nodes`. `NodeManager` is the behavior that
creates, moves, and runs nodes against it.
"""

from __future__ import annotations


class WorkflowNodes:
    """Which flow each node of one open workflow belongs to, and which nodes are running on a worker."""

    def __init__(self) -> None:
        self.name_to_parent_flow_name: dict[str, str] = {}
        # Orchestrator-side: node_name → (target_request_id, worker_engine_id, worker_request_topic)
        # for ExecuteNodeRequests currently routed to a worker. Populated while a node runs on a worker
        # and cleared when it finishes. Used to dispatch a CancelExecuteNodeRequest to the correct worker.
        self.orch_worker_requests: dict[str, tuple[str, str, str]] = {}

    def parent_flow_name(self, node_name: str) -> str:
        """The name of the flow the node belongs to.

        Raises:
            KeyError: No node of that name is in this workflow.
        """
        if node_name not in self.name_to_parent_flow_name:
            msg = f"Node '{node_name}' could not be found."
            raise KeyError(msg)
        return self.name_to_parent_flow_name[node_name]

    def rename_node(self, old_name: str, new_name: str) -> None:
        """Record that the node `old_name` is now called `new_name`, in the same flow."""
        self.name_to_parent_flow_name[new_name] = self.name_to_parent_flow_name.pop(old_name)

    def rename_flow(self, old_name: str, new_name: str) -> None:
        """Point every node that belonged to the flow `old_name` at `new_name`."""
        for node_name, parent_flow_name in self.name_to_parent_flow_name.items():
            if parent_flow_name == old_name:
                self.name_to_parent_flow_name[node_name] = new_name
