"""Which open workflow the current work belongs to.

Dispatch binds the workflow a request acts on (see `RequestScope`) in a ContextVar, so its handler and
the tasks it spawns act on that workflow. Kept apart from `WorkflowRuntime` and its state so node code
can read the binding without importing what a workflow holds.
"""

from __future__ import annotations

from contextvars import ContextVar
from enum import Enum
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from griptape_nodes.retained_mode.runtime.workflow_runtime import WorkflowRuntime


class NoWorkflow(Enum):
    """Bound by work that explicitly acts on no workflow, such as a path lookup made from the host."""

    NO_WORKFLOW = "no_workflow"


NO_WORKFLOW: Final = NoWorkflow.NO_WORKFLOW

# None means nothing was bound, which is different from binding NO_WORKFLOW: unbound work has the
# engine resolve a workflow for it (see `Engine.current_workflow`), and NO_WORKFLOW work has none.
bound_workflow: ContextVar[WorkflowRuntime | NoWorkflow | None] = ContextVar(
    "griptape_nodes_bound_workflow", default=None
)


def bound_workflow_id() -> str | None:
    """The id of the workflow the current work is bound to, or None when it is bound to none.

    Only what was bound: nothing is resolved. For tagging what the current work emits, such as a log
    record, where naming no workflow is better than naming the wrong one.
    """
    bound = bound_workflow.get()
    if bound is None or bound is NO_WORKFLOW:
        return None
    return bound.workflow_id


class WorkflowNotOpenError(Exception):
    """A request named a workflow the engine doesn't hold open."""


class WorkflowNotNamedError(Exception):
    """Work that needs a workflow named none, and several are open, so none can be chosen for it."""
