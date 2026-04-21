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

    _EXECUTE_RAW_SUCCESS: ClassVar[dict] = {
        "result_type": ExecuteNodeResultSuccess.__name__,
        "result": {"parameter_output_values": {"out": 42}, "result_details": "ok"},
    }
    _EXECUTE_RAW_FAILURE: ClassVar[dict] = {
        "result_type": ExecuteNodeResultFailure.__name__,
        "result": {"result_details": "execution failed"},
    }

    @pytest.mark.asyncio
    async def test_sends_single_execute_request_to_worker(self) -> None:
        node = self._make_node()
        worker = (_ENGINE, _WORKER_REQUEST_TOPIC)
        wm = MagicMock()
        wm.route_to_worker = AsyncMock(return_value=self._EXECUTE_RAW_SUCCESS)

        await _execute_node_on_worker(wm, node, worker)

        wm.route_to_worker.assert_called_once()
        request: EventRequest = wm.route_to_worker.call_args[0][0]
        assert isinstance(request.request, ExecuteNodeRequest)
        assert request.request.node_name == "my_node"

    @pytest.mark.asyncio
    async def test_execute_request_carries_node_metadata(self) -> None:
        node = self._make_node()
        worker = (_ENGINE, _WORKER_REQUEST_TOPIC)
        wm = MagicMock()
        wm.route_to_worker = AsyncMock(return_value=self._EXECUTE_RAW_SUCCESS)

        await _execute_node_on_worker(wm, node, worker)

        request: EventRequest = wm.route_to_worker.call_args[0][0]
        assert isinstance(request.request, ExecuteNodeRequest)
        assert request.request.node_metadata == {"node_type": "MyNode", "library": "my_library"}
        assert request.request.parameter_values == {"x": 1}

    @pytest.mark.asyncio
    async def test_returns_execute_result_on_success(self) -> None:
        node = self._make_node()
        worker = (_ENGINE, _WORKER_REQUEST_TOPIC)
        wm = MagicMock()
        wm.route_to_worker = AsyncMock(return_value=self._EXECUTE_RAW_SUCCESS)

        result = await _execute_node_on_worker(wm, node, worker)

        assert isinstance(result, ExecuteNodeResultSuccess)
        assert result.parameter_output_values == {"out": 42}

    @pytest.mark.asyncio
    async def test_returns_failure_result_from_worker(self) -> None:
        node = self._make_node()
        worker = (_ENGINE, _WORKER_REQUEST_TOPIC)
        wm = MagicMock()
        wm.route_to_worker = AsyncMock(return_value=self._EXECUTE_RAW_FAILURE)

        result = await _execute_node_on_worker(wm, node, worker)

        assert isinstance(result, ExecuteNodeResultFailure)
