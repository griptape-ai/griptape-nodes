from griptape_nodes.retained_mode.events.node_events import (
    BatchSetNodeMetadataRequest,
    BatchSetNodeMetadataResultFailure,
    BatchSetNodeMetadataResultSuccess,
)
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes


class TestNodeManagerBatchSetNodeMetadata:
    """Test the batch_set_node_metadata functionality in NodeManager."""

    def test_batch_set_node_metadata_empty_request_succeeds(self) -> None:
        """Test that an empty batch request succeeds without errors."""
        # Create an empty batch request
        request = BatchSetNodeMetadataRequest(node_metadata_updates={})

        # Execute the batch update through GriptapeNodes
        result = GriptapeNodes.handle_request(request)

        # Should succeed even with no updates
        assert isinstance(result, BatchSetNodeMetadataResultSuccess)
        assert result.updated_nodes == []
        assert result.failed_nodes == {}

    def test_batch_set_node_metadata_all_nodes_not_found_fails(self) -> None:
        """Test that batch update fails when all nodes are not found."""
        # Create request with non-existent nodes
        request = BatchSetNodeMetadataRequest(
            node_metadata_updates={
                "nonexistent_node1": {"position": {"x": 100, "y": 200}},
                "nonexistent_node2": {"position": {"x": 300, "y": 400}},
            }
        )

        # Execute the batch update through GriptapeNodes
        result = GriptapeNodes.handle_request(request)

        # Should fail because all nodes failed to be found
        assert isinstance(result, BatchSetNodeMetadataResultFailure)
        # Check that the error message contains expected information
        result_str = str(result.result_details)
        assert "Failed to update any nodes" in result_str
        assert "nonexistent_node1" in result_str
        assert "nonexistent_node2" in result_str
