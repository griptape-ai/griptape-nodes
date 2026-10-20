"""A node group run in its own engine process hands that engine the run it belongs to."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock

import pytest

from griptape_nodes.bootstrap.workflow_executors.subprocess_workflow_executor import SubprocessWorkflowExecutor
from griptape_nodes.retained_mode.events.execution_events import PARENT_RUN_ID_ENV_VAR

if TYPE_CHECKING:
    from pathlib import Path


async def _child_env(tmp_path: Path, parent_run_id: str | None) -> dict[str, str]:
    workflow = tmp_path / "workflow.py"
    workflow.write_text("")
    executor = SubprocessWorkflowExecutor(workflow_path=str(workflow), parent_run_id=parent_run_id)
    execute = AsyncMock()
    executor.execute_python_script = execute  # type: ignore[method-assign]

    await executor.arun(flow_input={})

    return execute.call_args.kwargs["env"]


@pytest.mark.asyncio
async def test_the_child_engine_is_told_the_parent_run(tmp_path: Path) -> None:
    """The group's spend then counts toward the run that started the group."""
    env = await _child_env(tmp_path, "parent-run")

    assert env[PARENT_RUN_ID_ENV_VAR] == "parent-run"


@pytest.mark.asyncio
async def test_no_parent_run_means_the_child_mints_its_own(tmp_path: Path) -> None:
    """A workflow run on its own is a run of its own."""
    env = await _child_env(tmp_path, None)

    assert PARENT_RUN_ID_ENV_VAR not in env
