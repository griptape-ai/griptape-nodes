"""The open workflow's runtime: how it opens and closes, and the state it holds."""

from __future__ import annotations

import pytest

from griptape_nodes.retained_mode.runtime.open_workflow_set import (
    NoOpenWorkflowError,
    OpenWorkflowError,
    OpenWorkflowSet,
)
from griptape_nodes.retained_mode.runtime.workflow_runtime import WorkflowRuntime


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
