"""Tests for the _execute_node_on_worker helper in node_executor."""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar
from unittest.mock import AsyncMock, MagicMock

import pytest

from griptape_nodes.common.node_executor import _execute_node_on_worker
from griptape_nodes.retained_mode.events.execution_events import (
    ExecuteNodeRequest,
    ExecuteNodeResultFailure,
    ExecuteNodeResultSuccess,
    UpsertNodeRequest,
    UpsertNodeResultFailure,
    UpsertNodeResultSuccess,
)

if TYPE_CHECKING:
    from griptape_nodes.retained_mode.events.base_events import EventRequest

_ENGINE = "eng-xyz"
_SESSION = "sess-abc"
_WORKER_REQUEST_TOPIC = f"sessions/{_SESSION}/workers/{_ENGINE}/request"


class TestExecuteNodeOnWorker:
    def _make_node(self, *, node_type: str = "MyNode", library: str = "my_library") -> MagicMock:
        node = MagicMock()
        node.name = "my_node"
        node.parameter_values = {"x": 1}
        node.metadata = {"node_type": node_type, "library": library}
        return node

    _CREATE_RAW_SUCCESS: ClassVar[dict] = {
        "result_type": UpsertNodeResultSuccess.__name__,
        "result": {"node_name": "my_node", "result_details": "created"},
    }
    _EXECUTE_RAW_SUCCESS: ClassVar[dict] = {
        "result_type": ExecuteNodeResultSuccess.__name__,
        "result": {"parameter_output_values": {"out": 42}, "result_details": "ok"},
    }
    _CREATE_RAW_FAILURE: ClassVar[dict] = {
        "result_type": UpsertNodeResultFailure.__name__,
        "result": {"result_details": "type not found"},
    }

    @pytest.mark.asyncio
    async def test_sends_create_then_execute_to_worker(self) -> None:
        node = self._make_node()
        worker = (_ENGINE, _WORKER_REQUEST_TOPIC)
        wm = MagicMock()
        wm.route_to_worker = AsyncMock(side_effect=[self._CREATE_RAW_SUCCESS, self._EXECUTE_RAW_SUCCESS])

        await _execute_node_on_worker(wm, node, worker)

        expected_calls = 2  # one create + one execute
        assert wm.route_to_worker.call_count == expected_calls
        first_request: EventRequest = wm.route_to_worker.call_args_list[0][0][0]
        second_request: EventRequest = wm.route_to_worker.call_args_list[1][0][0]
        assert isinstance(first_request.request, UpsertNodeRequest)
        assert first_request.request.node_name == "my_node"
        assert first_request.request.node_type == "MyNode"
        assert first_request.request.library_name == "my_library"
        assert isinstance(second_request.request, ExecuteNodeRequest)
        assert second_request.request.node_name == "my_node"

    @pytest.mark.asyncio
    async def test_returns_failure_when_node_has_no_type_in_metadata(self) -> None:
        node = MagicMock()
        node.name = "typeless_node"
        node.metadata = {}
        worker = (_ENGINE, _WORKER_REQUEST_TOPIC)
        wm = MagicMock()
        wm.route_to_worker = AsyncMock()

        result = await _execute_node_on_worker(wm, node, worker)

        assert isinstance(result, ExecuteNodeResultFailure)
        assert "typeless_node" in str(result.result_details)
        wm.route_to_worker.assert_not_called()

    @pytest.mark.asyncio
    async def test_returns_failure_when_create_step_fails(self) -> None:
        node = self._make_node()
        worker = (_ENGINE, _WORKER_REQUEST_TOPIC)
        wm = MagicMock()
        wm.route_to_worker = AsyncMock(return_value=self._CREATE_RAW_FAILURE)

        result = await _execute_node_on_worker(wm, node, worker)

        assert isinstance(result, ExecuteNodeResultFailure)
        assert "my_node" in str(result.result_details)
        assert wm.route_to_worker.call_count == 1

    @pytest.mark.asyncio
    async def test_execute_request_has_no_node_type_or_library(self) -> None:
        node = self._make_node()
        worker = (_ENGINE, _WORKER_REQUEST_TOPIC)
        wm = MagicMock()
        wm.route_to_worker = AsyncMock(side_effect=[self._CREATE_RAW_SUCCESS, self._EXECUTE_RAW_SUCCESS])

        await _execute_node_on_worker(wm, node, worker)

        execute_event: EventRequest = wm.route_to_worker.call_args_list[1][0][0]
        assert isinstance(execute_event.request, ExecuteNodeRequest)
        assert execute_event.request.node_type is None
        assert execute_event.request.library_name is None

    @pytest.mark.asyncio
    async def test_returns_execute_result_on_success(self) -> None:
        node = self._make_node()
        worker = (_ENGINE, _WORKER_REQUEST_TOPIC)
        wm = MagicMock()
        wm.route_to_worker = AsyncMock(side_effect=[self._CREATE_RAW_SUCCESS, self._EXECUTE_RAW_SUCCESS])

        result = await _execute_node_on_worker(wm, node, worker)

        assert isinstance(result, ExecuteNodeResultSuccess)
        assert result.parameter_output_values == {"out": 42}
