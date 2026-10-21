"""Tests for validating, before a flow starts, the nodes whose inputs are already known."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from unittest.mock import patch

import pytest

from griptape_nodes.exe_types.connections import Connections
from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import DataNode, NodeResolutionState
from griptape_nodes.machines.upfront_validation import known_inputs, validate_nodes_with_known_inputs
from griptape_nodes.retained_mode.events.validation_events import ValidateFlowDependenciesRequest

if TYPE_CHECKING:
    from griptape_nodes.retained_mode.engine import Engine


def _data_parameter(name: str = "value") -> Parameter:
    return Parameter(
        name=name,
        type="str",
        default_value="",
        tooltip="",
        allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY, ParameterMode.OUTPUT},
    )


class _Node(DataNode):
    """A node with one passthrough ``value`` whose validation refuses values starting with "bad"."""

    def __init__(self, name: str) -> None:
        super().__init__(name)
        self.add_parameter(_data_parameter())
        self.checked: list[Any] = []

    def process(self) -> None: ...

    def validate_before_node_run(self) -> list[Exception] | None:
        value = self.get_parameter_value("value")
        self.checked.append(value)
        if isinstance(value, str) and value.startswith("bad"):
            return [ValueError(f"'value' is {value!r}.")]
        return None


def _param(node: _Node, name: str = "value") -> Parameter:
    parameter = node.get_parameter_by_name(name)
    assert parameter is not None
    return parameter


def _connect(connections: Connections, source: _Node, target: _Node) -> None:
    connections.add_connection(source, _param(source), target, _param(target))


def _resolved(name: str, output: str) -> _Node:
    node = _Node(name)
    node.state = NodeResolutionState.RESOLVED
    node.parameter_output_values["value"] = output
    return node


class TestReadingInputs:
    def test_reads_the_provided_value_without_storing_it(self) -> None:
        node = _Node("Node")
        node.parameter_values["value"] = "stored"
        with node.reading_inputs({"value": "provided"}):
            assert node.get_parameter_value("value") == "provided"
        assert node.get_parameter_value("value") == "stored"
        assert node.parameter_values["value"] == "stored"

    def test_leaves_other_nodes_and_parameters_alone(self) -> None:
        node = _Node("Node")
        other = _Node("Other")
        node.parameter_values["value"] = "stored"
        other.parameter_values["value"] = "other"
        with node.reading_inputs({"missing": "x"}):
            assert node.get_parameter_value("value") == "stored"
            assert other.get_parameter_value("value") == "other"

    def test_does_not_mark_the_node_unresolved(self) -> None:
        node = _Node("Node")
        node.state = NodeResolutionState.UNRESOLVED
        with node.reading_inputs({"value": "provided"}):
            node.get_parameter_value("value")
        assert node.state == NodeResolutionState.UNRESOLVED


class TestKnownInputs:
    def test_an_unconnected_node_is_known_with_nothing_to_provide(self) -> None:
        assert known_inputs(_Node("Lone"), Connections()) == {}

    def test_reads_a_resolved_upstream_nodes_output(self) -> None:
        upstream = _resolved("Upstream", "cat.png")
        node = _Node("Node")
        connections = Connections()
        _connect(connections, upstream, node)
        assert known_inputs(node, connections) == {"value": "cat.png"}

    def test_reads_a_locked_upstream_nodes_output(self) -> None:
        upstream = _Node("Upstream")
        upstream.lock = True
        upstream.parameter_output_values["value"] = "frozen.png"
        node = _Node("Node")
        connections = Connections()
        _connect(connections, upstream, node)
        assert known_inputs(node, connections) == {"value": "frozen.png"}

    def test_is_unknown_when_an_upstream_node_will_run(self) -> None:
        upstream = _Node("Upstream")
        node = _Node("Node")
        connections = Connections()
        _connect(connections, upstream, node)
        assert known_inputs(node, connections) is None


class TestValidateNodesWithKnownInputs:
    def test_checks_known_nodes_against_the_values_they_will_receive(self) -> None:
        upstream = _resolved("Upstream", "bad.gif")
        node = _Node("Node")
        node.parameter_values["value"] = "stale.png"
        connections = Connections()
        _connect(connections, upstream, node)

        failures = validate_nodes_with_known_inputs([upstream, node], connections)

        assert [failure.node.name for failure in failures] == ["Node"]
        assert [str(e) for e in failures[0].exceptions] == ["'value' is 'bad.gif'."]
        # It looked without changing anything.
        assert node.parameter_values["value"] == "stale.png"
        assert node.state == NodeResolutionState.UNRESOLVED

    def test_reports_every_failing_node(self) -> None:
        first = _Node("First")
        second = _Node("Second")
        first.parameter_values["value"] = "bad one"
        second.parameter_values["value"] = "bad two"

        failures = validate_nodes_with_known_inputs([first, second], Connections())

        assert [failure.node.name for failure in failures] == ["First", "Second"]

    def test_leaves_a_node_fed_by_a_node_that_will_run_for_its_turn(self) -> None:
        upstream = _Node("Upstream")
        node = _Node("Node")
        connections = Connections()
        _connect(connections, upstream, node)

        validate_nodes_with_known_inputs([node], connections)

        assert node.checked == []

    def test_skips_nodes_this_run_wont_execute(self) -> None:
        resolved = _resolved("Resolved", "x")
        resolved.parameter_values["value"] = "bad but resolved"

        assert validate_nodes_with_known_inputs([resolved], Connections()) == []
        assert resolved.checked == []

    def test_reports_a_check_that_raises_as_that_nodes_failure(self) -> None:
        node = _Node("Node")
        boom = RuntimeError("boom")
        with patch.object(node, "validate_before_node_run", side_effect=boom):
            failures = validate_nodes_with_known_inputs([node], Connections())
        assert failures[0].exceptions == [boom]


class TestFlowValidation:
    @pytest.mark.asyncio
    async def test_a_bad_known_input_fails_validation_and_marks_the_node(self, engine: Engine) -> None:
        good = _Node("Good")
        bad = _Node("Bad")
        good.parameter_values["value"] = "fine"
        bad.parameter_values["value"] = "bad input"
        flow_manager = engine.flow_manager
        flow = type("Flow", (), {"nodes": {"Good": good, "Bad": bad}})()
        events: list[Any] = []

        async def capture(event: Any) -> None:
            events.append(event)

        with (
            patch.object(flow_manager, "get_flow_by_name", return_value=flow),
            patch.object(flow_manager, "get_connections", return_value=Connections()),
            patch.object(engine.event_manager, "aput_event", side_effect=capture),
        ):
            result = await flow_manager.on_validate_flow_dependencies_request(
                ValidateFlowDependenciesRequest(flow_name="Flow")
            )

        assert result.succeeded()
        assert result.validation_succeeded is False  # type: ignore[attr-defined]
        assert [str(e) for e in result.exceptions] == ["'value' is 'bad input'."]  # type: ignore[attr-defined]
        payloads = [event.wrapped_event.payload for event in events]
        assert [payload.node_name for payload in payloads] == ["Bad"]
        assert payloads[0].error.message == "'value' is 'bad input'."
