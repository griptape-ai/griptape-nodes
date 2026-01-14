from griptape_nodes.retained_mode.events.node_events import (
    BatchSetNodeLockStateResultFailure,
    SetLockNodeStateRequest,
    SetLockNodeStateResultFailure,
)
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
from griptape_nodes.retained_mode.retained_mode import RetainedMode


class TestRetainedModeLock:
    def test_lock_without_current_context_returns_failure(self) -> None:
        # Ensure empty current context for nodes
        ctx = GriptapeNodes.ContextManager()
        while ctx.has_current_node():
            ctx.pop_node()
        res = GriptapeNodes.handle_request(SetLockNodeStateRequest(node_name=None, lock=True))
        assert isinstance(res, SetLockNodeStateResultFailure)
        assert "Current Context" in str(res.result_details)

    def test_lock_all_missing_nodes_failure(self) -> None:
        missing_nodes = ["nope_a_123", "nope_b_456"]
        res = RetainedMode.batch_set_lock_node_state(node_names=missing_nodes, lock=True)
        assert isinstance(res, BatchSetNodeLockStateResultFailure)
        details = str(res.result_details)
        assert "Failed to update any nodes" in details
