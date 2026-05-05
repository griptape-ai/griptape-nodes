import asyncio
import threading
from dataclasses import dataclass
from unittest.mock import Mock

import pytest

from griptape_nodes.exe_types.core_types import Parameter
from griptape_nodes.exe_types.node_types import AsyncResult
from griptape_nodes.retained_mode.events.base_events import RequestPayload, ResultPayloadSuccess
from griptape_nodes.retained_mode.managers.event_manager import EventManager

from .mocks import MockNode


@dataclass
class _ProbeRequest(RequestPayload):
    pass


class _ProbeResult(ResultPayloadSuccess):
    pass


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

    @pytest.mark.asyncio
    async def test_aprocess_runs_sync_process_off_event_loop_thread(self) -> None:
        """Sync process() must run in a worker thread, not on the event loop thread.

        This is the guarantee that lets sync GriptapeNodes.handle_request(...) calls
        from inside sync node code dispatch async handlers via asyncio.run without
        tripping the running-loop guard documented in issue #4469.
        """
        loop_thread_id = threading.get_ident()
        captured: dict[str, int | bool] = {}

        class _ThreadProbingNode(MockNode):
            def process(self) -> AsyncResult | None:
                captured["process_thread_id"] = threading.get_ident()
                try:
                    asyncio.get_running_loop()
                except RuntimeError:
                    captured["has_running_loop"] = False
                else:
                    captured["has_running_loop"] = True
                return None

        node = _ThreadProbingNode()
        await node.aprocess()

        assert captured["process_thread_id"] != loop_thread_id
        assert captured["has_running_loop"] is False

    @pytest.mark.asyncio
    async def test_aprocess_sync_process_can_reach_async_handler_via_sync_dispatch(self) -> None:
        """Regression test for #4469 trips from sync nodes.

        A sync process() that calls the sync handle_request entry point with an
        async handler target must succeed, because aprocess runs process() on a
        worker thread (no running loop there), not on the event loop thread.
        """
        event_manager = EventManager()

        async def async_handler(_request: _ProbeRequest) -> _ProbeResult:
            return _ProbeResult(result_details="ok")

        event_manager.assign_manager_to_request_type(_ProbeRequest, async_handler)

        captured: dict[str, bool] = {}

        class _DispatchingNode(MockNode):
            def process(self) -> AsyncResult | None:
                event = event_manager.handle_request(_ProbeRequest())
                captured["succeeded"] = event.result.succeeded()
                return None

        node = _DispatchingNode()
        await node.aprocess()

        assert captured["succeeded"] is True


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
