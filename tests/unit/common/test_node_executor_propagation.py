"""Regression tests for downstream propagation on NodeExecutor.execute().

The in-process side-effect path in NodeManager.on_set_parameter_value_request
already fans outputs to downstream connections when node.aprocess() writes them.
The workers PR (#4336) routed the orchestrator-only path through
ExecuteNodeRequest and copied outputs back onto the node via
node.set_parameter_value, which re-entered the side-effect propagation path
and duplicated downstream fan-out (observed as "~10 duplicate RescaleImage
outputs"). The orchestrator-only path also broke single-node flows like
LoadImage because ExecuteNodeRequest re-hydrates inputs via
set_parameter_value.

These tests lock in:
  * orchestrator-only path: bare `await node.aprocess()`; no
    set_parameter_value, no ExecuteNodeRequest round-trip.
  * worker branch: _execute_node_on_worker is invoked; the helper (not
    NodeExecutor.execute) owns the copy-back onto the in-memory node.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from griptape_nodes.common.node_executor import NodeExecutor

_GRIPTAPE_NODES_PATH = "griptape_nodes.common.node_executor.GriptapeNodes"
_EXECUTE_ON_WORKER_PATH = "griptape_nodes.common.node_executor._execute_node_on_worker"


def _make_executor() -> NodeExecutor:
    return NodeExecutor.__new__(NodeExecutor)


def _make_local_node() -> MagicMock:
    node = MagicMock()
    node.name = "UpstreamNode"
    node.parameter_values = {}
    # No "library" key so the executor's `get_worker_for_library` branch
    # is never exercised — we're on the local path.
    node.metadata = {}
    node.aprocess = AsyncMock()
    return node


def _make_worker_node() -> MagicMock:
    node = MagicMock()
    node.name = "UpstreamNode"
    node.parameter_values = {}
    node.metadata = {"library": "my_lib"}
    node.aprocess = AsyncMock()
    return node


class TestOrchestratorOnlyPath:
    """The orchestrator-only path must match pre-workers behavior exactly.

    That means a bare `await node.aprocess()` with no ExecuteNodeRequest
    round-trip and no copy-back onto the node. aprocess() writes outputs
    directly on the node, and NodeManager's on_set_parameter_value_request
    fans them out to downstream connections in-process.
    """

    @pytest.mark.asyncio
    async def test_calls_aprocess_directly(self) -> None:
        node = _make_local_node()

        with patch(_GRIPTAPE_NODES_PATH) as mock_gn:
            mock_gn.WorkerManager.return_value = None
            mock_gn.ahandle_request = AsyncMock()
            await _make_executor().execute(node)

        node.aprocess.assert_awaited_once()
        mock_gn.ahandle_request.assert_not_called()

    @pytest.mark.asyncio
    async def test_does_not_set_parameter_value_on_node(self) -> None:
        node = _make_local_node()

        with patch(_GRIPTAPE_NODES_PATH) as mock_gn:
            mock_gn.WorkerManager.return_value = None
            await _make_executor().execute(node)

        # The regression: prior code routed through ExecuteNodeRequest and
        # unconditionally called node.set_parameter_value for each output.
        # That re-entered the side-effect propagation path and duplicated
        # downstream fan-out. It also broke LoadImage because the
        # ExecuteNodeRequest input-hydrate loop re-fired set_parameter_value
        # on inputs.
        node.set_parameter_value.assert_not_called()

    @pytest.mark.asyncio
    async def test_propagates_aprocess_exception(self) -> None:
        node = _make_local_node()
        node.aprocess = AsyncMock(side_effect=RuntimeError("boom"))

        with patch(_GRIPTAPE_NODES_PATH) as mock_gn:
            mock_gn.WorkerManager.return_value = None

            with pytest.raises(RuntimeError, match="boom"):
                await _make_executor().execute(node)

        node.set_parameter_value.assert_not_called()


class TestWorkerBranchRoutesToHelper:
    """Worker branch must delegate to _execute_node_on_worker.

    The helper owns the copy-back onto the in-memory node; NodeExecutor.execute
    itself does not touch node.set_parameter_value.
    """

    @pytest.mark.asyncio
    async def test_worker_path_calls_helper_and_skips_aprocess(self) -> None:
        node = _make_worker_node()

        async def fake_execute(_wm: Any, _node: Any, _worker: Any) -> None:
            return None

        with (
            patch(_GRIPTAPE_NODES_PATH) as mock_gn,
            patch(_EXECUTE_ON_WORKER_PATH, new=AsyncMock(side_effect=fake_execute)) as mock_exec,
        ):
            mock_gn.WorkerManager.return_value = MagicMock()
            mock_gn.LibraryManager.return_value.get_worker_for_library.return_value = ("eng-id", "topic")
            await _make_executor().execute(node)

        mock_exec.assert_awaited_once()
        node.aprocess.assert_not_called()
