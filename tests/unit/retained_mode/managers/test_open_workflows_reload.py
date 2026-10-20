"""A library reload keeps every open workflow as it was, and says so when it cannot."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock, patch

import pytest

from griptape_nodes.node_library.workflow_registry import WorkflowMetadata
from griptape_nodes.retained_mode.events.base_events import ResultDetails
from griptape_nodes.retained_mode.events.flow_events import (
    ListNodesInFlowRequest,
    ListNodesInFlowResultSuccess,
    SerializeFlowToCommandsRequest,
    SerializeFlowToCommandsResultFailure,
)
from griptape_nodes.retained_mode.events.library_events import (
    ListRegisteredLibrariesRequest,
    ListRegisteredLibrariesResultSuccess,
    ReloadAllLibrariesRequest,
    ReloadAllLibrariesResultSuccess,
)
from griptape_nodes.retained_mode.events.node_events import CreateNodeRequest, CreateNodeResultSuccess
from griptape_nodes.retained_mode.events.open_workflow_events import (
    OpenWorkflowRequest,
    OpenWorkflowResultSuccess,
)
from griptape_nodes.retained_mode.managers.open_workflows_manager import WorkflowEditsNotPreserved

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable
    from pathlib import Path

    from griptape_nodes.retained_mode.engine import Engine
    from griptape_nodes.retained_mode.events.base_events import RequestPayload, ResultPayload

SAVED_WORKFLOW_BODY = """
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
from griptape_nodes.retained_mode.events.flow_events import CreateFlowRequest
from griptape_nodes.retained_mode.events.node_events import CreateNodeRequest

GriptapeNodes.handle_request(CreateFlowRequest(parent_flow_name=None, set_as_new_context=True))
GriptapeNodes.handle_request(CreateNodeRequest(node_type="Note", node_name="SavedNote"))
"""


def _open_saved_workflow(engine: Engine, directory: Path) -> OpenWorkflowResultSuccess:
    """Register a workflow file that makes one node, and open it."""
    workflow_file = directory / "saved_workflow.py"
    workflow_file.write_text(SAVED_WORKFLOW_BODY, encoding="utf-8")
    metadata = WorkflowMetadata(
        name="Saved Workflow",
        schema_version=WorkflowMetadata.LATEST_SCHEMA_VERSION,
        engine_version_created_with="0.0.0",
        node_libraries_referenced=[],
    )
    registry_key = str(workflow_file)
    engine.workflow_registry.generate_new_workflow(registry_key, metadata, file_path=registry_key)
    opened = engine.handle_request(OpenWorkflowRequest(workflow_name=registry_key))
    assert isinstance(opened, OpenWorkflowResultSuccess), opened
    return opened


def _open_unsaved_workflow(engine: Engine, display_name: str) -> OpenWorkflowResultSuccess:
    opened = engine.handle_request(OpenWorkflowRequest(display_name=display_name))
    assert isinstance(opened, OpenWorkflowResultSuccess), opened
    return opened


def _add_note(engine: Engine, workflow_id: str, note_name: str) -> None:
    node = engine.handle_request(CreateNodeRequest(node_type="Note", node_name=note_name), workflow_id=workflow_id)
    assert isinstance(node, CreateNodeResultSuccess), node


def _node_names(engine: Engine, workflow_id: str) -> set[str]:
    result = engine.handle_request(ListNodesInFlowRequest(), workflow_id=workflow_id)
    assert isinstance(result, ListNodesInFlowResultSuccess), result
    return set(result.node_names)


def _failing_to_serialize(engine: Engine, workflow_id: str | None) -> Callable[..., Awaitable[ResultPayload]]:
    """An `ahandle_request` that cannot serialize the flow of one workflow and handles all else as usual.

    It also reports no registered libraries, so a reload through it has none to unload.
    """
    real = engine.ahandle_request
    runtime = None
    if workflow_id is not None:
        runtime = engine.find_workflow_runtime(workflow_id)

    async def ahandle_request(request: RequestPayload, *args: Any, **kwargs: Any) -> ResultPayload:
        if isinstance(request, SerializeFlowToCommandsRequest) and engine.current_workflow is runtime:
            return SerializeFlowToCommandsResultFailure(result_details="A node could not be serialized.")
        if isinstance(request, ListRegisteredLibrariesRequest):
            return ListRegisteredLibrariesResultSuccess(libraries=[], result_details="No libraries.")
        return await real(request, *args, **kwargs)

    return ahandle_request


async def _reload_libraries(engine: Engine, unserializable_workflow_id: str | None) -> ResultPayload:
    library_manager = engine.library_manager
    with (
        patch.object(engine, "ahandle_request", _failing_to_serialize(engine, unserializable_workflow_id)),
        patch.object(library_manager, "load_all_libraries_from_config", AsyncMock(return_value=[])),
        patch.object(library_manager.workers, "maybe_start_workers_for_existing_session", AsyncMock()),
    ):
        return await library_manager.reload_libraries_request(ReloadAllLibrariesRequest())


@pytest.mark.usefixtures("engine")
class TestEditsNotPreserved:
    @pytest.mark.asyncio
    async def test_a_saved_workflow_that_cannot_be_serialized_is_rebuilt_from_its_file(
        self, engine: Engine, tmp_path: Path
    ) -> None:
        opened = _open_saved_workflow(engine, tmp_path)
        _add_note(engine, opened.workflow_id, "UnsavedNote")
        open_workflows = engine.open_workflows_manager

        with patch.object(engine, "ahandle_request", _failing_to_serialize(engine, opened.workflow_id)):
            suspended = await open_workflows.suspend_open_workflows()
        failures = await open_workflows.resume_open_workflows(suspended)
        lost = open_workflows.find_edits_not_preserved(suspended)

        assert failures == []
        assert [(w.workflow_name, w.display_name, w.reopened_from_file) for w in lost] == [
            (opened.workflow_name, "Saved Workflow", True)
        ]
        assert _node_names(engine, opened.workflow_id) == {"SavedNote"}

    @pytest.mark.asyncio
    async def test_an_unsaved_workflow_that_cannot_be_serialized_is_reopened_empty_and_reported(
        self, engine: Engine
    ) -> None:
        opened = _open_unsaved_workflow(engine, "Scratch")
        _add_note(engine, opened.workflow_id, "UnsavedNote")
        open_workflows = engine.open_workflows_manager

        with patch.object(engine, "ahandle_request", _failing_to_serialize(engine, opened.workflow_id)):
            suspended = await open_workflows.suspend_open_workflows()
        failures = await open_workflows.resume_open_workflows(suspended)
        lost = open_workflows.find_edits_not_preserved(suspended)

        assert failures == []
        assert [(w.workflow_name, w.reopened_from_file) for w in lost] == [(opened.workflow_name, False)]
        assert _node_names(engine, opened.workflow_id) == set()

    @pytest.mark.asyncio
    async def test_a_workflow_that_serializes_is_not_reported(self, engine: Engine, tmp_path: Path) -> None:
        saved = _open_saved_workflow(engine, tmp_path)
        scratch = _open_unsaved_workflow(engine, "Scratch")
        _add_note(engine, saved.workflow_id, "UnsavedNote")
        _add_note(engine, scratch.workflow_id, "ScratchNote")
        open_workflows = engine.open_workflows_manager

        suspended = await open_workflows.suspend_open_workflows()
        await open_workflows.resume_open_workflows(suspended)

        assert open_workflows.find_edits_not_preserved(suspended) == []
        assert _node_names(engine, saved.workflow_id) == {"SavedNote", "UnsavedNote"}
        assert _node_names(engine, scratch.workflow_id) == {"ScratchNote"}

    def test_the_message_names_each_workflow_and_what_became_of_it(self, engine: Engine) -> None:
        open_workflows = engine.open_workflows_manager
        lost = [
            WorkflowEditsNotPreserved(workflow_name="saved.py", display_name="Saved Workflow", reopened_from_file=True),
            WorkflowEditsNotPreserved(workflow_name="unsaved:1", display_name="Scratch", reopened_from_file=False),
        ]

        message = open_workflows.describe_edits_not_preserved(lost)

        assert "'Saved Workflow'" in message
        assert "reopened from its last save" in message
        assert "may have lost unsaved changes" in message
        assert "'Scratch' had never been saved" in message
        assert "reopened empty" in message
        assert open_workflows.describe_edits_not_preserved([]) == ""


@pytest.mark.usefixtures("engine")
class TestReloadResult:
    @pytest.mark.asyncio
    async def test_a_reload_names_the_saved_workflow_that_could_not_be_kept(
        self, engine: Engine, tmp_path: Path
    ) -> None:
        opened = _open_saved_workflow(engine, tmp_path)
        _add_note(engine, opened.workflow_id, "UnsavedNote")

        result = await _reload_libraries(engine, opened.workflow_id)

        assert isinstance(result, ReloadAllLibrariesResultSuccess), result
        assert result.workflows_with_lost_changes == ["Saved Workflow"]
        assert isinstance(result.result_details, ResultDetails)
        warnings = [d.message for d in result.result_details.result_details if d.level == logging.WARNING]
        assert len(warnings) == 1
        assert "'Saved Workflow'" in warnings[0]
        assert "reopened from its last save" in warnings[0]
        assert _node_names(engine, opened.workflow_id) == {"SavedNote"}

    @pytest.mark.asyncio
    async def test_a_reload_names_the_unsaved_workflow_that_could_not_be_kept(self, engine: Engine) -> None:
        opened = _open_unsaved_workflow(engine, "Scratch")
        _add_note(engine, opened.workflow_id, "UnsavedNote")

        result = await _reload_libraries(engine, opened.workflow_id)

        assert isinstance(result, ReloadAllLibrariesResultSuccess), result
        assert result.workflows_with_lost_changes == ["Scratch"]
        assert "reopened empty" in str(result.result_details)

    @pytest.mark.asyncio
    async def test_a_clean_reload_reports_no_loss(self, engine: Engine, tmp_path: Path) -> None:
        saved = _open_saved_workflow(engine, tmp_path)
        scratch = _open_unsaved_workflow(engine, "Scratch")
        _add_note(engine, saved.workflow_id, "UnsavedNote")

        result = await _reload_libraries(engine, None)

        assert isinstance(result, ReloadAllLibrariesResultSuccess), result
        assert result.workflows_with_lost_changes == []
        assert isinstance(result.result_details, ResultDetails)
        assert [d.level for d in result.result_details.result_details] == [logging.INFO]
        assert _node_names(engine, saved.workflow_id) == {"SavedNote", "UnsavedNote"}
        assert _node_names(engine, scratch.workflow_id) == set()
