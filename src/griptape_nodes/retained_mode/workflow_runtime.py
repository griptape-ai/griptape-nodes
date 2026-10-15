"""The open workflows an engine holds, and which one the current work belongs to.

An engine can hold several workflows open at once. Each gets a `WorkflowRuntime`, and the managers
that keep per-workflow state (flows, nodes, connections, names, the context stack, execution) keep it
there rather than on themselves. A manager defines the shape of its own state and reads it through
`WorkflowRuntime.state`, so this module knows nothing about what managers store.

Requests are host requests or workflow requests (see `base_events`). Dispatch binds a workflow request
to the runtime it names, in a ContextVar, so its handler and the tasks it spawns act on that workflow.
Nodes record the runtime they were created in, so their events name it even from threads that lost the
binding.
"""

from __future__ import annotations

import uuid
from contextvars import ContextVar
from enum import Enum
from typing import TYPE_CHECKING, Any, Final

if TYPE_CHECKING:
    from collections.abc import Callable


class WorkflowRuntime:
    """The state of one open workflow, keyed by the type of each manager's state object."""

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
        self._states: dict[type, Any] = {}

    def state[T](self, state_type: type[T], factory: Callable[[], T]) -> T:
        """Return this runtime's instance of `state_type`, creating it with `factory` on first use."""
        existing = self._states.get(state_type)
        if existing is not None:
            return existing
        created = factory()
        self._states[state_type] = created
        return created


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
    if isinstance(bound, WorkflowRuntime):
        return bound.workflow_id
    return None


class WorkflowNotOpenError(Exception):
    """A request named a workflow the engine doesn't hold open."""


class WorkflowNotNamedError(Exception):
    """Work that needs a workflow named none, and several are open, so none can be chosen for it."""
