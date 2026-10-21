"""Tests for validating, before a flow starts, the nodes whose inputs are already known."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar
from unittest.mock import patch

import pytest

from griptape_nodes.exe_types.connections import Connections, Direction
from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.local_objects import make_reference
from griptape_nodes.exe_types.node_types import DataNode, NodeResolutionState
from griptape_nodes.machines import upfront_validation
from griptape_nodes.machines.upfront_validation import inputs_are_known, validate_nodes_with_known_inputs
from griptape_nodes.retained_mode.events.validation_events import ValidateFlowDependenciesRequest

if TYPE_CHECKING:
    from collections.abc import Iterator

    from griptape_nodes.exe_types.node_types import BaseNode
    from griptape_nodes.retained_mode.engine import Engine


def _data_parameter(name: str) -> Parameter:
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
        self.add_parameter(_data_parameter("value"))
        self.checked: list[Any] = []

    def process(self) -> None: ...

    def validate_before_node_run(self) -> list[Exception] | None:
        value = self.get_parameter_value("value")
        self.checked.append(value)
        if isinstance(value, str) and value.startswith("bad"):
            return [ValueError(f"'value' is {value!r}.")]
        return None


class _SwitchingNode(DataNode):
    """Like a Kling node: changing ``model`` switches a ``duration`` the model doesn't allow.

    Its check reads ``duration`` and refuses one the model doesn't allow, trusting that the switch in
    `after_value_set` has already run.
    """

    ALLOWED: ClassVar[dict[str, list[int]]] = {"long": [5, 10, 15], "short": [5, 10]}

    def __init__(self, name: str) -> None:
        super().__init__(name)
        self.add_parameter(_data_parameter("model"))
        self.add_parameter(_data_parameter("duration"))

    def process(self) -> None: ...

    def after_value_set(self, parameter: Parameter, value: Any) -> None:
        super().after_value_set(parameter, value)
        if parameter.name == "model":
            allowed = self.ALLOWED.get(value, [5])
            if self.get_parameter_value("duration") not in allowed:
                self.set_parameter_value("duration", allowed[0])

    def validate_before_node_run(self) -> list[Exception] | None:
        allowed = self.ALLOWED.get(self.get_parameter_value("model"), [5])
        duration = self.get_parameter_value("duration")
        if duration not in allowed:
            return [ValueError(f"Duration {duration} isn't allowed.")]
        return None


def _param(node: BaseNode, name: str) -> Parameter:
    parameter = node.get_parameter_by_name(name)
    assert parameter is not None
    return parameter


def _connect(graph: Connections, source: BaseNode, target: BaseNode, name: str = "value") -> None:
    graph.add_connection(source, _param(source, name), target, _param(target, name))


def _resolved(name: str, output: Any) -> _Node:
    node = _Node(name)
    node.state = NodeResolutionState.RESOLVED
    node.parameter_output_values["value"] = output
    return node


@pytest.fixture
def connections() -> Iterator[Connections]:
    """Connections, with upstream values set the way the run sets them: through the node, so hooks run.

    The real `collect_upstream_values_into` sets values through the engine's request bus, which needs
    the nodes registered in a flow. Setting them on the node directly still runs `after_value_set`,
    which is what these tests exercise.
    """
    graph = Connections()

    async def set_upstream_values(_engine: Engine, node: BaseNode) -> None:
        for parameter in node.parameters:
            upstream = graph.get_connected_node(node, parameter, direction=Direction.UPSTREAM)
            if upstream is not None:
                upstream_node, upstream_parameter = upstream
                node.set_parameter_value(parameter.name, upstream_node.parameter_output_values[upstream_parameter.name])

    with patch.object(upfront_validation, "collect_upstream_values_into", side_effect=set_upstream_values):
        yield graph


class TestInputsAreKnown:
    def test_an_unconnected_node_is_known(self) -> None:
        assert inputs_are_known(_Node("Lone"), Connections()) is True

    def test_a_node_fed_by_a_resolved_node_is_known(self) -> None:
        graph = Connections()
        node = _Node("Node")
        _connect(graph, _resolved("Upstream", "cat.png"), node)
        assert inputs_are_known(node, graph) is True

    def test_a_node_fed_by_a_locked_node_is_known(self) -> None:
        upstream = _Node("Upstream")
        upstream.lock = True
        upstream.parameter_output_values["value"] = "frozen.png"
        graph = Connections()
        node = _Node("Node")
        _connect(graph, upstream, node)
        assert inputs_are_known(node, graph) is True

    def test_a_node_fed_by_a_node_that_will_run_is_not_known(self) -> None:
        graph = Connections()
        node = _Node("Node")
        _connect(graph, _Node("Upstream"), node)
        assert inputs_are_known(node, graph) is False

    @pytest.mark.parametrize(
        "held",
        [
            make_reference(worker="worker-1", key="k1", source="Load Model"),
            [make_reference(worker="worker-1", key="k1", source="Load Model")],
        ],
        ids=["key", "key-in-a-list"],
    )
    def test_a_node_with_a_worker_held_input_is_not_known(self, held: Any) -> None:
        # The check runs in the engine, where a worker's object can't be read, so leave it for its turn.
        graph = Connections()
        node = _Node("Node")
        _connect(graph, _resolved("Upstream", held), node)
        assert inputs_are_known(node, graph) is False


class TestValidateNodesWithKnownInputs:
    @pytest.mark.asyncio
    async def test_checks_a_known_node_against_the_values_it_will_receive(
        self, engine: Engine, connections: Connections
    ) -> None:
        upstream = _resolved("Upstream", "bad.gif")
        node = _Node("Node")
        node.parameter_values["value"] = "stale.png"
        _connect(connections, upstream, node)

        failures = await validate_nodes_with_known_inputs(engine, [upstream, node], connections)

        assert [failure.node.name for failure in failures] == ["Node"]
        assert [str(e) for e in failures[0].exceptions] == ["'value' is 'bad.gif'."]

    @pytest.mark.asyncio
    async def test_judges_the_value_after_the_nodes_own_switch(self, engine: Engine, connections: Connections) -> None:
        # 15 was picked under the "long" model. The connected "short" model allows 5 or 10, and the node
        # switches 15 to 5 when the model is set, as the run would. The check must see 5, not refuse 15.
        model = _SwitchingNode("Model")
        model.state = NodeResolutionState.RESOLVED
        model.parameter_output_values["model"] = "short"
        node = _SwitchingNode("Video")
        node.set_parameter_value("model", "long")
        node.set_parameter_value("duration", 15)
        _connect(connections, model, node, name="model")

        assert await validate_nodes_with_known_inputs(engine, [node], connections) == []
        assert node.get_parameter_value("duration") == _SwitchingNode.ALLOWED["short"][0]

    @pytest.mark.asyncio
    async def test_still_refuses_a_value_no_switch_corrects(self, engine: Engine, connections: Connections) -> None:
        # A bad duration with no model change goes through no switch, so it's still refused.
        node = _SwitchingNode("Video")
        node.set_parameter_value("model", "short")
        node.parameter_values["duration"] = 45

        failures = await validate_nodes_with_known_inputs(engine, [node], connections)

        assert [str(e) for e in failures[0].exceptions] == ["Duration 45 isn't allowed."]

    @pytest.mark.asyncio
    async def test_reports_every_failing_node(self, engine: Engine, connections: Connections) -> None:
        first = _Node("First")
        second = _Node("Second")
        first.parameter_values["value"] = "bad one"
        second.parameter_values["value"] = "bad two"

        failures = await validate_nodes_with_known_inputs(engine, [first, second], connections)

        assert [failure.node.name for failure in failures] == ["First", "Second"]

    @pytest.mark.asyncio
    async def test_leaves_a_node_fed_by_a_node_that_will_run_for_its_turn(
        self, engine: Engine, connections: Connections
    ) -> None:
        node = _Node("Node")
        _connect(connections, _Node("Upstream"), node)

        await validate_nodes_with_known_inputs(engine, [node], connections)

        assert node.checked == []

    @pytest.mark.asyncio
    async def test_skips_nodes_this_run_wont_execute(self, engine: Engine, connections: Connections) -> None:
        resolved = _resolved("Resolved", "x")
        resolved.parameter_values["value"] = "bad but resolved"

        assert await validate_nodes_with_known_inputs(engine, [resolved], connections) == []
        assert resolved.checked == []

    @pytest.mark.asyncio
    async def test_reports_a_check_that_raises_as_that_nodes_failure(
        self, engine: Engine, connections: Connections
    ) -> None:
        node = _Node("Node")
        boom = RuntimeError("boom")
        with patch.object(node, "validate_before_node_run", side_effect=boom):
            failures = await validate_nodes_with_known_inputs(engine, [node], connections)
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
