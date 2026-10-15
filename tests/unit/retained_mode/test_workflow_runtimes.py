"""Several workflows open at once: each keeps its own graph, and requests act on the one they name."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest

from griptape_nodes.retained_mode.events.base_events import ExecutionEvent, ExecutionGriptapeNodeEvent
from griptape_nodes.retained_mode.events.execution_events import ParameterValueUpdateEvent
from griptape_nodes.retained_mode.events.flow_events import ListNodesInFlowRequest, ListNodesInFlowResultSuccess
from griptape_nodes.retained_mode.events.node_events import CreateNodeRequest, CreateNodeResultSuccess
from griptape_nodes.retained_mode.events.object_events import ClearAllObjectStateRequest
from griptape_nodes.retained_mode.events.open_workflow_events import (
    CloseWorkflowRequest,
    CloseWorkflowResultSuccess,
    ListOpenWorkflowsRequest,
    ListOpenWorkflowsResultSuccess,
    OpenWorkflowRequest,
    OpenWorkflowResultFailure,
    OpenWorkflowResultSuccess,
)
from griptape_nodes.retained_mode.managers.flow_manager import FlowManager

if TYPE_CHECKING:
    from collections.abc import Callable

    from griptape_nodes.retained_mode.engine import Engine


def _open_new_workflow_with_note(engine: Engine, note_name: str) -> OpenWorkflowResultSuccess:
    """Open a new workflow and put one note in its flow."""
    opened = engine.handle_request(OpenWorkflowRequest(display_name=note_name))
    assert isinstance(opened, OpenWorkflowResultSuccess), opened
    node = engine.handle_request(CreateNodeRequest(node_type="Note", node_name=note_name))
    assert isinstance(node, CreateNodeResultSuccess), node
    return opened


def _node_names(engine: Engine, workflow_id: str | None = None) -> set[str]:
    """The nodes in the current flow of a workflow, by default the active one."""
    result = engine.handle_request(ListNodesInFlowRequest(workflow_id=workflow_id))
    assert isinstance(result, ListNodesInFlowResultSuccess), result
    return set(result.node_names)


def _listed(engine: Engine) -> ListOpenWorkflowsResultSuccess:
    result = engine.handle_request(ListOpenWorkflowsRequest())
    assert isinstance(result, ListOpenWorkflowsResultSuccess), result
    return result


class TestOpenWorkflow:
    def test_opening_another_keeps_the_first(self, engine: Engine) -> None:
        a = _open_new_workflow_with_note(engine, "NoteA")
        b = _open_new_workflow_with_note(engine, "NoteB")

        assert _node_names(engine) == {"NoteB"}
        assert _node_names(engine, a.workflow_id) == {"NoteA"}
        assert [w.workflow_id for w in _listed(engine).workflows] == [a.workflow_id, b.workflow_id]

    def test_opening_an_open_workflow_activates_it(self, engine: Engine) -> None:
        a = _open_new_workflow_with_note(engine, "NoteA")
        _open_new_workflow_with_note(engine, "NoteB")

        result = engine.handle_request(OpenWorkflowRequest(workflow_name=a.workflow_name))

        assert isinstance(result, OpenWorkflowResultSuccess), result
        assert result.already_open is True
        assert result.workflow_id == a.workflow_id
        assert _listed(engine).active_workflow_id == a.workflow_id
        assert _node_names(engine) == {"NoteA"}

    def test_a_workflow_not_in_the_registry_fails_and_changes_nothing(self, engine: Engine) -> None:
        a = _open_new_workflow_with_note(engine, "NoteA")

        result = engine.handle_request(OpenWorkflowRequest(workflow_name="no_such_workflow"))

        assert isinstance(result, OpenWorkflowResultFailure), result
        assert [w.workflow_id for w in _listed(engine).workflows] == [a.workflow_id]

    def test_the_same_node_name_in_two_workflows(self, engine: Engine) -> None:
        a = _open_new_workflow_with_note(engine, "Note")
        b = _open_new_workflow_with_note(engine, "Note")

        runtime_a = engine.find_workflow_runtime(a.workflow_id)
        runtime_b = engine.find_workflow_runtime(b.workflow_id)
        assert runtime_a is not None
        assert runtime_b is not None
        with engine.bind_workflow_runtime(runtime_a):
            note_a = engine.node_manager.get_node_by_name("Note")
        with engine.bind_workflow_runtime(runtime_b):
            note_b = engine.node_manager.get_node_by_name("Note")

        assert note_a is not note_b


class TestRequestTargeting:
    def test_a_request_acts_on_the_workflow_it_names(self, engine: Engine) -> None:
        a = _open_new_workflow_with_note(engine, "NoteA")
        _open_new_workflow_with_note(engine, "NoteB")

        created = engine.handle_request(
            CreateNodeRequest(node_type="Note", node_name="Added", workflow_id=a.workflow_id)
        )

        assert isinstance(created, CreateNodeResultSuccess), created
        assert _node_names(engine, a.workflow_id) == {"NoteA", "Added"}
        assert _node_names(engine) == {"NoteB"}

    def test_a_request_naming_a_closed_workflow_fails(self, engine: Engine) -> None:
        a = _open_new_workflow_with_note(engine, "NoteA")
        _open_new_workflow_with_note(engine, "NoteB")
        engine.handle_request(CloseWorkflowRequest(workflow_id=a.workflow_id))

        result = engine.handle_request(CreateNodeRequest(node_type="Note", workflow_id=a.workflow_id))

        assert result.failed()
        assert _node_names(engine) == {"NoteB"}

    def test_the_engine_records_the_workflow_a_request_acted_on(self, engine: Engine) -> None:
        b = _open_new_workflow_with_note(engine, "NoteB")
        request = ListOpenWorkflowsRequest()

        engine.handle_request(request)

        assert request.workflow_id == b.workflow_id

    @pytest.mark.asyncio
    async def test_a_task_keeps_the_workflow_its_request_acted_on(self, engine: Engine) -> None:
        a = _open_new_workflow_with_note(engine, "NoteA")
        b = _open_new_workflow_with_note(engine, "NoteB")
        switched = asyncio.Event()
        tasks: list[asyncio.Task[set[str]]] = []

        async def read_after_switch() -> set[str]:
            await switched.wait()
            return {node.name for node in engine.context_manager.get_current_flow().nodes.values()}

        runtime_a = engine.find_workflow_runtime(a.workflow_id)
        assert runtime_a is not None
        with engine.bind_workflow_runtime(runtime_a):
            tasks.append(asyncio.create_task(read_after_switch()))
        await engine.ahandle_request(OpenWorkflowRequest(workflow_name=b.workflow_name))
        switched.set()

        assert await tasks[0] == {"NoteA"}

    def test_run_events_name_their_workflow(self, engine: Engine) -> None:
        a = _open_new_workflow_with_note(engine, "NoteA")
        engine.event_manager.initialize_queue(asyncio.Queue())
        event = ExecutionGriptapeNodeEvent(
            wrapped_event=ExecutionEvent(
                payload=ParameterValueUpdateEvent(node_name="NoteA", parameter_name="p", data_type="str", value="v")
            )
        )

        engine.event_manager.put_event(event)

        assert event.wrapped_event.workflow_id == a.workflow_id


class TestCloseWorkflow:
    def test_closing_an_inactive_workflow_keeps_the_active_one(self, engine: Engine) -> None:
        a = _open_new_workflow_with_note(engine, "NoteA")
        b = _open_new_workflow_with_note(engine, "NoteB")

        result = engine.handle_request(CloseWorkflowRequest(workflow_id=a.workflow_id))

        assert isinstance(result, CloseWorkflowResultSuccess), result
        assert [w.workflow_id for w in _listed(engine).workflows] == [b.workflow_id]
        assert _node_names(engine) == {"NoteB"}

    def test_closing_the_active_workflow_activates_the_last_opened(self, engine: Engine) -> None:
        a = _open_new_workflow_with_note(engine, "NoteA")
        b = _open_new_workflow_with_note(engine, "NoteB")

        engine.handle_request(CloseWorkflowRequest(workflow_id=b.workflow_id))

        assert _listed(engine).active_workflow_id == a.workflow_id

    def test_closing_the_last_workflow_leaves_none_open(self, engine: Engine) -> None:
        a = _open_new_workflow_with_note(engine, "NoteA")

        engine.handle_request(CloseWorkflowRequest(workflow_id=a.workflow_id))

        listed = _listed(engine)
        assert listed.workflows == []
        assert listed.active_workflow_id is None

    def test_clear_all_closes_every_workflow(self, engine: Engine) -> None:
        _open_new_workflow_with_note(engine, "NoteA")
        _open_new_workflow_with_note(engine, "NoteB")

        engine.handle_request(ClearAllObjectStateRequest(i_know_what_im_doing=True))

        assert _listed(engine).workflows == []
        assert len(engine.workflow_runtimes) == 1


class TestOneRunAtATime:
    @pytest.mark.asyncio
    async def test_a_second_workflow_cannot_start_while_one_runs(self, engine: Engine) -> None:
        a = _open_new_workflow_with_note(engine, "NoteA")
        b = _open_new_workflow_with_note(engine, "NoteB")
        runtime_a = engine.find_workflow_runtime(a.workflow_id)
        assert runtime_a is not None

        with patch.object(FlowManager, "check_for_existing_running_flow", _running_in(engine, b.workflow_id)):
            listed = _listed(engine)
            with engine.bind_workflow_runtime(runtime_a):
                flow = engine.context_manager.get_current_flow()
                with pytest.raises(RuntimeError, match="is running"):
                    await engine.flow_manager.start_flow(flow)

        assert {w.workflow_id: w.is_running for w in listed.workflows} == {
            a.workflow_id: False,
            b.workflow_id: True,
        }


def _running_in(engine: Engine, workflow_id: str) -> Callable[[FlowManager], bool]:
    """A stand-in for `check_for_existing_running_flow` that reports only one workflow as running."""

    def check(_flow_manager: FlowManager) -> bool:
        return engine.workflow_binding.workflow_id == workflow_id

    return check


class TestReopenAfterReset:
    @pytest.mark.asyncio
    async def test_saved_workflows_are_listed_with_the_active_one_last(self, engine: Engine) -> None:
        a = _open_new_workflow_with_note(engine, "NoteA")
        b = _open_new_workflow_with_note(engine, "NoteB")
        engine.handle_request(OpenWorkflowRequest(workflow_name=a.workflow_name))

        with patch.object(engine.workflow_registry, "get_workflow_by_name") as get_workflow:
            get_workflow.return_value.is_saved = True
            names = engine.open_workflows_manager.saved_open_workflow_names()

        assert names == [b.workflow_name, a.workflow_name]

    def test_unsaved_workflows_are_not_listed(self, engine: Engine) -> None:
        _open_new_workflow_with_note(engine, "NoteA")

        assert engine.open_workflows_manager.saved_open_workflow_names() == []
