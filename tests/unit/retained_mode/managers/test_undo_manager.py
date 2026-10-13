"""Undo and redo of edits to the current workflow.

Each test drives the engine the way the editor does: every request carries the `undo_group` of the
user action it belongs to, and Undo and Redo are requests too.
"""

from __future__ import annotations

import contextvars
import uuid
from contextlib import contextmanager
from typing import TYPE_CHECKING, Any
from unittest.mock import patch

import pytest

from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.flow import ControlFlow
from griptape_nodes.exe_types.node_groups.base_node_group import BaseNodeGroup
from griptape_nodes.exe_types.node_types import BaseNode
from griptape_nodes.node_library.library_registry import (
    LibraryMetadata,
    LibraryRegistry,
    LibrarySchema,
    NodeMetadata,
)
from griptape_nodes.retained_mode.events.base_events import AppEvent, GriptapeNodeEvent
from griptape_nodes.retained_mode.events.connection_events import CreateConnectionRequest, DeleteConnectionRequest
from griptape_nodes.retained_mode.events.context_events import SetWorkflowContextRequest
from griptape_nodes.retained_mode.events.flow_events import AutoLayoutFlowRequest, CreateFlowRequest
from griptape_nodes.retained_mode.events.node_events import (
    AddNodesToNodeGroupRequest,
    CreateNodeRequest,
    DeleteNodeRequest,
    DeleteNodeResultFailure,
    DeserializeNodeFromCommandsRequest,
    DeserializeNodeFromCommandsResultFailure,
    GetNodeMetadataRequest,
    MoveNodeToNewFlowRequest,
    RemoveNodeFromNodeGroupRequest,
    SerializeNodeToCommandsResultFailure,
    SetLockNodeStateRequest,
    SetNodeMetadataRequest,
    UnresolveNodeRequest,
)
from griptape_nodes.retained_mode.events.object_events import ClearAllObjectStateRequest, RenameObjectRequest
from griptape_nodes.retained_mode.events.parameter_events import (
    AddParameterToNodeRequest,
    RemoveParameterFromNodeRequest,
    SetParameterValueRequest,
)
from griptape_nodes.retained_mode.events.undo_events import (
    ClearUndoHistoryRequest,
    GetUndoHistoryRequest,
    GetUndoHistoryResultSuccess,
    RedoRequest,
    RedoResultFailure,
    RedoResultSuccess,
    UndoHistoryChanged,
    UndoRequest,
    UndoResultFailure,
    UndoResultSuccess,
)
from griptape_nodes.retained_mode.managers.undo.recording import Edit
from griptape_nodes.retained_mode.managers.undo.snapshot import capture_node

if TYPE_CHECKING:
    from collections.abc import Iterator

    from griptape_nodes.retained_mode.engine import Engine
    from griptape_nodes.retained_mode.events.base_events import RequestPayload, ResultPayload

_LIBRARY = "undo-test-library"


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


class _Sealed(BaseNode):
    """Holds a value a person cannot set, the way nodes guard values they compute."""

    def __init__(self, name: str, metadata: dict[Any, Any] | None = None) -> None:
        super().__init__(name, metadata)
        self.add_parameter(
            Parameter(
                name="text",
                type="str",
                default_value="",
                tooltip="text",
                allowed_modes={ParameterMode.PROPERTY},
                settable=False,
            )
        )

    def process(self) -> None:
        return None


class _Optional(BaseNode):
    """Has no default, like most media inputs."""

    def __init__(self, name: str, metadata: dict[Any, Any] | None = None) -> None:
        super().__init__(name, metadata)
        self.add_parameter(
            Parameter(
                name="text", type="str", default_value=None, tooltip="text", allowed_modes={ParameterMode.PROPERTY}
            )
        )

    def process(self) -> None:
        return None


class _Group(BaseNodeGroup):
    def process(self) -> None:
        return None


@pytest.fixture
def engine(engine: Engine) -> Iterator[Engine]:
    """An engine with a workflow and flow open and the probe nodes registered."""
    LibraryRegistry._clear()
    schema = LibrarySchema(
        name=_LIBRARY,
        library_schema_version=LibrarySchema.LATEST_SCHEMA_VERSION,
        metadata=LibraryMetadata(author="t", description="d", library_version="1.0.0", engine_version="1.0.0", tags=[]),
        categories=[],
        nodes=[],
    )
    library = LibraryRegistry.generate_new_library(library_data=schema)
    for node_class in (_Probe, _Toggle, _Sealed, _Optional, _Group):
        library.register_new_node_type(
            node_class, NodeMetadata(category="t", description="d", display_name=node_class.__name__)
        )

    engine.context_manager.push_workflow("undo_test_workflow")
    engine.handle_request(CreateFlowRequest(parent_flow_name=None, flow_name="main", set_as_new_context=True))
    yield engine
    LibraryRegistry._clear()


def _edit(engine: Engine, request: RequestPayload, group: str | None = None) -> ResultPayload:
    """Send a request the way the editor does, as part of a user action."""
    request.undo_group = group or uuid.uuid4().hex
    result = engine.handle_request(request)
    assert result.succeeded(), result.result_details
    return result


def _undo(engine: Engine, group: str | None = None) -> ResultPayload:
    return engine.handle_request(UndoRequest(undo_group=group or uuid.uuid4().hex))


def _redo(engine: Engine, group: str | None = None) -> ResultPayload:
    return engine.handle_request(RedoRequest(undo_group=group or uuid.uuid4().hex))


def _history(engine: Engine) -> GetUndoHistoryResultSuccess:
    result = engine.handle_request(GetUndoHistoryRequest())
    assert isinstance(result, GetUndoHistoryResultSuccess)
    return result


def _node(engine: Engine, name: str) -> BaseNode | None:
    return engine.object_manager.attempt_get_object_by_name_as_type(name, BaseNode)


def _value(engine: Engine, node_name: str, parameter_name: str) -> Any:
    node = _node(engine, node_name)
    assert node is not None
    return node.get_parameter_value(parameter_name)


def _connections(engine: Engine) -> set[tuple[str, str, str, str]]:
    return {
        (c.source_node.name, c.source_parameter.name, c.target_node.name, c.target_parameter.name)
        for c in engine.flow_manager.get_connections().connections.values()
    }


def _create(engine: Engine, name: str, node_type: str = "_Probe", **kwargs: Any) -> None:
    _edit(engine, CreateNodeRequest(node_type=node_type, specific_library_name=_LIBRARY, node_name=name, **kwargs))


def _connect(engine: Engine, source: str, target: str) -> None:
    _edit(
        engine,
        CreateConnectionRequest(
            source_node_name=source, source_parameter_name="text", target_node_name=target, target_parameter_name="text"
        ),
    )


class TestRecording:
    def test_each_user_action_is_one_step(self, engine: Engine) -> None:
        _create(engine, "A")
        _edit(engine, SetParameterValueRequest(node_name="A", parameter_name="text", value="hello"))

        assert _history(engine).undo_labels == ["Add 'A'", "Change 'text' on 'A'"]

    def test_requests_sharing_a_group_are_one_step(self, engine: Engine) -> None:
        """A drag sends one request per node, and the editor follows a create with its own requests."""
        _create(engine, "A")
        _create(engine, "B")

        _edit(engine, SetNodeMetadataRequest(node_name="A", metadata={"position": {"x": 1, "y": 1}}), "drag")
        _edit(engine, SetNodeMetadataRequest(node_name="B", metadata={"position": {"x": 2, "y": 2}}), "drag")

        assert _history(engine).undo_labels[-1] == "Move 2 nodes"
        assert isinstance(_undo(engine), UndoResultSuccess)
        assert _node(engine, "A").metadata.get("position") != {"x": 1, "y": 1}  # type: ignore[union-attr]
        assert _node(engine, "B").metadata.get("position") != {"x": 2, "y": 2}  # type: ignore[union-attr]

    def test_requests_without_a_group_are_not_recorded(self, engine: Engine) -> None:
        """A library process forwards the requests its nodes make with a request id but no group."""
        engine.event_manager.handle_request(
            CreateNodeRequest(node_type="_Probe", specific_library_name=_LIBRARY, node_name="A"),
            result_context={"request_id": "request-1"},
        )

        assert _history(engine).undo_labels == []

    def test_requests_the_engine_sends_itself_are_not_recorded(self, engine: Engine) -> None:
        engine.handle_request(CreateNodeRequest(node_type="_Probe", specific_library_name=_LIBRARY, node_name="A"))

        assert _history(engine).undo_labels == []

    def test_reads_and_no_op_edits_leave_no_step(self, engine: Engine) -> None:
        _create(engine, "A")
        _edit(engine, GetNodeMetadataRequest(node_name="A"))
        _edit(engine, SetParameterValueRequest(node_name="A", parameter_name="text", value=""))

        assert _history(engine).undo_labels == ["Add 'A'"]

    def test_a_new_edit_clears_redo(self, engine: Engine) -> None:
        _create(engine, "A")
        _undo(engine)
        _create(engine, "B")

        assert _history(engine).redo_labels == []

    def test_switching_workflows_clears_history(self, engine: Engine) -> None:
        _create(engine, "A")
        engine.context_manager.push_workflow("another_workflow")
        labels = _history(engine).undo_labels
        engine.context_manager.pop_workflow()

        assert labels == []

    def test_renaming_the_workflow_keeps_history(self, engine: Engine) -> None:
        _create(engine, "A")
        engine.context_manager.set_current_workflow_name("saved_workflow")

        assert isinstance(_undo(engine), UndoResultSuccess)
        assert _node(engine, "A") is None

    def test_requests_that_replace_the_workflow_clear_history(self, engine: Engine) -> None:
        _create(engine, "A")
        engine.handle_request(ClearAllObjectStateRequest(i_know_what_im_doing=True, undo_group="switch"))

        assert _history(engine).undo_labels == []

    def test_requests_that_replace_the_workflow_without_a_group_clear_history(self, engine: Engine) -> None:
        _create(engine, "A")
        engine.handle_request(ClearAllObjectStateRequest(i_know_what_im_doing=True))

        assert _history(engine).undo_labels == []

    def test_closing_the_workflow_clears_history(self, engine: Engine) -> None:
        _create(engine, "A")
        node = _node(engine, "A")
        workflow = engine.context_manager.get_current_workflow_state()
        moved = {"x": 1, "y": 1}

        # The workflow closes as the request's change lands.
        def current_workflow() -> object:
            if node is not None and node.metadata.get("position") == moved:
                return None
            return workflow

        with (
            patch.object(engine.context_manager, "get_current_workflow_state", side_effect=current_workflow),
            patch.object(engine.event_manager, "put_event") as put_event,
        ):
            _edit(engine, SetNodeMetadataRequest(node_name="A", metadata={"position": moved}))

        announced = [
            call.args[0].payload
            for call in put_event.call_args_list
            if isinstance(call.args[0], AppEvent) and isinstance(call.args[0].payload, UndoHistoryChanged)
        ]
        assert announced[-1] == UndoHistoryChanged(undo_label=None, redo_label=None)

    def test_a_refused_workflow_switch_keeps_history(self, engine: Engine) -> None:
        _create(engine, "A")
        result = engine.handle_request(SetWorkflowContextRequest(workflow_name="other", undo_group="switch"))

        assert not result.succeeded()
        assert _history(engine).undo_labels == ["Add 'A'"]

    def test_undo_refuses_history_from_another_workflow(self, engine: Engine) -> None:
        _create(engine, "A")

        engine.context_manager.push_workflow("another_workflow")
        result = _undo(engine)
        engine.context_manager.pop_workflow()

        assert isinstance(result, UndoResultFailure)
        assert _node(engine, "A") is not None

    def test_a_request_naming_the_context_node_is_recorded(self, engine: Engine) -> None:
        _create(engine, "A")
        node = _node(engine, "A")
        assert node is not None
        position_before = node.metadata.get("position")

        with engine.context_manager.node(node):
            _edit(engine, SetNodeMetadataRequest(node_name=None, metadata={"position": {"x": 5, "y": 5}}))
        _undo(engine)

        assert node.metadata.get("position") == position_before

    def test_history_changes_are_announced(self, engine: Engine) -> None:
        with patch.object(engine.event_manager, "put_event") as put_event:
            _create(engine, "A")

        announced = [
            call.args[0].payload
            for call in put_event.call_args_list
            if isinstance(call.args[0], AppEvent) and isinstance(call.args[0].payload, UndoHistoryChanged)
        ]
        assert announced == [UndoHistoryChanged(undo_label="Add 'A'", redo_label=None)]


class TestNodes:
    def test_undo_and_redo_a_new_node(self, engine: Engine) -> None:
        create = CreateNodeRequest(
            node_type="_Probe", specific_library_name=_LIBRARY, node_name="A", metadata={"position": {"x": 5, "y": 6}}
        )
        _edit(engine, create, "create")
        _edit(engine, SetParameterValueRequest(node_name="A", parameter_name="text", value="kept"), "create")

        _undo(engine)
        assert _node(engine, "A") is None

        _redo(engine)
        assert _value(engine, "A", "text") == "kept"
        assert _node(engine, "A").metadata["position"] == {"x": 5, "y": 6}  # type: ignore[union-attr]

    def test_undo_a_delete_restores_values_and_connections(self, engine: Engine) -> None:
        _create(engine, "A")
        _create(engine, "B")
        _connect(engine, "A", "B")
        _edit(engine, SetParameterValueRequest(node_name="A", parameter_name="text", value="hello"))

        _edit(engine, DeleteNodeRequest(node_name="A"))
        assert _connections(engine) == set()

        result = _undo(engine)
        assert isinstance(result, UndoResultSuccess)
        assert result.label == "Delete 'A'"
        assert _value(engine, "A", "text") == "hello"
        assert _connections(engine) == {("A", "text", "B", "text")}

    def test_undo_a_rename_keeps_connections(self, engine: Engine) -> None:
        _create(engine, "A")
        _create(engine, "B")
        _connect(engine, "A", "B")

        _edit(engine, RenameObjectRequest(object_name="A", requested_name="Renamed"))
        _undo(engine)

        assert _node(engine, "Renamed") is None
        assert _connections(engine) == {("A", "text", "B", "text")}
        _redo(engine)
        assert _connections(engine) == {("Renamed", "text", "B", "text")}

    def test_undo_lock(self, engine: Engine) -> None:
        _create(engine, "A")
        _edit(engine, SetLockNodeStateRequest(node_name="A", lock=True))

        _undo(engine)

        assert _node(engine, "A").lock is False  # type: ignore[union-attr]

    def test_undo_removes_a_metadata_key_the_edit_added(self, engine: Engine) -> None:
        _create(engine, "A")
        _edit(engine, SetNodeMetadataRequest(node_name="A", metadata={"collapsed": True}))

        _undo(engine)

        assert "collapsed" not in _node(engine, "A").metadata  # type: ignore[union-attr]


class TestValuesAndConnections:
    def test_undo_a_value(self, engine: Engine) -> None:
        _create(engine, "A")
        _edit(engine, SetParameterValueRequest(node_name="A", parameter_name="text", value="one"))
        _edit(engine, SetParameterValueRequest(node_name="A", parameter_name="text", value="two"))

        _undo(engine)
        assert _value(engine, "A", "text") == "one"
        _redo(engine)
        assert _value(engine, "A", "text") == "two"

    def test_undo_a_value_lets_the_node_update_its_own_parameters(self, engine: Engine) -> None:
        """The node hides `detail` again itself, so nothing has to rebuild it."""
        _create(engine, "T", node_type="_Toggle")
        _edit(engine, SetParameterValueRequest(node_name="T", parameter_name="mode", value="detailed"))
        toggle = _node(engine, "T")
        assert toggle is not None

        _undo(engine)

        assert _node(engine, "T") is toggle
        assert toggle.get_parameter_by_name("detail").ui_options.get("hide") is True  # type: ignore[union-attr]

    def test_undo_a_connection_restores_the_value_it_overwrote(self, engine: Engine) -> None:
        _create(engine, "A")
        _create(engine, "B")
        _edit(engine, SetParameterValueRequest(node_name="A", parameter_name="text", value="upstream"))
        _edit(engine, SetParameterValueRequest(node_name="B", parameter_name="text", value="own"))
        _connect(engine, "A", "B")
        assert _value(engine, "B", "text") == "upstream"

        result = _undo(engine)

        assert isinstance(result, UndoResultSuccess)
        assert result.label == "Connect 'A' to 'B'"
        assert _connections(engine) == set()
        assert _value(engine, "B", "text") == "own"

    def test_undo_a_disconnect(self, engine: Engine) -> None:
        _create(engine, "A")
        _create(engine, "B")
        _connect(engine, "A", "B")
        _edit(
            engine,
            DeleteConnectionRequest(
                source_node_name="A", source_parameter_name="text", target_node_name="B", target_parameter_name="text"
            ),
        )

        _undo(engine)

        assert _connections(engine) == {("A", "text", "B", "text")}


class TestStructure:
    def test_undo_an_added_parameter(self, engine: Engine) -> None:
        _create(engine, "A")
        _edit(
            engine,
            AddParameterToNodeRequest(
                node_name="A",
                parameter_name="extra",
                type="str",
                default_value="x",
                tooltip="extra",
                mode_allowed_property=True,
                is_user_defined=True,
            ),
        )
        assert _history(engine).undo_labels[-1] == "Add 'extra' to 'A'"

        _undo(engine)
        assert _node(engine, "A").get_parameter_by_name("extra") is None  # type: ignore[union-attr]
        _redo(engine)
        assert _node(engine, "A").get_parameter_by_name("extra") is not None  # type: ignore[union-attr]


class TestGroups:
    def test_undo_and_redo_making_a_group(self, engine: Engine) -> None:
        _create(engine, "A")
        _create(engine, "G", node_type="_Group", node_names_to_add=["A"])

        _undo(engine)
        assert _node(engine, "G") is None
        assert _node(engine, "A").parent_group is None  # type: ignore[union-attr]

        _redo(engine)
        group = _node(engine, "G")
        assert isinstance(group, BaseNodeGroup)
        assert list(group.nodes) == ["A"]

    def test_undo_deleting_a_group_brings_its_members_back_in(self, engine: Engine) -> None:
        _create(engine, "A")
        _create(engine, "G", node_type="_Group", node_names_to_add=["A"])
        _edit(engine, DeleteNodeRequest(node_name="G"))

        _undo(engine)

        group = _node(engine, "G")
        assert isinstance(group, BaseNodeGroup)
        assert list(group.nodes) == ["A"]
        assert _node(engine, "A").parent_group is group  # type: ignore[union-attr]

    def test_undo_ungrouping(self, engine: Engine) -> None:
        _create(engine, "A")
        _create(engine, "G", node_type="_Group", node_names_to_add=["A"])
        _edit(engine, RemoveNodeFromNodeGroupRequest(node_names=["A"], node_group_name="G", flow_name="main"))

        result = _undo(engine)

        assert isinstance(result, UndoResultSuccess)
        assert result.label == "Ungroup 'A'"
        assert list(_node(engine, "G").nodes) == ["A"]  # type: ignore[union-attr]

    def test_undo_adding_to_a_group(self, engine: Engine) -> None:
        _create(engine, "A")
        _create(engine, "G", node_type="_Group")
        _edit(engine, AddNodesToNodeGroupRequest(node_names=["A"], node_group_name="G", flow_name="main"))

        _undo(engine)

        assert _node(engine, "A").parent_group is None  # type: ignore[union-attr]
        assert list(_node(engine, "G").nodes) == []  # type: ignore[union-attr]


class TestEchoes:
    def test_requests_reacting_to_an_undo_are_not_recorded(self, engine: Engine) -> None:
        """The editor answers what an undo changed with requests of its own, under the undo's group."""
        _create(engine, "A")
        _edit(engine, SetNodeMetadataRequest(node_name="A", metadata={"position": {"x": 9, "y": 9}}))

        _undo(engine, "undo-press")
        _edit(
            engine, SetNodeMetadataRequest(node_name="A", metadata={"size": {"width": 10, "height": 10}}), "undo-press"
        )

        history = _history(engine)
        assert history.undo_labels == ["Add 'A'"]
        assert history.redo_labels == ["Move 'A'"]
        assert isinstance(_redo(engine), RedoResultSuccess)

    def test_requests_an_undo_issues_carry_its_group(self, engine: Engine) -> None:
        """A client tells a replayed result from one it should react to by the Undo's group."""
        _create(engine, "A")
        _edit(engine, SetNodeMetadataRequest(node_name="A", metadata={"position": {"x": 9, "y": 9}}))

        with patch.object(engine.event_manager, "put_event") as put_event:
            _undo(engine, "undo-press")

        broadcast = [call.args[0] for call in put_event.call_args_list if isinstance(call.args[0], GriptapeNodeEvent)]
        replayed = [
            event.wrapped_event.request
            for event in broadcast
            if isinstance(event.wrapped_event.request, SetNodeMetadataRequest)
        ]
        assert [request.undo_group for request in replayed] == ["undo-press"]


class TestRefusals:
    def test_nothing_to_undo(self, engine: Engine) -> None:
        assert isinstance(_undo(engine), UndoResultFailure)

    def test_not_while_the_workflow_runs(self, engine: Engine) -> None:
        _create(engine, "A")

        with patch.object(engine.flow_manager, "check_for_existing_running_flow", return_value=True):
            result = _undo(engine)

        assert isinstance(result, UndoResultFailure)
        assert _node(engine, "A") is not None

    def test_clearing_history(self, engine: Engine) -> None:
        _create(engine, "A")
        engine.handle_request(ClearUndoHistoryRequest())

        assert _history(engine).undo_labels == []


def test_flow_context_is_left_as_it_was(engine: Engine) -> None:
    """Recording images nodes inside their flow's context, and must put the context back."""
    flow_before = engine.context_manager.get_current_flow()
    _create(engine, "A")
    _edit(engine, SetParameterValueRequest(node_name="A", parameter_name="text", value="hello"))
    _undo(engine)

    assert engine.context_manager.get_current_flow() is flow_before
    assert isinstance(flow_before, ControlFlow)


@contextmanager
def _refusing(engine: Engine, request_type: type[RequestPayload], failure: ResultPayload) -> Iterator[None]:
    """Make the engine refuse one kind of request, the way it does when a manager rejects it."""
    handle_request = engine.handle_request

    def maybe_refuse(request: RequestPayload, *args: Any, **kwargs: Any) -> ResultPayload:
        if isinstance(request, request_type):
            return failure
        return handle_request(request, *args, **kwargs)

    with patch.object(engine, "handle_request", side_effect=maybe_refuse):
        yield


def _disconnect(engine: Engine, source: str, target: str, group: str | None = None) -> None:
    _edit(
        engine,
        DeleteConnectionRequest(
            source_node_name=source, source_parameter_name="text", target_node_name=target, target_parameter_name="text"
        ),
        group,
    )


def _undid_cleanly(result: ResultPayload) -> bool:
    return isinstance(result, UndoResultSuccess) and "could not be restored" not in str(result.result_details)


def _add_extra_parameter(engine: Engine, node_name: str, group: str | None = None) -> None:
    _edit(
        engine,
        AddParameterToNodeRequest(
            node_name=node_name,
            parameter_name="extra",
            type="str",
            default_value="x",
            tooltip="extra",
            mode_allowed_property=True,
            is_user_defined=True,
        ),
        group,
    )


class TestReplayEdgeCases:
    def test_undo_chained_renames(self, engine: Engine) -> None:
        """Undoing A -> C and B -> A has to move C back to A while A still holds B."""
        _create(engine, "A")
        _create(engine, "B")
        _edit(engine, RenameObjectRequest(object_name="A", requested_name="C"), "rename")
        _edit(engine, RenameObjectRequest(object_name="B", requested_name="A"), "rename")
        node_a, node_b = _node(engine, "C"), _node(engine, "A")

        result = _undo(engine)

        assert isinstance(result, UndoResultSuccess)
        assert _node(engine, "A") is node_a
        assert _node(engine, "B") is node_b
        assert _node(engine, "C") is None

    def test_undo_a_value_on_a_locked_node(self, engine: Engine) -> None:
        """The node is unlocked to take the value. The lock was set outside the history, so it is not kept."""
        _create(engine, "A")
        _edit(engine, SetParameterValueRequest(node_name="A", parameter_name="text", value="one"))
        _edit(engine, SetParameterValueRequest(node_name="A", parameter_name="text", value="two"))
        engine.handle_request(SetLockNodeStateRequest(node_name="A", lock=True))

        result = _undo(engine)

        assert isinstance(result, UndoResultSuccess)
        assert _value(engine, "A", "text") == "one"

    def test_undo_a_value_and_lock_set_together(self, engine: Engine) -> None:
        _create(engine, "A")
        _edit(engine, SetParameterValueRequest(node_name="A", parameter_name="text", value="one"))
        _edit(engine, SetParameterValueRequest(node_name="A", parameter_name="text", value="two"), "edit-and-lock")
        _edit(engine, SetLockNodeStateRequest(node_name="A", lock=True), "edit-and-lock")

        _undo(engine)
        assert _value(engine, "A", "text") == "one"
        assert _node(engine, "A").lock is False  # type: ignore[union-attr]

        _redo(engine)
        assert _value(engine, "A", "text") == "two"
        assert _node(engine, "A").lock is True  # type: ignore[union-attr]

    def test_undo_a_first_value_restores_the_default(self, engine: Engine) -> None:
        _create(engine, "A")
        _edit(engine, SetParameterValueRequest(node_name="A", parameter_name="text", value="set"))

        _undo(engine)

        assert _value(engine, "A", "text") == ""

    def test_undo_a_removed_parameter_rebuilds_the_node_with_its_connections(self, engine: Engine) -> None:
        _create(engine, "A")
        _create(engine, "B")
        _connect(engine, "A", "B")
        _add_extra_parameter(engine, "B")
        _edit(engine, RemoveParameterFromNodeRequest(node_name="B", parameter_name="extra"))

        result = _undo(engine)

        assert isinstance(result, UndoResultSuccess), result.result_details
        assert _node(engine, "B").get_parameter_by_name("extra") is not None  # type: ignore[union-attr]
        assert _connections(engine) == {("A", "text", "B", "text")}

    def test_rebuilding_a_group_member_keeps_it_in_the_group(self, engine: Engine) -> None:
        _create(engine, "A")
        _create(engine, "G", node_type="_Group", node_names_to_add=["A"])
        _add_extra_parameter(engine, "A")

        _undo(engine)

        member = _node(engine, "A")
        assert member is not None
        assert member.get_parameter_by_name("extra") is None
        assert member.parent_group is _node(engine, "G")

    def test_undo_moving_a_node_to_another_flow(self, engine: Engine) -> None:
        engine.handle_request(CreateFlowRequest(parent_flow_name="main", flow_name="other", set_as_new_context=False))
        _create(engine, "A")
        _edit(engine, MoveNodeToNewFlowRequest(node_name="A", target_flow_name="other"))
        assert engine.node_manager.get_node_parent_flow_by_name("A") == "other"

        _undo(engine)

        assert engine.node_manager.get_node_parent_flow_by_name("A") == "main"

    def test_undo_an_auto_layout_restores_every_position(self, engine: Engine) -> None:
        _create(engine, "A")
        _create(engine, "B")
        _connect(engine, "A", "B")
        positions = {name: _node(engine, name).metadata.get("position") for name in ("A", "B")}  # type: ignore[union-attr]
        _edit(engine, AutoLayoutFlowRequest(flow_name="main", origin_x=1000, origin_y=1000))

        _undo(engine)

        assert {name: _node(engine, name).metadata.get("position") for name in ("A", "B")} == positions  # type: ignore[union-attr]

    def test_a_part_that_cannot_be_restored_is_reported(self, engine: Engine) -> None:
        _create(engine, "A")
        _edit(engine, DeleteNodeRequest(node_name="A"))
        # Something outside the history takes the name.
        engine.handle_request(CreateNodeRequest(node_type="_Probe", specific_library_name=_LIBRARY, node_name="A"))

        result = _undo(engine)

        assert isinstance(result, UndoResultSuccess)
        assert "because the name is taken" in str(result.result_details)

    def test_a_rename_back_to_a_taken_name_is_reported(self, engine: Engine) -> None:
        _create(engine, "A")
        _edit(engine, RenameObjectRequest(object_name="A", requested_name="B"))
        engine.handle_request(CreateNodeRequest(node_type="_Probe", specific_library_name=_LIBRARY, node_name="A"))

        result = _undo(engine)

        assert isinstance(result, UndoResultSuccess)
        assert "Could not rename 'A__undo_0' back to 'A'." in str(result.result_details)

    def test_an_unexpected_error_stops_the_replay_but_keeps_the_history_moving(self, engine: Engine) -> None:
        _create(engine, "A")

        with patch("griptape_nodes.retained_mode.managers.undo.manager.replay", side_effect=RuntimeError("boom")):
            result = _undo(engine)

        assert isinstance(result, UndoResultSuccess)
        assert "Stopped partway because of an unexpected error: boom" in str(result.result_details)
        assert _history(engine).redo_labels == ["Add 'A'"]


class TestRecordingEdgeCases:
    def test_an_edit_undone_within_its_own_action_leaves_no_step(self, engine: Engine) -> None:
        _create(engine, "A")
        _edit(engine, SetParameterValueRequest(node_name="A", parameter_name="text", value="x"), "typing")
        assert _history(engine).undo_labels[-1] == "Change 'text' on 'A'"

        _edit(engine, SetParameterValueRequest(node_name="A", parameter_name="text", value=""), "typing")

        assert _history(engine).undo_labels == ["Add 'A'"]

    @pytest.mark.parametrize(
        "serialize",
        [
            {"side_effect": RuntimeError("boom")},
            {"return_value": SerializeNodeToCommandsResultFailure(result_details="refused")},
        ],
        ids=["raises", "fails"],
    )
    def test_a_node_that_cannot_be_imaged_is_left_out(self, engine: Engine, serialize: dict[str, Any]) -> None:
        _create(engine, "A")

        with patch.object(engine.node_manager, "on_serialize_node_to_commands", **serialize):
            _edit(engine, SetParameterValueRequest(node_name="A", parameter_name="text", value="x"))

        assert _value(engine, "A", "text") == "x"
        assert _history(engine).undo_labels == ["Add 'A'"]

    def test_a_failure_to_start_recording_lets_the_request_run(self, engine: Engine) -> None:
        with patch.object(Edit, "capture_named", side_effect=RuntimeError("boom")):
            _create(engine, "A")

        assert _node(engine, "A") is not None
        assert _history(engine).undo_labels == []

    def test_a_failure_to_commit_lets_the_request_run(self, engine: Engine) -> None:
        with patch.object(Edit, "finish", side_effect=RuntimeError("boom")):
            _create(engine, "A")

        assert _node(engine, "A") is not None
        assert _history(engine).undo_labels == []
        _create(engine, "B")
        assert _history(engine).undo_labels == ["Add 'B'"]

    def test_an_unrecorded_request_inside_an_action_is_left_out(self, engine: Engine) -> None:
        """A run or save a handler starts is not part of the edit, but the rest of the edit is."""
        _create(engine, "A")
        undo_manager = engine.undo_manager
        scope = undo_manager.begin_dispatch(
            SetNodeMetadataRequest(node_name="A", metadata={"position": {"x": 3, "y": 3}}, undo_group="outer")
        )
        engine.handle_request(UnresolveNodeRequest(node_name="A"))
        engine.handle_request(SetNodeMetadataRequest(node_name="A", metadata={"position": {"x": 3, "y": 3}}))
        undo_manager.end_dispatch(scope)

        assert _history(engine).undo_labels == ["Add 'A'", "Move 'A'"]


class TestMoreRefusals:
    def test_nothing_to_redo(self, engine: Engine) -> None:
        assert isinstance(_redo(engine), RedoResultFailure)

    def test_redo_not_while_the_workflow_runs(self, engine: Engine) -> None:
        _create(engine, "A")
        _undo(engine)

        with patch.object(engine.flow_manager, "check_for_existing_running_flow", return_value=True):
            result = _redo(engine)

        assert isinstance(result, RedoResultFailure)
        assert _node(engine, "A") is None

    def test_not_while_an_edit_is_being_applied(self, engine: Engine) -> None:
        _create(engine, "A")
        undo_manager = engine.undo_manager
        scope = undo_manager.begin_dispatch(
            SetNodeMetadataRequest(node_name="A", metadata={"position": {"x": 3, "y": 3}}, undo_group="slow")
        )

        result = engine.handle_request(UndoRequest(undo_group="press"))
        undo_manager.end_dispatch(scope)

        assert isinstance(result, UndoResultFailure)
        assert "still being applied" in str(result.result_details)

    def test_not_during_another_undo(self, engine: Engine) -> None:
        _create(engine, "A")
        _create(engine, "B")
        nested: list[ResultPayload] = []

        def replay_and_undo_again(*_args: Any) -> list[str]:
            nested.append(engine.handle_request(UndoRequest()))
            return []

        with patch("griptape_nodes.retained_mode.managers.undo.manager.replay", side_effect=replay_and_undo_again):
            _undo(engine)

        assert isinstance(nested[0], UndoResultFailure)
        assert "already in progress" in str(nested[0].result_details)
        assert _history(engine).undo_labels == ["Add 'A'"]


class TestStaleHistory:
    """Undo reads the workflow as it is, so changes made outside the history are skipped, not fought."""

    def test_a_node_already_deleted(self, engine: Engine) -> None:
        _create(engine, "A")
        engine.handle_request(DeleteNodeRequest(node_name="A"))

        assert _undid_cleanly(_undo(engine))

    def test_a_connection_already_removed(self, engine: Engine) -> None:
        _create(engine, "A")
        _create(engine, "B")
        _connect(engine, "A", "B")
        engine.handle_request(
            DeleteConnectionRequest(
                source_node_name="A", source_parameter_name="text", target_node_name="B", target_parameter_name="text"
            )
        )

        assert _undid_cleanly(_undo(engine))
        assert _connections(engine) == set()

    def test_a_connection_already_restored(self, engine: Engine) -> None:
        _create(engine, "A")
        _create(engine, "B")
        _connect(engine, "A", "B")
        _disconnect(engine, "A", "B")
        engine.handle_request(
            CreateConnectionRequest(
                source_node_name="A", source_parameter_name="text", target_node_name="B", target_parameter_name="text"
            )
        )

        assert _undid_cleanly(_undo(engine))
        assert _connections(engine) == {("A", "text", "B", "text")}

    def test_a_connection_whose_node_is_gone(self, engine: Engine) -> None:
        _create(engine, "A")
        _create(engine, "B")
        _connect(engine, "A", "B")
        _disconnect(engine, "A", "B")
        engine.handle_request(DeleteNodeRequest(node_name="A"))

        assert isinstance(_undo(engine), UndoResultSuccess)
        assert _connections(engine) == set()

    def test_values_and_parameters_of_a_node_that_is_gone(self, engine: Engine) -> None:
        _create(engine, "A")
        _edit(engine, SetParameterValueRequest(node_name="A", parameter_name="text", value="x"), "edit")
        _add_extra_parameter(engine, "A", "edit")
        engine.handle_request(DeleteNodeRequest(node_name="A"))

        assert _undid_cleanly(_undo(engine))
        assert _node(engine, "A") is None

    def test_a_rebuilt_node_whose_connection_partner_is_gone(self, engine: Engine) -> None:
        _create(engine, "A")
        _create(engine, "B")
        _connect(engine, "A", "B")
        _add_extra_parameter(engine, "B")
        _edit(engine, RemoveParameterFromNodeRequest(node_name="B", parameter_name="extra"))
        engine.handle_request(DeleteNodeRequest(node_name="A"))

        assert _undid_cleanly(_undo(engine))
        assert _node(engine, "B").get_parameter_by_name("extra") is not None  # type: ignore[union-attr]
        assert _connections(engine) == set()

    def test_a_member_already_out_of_its_group(self, engine: Engine) -> None:
        _create(engine, "A")
        _create(engine, "G", node_type="_Group")
        _edit(engine, AddNodesToNodeGroupRequest(node_names=["A"], node_group_name="G", flow_name="main"))
        engine.handle_request(RemoveNodeFromNodeGroupRequest(node_names=["A"], node_group_name="G", flow_name="main"))

        assert _undid_cleanly(_undo(engine))
        assert _node(engine, "A").parent_group is None  # type: ignore[union-attr]

    def test_a_member_already_back_in_its_group(self, engine: Engine) -> None:
        _create(engine, "A")
        _create(engine, "G", node_type="_Group", node_names_to_add=["A"])
        _edit(engine, RemoveNodeFromNodeGroupRequest(node_names=["A"], node_group_name="G", flow_name="main"))
        engine.handle_request(AddNodesToNodeGroupRequest(node_names=["A"], node_group_name="G", flow_name="main"))

        assert _undid_cleanly(_undo(engine))
        assert _node(engine, "A").parent_group is _node(engine, "G")  # type: ignore[union-attr]

    def test_a_group_that_is_gone(self, engine: Engine) -> None:
        _create(engine, "A")
        _create(engine, "G", node_type="_Group", node_names_to_add=["A"])
        _edit(engine, RemoveNodeFromNodeGroupRequest(node_names=["A"], node_group_name="G", flow_name="main"))
        engine.handle_request(DeleteNodeRequest(node_name="G"))

        assert _undid_cleanly(_undo(engine))
        assert _node(engine, "A").parent_group is None  # type: ignore[union-attr]


class TestMoreReplay:
    def test_undo_swapped_names(self, engine: Engine) -> None:
        _create(engine, "A")
        _create(engine, "B")
        node_a, node_b = _node(engine, "A"), _node(engine, "B")
        _edit(engine, RenameObjectRequest(object_name="A", requested_name="T"), "swap")
        _edit(engine, RenameObjectRequest(object_name="B", requested_name="A"), "swap")
        _edit(engine, RenameObjectRequest(object_name="T", requested_name="B"), "swap")

        assert _undid_cleanly(_undo(engine))
        assert _node(engine, "A") is node_a
        assert _node(engine, "B") is node_b

    def test_a_taken_placeholder_name_is_reported(self, engine: Engine) -> None:
        _create(engine, "A")
        _create(engine, "B")
        _edit(engine, RenameObjectRequest(object_name="A", requested_name="T"), "swap")
        _edit(engine, RenameObjectRequest(object_name="B", requested_name="A"), "swap")
        _edit(engine, RenameObjectRequest(object_name="T", requested_name="B"), "swap")
        engine.handle_request(
            CreateNodeRequest(node_type="_Probe", specific_library_name=_LIBRARY, node_name="A__undo_0")
        )

        result = _undo(engine)

        assert isinstance(result, UndoResultSuccess)
        assert "Could not rename 'B' back to 'A__undo_0'." in str(result.result_details)

    def test_undo_a_disconnect_and_the_value_typed_after_it(self, engine: Engine) -> None:
        """The value comes back through the connection, not by setting the parameter."""
        _create(engine, "A")
        _create(engine, "B")
        _edit(engine, SetParameterValueRequest(node_name="A", parameter_name="text", value="upstream"))
        _connect(engine, "A", "B")
        _disconnect(engine, "A", "B", "retype")
        _edit(engine, SetParameterValueRequest(node_name="B", parameter_name="text", value="own"), "retype")

        assert _undid_cleanly(_undo(engine))
        assert _connections(engine) == {("A", "text", "B", "text")}
        assert _value(engine, "B", "text") == "upstream"

    def test_undo_a_value_a_person_cannot_set(self, engine: Engine) -> None:
        """A value the node refuses from a person is restored the way loading a workflow does."""
        _create(engine, "S", node_type="_Sealed")
        _edit(engine, SetParameterValueRequest(node_name="S", parameter_name="text", value="x", initial_setup=True))

        assert _undid_cleanly(_undo(engine))
        assert _value(engine, "S", "text") == ""

    def test_undo_the_first_value_on_a_parameter_with_no_default(self, engine: Engine) -> None:
        _create(engine, "O", node_type="_Optional")
        _edit(engine, SetParameterValueRequest(node_name="O", parameter_name="text", value="x"))

        assert _undid_cleanly(_undo(engine))
        assert _value(engine, "O", "text") is None

    def test_a_rebuild_that_cannot_delete_the_node_is_reported(self, engine: Engine) -> None:
        _create(engine, "B")
        _add_extra_parameter(engine, "B")
        _edit(engine, RemoveParameterFromNodeRequest(node_name="B", parameter_name="extra"))

        with _refusing(engine, DeleteNodeRequest, DeleteNodeResultFailure(result_details="refused")):
            result = _undo(engine)

        assert "Could not rebuild 'B'." in str(result.result_details)
        assert _node(engine, "B") is not None

    def test_a_rebuild_that_cannot_recreate_the_node_is_reported(self, engine: Engine) -> None:
        _create(engine, "B")
        _add_extra_parameter(engine, "B")
        _edit(engine, RemoveParameterFromNodeRequest(node_name="B", parameter_name="extra"))
        refused = DeserializeNodeFromCommandsResultFailure(result_details="refused")

        with _refusing(engine, DeserializeNodeFromCommandsRequest, refused):
            result = _undo(engine)

        assert "Could not bring back 'B'." in str(result.result_details)


class TestMoreRecording:
    def test_undo_without_a_group(self, engine: Engine) -> None:
        _create(engine, "A")

        assert isinstance(engine.handle_request(UndoRequest()), UndoResultSuccess)
        assert _node(engine, "A") is None

    def test_a_node_created_and_deleted_in_one_action_leaves_no_step(self, engine: Engine) -> None:
        _create(engine, "A")
        _edit(engine, CreateNodeRequest(node_type="_Probe", specific_library_name=_LIBRARY, node_name="B"), "scratch")
        _edit(engine, DeleteNodeRequest(node_name="B"), "scratch")

        assert _history(engine).undo_labels == ["Add 'A'"]

    def test_a_flow_wide_request_for_a_missing_flow_records_nothing(self, engine: Engine) -> None:
        _create(engine, "A")

        result = engine.handle_request(AutoLayoutFlowRequest(flow_name="missing", undo_group="layout"))

        assert not result.succeeded()
        assert _history(engine).undo_labels == ["Add 'A'"]

    def test_overlapping_requests_in_one_action_commit_when_the_last_finishes(self, engine: Engine) -> None:
        """Async handlers can overlap. Each runs in its own context, and the action records once."""
        _create(engine, "A")
        _create(engine, "B")
        undo_manager = engine.undo_manager
        first, second = contextvars.Context(), contextvars.Context()
        first_scope = first.run(
            undo_manager.begin_dispatch,
            SetNodeMetadataRequest(node_name="A", metadata={"position": {"x": 1, "y": 1}}, undo_group="drag"),
        )
        second_scope = second.run(
            undo_manager.begin_dispatch,
            SetNodeMetadataRequest(node_name="B", metadata={"position": {"x": 2, "y": 2}}, undo_group="drag"),
        )
        engine.handle_request(SetNodeMetadataRequest(node_name="A", metadata={"position": {"x": 1, "y": 1}}))
        engine.handle_request(SetNodeMetadataRequest(node_name="B", metadata={"position": {"x": 2, "y": 2}}))

        first.run(undo_manager.end_dispatch, first_scope)
        assert _history(engine).undo_labels == ["Add 'A'", "Add 'B'"]
        second.run(undo_manager.end_dispatch, second_scope)
        assert _history(engine).undo_labels == ["Add 'A'", "Add 'B'", "Move 2 nodes"]

    def test_clearing_history_during_an_action_keeps_only_that_action(self, engine: Engine) -> None:
        _create(engine, "A")
        _edit(engine, SetNodeMetadataRequest(node_name="A", metadata={"position": {"x": 1, "y": 1}}), "drag")
        undo_manager = engine.undo_manager
        scope = undo_manager.begin_dispatch(
            SetNodeMetadataRequest(node_name="A", metadata={"position": {"x": 2, "y": 2}}, undo_group="drag")
        )
        engine.handle_request(ClearUndoHistoryRequest())
        engine.handle_request(SetNodeMetadataRequest(node_name="A", metadata={"position": {"x": 2, "y": 2}}))
        undo_manager.end_dispatch(scope)

        assert _history(engine).undo_labels == ["Move 'A'"]

    def test_a_node_noted_as_created_after_it_was_imaged_keeps_its_image(self, engine: Engine) -> None:
        _create(engine, "A")
        node = _node(engine, "A")
        assert node is not None
        edit = Edit(engine, "group")
        edit.capture(engine, node)
        edit.note_created(node)

        assert edit.finish(engine).is_empty()


class TestCapture:
    def test_a_node_outside_any_flow_cannot_be_imaged(self, engine: Engine) -> None:
        assert capture_node(engine, _Probe("Orphan")) is None

    def test_no_image_without_an_open_workflow(self, engine: Engine) -> None:
        _create(engine, "A")
        node = _node(engine, "A")
        assert node is not None

        with patch.object(engine.context_manager, "has_current_workflow", return_value=False):
            assert capture_node(engine, node) is None
