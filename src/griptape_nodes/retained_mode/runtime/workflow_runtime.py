"""The runtime of one open workflow.

An engine can hold several workflows open at once, and each gets a `WorkflowRuntime`. A handler that
acts on a workflow takes it as its `workflow` parameter; code that has no runtime to hand reads the
one the current work is bound to (see `binding`). Nodes record the runtime they were created in, so
their events name it even from threads that lost the binding.
"""

from __future__ import annotations

import uuid

from griptape_nodes.retained_mode.runtime.context import WorkflowContextStack
from griptape_nodes.retained_mode.runtime.flows import WorkflowFlows
from griptape_nodes.retained_mode.runtime.loading import WorkflowLoading
from griptape_nodes.retained_mode.runtime.nodes import WorkflowNodes
from griptape_nodes.retained_mode.runtime.objects import WorkflowObjects
from griptape_nodes.retained_mode.runtime.variables import WorkflowVariables


class WorkflowRuntime:
    """The state of one open workflow, made with the runtime and dropped with it.

    Managers hold no state of their own for a workflow: what a workflow is lives here, one typed
    attribute per concern. Anything a manager keeps on itself is shared by every open workflow.
    """

    def __init__(self, owner: object, workflow_id: str | None = None) -> None:
        """Make an empty runtime.

        Args:
            owner: The engine holding it, so a binding made by one engine is never read by another.
            workflow_id: The id to address it by. A worker passes the orchestrator's id for the workflow
                it runs nodes for; otherwise a fresh one is made.
        """
        # Stable for as long as the workflow is open, unlike its registry key, which changes when it is
        # saved, renamed, or moved.
        self.workflow_id = workflow_id if workflow_id is not None else uuid.uuid4().hex
        self.owner = owner
        self.context = WorkflowContextStack()
        self.variables = WorkflowVariables()
        self.objects = WorkflowObjects()
        self.nodes = WorkflowNodes()
        self.flows = WorkflowFlows()
        self.loading = WorkflowLoading()
