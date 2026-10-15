"""Undo and redo return the workflow to exactly the state on each side of an edit.

Each scenario records a fingerprint of the whole workflow, makes an edit the way the editor does,
then checks that undo restores the first fingerprint and redo the second, twice over. The
fingerprint reads the live objects rather than anything undo recorded, so a write the journal
missed shows up as a difference.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

import pytest

from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.flow import ControlFlow
from griptape_nodes.exe_types.node_groups.base_node_group import BaseNodeGroup
from griptape_nodes.exe_types.node_groups.subflow_node_group import SubflowNodeGroup
from griptape_nodes.exe_types.node_types import BaseNode
from griptape_nodes.node_library.library_registry import LibraryRegistry, NodeMetadata
from griptape_nodes.retained_mode.events.connection_events import CreateConnectionRequest, DeleteConnectionRequest
from griptape_nodes.retained_mode.events.flow_events import AutoLayoutFlowRequest
from griptape_nodes.retained_mode.events.node_events import (
    AddNodesToNodeGroupRequest,
    CreateNodeRequest,
    DeleteNodeRequest,
    DeserializeSelectedNodesFromCommandsRequest,
    DuplicateSelectedNodesRequest,
    RemoveNodeFromNodeGroupRequest,
    SerializeSelectedNodesToCommandsRequest,
    SerializeSelectedNodesToCommandsResultSuccess,
    SetLockNodeStateRequest,
    SetNodeMetadataRequest,
)
from griptape_nodes.retained_mode.events.object_events import RenameObjectRequest
from griptape_nodes.retained_mode.events.parameter_events import (
    AddParameterToNodeRequest,
    RemoveParameterFromNodeRequest,
    RenameParameterRequest,
    SetParameterValueRequest,
)
from griptape_nodes.retained_mode.events.undo_events import (
    RedoRequest,
    RedoResultSuccess,
    UndoRequest,
    UndoResultSuccess,
)
from tests.unit.retained_mode.managers.test_undo_manager import _LIBRARY, open_undo_test_workflow

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator

    from griptape_nodes.retained_mode.engine import Engine
    from griptape_nodes.retained_mode.events.base_events import RequestPayload, ResultPayload


class _Subflow(SubflowNodeGroup):
    """The kind of group the editor creates, with its own subflow and proxy parameters."""

    async def aprocess(self) -> None:
        return None


class _Mirror(BaseNode):
    """Copies its text onto the node named in `target`, so an edit writes to a node no request named."""

    def __init__(self, name: str, metadata: dict[Any, Any] | None = None) -> None:
        super().__init__(name, metadata)
        for parameter_name in ("text", "target"):
            self.add_parameter(
                Parameter(
                    name=parameter_name,
                    type="str",
                    default_value="",
                    tooltip=parameter_name,
                    allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY, ParameterMode.OUTPUT},
                )
            )

    def after_value_set(self, parameter: Parameter, value: Any) -> None:
        if parameter.name == "text":
            target = self.engine.object_manager.attempt_get_object_by_name_as_type(
                self.get_parameter_value("target"), BaseNode
            )
            if target is not None:
                target.set_parameter_value("text", value)
        return super().after_value_set(parameter, value)

    def process(self) -> None:
        return None


@pytest.fixture
def engine(engine: Engine) -> Iterator[Engine]:
    """The undo tests' workflow, with this module's nodes registered too."""
    for opened in open_undo_test_workflow(engine):
        _register_round_trip_nodes()
        yield opened


def _register_round_trip_nodes() -> None:
    library = LibraryRegistry.get_library(_LIBRARY)
    for node_class in (_Subflow, _Mirror):
        library.register_new_node_type(
            node_class, NodeMetadata(category="t", description="d", display_name=node_class.__name__)
        )


def _send(engine: Engine, request: RequestPayload, group: str) -> ResultPayload:
    request.undo_group = group
    result = engine.handle_request(request)
    assert result.succeeded(), result.result_details
    return result


def _create(engine: Engine, name: str, node_type: str = "_Probe", **kwargs: Any) -> None:
    request = CreateNodeRequest(node_type=node_type, specific_library_name=_LIBRARY, node_name=name, **kwargs)
    _send(engine, request, uuid.uuid4().hex)


def _connection(source: str, target: str, *, delete: bool = False, source_parameter: str = "text") -> RequestPayload:
    request_type = DeleteConnectionRequest if delete else CreateConnectionRequest
    return request_type(
        source_node_name=source,
        source_parameter_name=source_parameter,
        target_node_name=target,
        target_parameter_name="text",
    )


def _fingerprint(engine: Engine) -> dict[str, Any]:
    nodes = {}
    for name, node in engine.object_manager.get_filtered_subset(type=BaseNode).items():
        nodes[name] = {
            "object": id(node),
            "type": type(node).__name__,
            "flow": engine.node_manager.get_node_parent_flow_by_name(name),
            "group": node.parent_group.name if node.parent_group is not None else None,
            "members": sorted(node.nodes) if isinstance(node, BaseNodeGroup) else None,
            "lock": node.lock,
            "metadata": repr(sorted(node.metadata.items(), key=lambda item: str(item[0]))),
            "values": {key: repr(value) for key, value in sorted(node.parameter_values.items())},
            "elements": _without_badges(node.root_ui_element.to_dict()),
            # Serialization reads this to save parameters a node did not declare itself.
            "added_after_construction": sorted(node.parameters_added_after_construction),
        }
    flows = {
        name: {
            "object": id(flow),
            "nodes": sorted(flow.nodes),
            "parent": engine.flow_manager.get_parent_flow(name),
            "metadata": repr(flow.metadata),
        }
        for name, flow in engine.object_manager.get_filtered_subset(type=ControlFlow).items()
    }
    tables = engine.flow_manager.get_connections()
    connections = sorted(
        (c.source_node.name, c.source_parameter.name, c.target_node.name, c.target_parameter.name, id(c))
        for c in tables.connections.values()
    )
    # The indexes are kept beside the connections, so they are checked on their own.
    indexes = {
        "incoming": repr(sorted((node, sorted(params.items())) for node, params in tables.incoming_index.items())),
        "outgoing": repr(sorted((node, sorted(params.items())) for node, params in tables.outgoing_index.items())),
    }
    return {"nodes": nodes, "flows": flows, "connections": connections, "indexes": indexes}


def _without_badges(data: Any) -> Any:
    # Badges report run status, which undo does not restore.
    if isinstance(data, dict):
        return {key: _without_badges(value) for key, value in data.items() if key != "badge"}
    if isinstance(data, list):
        return [_without_badges(item) for item in data]
    return data


def _paste(engine: Engine, group: str) -> None:
    copied = _send(engine, SerializeSelectedNodesToCommandsRequest(nodes_to_serialize=[["A", "0"], ["B", "0"]]), group)
    assert isinstance(copied, SerializeSelectedNodesToCommandsResultSuccess)
    _send(
        engine,
        DeserializeSelectedNodesFromCommandsRequest(
            deserialize_commands=copied.serialized_selected_node_commands, pickled_values=copied.pickled_values
        ),
        group,
    )


def _drag(engine: Engine, group: str) -> None:
    for step in range(5):
        for name in ("A", "B"):
            position = {"x": 10 * step, "y": 5 * step}
            _send(engine, SetNodeMetadataRequest(node_name=name, metadata={"position": position}), group)


def _group_and_wire(engine: Engine, group: str) -> None:
    _send(
        engine,
        CreateNodeRequest(node_type="_Subflow", specific_library_name=_LIBRARY, node_name="G", node_names_to_add=["B"]),
        group,
    )


_SCENARIOS: dict[str, Callable[[Engine, str], Any]] = {
    "create": lambda engine, group: _send(
        engine, CreateNodeRequest(node_type="_Probe", specific_library_name=_LIBRARY, node_name="N"), group
    ),
    "value": lambda engine, group: _send(
        engine, SetParameterValueRequest(node_name="A", parameter_name="text", value="x"), group
    ),
    "value_shows_a_parameter": lambda engine, group: _send(
        engine, SetParameterValueRequest(node_name="T", parameter_name="mode", value="detailed"), group
    ),
    "hook_writes_another_node": lambda engine, group: _send(
        engine, SetParameterValueRequest(node_name="M", parameter_name="text", value="mirrored"), group
    ),
    "connect": lambda engine, group: _send(engine, _connection("B", "C"), group),
    "disconnect": lambda engine, group: _send(engine, _connection("A", "B", delete=True), group),
    "delete_connected_node": lambda engine, group: _send(engine, DeleteNodeRequest(node_name="B"), group),
    "rename_connected_node": lambda engine, group: _send(
        engine, RenameObjectRequest(object_name="B", requested_name="Renamed"), group
    ),
    "lock": lambda engine, group: _send(engine, SetLockNodeStateRequest(node_name="A", lock=True), group),
    "drag_two_nodes": _drag,
    "add_parameter": lambda engine, group: _send(
        engine,
        AddParameterToNodeRequest(
            node_name="A",
            parameter_name="extra",
            type="str",
            default_value="",
            tooltip="extra",
            mode_allowed_property=True,
        ),
        group,
    ),
    "group_a_connected_node": _group_and_wire,
    "rename_a_connected_parameter": lambda engine, group: _send(
        engine, RenameParameterRequest(node_name="C", parameter_name="extra", new_parameter_name="renamed"), group
    ),
    "duplicate": lambda engine, group: _send(
        engine, DuplicateSelectedNodesRequest(nodes_to_duplicate=[["A", "0"], ["B", "0"]]), group
    ),
    "paste": _paste,
    "auto_layout": lambda engine, group: _send(engine, AutoLayoutFlowRequest(flow_name="main"), group),
    "remove_parameter": lambda engine, group: _send(
        engine, RemoveParameterFromNodeRequest(node_name="C", parameter_name="extra"), group
    ),
    "take_a_node_out_of_its_group": lambda engine, group: _send(
        engine, RemoveNodeFromNodeGroupRequest(node_names=["C"], node_group_name="H", flow_name="main"), group
    ),
    "put_a_node_into_a_group": lambda engine, group: _send(
        engine, AddNodesToNodeGroupRequest(node_names=["A"], node_group_name="H", flow_name="main"), group
    ),
    "delete_a_group": lambda engine, group: _send(engine, DeleteNodeRequest(node_name="H"), group),
}


def _setup(engine: Engine) -> None:
    """A small workflow with a connection to every kind of node the scenarios touch."""
    _create(engine, "A")
    _create(engine, "B")
    _create(engine, "C")
    _create(engine, "T", node_type="_Toggle")
    _create(engine, "M", node_type="_Mirror")
    _create(engine, "F")
    # A fans out, so a connection put back has to return to its place among A's outgoing ones.
    _send(engine, _connection("A", "B"), uuid.uuid4().hex)
    _send(engine, _connection("A", "F"), uuid.uuid4().hex)
    _send(engine, SetParameterValueRequest(node_name="M", parameter_name="target", value="C"), uuid.uuid4().hex)
    _send(engine, SetParameterValueRequest(node_name="C", parameter_name="text", value="c"), uuid.uuid4().hex)
    _send(
        engine,
        AddParameterToNodeRequest(
            node_name="C",
            parameter_name="extra",
            type="str",
            default_value="",
            tooltip="extra",
            mode_allowed_property=True,
            mode_allowed_output=True,
            is_user_defined=True,
        ),
        uuid.uuid4().hex,
    )
    _create(engine, "D")
    _create(engine, "E")
    _send(engine, _connection("C", "D"), uuid.uuid4().hex)
    _send(engine, _connection("C", "E", source_parameter="extra"), uuid.uuid4().hex)
    _send(
        engine,
        CreateNodeRequest(node_type="_Subflow", specific_library_name=_LIBRARY, node_name="H", node_names_to_add=["C"]),
        uuid.uuid4().hex,
    )


@pytest.mark.parametrize("scenario", sorted(_SCENARIOS))
def test_undo_and_redo_round_trip(engine: Engine, scenario: str) -> None:
    """Undo restores the state before the edit and redo the state after it, twice over."""
    _setup(engine)
    before = _fingerprint(engine)
    _SCENARIOS[scenario](engine, f"scenario-{scenario}")
    after = _fingerprint(engine)
    assert after != before, "The scenario changed nothing, so it tests nothing."

    for _ in range(2):
        undone = engine.handle_request(UndoRequest(undo_group=uuid.uuid4().hex))
        assert isinstance(undone, UndoResultSuccess), undone.result_details
        assert "could not be restored" not in str(undone.result_details)
        assert _fingerprint(engine) == before

        redone = engine.handle_request(RedoRequest(undo_group=uuid.uuid4().hex))
        assert isinstance(redone, RedoResultSuccess), redone.result_details
        assert _fingerprint(engine) == after


def test_every_step_undone_returns_to_the_start_and_redone_to_the_end(engine: Engine) -> None:
    """Steps undone one after another unwind the whole session, and redone replay it."""
    start = _fingerprint(engine)
    _setup(engine)
    for scenario in ("value", "connect", "group_a_connected_node", "lock", "paste", "rename_connected_node"):
        _SCENARIOS[scenario](engine, f"step-{scenario}")
    end = _fingerprint(engine)

    while isinstance(engine.handle_request(UndoRequest(undo_group=uuid.uuid4().hex)), UndoResultSuccess):
        pass
    assert _fingerprint(engine) == start
    while isinstance(engine.handle_request(RedoRequest(undo_group=uuid.uuid4().hex)), RedoResultSuccess):
        pass
    assert _fingerprint(engine) == end
