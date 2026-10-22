"""The open workflow's runtime: how it opens and closes, and the state it holds."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, patch

import pytest

from griptape_nodes.exe_types.flow import ControlFlow
from griptape_nodes.retained_mode.events.flow_events import (
    CreateFlowRequest,
    CreateFlowResultFailure,
    CreateFlowResultSuccess,
)
from griptape_nodes.retained_mode.events.object_events import (
    ClearAllObjectStateRequest,
    RenameObjectRequest,
    RenameObjectResultSuccess,
)
from griptape_nodes.retained_mode.events.variable_events import (
    CreateVariableRequest,
    CreateVariableResultFailure,
    CreateVariableResultSuccess,
    GetVariableValueRequest,
    GetVariableValueResultFailure,
)
from griptape_nodes.retained_mode.events.workflow_events import (
    DeleteWorkflowRequest,
    SetVariableSubstitutionEnabledRequest,
    SetVariableSubstitutionEnabledResultFailure,
)
from griptape_nodes.retained_mode.runtime.open_workflow_set import (
    NoOpenWorkflowError,
    OpenWorkflowError,
    OpenWorkflowSet,
)
from griptape_nodes.retained_mode.runtime.workflow_runtime import WorkflowRuntime
from griptape_nodes.retained_mode.variable_types import VariableScope
from tests.workflow_context import push_unsaved_workflow

if TYPE_CHECKING:
    from griptape_nodes.retained_mode.engine import Engine


class TestOpenWorkflowSet:
    def test_open_returns_an_empty_runtime_under_the_id(self) -> None:
        workflows = OpenWorkflowSet()

        workflow = workflows.open("abc")

        assert workflow.workflow_id == "abc"
        assert len(workflow.objects) == 0
        assert workflows.get("abc") is workflow
        assert workflows.find("abc") is workflow

    def test_opening_the_same_id_twice_is_refused(self) -> None:
        workflows = OpenWorkflowSet()
        workflows.open("abc")

        with pytest.raises(OpenWorkflowError, match="already open"):
            workflows.open("abc")

    def test_opening_a_second_workflow_is_refused(self) -> None:
        workflows = OpenWorkflowSet()
        first = workflows.open("abc")

        with pytest.raises(OpenWorkflowError, match="'abc' is already open"):
            workflows.open("def")

        assert workflows.sole_workflow() is first

    def test_get_of_a_closed_workflow_raises(self) -> None:
        workflows = OpenWorkflowSet()

        with pytest.raises(OpenWorkflowError, match="not open"):
            workflows.get("abc")
        assert workflows.find("abc") is None

    def test_close_forgets_the_workflow(self) -> None:
        workflows = OpenWorkflowSet()
        workflow = workflows.open("abc")

        workflows.close(workflow)

        assert workflows.find("abc") is None
        assert workflows.sole_workflow_or_none() is None

    def test_close_refuses_a_runtime_that_is_not_open(self) -> None:
        workflows = OpenWorkflowSet()
        workflow = workflows.open("abc")
        workflows.close(workflow)
        reopened = workflows.open("abc")

        with pytest.raises(OpenWorkflowError, match="not open"):
            workflows.close(workflow)
        assert workflows.sole_workflow() is reopened

    def test_sole_workflow_with_none_open(self) -> None:
        workflows = OpenWorkflowSet()

        assert workflows.sole_workflow_or_none() is None
        with pytest.raises(NoOpenWorkflowError, match="no workflow is open"):
            workflows.sole_workflow()

    def test_sole_workflow_with_one_open(self) -> None:
        workflows = OpenWorkflowSet()
        workflow = workflows.open("abc")

        assert workflows.sole_workflow() is workflow
        assert workflows.sole_workflow_or_none() is workflow

    def test_sole_workflow_never_picks_one_of_several(self) -> None:
        workflows = OpenWorkflowSet()
        workflows.open("abc")
        # Several open cannot happen through `open`; force it to check the read refuses to guess.
        workflows._by_id["def"] = WorkflowRuntime("def")

        with pytest.raises(OpenWorkflowError, match="2 workflows are open"):
            workflows.sole_workflow_or_none()
        with pytest.raises(OpenWorkflowError, match="2 workflows are open"):
            workflows.sole_workflow()

    def test_reads_never_open_a_workflow(self) -> None:
        workflows = OpenWorkflowSet()

        workflows.find("abc")
        workflows.sole_workflow_or_none()
        with pytest.raises(OpenWorkflowError):
            workflows.get("abc")
        with pytest.raises(NoOpenWorkflowError):
            workflows.sole_workflow()

        assert workflows.sole_workflow_or_none() is None


class TestRuntimeLifecycle:
    """The runtime is open exactly while the context stack holds a workflow."""

    def test_a_push_onto_an_empty_stack_opens_the_pushed_workflow(self, engine: Engine) -> None:
        workflow = push_unsaved_workflow(engine)

        assert engine.open_workflows.sole_workflow().workflow_id == workflow.workflow_id

    def test_a_nested_push_opens_nothing(self, engine: Engine) -> None:
        outer = push_unsaved_workflow(engine, "outer")
        runtime = engine.open_workflows.sole_workflow()

        inner = push_unsaved_workflow(engine, "inner")

        assert engine.open_workflows.sole_workflow() is runtime
        assert engine.open_workflows.find(outer.workflow_id) is runtime
        assert engine.open_workflows.find(inner.workflow_id) is None

    def test_popping_a_nested_entry_keeps_the_workflow_open(self, engine: Engine) -> None:
        push_unsaved_workflow(engine, "outer")
        runtime = engine.open_workflows.sole_workflow()
        push_unsaved_workflow(engine, "inner")

        engine.context_manager.pop_workflow()

        assert engine.open_workflows.sole_workflow() is runtime

    def test_popping_the_last_entry_closes_the_workflow(self, engine: Engine) -> None:
        push_unsaved_workflow(engine, "outer")
        push_unsaved_workflow(engine, "inner")

        engine.context_manager.pop_workflow()
        engine.context_manager.pop_workflow()

        assert engine.open_workflows.sole_workflow_or_none() is None

    def test_mirroring_a_peers_workflow_opens_nothing(self, engine: Engine) -> None:
        engine.context_manager.mirror_workflow_context("00000000000000000000000000000abc", None, None, None)

        assert engine.context_manager.has_current_workflow()
        assert engine.open_workflows.sole_workflow_or_none() is None

        engine.context_manager.mirror_workflow_context(None, None, None, None)
        assert engine.open_workflows.sole_workflow_or_none() is None


class TestCloseWorkflowState:
    @pytest.mark.asyncio
    async def test_cancels_the_running_flow_before_tearing_down(self, engine: Engine) -> None:
        push_unsaved_workflow(engine)
        calls: list[str] = []
        clear_top_entry = engine._clear_top_workflow_entry

        def record_teardown() -> None:
            calls.append("teardown")
            clear_top_entry()

        with (
            patch.object(
                engine.flow_manager,
                "cancel_running_flow_before_teardown",
                AsyncMock(side_effect=lambda: calls.append("cancel")),
            ),
            patch.object(engine, "_clear_top_workflow_entry", side_effect=record_teardown),
            patch.object(
                engine.worker_manager,
                "broadcast_local_object_teardown",
                AsyncMock(side_effect=lambda: calls.append("broadcast")),
            ),
        ):
            await engine.close_workflow_state(engine.open_workflows.sole_workflow())

        assert calls == ["cancel", "teardown", "broadcast"]

    @pytest.mark.asyncio
    async def test_pops_every_entry_and_leaves_no_workflow_open(self, engine: Engine) -> None:
        push_unsaved_workflow(engine, "outer")
        push_unsaved_workflow(engine, "inner")

        await engine.close_workflow_state(engine.open_workflows.sole_workflow())

        assert not engine.context_manager.has_current_workflow()
        assert engine.open_workflows.sole_workflow_or_none() is None

    @pytest.mark.asyncio
    async def test_tells_the_workers_even_when_the_teardown_raises(self, engine: Engine) -> None:
        push_unsaved_workflow(engine)

        with (
            patch.object(engine, "_clear_top_workflow_entry", side_effect=RuntimeError("teardown blew up")),
            patch.object(engine.worker_manager, "broadcast_local_object_teardown", AsyncMock()) as broadcast,
            pytest.raises(RuntimeError, match="teardown blew up"),
        ):
            await engine.close_workflow_state(engine.open_workflows.sole_workflow())

        broadcast.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_a_workflow_opened_while_the_cancel_is_awaited_is_left_alone(self, engine: Engine) -> None:
        """Delete awaits the cancel, so the editor can clear and open another workflow meanwhile."""
        first = push_unsaved_workflow(engine, "first")
        cancel_calls: list[None] = []
        opened: dict[str, WorkflowRuntime] = {}

        async def clear_and_open_another() -> None:
            cancel_calls.append(None)
            # ClearAll below awaits this same cancel; only the first call interleaves.
            if len(cancel_calls) > 1:
                return
            await asyncio.sleep(0)
            await engine.ahandle_request(ClearAllObjectStateRequest(i_know_what_im_doing=True))
            push_unsaved_workflow(engine, "second")
            engine.handle_request(CreateFlowRequest(parent_flow_name=None, flow_name="canvas"))
            opened["second"] = engine.open_workflows.sole_workflow()

        with patch.object(
            engine.flow_manager, "cancel_running_flow_before_teardown", side_effect=clear_and_open_another
        ):
            result = await engine.ahandle_request(DeleteWorkflowRequest(workflow_id=first.workflow_id))

        assert result.succeeded()
        assert engine.open_workflows.sole_workflow() is opened["second"]
        assert engine.object_manager.has_object_with_name("canvas")

    @pytest.mark.asyncio
    async def test_a_workflow_closed_while_the_cancel_is_awaited_does_not_tell_the_workers(
        self, engine: Engine
    ) -> None:
        push_unsaved_workflow(engine)
        runtime = engine.open_workflows.sole_workflow()

        async def close_meanwhile() -> None:
            engine.context_manager.pop_workflow()

        with (
            patch.object(engine.flow_manager, "cancel_running_flow_before_teardown", side_effect=close_meanwhile),
            patch.object(engine.worker_manager, "broadcast_local_object_teardown", AsyncMock()) as broadcast,
        ):
            await engine.close_workflow_state(runtime)

        broadcast.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_refuses_a_workflow_that_is_not_open(self, engine: Engine) -> None:
        push_unsaved_workflow(engine)

        with pytest.raises(OpenWorkflowError, match="not the open workflow"):
            await engine.close_workflow_state(WorkflowRuntime("stale"))

        assert engine.context_manager.has_current_workflow()

    def test_clear_all_object_state_closes_the_open_workflow_through_it(self, engine: Engine) -> None:
        push_unsaved_workflow(engine)
        runtime = engine.open_workflows.sole_workflow()

        with patch.object(engine, "close_workflow_state", wraps=engine.close_workflow_state) as close:
            result = engine.handle_request(ClearAllObjectStateRequest(i_know_what_im_doing=True))

        assert result.succeeded()
        close.assert_awaited_once_with(runtime)
        assert engine.open_workflows.sole_workflow_or_none() is None

    def test_clear_all_object_state_with_nothing_open_still_tells_the_workers(self, engine: Engine) -> None:
        with (
            patch.object(engine, "close_workflow_state", AsyncMock()) as close,
            patch.object(engine.worker_manager, "broadcast_local_object_teardown", AsyncMock()) as broadcast,
        ):
            result = engine.handle_request(ClearAllObjectStateRequest(i_know_what_im_doing=True))

        assert result.succeeded()
        close.assert_not_awaited()
        broadcast.assert_awaited_once()

    def test_deleting_the_open_workflow_closes_it_through_it(self, engine: Engine) -> None:
        workflow = push_unsaved_workflow(engine)
        runtime = engine.open_workflows.sole_workflow()

        with patch.object(engine, "close_workflow_state", wraps=engine.close_workflow_state) as close:
            result = engine.handle_request(DeleteWorkflowRequest(workflow_id=workflow.workflow_id))

        assert result.succeeded()
        close.assert_awaited_once_with(runtime)
        assert engine.open_workflows.sole_workflow_or_none() is None

    def test_deleting_another_workflow_leaves_the_open_one_alone(self, engine: Engine) -> None:
        other = engine.workflow_registry.register_unsaved("other", None)
        push_unsaved_workflow(engine)
        runtime = engine.open_workflows.sole_workflow()

        with patch.object(engine, "close_workflow_state", AsyncMock()) as close:
            result = engine.handle_request(DeleteWorkflowRequest(workflow_id=other.workflow_id))

        assert result.succeeded()
        close.assert_not_awaited()
        assert engine.open_workflows.sole_workflow() is runtime


class TestObjectsOnTheRuntime:
    def test_a_created_flow_is_held_by_the_open_workflow(self, engine: Engine) -> None:
        push_unsaved_workflow(engine)

        result = engine.handle_request(CreateFlowRequest(parent_flow_name=None, flow_name="canvas"))

        assert isinstance(result, CreateFlowResultSuccess)
        assert engine.open_workflows.sole_workflow().objects.has("canvas")
        assert engine.object_manager.has_object_with_name("canvas")

    def test_lookups_find_nothing_with_no_workflow_open(self, engine: Engine) -> None:
        object_manager = engine.object_manager

        assert object_manager.get_filtered_subset() == {}
        assert object_manager.attempt_get_object_by_name("canvas") is None
        assert object_manager.attempt_get_object_by_name_as_type("canvas", ControlFlow) is None
        assert not object_manager.has_object_with_name("canvas")
        assert object_manager.generate_name_for_object("ControlFlow") == "ControlFlow_1"
        with pytest.raises(KeyError):
            object_manager.get_object_by_name("canvas")
        assert engine.open_workflows.sole_workflow_or_none() is None

    def test_changes_need_an_open_workflow(self, engine: Engine) -> None:
        object_manager = engine.object_manager

        with pytest.raises(NoOpenWorkflowError):
            object_manager.add_object_by_name("thing", object())
        with pytest.raises(NoOpenWorkflowError):
            object_manager.del_obj_by_name("thing")

    def test_create_flow_with_no_workflow_open_is_refused_before_it_needs_one(self, engine: Engine) -> None:
        result = engine.handle_request(CreateFlowRequest(parent_flow_name=None, flow_name="canvas"))

        assert isinstance(result, CreateFlowResultFailure)
        assert "no Workflow was active" in str(result.result_details)

    def test_rename_moves_the_object_within_the_open_workflow(self, engine: Engine) -> None:
        push_unsaved_workflow(engine)
        engine.handle_request(CreateFlowRequest(parent_flow_name=None, flow_name="canvas"))

        result = engine.handle_request(RenameObjectRequest(object_name="canvas", requested_name="renamed"))

        assert isinstance(result, RenameObjectResultSuccess)
        objects = engine.open_workflows.sole_workflow().objects
        assert objects.has("renamed")
        assert not objects.has("canvas")

    @pytest.mark.asyncio
    async def test_closing_drops_the_objects(self, engine: Engine) -> None:
        push_unsaved_workflow(engine)
        engine.handle_request(CreateFlowRequest(parent_flow_name=None, flow_name="canvas"))
        runtime = engine.open_workflows.sole_workflow()

        await engine.close_workflow_state(runtime)

        assert len(runtime.objects) == 0
        push_unsaved_workflow(engine)
        assert not engine.object_manager.has_object_with_name("canvas")

    def test_popping_the_last_entry_drops_objects_left_in_it(self, engine: Engine) -> None:
        push_unsaved_workflow(engine)
        engine.handle_request(CreateFlowRequest(parent_flow_name=None, flow_name="canvas"))

        engine.context_manager.pop_workflow()
        push_unsaved_workflow(engine)

        assert not engine.object_manager.has_object_with_name("canvas")


class TestVariablesOnTheRuntime:
    def test_a_global_variable_is_held_by_the_open_workflow(self, engine: Engine) -> None:
        push_unsaved_workflow(engine)

        result = engine.handle_request(CreateVariableRequest(name="greeting", type="str", is_global=True, value="hi"))

        assert isinstance(result, CreateVariableResultSuccess)
        assert engine.open_workflows.sole_workflow().variables.global_layer.has("greeting")

    def test_a_flow_variable_is_held_by_the_open_workflow(self, engine: Engine) -> None:
        push_unsaved_workflow(engine)
        engine.handle_request(CreateFlowRequest(parent_flow_name=None, flow_name="canvas"))

        result = engine.handle_request(
            CreateVariableRequest(name="greeting", type="str", owning_flow="canvas", value="hi")
        )

        assert isinstance(result, CreateVariableResultSuccess)
        layer = engine.open_workflows.sole_workflow().variables.flow_layer("canvas")
        assert layer is not None
        assert layer.has("greeting")

    def test_lookups_find_no_global_variable_with_no_workflow_open(self, engine: Engine) -> None:
        result = engine.handle_request(GetVariableValueRequest(name="greeting", lookup_scope=VariableScope.GLOBAL_ONLY))

        assert isinstance(result, GetVariableValueResultFailure)
        assert engine.open_workflows.sole_workflow_or_none() is None

    def test_creating_a_global_variable_needs_an_open_workflow(self, engine: Engine) -> None:
        result = engine.handle_request(CreateVariableRequest(name="greeting", type="str", is_global=True, value="hi"))

        assert isinstance(result, CreateVariableResultFailure)
        assert "no workflow is open" in str(result.result_details)
        assert engine.open_workflows.sole_workflow_or_none() is None

    def test_variables_do_not_survive_clearing_and_reopening(self, engine: Engine) -> None:
        push_unsaved_workflow(engine)
        engine.handle_request(CreateVariableRequest(name="greeting", type="str", is_global=True, value="hi"))

        engine.handle_request(ClearAllObjectStateRequest(i_know_what_im_doing=True))
        push_unsaved_workflow(engine)

        result = engine.handle_request(GetVariableValueRequest(name="greeting", lookup_scope=VariableScope.GLOBAL_ONLY))
        assert isinstance(result, GetVariableValueResultFailure)

    def test_popping_the_last_entry_drops_the_variables(self, engine: Engine) -> None:
        push_unsaved_workflow(engine)
        engine.handle_request(CreateVariableRequest(name="greeting", type="str", is_global=True, value="hi"))

        engine.context_manager.pop_workflow()
        push_unsaved_workflow(engine)

        assert not engine.open_workflows.sole_workflow().variables.global_layer.has("greeting")


class TestSubstitutionFlagOnTheRuntime:
    def test_substitution_is_enabled_with_no_workflow_open(self, engine: Engine) -> None:
        assert engine.workflow_manager.variable_substitution.is_enabled() is True

    def test_setting_the_flag_with_no_workflow_open_fails(self, engine: Engine) -> None:
        result = engine.handle_request(SetVariableSubstitutionEnabledRequest(enabled=False))

        assert isinstance(result, SetVariableSubstitutionEnabledResultFailure)

    def test_the_flag_is_held_by_the_open_workflow(self, engine: Engine) -> None:
        push_unsaved_workflow(engine)

        engine.handle_request(SetVariableSubstitutionEnabledRequest(enabled=False))

        assert engine.open_workflows.sole_workflow().variables.substitution_enabled is False
        assert engine.workflow_manager.variable_substitution.is_enabled() is False

    def test_the_flag_does_not_survive_clearing_and_reopening_the_same_workflow(self, engine: Engine) -> None:
        workflow = push_unsaved_workflow(engine)
        engine.handle_request(SetVariableSubstitutionEnabledRequest(enabled=False))

        engine.handle_request(ClearAllObjectStateRequest(i_know_what_im_doing=True))
        engine.context_manager.push_workflow(workflow_id=workflow.workflow_id)

        assert engine.workflow_manager.variable_substitution.is_enabled() is True
