"""The open workflows an engine holds, and which one the current work belongs to.

An engine can hold several workflows open at once. Each gets a `WorkflowRuntime`, and the managers
that keep per-workflow state (flows, nodes, connections, names, the context stack, execution) keep it
there rather than on themselves. A manager defines the shape of its own state and reads it through
`WorkflowRuntime.state`, so this module knows nothing about what managers store.

Every request acts on one open workflow, named by its `workflow_id`. A client sets the id to target a
workflow; otherwise the request acts on the active workflow, or on the one the request that issued it
was acting on. The choice is a `WorkflowBinding`, held in a ContextVar so the tasks a request spawns
inherit it.
"""

from __future__ import annotations

import uuid
from contextvars import ContextVar
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable


class WorkflowRuntime:
    """The state of one open workflow, keyed by the type of each manager's state object."""

    def __init__(self, owner: object) -> None:
        # Stable for as long as the workflow is open, unlike its registry key, which changes when an
        # unsaved workflow is first saved.
        self.workflow_id = uuid.uuid4().hex
        # The engine this runtime belongs to, so a binding made by one engine is never read by another.
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


@dataclass(frozen=True)
class WorkflowBinding:
    """The workflow the current work acts on.

    `workflow_id` is usually `runtime.workflow_id`. A worker is the exception: it acts for the
    orchestrator's workflows without holding them, so it binds its own runtime and keeps the
    orchestrator's id, which it passes along on the requests it forwards.
    """

    runtime: WorkflowRuntime
    workflow_id: str


bound_workflow: ContextVar[WorkflowBinding | None] = ContextVar("griptape_nodes_bound_workflow", default=None)


class WorkflowNotOpenError(Exception):
    """A request targeted a workflow the engine doesn't hold open."""
