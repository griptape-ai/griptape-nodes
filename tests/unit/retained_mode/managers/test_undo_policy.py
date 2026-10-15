"""Which requests undo records."""

from typing import Any

import pytest

from griptape_nodes.retained_mode.events.execution_events import StartFlowRequest
from griptape_nodes.retained_mode.events.node_events import (
    GetNodeMetadataRequest,
    SetNodeMetadataRequest,
)
from griptape_nodes.retained_mode.events.object_events import ClearAllObjectStateRequest
from griptape_nodes.retained_mode.events.undo_events import UndoRequest
from griptape_nodes.retained_mode.managers.undo.policy import RequestRole, classify


class TestPolicy:
    @pytest.mark.parametrize(
        ("request_payload", "role"),
        [
            (UndoRequest(), RequestRole.HISTORY),
            (ClearAllObjectStateRequest(), RequestRole.RESETS_HISTORY),
            (StartFlowRequest(flow_name="main"), RequestRole.UNRECORDED),
            (GetNodeMetadataRequest(node_name="A"), RequestRole.EDIT),
            (SetNodeMetadataRequest(node_name="A", metadata={}), RequestRole.EDIT),
        ],
    )
    def test_classify(self, request_payload: Any, role: RequestRole) -> None:
        assert classify(request_payload) is role
