"""Which requests undo records, and how it finds their nodes."""

from typing import Any

import pytest

from griptape_nodes.retained_mode.events.connection_events import CreateConnectionRequest
from griptape_nodes.retained_mode.events.execution_events import StartFlowRequest
from griptape_nodes.retained_mode.events.flow_events import AutoLayoutFlowRequest, DeleteFlowRequest
from griptape_nodes.retained_mode.events.node_events import (
    BatchSetNodeMetadataRequest,
    CreateNodeRequest,
    DuplicateSelectedNodesRequest,
    GetNodeMetadataRequest,
    SetNodeMetadataRequest,
)
from griptape_nodes.retained_mode.events.object_events import ClearAllObjectStateRequest
from griptape_nodes.retained_mode.events.undo_events import UndoRequest
from griptape_nodes.retained_mode.managers.undo.policy import RequestRole, classify, named_flow, named_nodes


class TestPolicy:
    @pytest.mark.parametrize(
        ("request_payload", "role"),
        [
            (UndoRequest(), RequestRole.HISTORY),
            (ClearAllObjectStateRequest(), RequestRole.RESETS_HISTORY),
            (StartFlowRequest(flow_name="main"), RequestRole.UNRECORDED),
            (GetNodeMetadataRequest(node_name="A"), RequestRole.READ),
            (SetNodeMetadataRequest(node_name="A", metadata={}), RequestRole.EDIT),
        ],
    )
    def test_classify(self, request_payload: Any, role: RequestRole) -> None:
        assert classify(request_payload) is role

    def test_named_nodes_reads_every_kind_of_field(self) -> None:
        connection = CreateConnectionRequest(
            source_node_name="A", source_parameter_name="text", target_node_name="B", target_parameter_name="text"
        )
        create = CreateNodeRequest(node_type="_Group", node_name="G", node_names_to_add=["C", "D"])
        batch = BatchSetNodeMetadataRequest(node_metadata_updates={"E": {}, None: {}})
        duplicate = DuplicateSelectedNodesRequest(nodes_to_duplicate=[["F", "0"], []])

        assert named_nodes(connection) == ["A", "B"]
        assert named_nodes(create) == ["G", "C", "D"]
        assert named_nodes(batch) == ["E"]
        assert named_nodes(duplicate) == ["F"]

    def test_named_flow_only_for_flow_wide_requests(self) -> None:
        assert named_flow(AutoLayoutFlowRequest(flow_name="main")) == "main"
        assert named_flow(DeleteFlowRequest(flow_name="main")) == "main"
        assert named_flow(AutoLayoutFlowRequest()) is None
        assert named_flow(SetNodeMetadataRequest(node_name="A", metadata={})) is None
