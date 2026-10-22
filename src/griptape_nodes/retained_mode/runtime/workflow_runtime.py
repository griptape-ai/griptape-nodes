"""The runtime of one open workflow."""

from __future__ import annotations

from griptape_nodes.retained_mode.runtime.objects import WorkflowObjects
from griptape_nodes.retained_mode.runtime.variables import WorkflowVariables


class WorkflowRuntime:
    """The state of one open workflow, made when it opens and dropped when it closes.

    Managers hold no state of their own for a workflow: what a workflow is lives here, one typed
    attribute per concern.
    """

    def __init__(self, workflow_id: str) -> None:
        """Make an empty runtime.

        Args:
            workflow_id: The registry id of the workflow this runtime holds open.
        """
        self.workflow_id = workflow_id
        self.objects = WorkflowObjects()
        self.variables = WorkflowVariables()
