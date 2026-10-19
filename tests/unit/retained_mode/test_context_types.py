"""Tests for WorkflowContextStack, the context state a WorkflowRuntime keeps as `context`."""

from unittest.mock import MagicMock

import pytest

from griptape_nodes.retained_mode.context_types import (
    EmptyStackError,
    NoActiveFlowError,
    NoActiveWorkflowError,
    WorkflowContextStack,
)
from griptape_nodes.retained_mode.engine import Engine
from griptape_nodes.retained_mode.events.context_events import (
    GetWorkflowContextRequest,
    GetWorkflowContextSuccess,
    SetWorkflowContextRequest,
    SetWorkflowContextSuccess,
)


class TestWorkflowContextStack:
    def test_an_empty_stack_has_no_context_to_ask_for(self) -> None:
        stack = WorkflowContextStack()

        assert not stack.has_current_workflow()
        assert not stack.has_current_flow()
        with pytest.raises(NoActiveWorkflowError):
            stack.get_current_workflow_name()
        with pytest.raises(NoActiveFlowError):
            stack.get_current_flow()
        with pytest.raises(EmptyStackError):
            stack.pop_workflow()

    def test_a_flow_cannot_be_entered_without_a_workflow(self) -> None:
        stack = WorkflowContextStack()

        with pytest.raises(NoActiveWorkflowError):
            stack.push_flow(MagicMock())

    def test_pushing_a_workflow_records_what_it_was_entered_with(self) -> None:
        stack = WorkflowContextStack()

        stack.push_workflow("w", "/a/w.py", "/a")

        assert stack.get_current_workflow_name() == "w"
        assert stack.get_current_workflow_file_path() == "/a/w.py"
        assert stack.get_current_workflow_working_directory() == "/a"

    def test_rekeying_renames_matching_entries_and_moves_their_file(self) -> None:
        stack = WorkflowContextStack()
        stack.push_workflow("old", None, None)

        stack.rekey_workflow("old", "new", "/a/new.py")

        assert stack.get_current_workflow_name() == "new"
        assert stack.get_current_workflow_file_path() == "/a/new.py"


class TestWorkflowContextPerRuntime:
    def test_each_workflow_keeps_its_own_context(self, engine: Engine) -> None:
        first = engine.open_workflow_runtime()
        second = engine.open_workflow_runtime()

        set_result = engine.handle_request(
            SetWorkflowContextRequest(workflow_name="first_workflow"), workflow_id=first.workflow_id
        )
        in_first = engine.handle_request(GetWorkflowContextRequest(), workflow_id=first.workflow_id)
        in_second = engine.handle_request(GetWorkflowContextRequest(), workflow_id=second.workflow_id)

        assert isinstance(set_result, SetWorkflowContextSuccess), set_result
        assert isinstance(in_first, GetWorkflowContextSuccess), in_first
        assert isinstance(in_second, GetWorkflowContextSuccess), in_second
        assert in_first.workflow_name == "first_workflow"
        assert in_second.workflow_name is None
        assert first.context.has_current_workflow()
        assert not second.context.has_current_workflow()
