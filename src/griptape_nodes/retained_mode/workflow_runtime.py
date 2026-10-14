"""One open workflow's in-memory state.

The engine can hold several workflows open at once. Each one gets a `WorkflowRuntime`, and the
managers that hold per-workflow state (flows, nodes, connections, names, the context stack,
execution) keep it here rather than on themselves. A manager defines the shape of its own state
and reads it through `state()`, so this class stays ignorant of what the managers store.

Exactly one runtime is active at a time: requests that don't name a workflow act on it. A request
is pinned to the runtime that was active when it was dispatched (see `Engine.bind_workflow_runtime`),
so tasks it spawns keep working on that workflow even if another becomes active.
"""

from __future__ import annotations

import uuid
from contextvars import ContextVar
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable

# The runtime the current request was dispatched against. A ContextVar so asyncio tasks a request
# spawns inherit it.
bound_workflow_runtime: ContextVar[WorkflowRuntime | None] = ContextVar(
    "griptape_nodes_bound_workflow_runtime", default=None
)


class WorkflowRuntime:
    """The state of one open workflow, keyed by the type of each manager's state object."""

    def __init__(self, owner: object) -> None:
        self.runtime_id = uuid.uuid4().hex
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
