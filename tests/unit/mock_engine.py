"""A mock engine for tests that build a manager on its own."""

from unittest.mock import MagicMock

from griptape_nodes.retained_mode.workflow_runtime import WorkflowRuntime


def mock_engine_with_workflow_runtime() -> MagicMock:
    """A `MagicMock` engine with a real runtime, so managers can keep per-workflow state."""
    engine = MagicMock()
    engine.workflow_runtime = WorkflowRuntime(owner=engine)
    engine.workflow_running_elsewhere.return_value = None
    return engine
