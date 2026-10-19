"""Which open workflows may run, decided in one place for the whole host.

Workers, the GPU, and held objects are shared by every open workflow, so starting a run is a host
decision rather than one a workflow can make for itself. Every way of starting a run (Run, Run Node,
stepping into a paused run) asks the scheduler first. The policy is one run at a time across the host;
lifting it means changing `admit` here and nowhere else.

Each admitted run gets a `run_id`. The work that drives a run binds it with `run_scope`, so the events
that run emits name it and a client can tell one run of a workflow from the next.
"""

from __future__ import annotations

import threading
import uuid
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator

    from griptape_nodes.retained_mode.runtime.workflow_runtime import WorkflowRuntime


@dataclass(frozen=True)
class Run:
    """One run of one open workflow."""

    run_id: str
    workflow_id: str


class RunRefusedError(RuntimeError):
    """A run was refused because another workflow is running."""


current_run: ContextVar[Run | None] = ContextVar("griptape_nodes_current_run", default=None)


@contextmanager
def run_scope(run: Run | None) -> Iterator[None]:
    """Attribute what runs inside the block, and the tasks it spawns, to `run`."""
    token = current_run.set(run)
    try:
        yield
    finally:
        current_run.reset(token)


@dataclass(frozen=True)
class _Lease:
    runtime: WorkflowRuntime
    run: Run


class RunScheduler:
    """Admits runs for the open workflows of one host, one at a time."""

    def __init__(
        self,
        *,
        is_running: Callable[[WorkflowRuntime], bool],
        display_name_of: Callable[[WorkflowRuntime], str],
    ) -> None:
        """Build a scheduler that asks each workflow's own execution state whether it is running.

        Args:
            is_running: Whether a workflow's run is still in progress. A lease outlives its run until the
                next admission, so this, not the lease, is what says a run is over.
            display_name_of: The name to show users for a workflow, for refusal messages.
        """
        self._is_running = is_running
        self._display_name_of = display_name_of
        self._lease: _Lease | None = None
        # Requests reach the engine on more than one event loop, so admission is guarded by a thread
        # lock rather than an asyncio one. Nothing in it awaits.
        self._lock = threading.Lock()

    def admit(self, runtime: WorkflowRuntime) -> Run:
        """Admit a run of `runtime`, or join the run it already has in progress.

        Raises:
            RunRefusedError: Another workflow is running.
        """
        with self._lock:
            lease = self._lease
            if lease is not None and self._is_running(lease.runtime):
                if lease.runtime is runtime:
                    return lease.run
                raise self._refusal(runtime, running=lease.runtime)
            run = Run(run_id=uuid.uuid4().hex, workflow_id=runtime.workflow_id)
            self._lease = _Lease(runtime=runtime, run=run)
            return run

    def raise_if_refused(self, runtime: WorkflowRuntime) -> None:
        """Refuse now, before changing anything, a run that `admit` would refuse.

        For entry points that alter the graph before they reach `admit`. `admit` still decides.

        Raises:
            RunRefusedError: Another workflow is running.
        """
        with self._lock:
            lease = self._lease
        if lease is None or lease.runtime is runtime or not self._is_running(lease.runtime):
            return
        raise self._refusal(runtime, running=lease.runtime)

    def run_of(self, runtime: WorkflowRuntime) -> Run | None:
        """The most recent run admitted for `runtime`, if no other workflow's run has been admitted since."""
        lease = self._lease
        if lease is None or lease.runtime is not runtime:
            return None
        return lease.run

    def running_runtime(self) -> WorkflowRuntime | None:
        """The workflow whose run is in progress, if any."""
        lease = self._lease
        if lease is None or not self._is_running(lease.runtime):
            return None
        return lease.runtime

    def release(self, runtime: WorkflowRuntime) -> None:
        """Forget `runtime`'s run, because the workflow is closing."""
        with self._lock:
            if self._lease is not None and self._lease.runtime is runtime:
                self._lease = None

    def _refusal(self, runtime: WorkflowRuntime, *, running: WorkflowRuntime) -> RunRefusedError:
        msg = (
            f"Attempted to run workflow '{self._display_name_of(runtime)}'. Failed because workflow "
            f"'{self._display_name_of(running)}' is running, and only one workflow runs at a time. "
            "Wait for it to finish or cancel it, then run this one."
        )
        return RunRefusedError(msg)
