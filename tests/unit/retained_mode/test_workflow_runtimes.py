"""Several workflows open at once: each keeps its own graph, and switching doesn't reload."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

import pytest

from griptape_nodes.retained_mode.events.context_events import (
    ActivateWorkflowRequest,
    ActivateWorkflowResultFailure,
    ActivateWorkflowResultSuccess,
    CloseWorkflowRequest,
    CloseWorkflowResultSuccess,
    ListOpenWorkflowsRequest,
    ListOpenWorkflowsResultSuccess,
)
from griptape_nodes.retained_mode.events.flow_events import CreateFlowRequest, CreateFlowResultSuccess
from griptape_nodes.retained_mode.events.node_events import CreateNodeRequest, CreateNodeResultSuccess
from griptape_nodes.retained_mode.events.object_events import ClearAllObjectStateRequest

if TYPE_CHECKING:
    from griptape_nodes.retained_mode.engine import Engine


def _open_workflow_with_note(engine: Engine, workflow_name: str, note_name: str) -> None:
    """Activate `workflow_name` in an empty slot and give it a flow holding one note."""
    activate = engine.handle_request(ActivateWorkflowRequest(workflow_name=workflow_name))
    assert isinstance(activate, ActivateWorkflowResultSuccess), activate
    assert activate.already_open is False
    engine.context_manager.push_workflow(workflow_name)
    flow = engine.handle_request(
        CreateFlowRequest(parent_flow_name=None, flow_name=f"{workflow_name}_flow", set_as_new_context=True)
    )
    assert isinstance(flow, CreateFlowResultSuccess), flow
    node = engine.handle_request(CreateNodeRequest(node_type="Note", node_name=note_name))
    assert isinstance(node, CreateNodeResultSuccess), node


def _node_names(engine: Engine) -> set[str]:
    return set(engine.flow_manager.get_flow_by_name(engine.context_manager.get_current_flow().name).nodes)


class TestOpenWorkflows:
    def test_switching_back_keeps_the_graph(self, engine: Engine) -> None:
        _open_workflow_with_note(engine, "wf_a", "NoteA")
        _open_workflow_with_note(engine, "wf_b", "NoteB")

        assert _node_names(engine) == {"NoteB"}

        result = engine.handle_request(ActivateWorkflowRequest(workflow_name="wf_a"))
        assert isinstance(result, ActivateWorkflowResultSuccess), result
        assert result.already_open is True
        assert engine.context_manager.get_current_workflow_name() == "wf_a"
        assert _node_names(engine) == {"NoteA"}

    def test_same_node_name_in_two_workflows(self, engine: Engine) -> None:
        _open_workflow_with_note(engine, "wf_a", "Note")
        _open_workflow_with_note(engine, "wf_b", "Note")

        engine.handle_request(ActivateWorkflowRequest(workflow_name="wf_a"))
        note_a = engine.node_manager.get_node_by_name("Note")
        engine.handle_request(ActivateWorkflowRequest(workflow_name="wf_b"))
        note_b = engine.node_manager.get_node_by_name("Note")

        assert note_a is not note_b

    def test_lists_open_workflows(self, engine: Engine) -> None:
        _open_workflow_with_note(engine, "wf_a", "NoteA")
        _open_workflow_with_note(engine, "wf_b", "NoteB")

        result = engine.handle_request(ListOpenWorkflowsRequest())

        assert isinstance(result, ListOpenWorkflowsResultSuccess), result
        assert result.workflow_names == ["wf_a", "wf_b"]
        assert result.active_workflow_name == "wf_b"

    def test_clear_all_only_clears_the_active_workflow(self, engine: Engine) -> None:
        _open_workflow_with_note(engine, "wf_a", "NoteA")
        _open_workflow_with_note(engine, "wf_b", "NoteB")

        engine.handle_request(ClearAllObjectStateRequest(i_know_what_im_doing=True))
        engine.handle_request(ActivateWorkflowRequest(workflow_name="wf_a"))

        assert _node_names(engine) == {"NoteA"}

    def test_closing_an_inactive_workflow_forgets_it(self, engine: Engine) -> None:
        _open_workflow_with_note(engine, "wf_a", "NoteA")
        _open_workflow_with_note(engine, "wf_b", "NoteB")

        result = engine.handle_request(CloseWorkflowRequest(workflow_name="wf_a"))

        assert isinstance(result, CloseWorkflowResultSuccess), result
        listed = engine.handle_request(ListOpenWorkflowsRequest())
        assert isinstance(listed, ListOpenWorkflowsResultSuccess)
        assert listed.workflow_names == ["wf_b"]
        assert _node_names(engine) == {"NoteB"}
        assert len(engine.workflow_runtimes) == 1

    def test_closing_the_active_workflow_leaves_an_empty_one_active(self, engine: Engine) -> None:
        _open_workflow_with_note(engine, "wf_a", "NoteA")

        engine.handle_request(CloseWorkflowRequest(workflow_name="wf_a"))

        assert not engine.context_manager.has_current_workflow()
        reopened = engine.handle_request(ActivateWorkflowRequest(workflow_name="wf_a"))
        assert isinstance(reopened, ActivateWorkflowResultSuccess)
        assert reopened.already_open is False

    def test_cannot_switch_away_from_a_running_workflow(self, engine: Engine, monkeypatch: pytest.MonkeyPatch) -> None:
        _open_workflow_with_note(engine, "wf_a", "NoteA")
        _open_workflow_with_note(engine, "wf_b", "NoteB")
        monkeypatch.setattr(engine.flow_manager, "check_for_existing_running_flow", lambda: True)

        result = engine.handle_request(ActivateWorkflowRequest(workflow_name="wf_a"))

        assert isinstance(result, ActivateWorkflowResultFailure), result
        assert engine.context_manager.get_current_workflow_name() == "wf_b"


class TestRequestPinning:
    @pytest.mark.asyncio
    async def test_a_task_keeps_the_workflow_it_was_started_in(self, engine: Engine) -> None:
        """A request's spawned tasks act on the workflow that was active when it arrived."""
        _open_workflow_with_note(engine, "wf_a", "NoteA")
        _open_workflow_with_note(engine, "wf_b", "NoteB")
        engine.handle_request(ActivateWorkflowRequest(workflow_name="wf_a"))

        switched = asyncio.Event()

        async def read_after_switch() -> str:
            await switched.wait()
            return engine.context_manager.get_current_workflow_name()

        with engine.bind_workflow_runtime():
            task = asyncio.create_task(read_after_switch())
        await engine.ahandle_request(ActivateWorkflowRequest(workflow_name="wf_b"))
        switched.set()

        assert await task == "wf_a"
        assert engine.context_manager.get_current_workflow_name() == "wf_b"
