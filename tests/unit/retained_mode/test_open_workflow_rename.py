"""Renaming or moving an open workflow keeps it open, under its new name and the same id."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from griptape_nodes.retained_mode.events.open_workflow_events import (
    ListOpenWorkflowsRequest,
    ListOpenWorkflowsResultSuccess,
    OpenWorkflowRequest,
    OpenWorkflowResultSuccess,
)
from griptape_nodes.retained_mode.events.workflow_events import (
    MoveWorkflowRequest,
    MoveWorkflowResultSuccess,
    RenameWorkflowRequest,
    RenameWorkflowResultSuccess,
    SaveWorkflowRequest,
    SaveWorkflowResultSuccess,
)

if TYPE_CHECKING:
    from pathlib import Path

    from griptape_nodes.retained_mode.engine import Engine


@pytest.fixture
def workspace(engine: Engine, tmp_path: Path) -> Path:
    """Save workflows into a temporary workspace."""
    engine.config_manager.set_config_value("workspace_directory", str(tmp_path))
    return tmp_path


def _open_saved_workflow(engine: Engine, file_name: str) -> OpenWorkflowResultSuccess:
    """Open a new workflow and save it as `file_name`."""
    opened = engine.handle_request(OpenWorkflowRequest(display_name=file_name))
    assert isinstance(opened, OpenWorkflowResultSuccess), opened
    saved = engine.handle_request(SaveWorkflowRequest(file_name=file_name), workflow_id=opened.workflow_id)
    assert isinstance(saved, SaveWorkflowResultSuccess), saved
    return opened


def _open_names_by_id(engine: Engine) -> dict[str, str]:
    listed = engine.handle_request(ListOpenWorkflowsRequest())
    assert isinstance(listed, ListOpenWorkflowsResultSuccess), listed
    return {workflow.workflow_id: workflow.workflow_name for workflow in listed.workflows}


@pytest.mark.usefixtures("workspace")
class TestRenameOpenWorkflow:
    def test_renaming_keeps_it_open_under_the_new_name(self, engine: Engine) -> None:
        alpha = _open_saved_workflow(engine, "alpha")
        beta = _open_saved_workflow(engine, "beta")

        renamed = engine.handle_request(
            RenameWorkflowRequest(workflow_name="alpha", requested_name="gamma"), workflow_id=alpha.workflow_id
        )

        assert isinstance(renamed, RenameWorkflowResultSuccess), renamed
        assert _open_names_by_id(engine) == {alpha.workflow_id: "gamma", beta.workflow_id: "beta"}

    def test_renaming_leaves_the_other_workflow_alone(self, engine: Engine) -> None:
        alpha = _open_saved_workflow(engine, "alpha")
        beta = _open_saved_workflow(engine, "beta")

        engine.handle_request(
            RenameWorkflowRequest(workflow_name="beta", requested_name="delta"), workflow_id=beta.workflow_id
        )

        assert _open_names_by_id(engine) == {alpha.workflow_id: "alpha", beta.workflow_id: "delta"}


@pytest.mark.usefixtures("workspace")
class TestMoveOpenWorkflow:
    def test_moving_a_workflow_that_is_not_the_one_acted_on_renames_its_runtime(self, engine: Engine) -> None:
        alpha = _open_saved_workflow(engine, "alpha")
        beta = _open_saved_workflow(engine, "beta")

        moved = engine.handle_request(MoveWorkflowRequest(workflow_name="alpha", target_directory="archive"))

        assert isinstance(moved, MoveWorkflowResultSuccess), moved
        assert _open_names_by_id(engine) == {alpha.workflow_id: "archive/alpha", beta.workflow_id: "beta"}
