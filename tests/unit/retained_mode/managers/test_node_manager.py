import logging

import pytest

from griptape_nodes.exe_types.core_types import Parameter
from griptape_nodes.retained_mode.events.node_events import (
    BatchSetNodeMetadataRequest,
    BatchSetNodeMetadataResultFailure,
    BatchSetNodeMetadataResultSuccess,
)
from griptape_nodes.retained_mode.events.parameter_events import AlterParameterDetailsRequest
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


class TestNodeManagerResolutionStateSerialization:
    """Test that node resolution states are preserved correctly during serialization."""

    def test_resolved_node_with_no_parameter_value_preserves_resolution(self) -> None:
        """Test that a resolved node with no parameter value set maintains its resolution state."""
        from unittest.mock import MagicMock

        from griptape_nodes.exe_types.core_types import Parameter
        from griptape_nodes.exe_types.node_types import BaseNode, NodeResolutionState
        from griptape_nodes.retained_mode.events.node_events import CreateNodeRequest
        from griptape_nodes.retained_mode.managers.node_manager import NodeManager

        # Create a simple parameter and node
        mock_parameter = MagicMock(spec=Parameter)
        mock_parameter.name = "test_param"

        mock_node = MagicMock(spec=BaseNode)
        mock_node.name = "test_node"
        mock_node.parameter_values = {}  # No value set
        mock_node.parameter_output_values = {}  # No output value

        # Start with resolved state
        create_node_request = CreateNodeRequest(
            node_type="TestNode", node_name="test_node", resolution=NodeResolutionState.RESOLVED.value
        )

        # Call the function
        result = NodeManager.handle_parameter_value_saving(
            parameter=mock_parameter,
            node=mock_node,
            unique_parameter_uuid_to_values={},
            serialized_parameter_value_tracker=MagicMock(),
            create_node_request=create_node_request,
        )

        # Should return None (no values to serialize) but preserve resolution
        assert result is None
        assert create_node_request.resolution == NodeResolutionState.RESOLVED.value

    def test_resolved_node_with_unserializable_parameter_becomes_unresolved(self) -> None:
        """Test that a resolved node becomes unresolved when parameter serialization fails."""
        from unittest.mock import MagicMock

        from griptape_nodes.exe_types.core_types import Parameter
        from griptape_nodes.exe_types.node_types import BaseNode, NodeResolutionState
        from griptape_nodes.retained_mode.events.node_events import CreateNodeRequest
        from griptape_nodes.retained_mode.managers.node_manager import NodeManager, SerializedParameterValueTracker

        # Create parameter with unserializable value
        mock_parameter = MagicMock(spec=Parameter)
        mock_parameter.name = "test_param"
        mock_parameter.serializable = True

        mock_node = MagicMock(spec=BaseNode)
        mock_node.name = "test_node"
        mock_node.parameter_values = {"test_param": "has_value"}
        mock_node.parameter_output_values = {}
        mock_node.get_parameter_value.return_value = "some_value"

        create_node_request = CreateNodeRequest(
            node_type="TestNode", node_name="test_node", resolution=NodeResolutionState.RESOLVED.value
        )

        # Mock tracker to return NOT_SERIALIZABLE to simulate serialization failure
        mock_tracker = MagicMock()
        mock_tracker.get_tracker_state.return_value = SerializedParameterValueTracker.TrackerState.NOT_SERIALIZABLE

        # Call the function - this should trigger the serialization failure path
        NodeManager.handle_parameter_value_saving(
            parameter=mock_parameter,
            node=mock_node,
            unique_parameter_uuid_to_values={},
            serialized_parameter_value_tracker=mock_tracker,
            create_node_request=create_node_request,
        )

        # Resolution should be reset to UNRESOLVED due to serialization failure
        assert create_node_request.resolution == NodeResolutionState.UNRESOLVED.value


class TestNodeManagerAlterParameterDetailsClearDefaultValue:
    """Test AlterParameterDetailsRequest behavior when clear_default_value and default_value are both set."""

    def test_clear_default_value_with_default_value_logs_warning_and_clears(
        self, griptape_nodes: GriptapeNodes, caplog: pytest.LogCaptureFixture
    ) -> None:
        """When both clear_default_value and default_value are provided, default is cleared and a warning is logged."""
        parameter = Parameter(name="test_param", default_value="original_value")
        request = AlterParameterDetailsRequest(
            parameter_name="test_param",
            node_name="test_node",
            clear_default_value=True,
            default_value="ignored_value",
        )

        caplog.clear()
        caplog.set_level(logging.WARNING)

        griptape_nodes.NodeManager().modify_key_parameter_fields(request, parameter)

        assert parameter.default_value is None
        assert len(caplog.records) == 1
        assert caplog.records[0].levelno == logging.WARNING
        assert "Conflicting options" in caplog.records[0].message
        assert "clear_default_value takes precedence" in caplog.records[0].message
        assert "test_param" in caplog.records[0].message
        assert "test_node" in caplog.records[0].message
