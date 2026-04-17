import warnings
from unittest.mock import Mock, patch

import pytest

from griptape_nodes.exe_types.core_types import Parameter
from griptape_nodes.exe_types.node_types import AsyncResult
from griptape_nodes.retained_mode.events.execution_events import ParameterValueUpdateEvent
from griptape_nodes.retained_mode.events.parameter_events import AlterElementEvent, RemoveElementEvent
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

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


def _get_emitted_payload_types(mock_put: Mock) -> list[type]:
    """Return the payload types for each ExecutionGriptapeNodeEvent put_event call."""
    types: list[type] = []
    for call in mock_put.call_args_list:
        event = call.args[0]
        wrapped = getattr(event, "wrapped_event", None)
        if wrapped is not None:
            types.append(type(wrapped.payload))
    return types


def _make_output_param(name: str = "out") -> Parameter:
    return Parameter(name=name, input_types=["str"], type="str", output_type="str", tooltip="test")


class TestParameterValueEvents:
    """Verify parameter event emission.

    Value writes emit ParameterValueUpdateEvent and structural changes emit
    AlterElementEvent / RemoveElementEvent.
    """

    def test_direct_dict_assignment_emits_parameter_value_update_event(self) -> None:
        """Direct dict assignment remains supported for out-of-tree node authors."""
        node = MockNode(name="n")
        node.add_parameter(_make_output_param("out"))

        event_mgr = GriptapeNodes.EventManager()
        with patch.object(event_mgr, "put_event") as mock_put:
            node.parameter_output_values["out"] = "hello"

        assert ParameterValueUpdateEvent in _get_emitted_payload_types(mock_put)
        assert AlterElementEvent not in _get_emitted_payload_types(mock_put)

    def test_other_dict_ops_do_not_emit(self) -> None:
        """Only __setitem__ is special; clear/pop/del are plain dict operations."""
        node = MockNode(name="n")
        node.add_parameter(_make_output_param("out"))
        node.parameter_output_values["out"] = "hello"

        event_mgr = GriptapeNodes.EventManager()
        with patch.object(event_mgr, "put_event") as mock_put:
            node.parameter_output_values.pop("out")

        assert mock_put.call_count == 0

        node.parameter_output_values["out"] = "hello"
        with patch.object(event_mgr, "put_event") as mock_put:
            node.parameter_output_values.clear()

        assert mock_put.call_count == 0

    def test_set_output_value_emits_parameter_value_update_event(self) -> None:
        node = MockNode(name="n")
        node.add_parameter(_make_output_param("out"))

        event_mgr = GriptapeNodes.EventManager()
        with patch.object(event_mgr, "put_event") as mock_put:
            node.set_output_value("out", "hello")

        assert ParameterValueUpdateEvent in _get_emitted_payload_types(mock_put)

    def test_set_parameter_value_emits_parameter_value_update_event(self) -> None:
        node = MockNode(name="n")
        node.add_parameter(_make_output_param("p"))

        event_mgr = GriptapeNodes.EventManager()
        with patch.object(event_mgr, "put_event") as mock_put:
            node.set_parameter_value("p", "hello")

        emitted = _get_emitted_payload_types(mock_put)
        assert ParameterValueUpdateEvent in emitted
        assert AlterElementEvent not in emitted

    def test_add_parameter_element_emits_alter_element_event(self) -> None:
        node = MockNode(name="n")
        event_mgr = GriptapeNodes.EventManager()

        with patch.object(event_mgr, "put_event") as mock_put:
            node.add_parameter(_make_output_param("p"))

        assert AlterElementEvent in _get_emitted_payload_types(mock_put)

    def test_remove_parameter_element_emits_remove_element_event(self) -> None:
        node = MockNode(name="n")
        param = _make_output_param("p")
        node.add_parameter(param)

        event_mgr = GriptapeNodes.EventManager()
        with patch.object(event_mgr, "put_event") as mock_put:
            node.remove_parameter_element(param)

        assert RemoveElementEvent in _get_emitted_payload_types(mock_put)

    def test_clear_node_emits_value_update_for_each_cleared_key(self) -> None:
        """Verify clear_node() clears outputs and re-broadcasts input values.

        clear_node() empties parameter_output_values and re-broadcasts each key
        with the input-side value so the UI reflects the input rather than a
        stale output.
        """
        node = MockNode(name="n")
        node.add_parameter(_make_output_param("p"))
        node.set_output_value("p", "output-value")
        node.set_parameter_value("p", "input-value")

        event_mgr = GriptapeNodes.EventManager()
        with patch.object(event_mgr, "put_event") as mock_put:
            node.clear_node()

        assert node.parameter_output_values == {}
        emitted_value_updates = [
            call.args[0].wrapped_event.payload
            for call in mock_put.call_args_list
            if isinstance(call.args[0].wrapped_event.payload, ParameterValueUpdateEvent)
        ]
        assert len(emitted_value_updates) == 1
        assert emitted_value_updates[0].value == "input-value"

    def test_alter_element_event_payload_does_not_carry_value(self) -> None:
        node = MockNode(name="n")
        param = _make_output_param("p")
        node.add_parameter(param)
        node.set_parameter_value("p", "some-value")

        event_data = param.to_event(node)

        assert "value" not in event_data


class TestDeprecatedMethods:
    """The legacy methods should still work but emit DeprecationWarning."""

    def test_publish_update_to_parameter_warns_and_delegates(self) -> None:
        node = MockNode(name="n")
        node.add_parameter(_make_output_param("p"))

        event_mgr = GriptapeNodes.EventManager()
        with patch.object(event_mgr, "put_event") as mock_put, warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            node.publish_update_to_parameter("p", "hello")

        assert any(issubclass(w.category, DeprecationWarning) for w in caught)
        assert ParameterValueUpdateEvent in _get_emitted_payload_types(mock_put)
        assert node.parameter_output_values["p"] == "hello"

    def test_append_value_to_parameter_warns_and_delegates(self) -> None:
        node = MockNode(name="n")
        node.add_parameter(_make_output_param("p"))

        event_mgr = GriptapeNodes.EventManager()
        with patch.object(event_mgr, "put_event"), warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            node.append_value_to_parameter("p", "hello")

        assert any(issubclass(w.category, DeprecationWarning) for w in caught)
        assert node.parameter_output_values["p"] == "hello"
