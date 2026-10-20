"""The runtime of one open workflow, and the namespace a worker keeps for one.

An engine can hold several workflows open at once, and each gets a `WorkflowRuntime`. A handler that
acts on a workflow takes it as its `workflow` parameter; code that has no runtime to hand reads the
one the current work is bound to (see `binding`). Nodes record the runtime they were created in, so
their events name it even from threads that lost the binding.

A worker opens no workflows. It keeps a `WorkflowRuntime` of kind `WORKER_NAMESPACE` for each of the
orchestrator's workflows it runs nodes for, so the handles those nodes hold have somewhere to live.
"""

from __future__ import annotations

import uuid
from enum import StrEnum

from griptape_nodes.retained_mode.runtime.context import WorkflowContextStack
from griptape_nodes.retained_mode.runtime.flows import WorkflowFlows
from griptape_nodes.retained_mode.runtime.loading import WorkflowLoading
from griptape_nodes.retained_mode.runtime.nodes import WorkflowNodes
from griptape_nodes.retained_mode.runtime.objects import WorkflowObjects
from griptape_nodes.retained_mode.runtime.variables import WorkflowVariables


class RuntimeKind(StrEnum):
    """What a runtime stands for."""

    # A workflow the engine has open, with a graph. The orchestrator's runtimes are all of this kind.
    OPEN_WORKFLOW = "open_workflow"
    # A worker's namespace of handles for a workflow the orchestrator has open. It is not an open workflow
    # on the worker: it has no graph, and listings, runs and heartbeats never see it.
    WORKER_NAMESPACE = "worker_namespace"


class WorkflowRuntime:
    """The state of one open workflow, made with the runtime and dropped with it.

    Managers hold no state of their own for a workflow: what a workflow is lives here, one typed
    attribute per concern. Anything a manager keeps on itself is shared by every open workflow.
    """

    def __init__(
        self, owner: object, workflow_id: str | None = None, kind: RuntimeKind = RuntimeKind.OPEN_WORKFLOW
    ) -> None:
        """Make an empty runtime.

        Args:
            owner: The engine holding it, so a binding made by one engine is never read by another.
            workflow_id: The id to address it by. A worker passes the orchestrator's id for the workflow
                it runs nodes for; otherwise a fresh one is made.
            kind: Whether this is an open workflow or a worker's namespace for one.
        """
        # Stable for as long as the workflow is open, unlike its registry key, which changes when it is
        # saved, renamed, or moved.
        self.workflow_id = workflow_id if workflow_id is not None else uuid.uuid4().hex
        self.owner = owner
        self.kind = kind
        self.context = WorkflowContextStack()
        self.variables = WorkflowVariables()
        self.objects = WorkflowObjects()
        self.nodes = WorkflowNodes()
        self.flows = WorkflowFlows()
        self.loading = WorkflowLoading()


def workflow_id_of(workflow: WorkflowRuntime | None) -> str | None:
    """The id to address a nested request to `workflow` by, or None when the work acts on no workflow.

    A nested request addressed to no workflow keeps the binding of the work that issued it: no workflow
    when dispatch gave the handler None, and the caller's own when node code calls the handler directly.
    """
    if workflow is None:
        return None
    return workflow.workflow_id
