from unittest.mock import Mock

import pytest

from griptape_nodes.exe_types.core_types import Parameter
from griptape_nodes.exe_types.node_types import AsyncResult

from .mocks import MockNode


class TestNodeTypes:
    """Test suite for node types functionality."""

    @pytest.mark.asyncio
    async def test_aprocess_with_multiple_yields(self) -> None:
        """Test that aprocess correctly handles nodes with multiple yields."""
        results = []

        def callable1() -> str:
            return "result1"

        def callable2() -> str:
            return "result2"

        def generator() -> AsyncResult:
            result1 = yield callable1
            results.append(result1)

            result2 = yield callable2
            results.append(result2)

        node = MockNode(process_result=generator())

        # Should complete without error
        await node.aprocess()

        # Verify all yields were processed
        assert results == ["result1", "result2"]


class TestConnectionRemovedHooks:
    def _make_param(self, name: str) -> Parameter:
        return Parameter(name=name, input_types=["str"], type="str", output_type="str", tooltip="test")

    def test_after_incoming_connection_removed_calls_callbacks(self) -> None:
        source_node = MockNode(name="source_node")
        target_node = MockNode(name="target_node")
        source_param = self._make_param("source_param")
        target_param = self._make_param("target_param")

        callback = Mock()
        target_param.on_incoming_connection_removed.append(callback)

        target_node.after_incoming_connection_removed(source_node, source_param, target_param)

        callback.assert_called_once_with(target_param, "source_node", "source_param")

    def test_after_incoming_connection_removed_calls_multiple_callbacks(self) -> None:
        source_node = MockNode(name="source_node")
        target_node = MockNode(name="target_node")
        source_param = self._make_param("source_param")
        target_param = self._make_param("target_param")

        callback1 = Mock()
        callback2 = Mock()
        target_param.on_incoming_connection_removed.append(callback1)
        target_param.on_incoming_connection_removed.append(callback2)

        target_node.after_incoming_connection_removed(source_node, source_param, target_param)

        callback1.assert_called_once_with(target_param, "source_node", "source_param")
        callback2.assert_called_once_with(target_param, "source_node", "source_param")

    def test_after_incoming_connection_removed_no_callbacks(self) -> None:
        source_node = MockNode(name="source_node")
        target_node = MockNode(name="target_node")
        source_param = self._make_param("source_param")
        target_param = self._make_param("target_param")

        # Should not raise when no callbacks are registered
        target_node.after_incoming_connection_removed(source_node, source_param, target_param)

    def test_after_outgoing_connection_removed_calls_callbacks(self) -> None:
        source_node = MockNode(name="source_node")
        target_node = MockNode(name="target_node")
        source_param = self._make_param("source_param")
        target_param = self._make_param("target_param")

        callback = Mock()
        source_param.on_outgoing_connection_removed.append(callback)

        source_node.after_outgoing_connection_removed(source_param, target_node, target_param)

        callback.assert_called_once_with(source_param, "target_node", "target_param")

    def test_after_outgoing_connection_removed_calls_multiple_callbacks(self) -> None:
        source_node = MockNode(name="source_node")
        target_node = MockNode(name="target_node")
        source_param = self._make_param("source_param")
        target_param = self._make_param("target_param")

        callback1 = Mock()
        callback2 = Mock()
        source_param.on_outgoing_connection_removed.append(callback1)
        source_param.on_outgoing_connection_removed.append(callback2)

        source_node.after_outgoing_connection_removed(source_param, target_node, target_param)

        callback1.assert_called_once_with(source_param, "target_node", "target_param")
        callback2.assert_called_once_with(source_param, "target_node", "target_param")

    def test_after_outgoing_connection_removed_no_callbacks(self) -> None:
        source_node = MockNode(name="source_node")
        target_node = MockNode(name="target_node")
        source_param = self._make_param("source_param")
        target_param = self._make_param("target_param")

        # Should not raise when no callbacks are registered
        source_node.after_outgoing_connection_removed(source_param, target_node, target_param)
