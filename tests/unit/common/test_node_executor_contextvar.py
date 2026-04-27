"""Tests for current_executing_node_name ContextVar in NodeExecutor.execute()."""

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from griptape_nodes.common.node_executor import NodeExecutor, current_executing_node_name

_GRIPTAPE_NODES_PATH = "griptape_nodes.common.node_executor.GriptapeNodes"
_EXECUTE_ON_WORKER_PATH = "griptape_nodes.common.node_executor._execute_node_on_worker"


def _make_executor() -> NodeExecutor:
    return NodeExecutor.__new__(NodeExecutor)


def _make_node(name: str) -> MagicMock:
    node = MagicMock()
    node.name = name
    # Use a real dict so metadata.get("library") returns None, skipping the worker branch.
    node.metadata = {}
    node.aprocess = AsyncMock()
    return node


def _make_node_with_library(name: str, library: str = "my_lib") -> MagicMock:
    node = MagicMock()
    node.name = name
    node.metadata = {"library": library}
    node.aprocess = AsyncMock()
    return node


class TestCurrentExecutingNodeNameDefault:
    def test_default_is_none(self) -> None:
        assert current_executing_node_name.get() is None


class TestNodeExecutorContextVar:
    @pytest.mark.asyncio
    async def test_contextvar_holds_node_name_during_aprocess(self) -> None:
        """The ContextVar holds the node name while execute() is running."""
        captured: list[str | None] = []
        node = _make_node("TestNode")

        async def fake_aprocess() -> None:
            captured.append(current_executing_node_name.get())

        node.aprocess = AsyncMock(side_effect=fake_aprocess)

        with patch(_GRIPTAPE_NODES_PATH) as mock_gn:
            mock_gn.WorkerManager.return_value = None
            await _make_executor().execute(node)

        assert captured == ["TestNode"]

    @pytest.mark.asyncio
    async def test_contextvar_reset_to_none_after_successful_execute(self) -> None:
        """The ContextVar is reset to None after execute() completes successfully."""
        node = _make_node("TestNode")

        with patch(_GRIPTAPE_NODES_PATH) as mock_gn:
            mock_gn.WorkerManager.return_value = None
            await _make_executor().execute(node)

        assert current_executing_node_name.get() is None

    @pytest.mark.asyncio
    async def test_contextvar_reset_to_none_when_aprocess_raises(self) -> None:
        """The ContextVar is reset to None even when execution raises an exception."""
        node = _make_node("TestNode")
        node.aprocess = AsyncMock(side_effect=RuntimeError("node failed"))

        with patch(_GRIPTAPE_NODES_PATH) as mock_gn:
            mock_gn.WorkerManager.return_value = None

            with pytest.raises(RuntimeError, match="node failed"):
                await _make_executor().execute(node)

        assert current_executing_node_name.get() is None

    @pytest.mark.asyncio
    async def test_parallel_executions_are_isolated(self) -> None:
        """Concurrent executions each see only their own node name via asyncio task context isolation."""
        results: dict[str, str | None] = {}

        node_a = _make_node("NodeA")
        node_b = _make_node("NodeB")

        def _fake_aprocess_for(node_name: str) -> Any:
            async def _aprocess() -> None:
                await asyncio.sleep(0)  # yield to allow interleaving
                results[node_name] = current_executing_node_name.get()

            return _aprocess

        node_a.aprocess = AsyncMock(side_effect=_fake_aprocess_for("NodeA"))
        node_b.aprocess = AsyncMock(side_effect=_fake_aprocess_for("NodeB"))

        with patch(_GRIPTAPE_NODES_PATH) as mock_gn:
            mock_gn.WorkerManager.return_value = None

            executor = _make_executor()
            await asyncio.gather(
                executor.execute(node_a),
                executor.execute(node_b),
            )

        assert results["NodeA"] == "NodeA"
        assert results["NodeB"] == "NodeB"


class TestNodeExecutorContextVarWorkerBranch:
    """ContextVar behavior when execution routes through the worker branch."""

    @pytest.mark.asyncio
    async def test_contextvar_holds_node_name_during_worker_execution(self) -> None:
        """The ContextVar holds the node name while executing on a worker."""
        captured: list[str | None] = []
        node = _make_node_with_library("TestNode")

        async def fake_execute(_wm: Any, _node: Any, _worker: Any) -> None:
            captured.append(current_executing_node_name.get())

        with (
            patch(_GRIPTAPE_NODES_PATH) as mock_gn,
            patch(_EXECUTE_ON_WORKER_PATH, new=AsyncMock(side_effect=fake_execute)),
        ):
            mock_gn.WorkerManager.return_value = MagicMock()
            mock_gn.LibraryManager.return_value.get_worker_for_library.return_value = ("eng-id", "topic")
            await _make_executor().execute(node)

        assert captured == ["TestNode"]

    @pytest.mark.asyncio
    async def test_contextvar_reset_after_successful_worker_execution(self) -> None:
        """The ContextVar is reset to None after worker execution completes successfully."""
        node = _make_node_with_library("TestNode")

        with (
            patch(_GRIPTAPE_NODES_PATH) as mock_gn,
            patch(_EXECUTE_ON_WORKER_PATH, new=AsyncMock(return_value=None)),
        ):
            mock_gn.WorkerManager.return_value = MagicMock()
            mock_gn.LibraryManager.return_value.get_worker_for_library.return_value = ("eng-id", "topic")
            await _make_executor().execute(node)

        assert current_executing_node_name.get() is None

    @pytest.mark.asyncio
    async def test_contextvar_reset_when_worker_execution_raises(self) -> None:
        """The ContextVar is reset to None even when worker execution raises an exception."""
        node = _make_node_with_library("TestNode")

        with (
            patch(_GRIPTAPE_NODES_PATH) as mock_gn,
            patch(_EXECUTE_ON_WORKER_PATH, new=AsyncMock(side_effect=RuntimeError("worker failed"))),
        ):
            mock_gn.WorkerManager.return_value = MagicMock()
            mock_gn.LibraryManager.return_value.get_worker_for_library.return_value = ("eng-id", "topic")

            with pytest.raises(RuntimeError, match="worker failed"):
                await _make_executor().execute(node)

        assert current_executing_node_name.get() is None
