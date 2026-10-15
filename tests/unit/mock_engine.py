"""A mock engine for tests that build a manager on its own."""

from unittest.mock import MagicMock

from griptape_nodes.retained_mode.run_scheduler import RunScheduler
from griptape_nodes.retained_mode.workflow_runtime import WorkflowRuntime


def mock_engine_with_workflow_runtime() -> MagicMock:
    """A `MagicMock` engine with one real open workflow, so managers can keep per-workflow state."""
    engine = MagicMock()
    runtime = WorkflowRuntime(owner=engine)
    engine.current_workflow = runtime
    engine.current_workflow_or_none.return_value = runtime
    engine.workflow_runtimes = [runtime]
    engine.run_scheduler = RunScheduler(is_running=lambda _runtime: False, display_name_of=lambda _runtime: "Workflow")
    return engine
