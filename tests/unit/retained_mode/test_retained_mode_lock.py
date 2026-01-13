from griptape_nodes.retained_mode.events.node_events import (
    BatchSetNodeLockStateResultFailure,
    BatchSetNodeLockStateResultSuccess,
    CreateNodeRequest,
    GetAllNodeInfoRequest,
    SetLockNodeStateResultSuccess,
)
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
from griptape_nodes.retained_mode.retained_mode import RetainedMode


class TestRetainedModeLock:
    def test_helper_single_and_multi_lock(self) -> None:
        # Create two nodes
        r1 = GriptapeNodes.handle_request(
            CreateNodeRequest(node_type="RunAgentNode", override_parent_flow_name="canvas")
        )
        r2 = GriptapeNodes.handle_request(
            CreateNodeRequest(node_type="RunAgentNode", override_parent_flow_name="canvas")
        )
        assert hasattr(r1, "node_name")
        assert hasattr(r2, "node_name")
        n1 = r1.node_name  # type: ignore[attr-defined]
        n2 = r2.node_name  # type: ignore[attr-defined]

        # Lock single via helper
        res1 = RetainedMode.set_lock_node_state(node_name=n1, lock=True)
        assert isinstance(res1, SetLockNodeStateResultSuccess)
        assert res1.locked is True
        assert res1.node_name == n1

        # Verify n1 locked, n2 not locked yet
        info1 = GriptapeNodes.handle_request(GetAllNodeInfoRequest(node_name=n1))
        info2 = GriptapeNodes.handle_request(GetAllNodeInfoRequest(node_name=n2))
        assert getattr(info1, "locked", False) is True
        assert getattr(info2, "locked", False) is False

        # Lock multiple via helper
        res2 = RetainedMode.batch_set_lock_node_state(node_names=[n1, n2], lock=True)
        assert isinstance(res2, BatchSetNodeLockStateResultSuccess)
        assert res2.updated_nodes == [n1, n2]
        assert res2.failed_nodes == {}

        # Verify both locked
        info1b = GriptapeNodes.handle_request(GetAllNodeInfoRequest(node_name=n1))
        info2b = GriptapeNodes.handle_request(GetAllNodeInfoRequest(node_name=n2))
        assert getattr(info1b, "locked", False) is True
        assert getattr(info2b, "locked", False) is True

        # Unlock multiple via helper
        res3 = RetainedMode.batch_set_lock_node_state(node_names=[n1, n2], lock=False)
        assert isinstance(res3, BatchSetNodeLockStateResultSuccess)
        assert res3.updated_nodes == [n1, n2]

        info1c = GriptapeNodes.handle_request(GetAllNodeInfoRequest(node_name=n1))
        info2c = GriptapeNodes.handle_request(GetAllNodeInfoRequest(node_name=n2))
        assert getattr(info1c, "locked", True) is False
        assert getattr(info2c, "locked", True) is False

    def test_lock_all_missing_nodes_failure(self) -> None:
        missing_nodes = ["nope_a_123", "nope_b_456"]
        res = RetainedMode.batch_set_lock_node_state(node_names=missing_nodes, lock=True)
        assert isinstance(res, BatchSetNodeLockStateResultFailure)
        details = str(res.result_details)
        assert "Failed to update any nodes" in details
