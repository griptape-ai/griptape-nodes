"""Capturing nodes and restoring either side of a history entry on a real engine.

Entries are built by hand from images of real nodes, so these tests exercise state capture and
replay without the recording that produces entries in the editor.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest

from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.node_groups.base_node_group import BaseNodeGroup
from griptape_nodes.exe_types.node_types import BaseNode
from griptape_nodes.node_library.library_registry import (
    LibraryMetadata,
    LibraryRegistry,
    LibrarySchema,
    NodeMetadata,
)
from griptape_nodes.retained_mode.events.connection_events import CreateConnectionRequest, DeleteConnectionRequest
from griptape_nodes.retained_mode.events.flow_events import CreateFlowRequest
from griptape_nodes.retained_mode.events.node_events import (
    AddNodesToNodeGroupRequest,
    CreateNodeRequest,
    DeleteNodeRequest,
    SetNodeMetadataRequest,
)
from griptape_nodes.retained_mode.events.object_events import RenameObjectRequest
from griptape_nodes.retained_mode.events.parameter_events import SetParameterValueRequest
from griptape_nodes.retained_mode.managers.undo.history import HistoryEntry, NodeChange
from griptape_nodes.retained_mode.managers.undo.replay import Direction, replay
from griptape_nodes.retained_mode.managers.undo.snapshot import ConnectionKey, NodeImage, capture_node

if TYPE_CHECKING:
    from collections.abc import Iterator

    from griptape_nodes.retained_mode.engine import Engine

_LIBRARY = "undo-replay-test-library"


class _Probe(BaseNode):
    def __init__(self, name: str, metadata: dict[Any, Any] | None = None) -> None:
        super().__init__(name, metadata)
        self.add_parameter(
            Parameter(
                name="text",
                type="str",
                default_value="",
                tooltip="text",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY, ParameterMode.OUTPUT},
            )
        )

    def process(self) -> None:
        self.parameter_output_values["text"] = self.get_parameter_value("text")


class _Toggle(BaseNode):
    """Shows its `detail` parameter only while `mode` is "detailed", the way many library nodes do."""

    def __init__(self, name: str, metadata: dict[Any, Any] | None = None) -> None:
        super().__init__(name, metadata)
        self.add_parameter(
            Parameter(
                name="mode", type="str", default_value="simple", tooltip="mode", allowed_modes={ParameterMode.PROPERTY}
            )
        )
        self.add_parameter(
            Parameter(
                name="detail",
                type="str",
                default_value="",
                tooltip="detail",
                allowed_modes={ParameterMode.PROPERTY},
                ui_options={"hide": True},
            )
        )

    def after_value_set(self, parameter: Parameter, value: Any) -> None:
        if parameter.name == "mode":
            if value == "detailed":
                self.show_parameter_by_name("detail")
            else:
                self.hide_parameter_by_name("detail")
        return super().after_value_set(parameter, value)

    def process(self) -> None:
        return None


class _Dynamic(BaseNode):
    """Adds an `extra` input while `mode` is "on" and removes it otherwise, as dynamic-input nodes do."""

    def __init__(self, name: str, metadata: dict[Any, Any] | None = None) -> None:
        super().__init__(name, metadata)
        self.add_parameter(
            Parameter(
                name="mode", type="str", default_value="off", tooltip="mode", allowed_modes={ParameterMode.PROPERTY}
            )
        )

    def after_value_set(self, parameter: Parameter, value: Any) -> None:
        if parameter.name == "mode":
            if value == "on" and self.get_parameter_by_name("extra") is None:
                self.add_parameter(
                    Parameter(
                        name="extra",
                        type="str",
                        default_value="",
                        tooltip="extra",
                        allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                    )
                )
            elif value != "on":
                self.remove_parameter_element_by_name("extra")
        return super().after_value_set(parameter, value)

    def process(self) -> None:
        return None


class _Group(BaseNodeGroup):
    def process(self) -> None:
        return None


@pytest.fixture
def engine(engine: Engine) -> Iterator[Engine]:
    """An engine with a workflow and flow open and the test nodes registered."""
    LibraryRegistry._clear()
    schema = LibrarySchema(
        name=_LIBRARY,
        library_schema_version=LibrarySchema.LATEST_SCHEMA_VERSION,
        metadata=LibraryMetadata(author="t", description="d", library_version="1.0.0", engine_version="1.0.0", tags=[]),
        categories=[],
        nodes=[],
    )
    library = LibraryRegistry.generate_new_library(library_data=schema)
    for node_class in (_Probe, _Toggle, _Dynamic, _Group):
        library.register_new_node_type(
            node_class, NodeMetadata(category="t", description="d", display_name=node_class.__name__)
        )

    engine.context_manager.push_workflow("undo_replay_test_workflow")
    engine.handle_request(CreateFlowRequest(parent_flow_name=None, flow_name="main", set_as_new_context=True))
    yield engine
    LibraryRegistry._clear()


def _send(engine: Engine, request: Any) -> None:
    result = engine.handle_request(request)
    assert result.succeeded(), result.result_details


def _create(engine: Engine, name: str, node_type: str = "_Probe", **kwargs: Any) -> None:
    _send(engine, CreateNodeRequest(node_type=node_type, specific_library_name=_LIBRARY, node_name=name, **kwargs))


def _set(engine: Engine, node_name: str, parameter_name: str, value: Any) -> None:
    _send(engine, SetParameterValueRequest(node_name=node_name, parameter_name=parameter_name, value=value))


def _connect(engine: Engine, source: str, target: str) -> None:
    _send(
        engine,
        CreateConnectionRequest(
            source_node_name=source, source_parameter_name="text", target_node_name=target, target_parameter_name="text"
        ),
    )


def _connect_request(source: str, source_parameter: str, target: str, target_parameter: str) -> CreateConnectionRequest:
    return CreateConnectionRequest(
        source_node_name=source,
        source_parameter_name=source_parameter,
        target_node_name=target,
        target_parameter_name=target_parameter,
    )


def _disconnect_request(
    source: str, source_parameter: str, target: str, target_parameter: str
) -> DeleteConnectionRequest:
    return DeleteConnectionRequest(
        source_node_name=source,
        source_parameter_name=source_parameter,
        target_node_name=target,
        target_parameter_name=target_parameter,
    )


def _node(engine: Engine, name: str) -> BaseNode | None:
    return engine.object_manager.attempt_get_object_by_name_as_type(name, BaseNode)


def _image(engine: Engine, name: str) -> NodeImage:
    node = _node(engine, name)
    assert node is not None
    image = capture_node(engine, node)
    assert image is not None
    return image


def _value(engine: Engine, node_name: str, parameter_name: str) -> Any:
    node = _node(engine, node_name)
    assert node is not None
    return node.get_parameter_value(parameter_name)


def _connections(engine: Engine) -> set[tuple[str, str, str, str]]:
    return {
        (c.source_node.name, c.source_parameter.name, c.target_node.name, c.target_parameter.name)
        for c in engine.flow_manager.get_connections().connections.values()
    }


class TestCapture:
    def test_image_records_the_live_node(self, engine: Engine) -> None:
        _create(engine, "A", metadata={"position": {"x": 1, "y": 2}, "note": "hi"})
        _create(engine, "B")
        _set(engine, "A", "text", "hello")
        _connect(engine, "A", "B")

        image = _image(engine, "A")

        assert (image.name, image.node_type, image.flow_name) == ("A", "_Probe", "main")
        assert image.parameters == ("text",)
        assert image.metadata["position"] == {"x": 1, "y": 2}
        assert image.metadata["note"] == "hi"
        assert "library" not in image.metadata
        assert "text" in image.values
        assert "text" in image.explicit_values
        assert image.connections == {ConnectionKey("A", "text", "B", "text")}

    def test_only_a_changed_node_has_a_different_state(self, engine: Engine) -> None:
        _create(engine, "A")
        before = _image(engine, "A")

        assert before.same_state(_image(engine, "A"))

        _set(engine, "A", "text", "hello")

        assert not before.same_state(_image(engine, "A"))
        assert before.changed_values(_image(engine, "A")) == {"text"}


class TestReplay:
    def test_deleted_node_comes_back_with_its_value_and_goes_again(self, engine: Engine) -> None:
        _create(engine, "A")
        _set(engine, "A", "text", "hello")
        entry = HistoryEntry(changes=[NodeChange(before=_image(engine, "A"), after=None)])
        _send(engine, DeleteNodeRequest(node_name="A"))

        assert replay(engine, entry, Direction.UNDO) == []
        assert _value(engine, "A", "text") == "hello"

        assert replay(engine, entry, Direction.REDO) == []
        assert _node(engine, "A") is None

    def test_created_node_goes_and_comes_back_with_its_value(self, engine: Engine) -> None:
        _create(engine, "A", metadata={"position": {"x": 3, "y": 4}})
        _set(engine, "A", "text", "hello")
        entry = HistoryEntry(changes=[NodeChange(before=None, after=_image(engine, "A"))])

        assert replay(engine, entry, Direction.UNDO) == []
        assert _node(engine, "A") is None

        assert replay(engine, entry, Direction.REDO) == []
        assert _value(engine, "A", "text") == "hello"
        node = _node(engine, "A")
        assert node is not None
        assert node.metadata["position"] == {"x": 3, "y": 4}

    def test_values_and_layout_restore_both_ways_including_removal_of_a_new_key(self, engine: Engine) -> None:
        _create(engine, "A", metadata={"position": {"x": 0, "y": 0}})
        before = _image(engine, "A")
        _set(engine, "A", "text", "hello")
        _send(engine, SetNodeMetadataRequest(node_name="A", metadata={"position": {"x": 9, "y": 9}, "note": "new"}))
        entry = HistoryEntry(changes=[NodeChange(before=before, after=_image(engine, "A"))])
        node = _node(engine, "A")
        assert node is not None

        assert replay(engine, entry, Direction.UNDO) == []
        assert _value(engine, "A", "text") == ""
        assert node.metadata["position"] == {"x": 0, "y": 0}
        assert "note" not in node.metadata

        assert replay(engine, entry, Direction.REDO) == []
        assert _value(engine, "A", "text") == "hello"
        assert node.metadata["position"] == {"x": 9, "y": 9}
        assert node.metadata["note"] == "new"

    def test_connecting_overwrites_a_value_that_replay_then_restores(self, engine: Engine) -> None:
        _create(engine, "A")
        _create(engine, "B")
        _set(engine, "A", "text", "from A")
        _set(engine, "B", "text", "mine")
        before = _image(engine, "B")
        _connect(engine, "A", "B")
        after = _image(engine, "B")
        key = ConnectionKey("A", "text", "B", "text")
        entry = HistoryEntry(changes=[NodeChange(before=before, after=after)], connections_added=frozenset({key}))

        assert replay(engine, entry, Direction.UNDO) == []
        assert _connections(engine) == set()
        assert _value(engine, "B", "text") == "mine"

        assert replay(engine, entry, Direction.REDO) == []
        assert _connections(engine) == {("A", "text", "B", "text")}
        assert _value(engine, "B", "text") == after.value_pool[after.values["text"]]

    def test_deleting_a_connected_node_restores_the_connection_when_it_comes_back(self, engine: Engine) -> None:
        _create(engine, "A")
        _create(engine, "B")
        _connect(engine, "A", "B")
        key = ConnectionKey("A", "text", "B", "text")
        entry = HistoryEntry(
            changes=[NodeChange(before=_image(engine, "A"), after=None)], connections_removed=frozenset({key})
        )
        _send(engine, DeleteNodeRequest(node_name="A"))

        assert replay(engine, entry, Direction.UNDO) == []
        assert _connections(engine) == {("A", "text", "B", "text")}

        assert replay(engine, entry, Direction.REDO) == []
        assert _node(engine, "A") is None
        assert _connections(engine) == set()

    def test_a_value_that_reshapes_the_node_restores_its_parameters(self, engine: Engine) -> None:
        _create(engine, "T", node_type="_Toggle")
        before = _image(engine, "T")
        _set(engine, "T", "mode", "detailed")
        after = _image(engine, "T")
        assert before.structure != after.structure
        entry = HistoryEntry(changes=[NodeChange(before=before, after=after)])

        assert replay(engine, entry, Direction.UNDO) == []
        assert _image(engine, "T").structure == before.structure

        assert replay(engine, entry, Direction.REDO) == []
        assert _image(engine, "T").structure == after.structure

    def test_a_connection_to_a_parameter_that_a_value_removes_comes_back_with_the_parameter(
        self, engine: Engine
    ) -> None:
        _create(engine, "A")
        _create(engine, "D", node_type="_Dynamic")
        _set(engine, "A", "text", "from A")
        _set(engine, "D", "mode", "on")
        _send(engine, _connect_request("A", "text", "D", "extra"))
        before = _image(engine, "D")
        key = ConnectionKey("A", "text", "D", "extra")
        _send(engine, _disconnect_request("A", "text", "D", "extra"))
        _set(engine, "D", "mode", "off")
        entry = HistoryEntry(
            changes=[NodeChange(before=before, after=_image(engine, "D"))], connections_removed=frozenset({key})
        )
        assert _node(engine, "D").get_parameter_by_name("extra") is None  # type: ignore[union-attr]

        assert replay(engine, entry, Direction.UNDO) == []
        assert _image(engine, "D").structure == before.structure
        assert _connections(engine) == {("A", "text", "D", "extra")}
        assert (_value(engine, "D", "mode"), _value(engine, "D", "extra")) == ("on", "from A")

        assert replay(engine, entry, Direction.REDO) == []
        assert _connections(engine) == set()
        assert _value(engine, "D", "mode") == "off"
        assert _node(engine, "D").get_parameter_by_name("extra") is None  # type: ignore[union-attr]

    def test_a_connection_to_a_parameter_that_a_value_adds_is_made_with_the_parameter(self, engine: Engine) -> None:
        _create(engine, "A")
        _create(engine, "D", node_type="_Dynamic")
        _set(engine, "A", "text", "from A")
        before = _image(engine, "D")
        _set(engine, "D", "mode", "on")
        _send(engine, _connect_request("A", "text", "D", "extra"))
        key = ConnectionKey("A", "text", "D", "extra")
        entry = HistoryEntry(
            changes=[NodeChange(before=before, after=_image(engine, "D"))], connections_added=frozenset({key})
        )

        assert replay(engine, entry, Direction.UNDO) == []
        assert _connections(engine) == set()
        assert _value(engine, "D", "mode") == "off"
        assert _node(engine, "D").get_parameter_by_name("extra") is None  # type: ignore[union-attr]

        assert replay(engine, entry, Direction.REDO) == []
        assert _connections(engine) == {("A", "text", "D", "extra")}
        assert (_value(engine, "D", "mode"), _value(engine, "D", "extra")) == ("on", "from A")

    def test_a_connection_whose_parameter_never_comes_back_is_reported_once(self, engine: Engine) -> None:
        _create(engine, "A")
        _create(engine, "D", node_type="_Dynamic")
        key = ConnectionKey("A", "text", "D", "extra")
        entry = HistoryEntry(changes=[], connections_removed=frozenset({key}))

        assert replay(engine, entry, Direction.UNDO) == ["Could not reconnect 'A' to 'D'."]
        assert _connections(engine) == set()

    def test_group_membership_restores_both_ways(self, engine: Engine) -> None:
        _create(engine, "A")
        _create(engine, "G", node_type="_Group")
        before = [_image(engine, "A"), _image(engine, "G")]
        _send(engine, AddNodesToNodeGroupRequest(node_names=["A"], node_group_name="G", flow_name="main"))
        after = [_image(engine, "A"), _image(engine, "G")]
        entry = HistoryEntry(changes=[NodeChange(before=b, after=a) for b, a in zip(before, after, strict=True)])
        node, group = _node(engine, "A"), _node(engine, "G")
        assert node is not None
        assert isinstance(group, BaseNodeGroup)

        assert replay(engine, entry, Direction.UNDO) == []
        assert node.parent_group is None
        assert "A" not in group.nodes

        assert replay(engine, entry, Direction.REDO) == []
        assert node.parent_group is group
        assert "A" in group.nodes

    def test_swapped_names_are_restored(self, engine: Engine) -> None:
        _create(engine, "A")
        _create(engine, "B")
        _set(engine, "A", "text", "a")
        _set(engine, "B", "text", "b")
        before = [_image(engine, "A"), _image(engine, "B")]
        _send(engine, RenameObjectRequest(object_name="A", requested_name="tmp"))
        _send(engine, RenameObjectRequest(object_name="B", requested_name="A"))
        _send(engine, RenameObjectRequest(object_name="tmp", requested_name="B"))
        after = [_image(engine, "B"), _image(engine, "A")]
        entry = HistoryEntry(changes=[NodeChange(before=b, after=a) for b, a in zip(before, after, strict=True)])

        assert replay(engine, entry, Direction.UNDO) == []
        assert (_value(engine, "A", "text"), _value(engine, "B", "text")) == ("a", "b")

        assert replay(engine, entry, Direction.REDO) == []
        assert (_value(engine, "A", "text"), _value(engine, "B", "text")) == ("b", "a")
