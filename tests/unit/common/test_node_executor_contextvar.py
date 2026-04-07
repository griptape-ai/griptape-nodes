"""Tests for current_executing_node_name ContextVar in NodeExecutor.execute()."""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from griptape_nodes.common.node_executor import NodeExecutor, current_executing_node_name


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
        """The ContextVar holds the node name while execute() is running aprocess()."""
        captured: list[str | None] = []
        node = _make_node("TestNode")

        async def capture_contextvar() -> None:
            captured.append(current_executing_node_name.get())

        node.aprocess = capture_contextvar

        await _make_executor().execute(node)

        assert captured == ["TestNode"]

    @pytest.mark.asyncio
    async def test_contextvar_reset_to_none_after_successful_execute(self) -> None:
        """The ContextVar is reset to None after execute() completes successfully."""
        node = _make_node("TestNode")

        await _make_executor().execute(node)

        assert current_executing_node_name.get() is None

    @pytest.mark.asyncio
    async def test_contextvar_reset_to_none_when_aprocess_raises(self) -> None:
        """The ContextVar is reset to None even when aprocess() raises an exception."""
        node = _make_node("TestNode")
        node.aprocess = AsyncMock(side_effect=RuntimeError("node failed"))

        with pytest.raises(RuntimeError, match="node failed"):
            await _make_executor().execute(node)

        assert current_executing_node_name.get() is None

    @pytest.mark.asyncio
    async def test_parallel_executions_are_isolated(self) -> None:
        """Concurrent executions each see only their own node name via asyncio task context isolation."""
        results: dict[str, str | None] = {}

        node_a = _make_node("NodeA")
        node_b = _make_node("NodeB")

        async def capture_a() -> None:
            await asyncio.sleep(0)  # yield to allow interleaving
            results["NodeA"] = current_executing_node_name.get()

        async def capture_b() -> None:
            await asyncio.sleep(0)  # yield to allow interleaving
            results["NodeB"] = current_executing_node_name.get()

        node_a.aprocess = capture_a
        node_b.aprocess = capture_b

        executor = _make_executor()
        await asyncio.gather(
            executor.execute(node_a),
            executor.execute(node_b),
        )

        assert results["NodeA"] == "NodeA"
        assert results["NodeB"] == "NodeB"
