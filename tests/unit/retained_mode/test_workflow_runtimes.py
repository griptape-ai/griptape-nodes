"""The open workflow's runtime: how it opens and closes, and the state it holds."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from griptape_nodes.retained_mode.runtime.open_workflow_set import (
    NoOpenWorkflowError,
    OpenWorkflowError,
    OpenWorkflowSet,
)
from griptape_nodes.retained_mode.runtime.workflow_runtime import WorkflowRuntime
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
