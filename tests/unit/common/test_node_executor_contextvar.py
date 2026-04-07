"""Tests for current_executing_node_name ContextVar in NodeExecutor.execute()."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from griptape_nodes.common.node_executor import NodeExecutor, current_executing_node_name
from griptape_nodes.retained_mode.events.execution_events import ExecuteNodeRequest, ExecuteNodeResultSuccess


def _make_executor() -> NodeExecutor:
    return NodeExecutor.__new__(NodeExecutor)


def _make_node(name: str) -> MagicMock:
    node = MagicMock()
    node.name = name
    node.aprocess = AsyncMock()
    return node


class TestCurrentExecutingNodeNameDefault:
    def test_default_is_none(self) -> None:
        assert current_executing_node_name.get() is None


class TestNodeExecutorContextVar:
    @pytest.mark.asyncio
    async def test_contextvar_holds_node_name_during_aprocess(self) -> None:
        """The ContextVar holds the node name while execute() is dispatching the request."""
        node = _make_node("TestNode")
        captured: list[str | None] = []

        async def mock_handler(_request: ExecuteNodeRequest) -> ExecuteNodeResultSuccess:
            captured.append(current_executing_node_name.get())
            return ExecuteNodeResultSuccess(result_details="")

        with patch(
            "griptape_nodes.common.node_executor.GriptapeNodes.ahandle_request",
            new=mock_handler,
        ):
            await _make_executor().execute(node)

        assert captured == ["TestNode"]

    @pytest.mark.asyncio
    async def test_contextvar_reset_to_none_after_successful_execute(self) -> None:
        """The ContextVar is reset to None after execute() completes successfully."""
        node = _make_node("TestNode")

        with patch(
            "griptape_nodes.common.node_executor.GriptapeNodes.ahandle_request",
            new=AsyncMock(return_value=ExecuteNodeResultSuccess(result_details="")),
        ):
            await _make_executor().execute(node)

        assert current_executing_node_name.get() is None

    @pytest.mark.asyncio
    async def test_contextvar_reset_to_none_when_aprocess_raises(self) -> None:
        """The ContextVar is reset to None even when execution raises an exception."""
        node = _make_node("TestNode")

        with (
            pytest.raises(RuntimeError, match="node failed"),
            patch(
                "griptape_nodes.common.node_executor.GriptapeNodes.ahandle_request",
                new=AsyncMock(side_effect=RuntimeError("node failed")),
            ),
        ):
            await _make_executor().execute(node)

        assert current_executing_node_name.get() is None

    @pytest.mark.asyncio
    async def test_parallel_executions_are_isolated(self) -> None:
        """Concurrent executions each see only their own node name via asyncio task context isolation."""
        results: dict[str, str | None] = {}

        async def mock_handler(request: ExecuteNodeRequest) -> ExecuteNodeResultSuccess:
            await asyncio.sleep(0)  # yield to allow interleaving
            results[request.node_name] = current_executing_node_name.get()
            return ExecuteNodeResultSuccess(result_details="")

        node_a = _make_node("NodeA")
        node_b = _make_node("NodeB")

        executor = _make_executor()
        with patch(
            "griptape_nodes.common.node_executor.GriptapeNodes.ahandle_request",
            new=mock_handler,
        ):
            await asyncio.gather(
                executor.execute(node_a),
                executor.execute(node_b),
            )

        assert results["NodeA"] == "NodeA"
        assert results["NodeB"] == "NodeB"
