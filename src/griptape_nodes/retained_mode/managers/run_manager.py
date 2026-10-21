"""Runs: what one request starts, and the queue that gives this machine to one of them at a time.

A run is what an artist starts with one click: running a workflow, a subflow, or a single node. Every
node it executes, nested subflows included, belongs to it. With the Queue runs beta feature on, a run
started while another is in progress waits for it instead of being refused.
"""

from __future__ import annotations

import contextlib
import functools
import uuid
from contextvars import ContextVar
from typing import TYPE_CHECKING, Any

from griptape_nodes.retained_mode.beta_features import RUN_QUEUE, is_beta_enabled
from griptape_nodes.retained_mode.engine import EngineScoped
from griptape_nodes.retained_mode.managers.run_queue import NotAdmittedError, RunQueue

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Awaitable, Callable

    from griptape_nodes.retained_mode.engine import Engine

# The run the code executing now belongs to, set for the length of a request that starts one. Tasks
# copy it when they are created, so every node the run executes, nested subflows included, sees it.
current_run_id: ContextVar[str | None] = ContextVar("current_run_id", default=None)


def runs_as_one_run[H: Callable[..., Awaitable[Any]]](
    failure: Callable[..., Any], flow_name_of: Callable[[Any, Any], str | None]
) -> Callable[[H], H]:
    """Make a request handler's request one run: everything it executes counts as that run.

    For the requests an artist starts a run with: running a workflow, a subflow, or a single node.
    One already inside a run joins it. The handler's object reaches its engine as `self.engine`.

    Args:
        failure: The handler's failure result type, returned for a run that waited in the run queue
            and never started, such as one cancelled while it waited.
        flow_name_of: The flow a request runs, given the handler's object and the request, or None if
            it names none. Cancelling that flow cancels the run while it waits.
    """

    def decorate(handler: H) -> H:
        @functools.wraps(handler)
        async def run(self: Any, request: Any) -> Any:
            try:
                async with self.engine.run_manager.run_scope(flow_name_of(self, request)):
                    return await handler(self, request)
            except NotAdmittedError as e:
                return failure(validation_exceptions=[], result_details=f"The run did not start: {e}")

        return run  # type: ignore[return-value]

    return decorate


class RunManager(EngineScoped):
    """Owns runs on this engine: their identity, and the queue that gives the machine to one at a time."""

    def __init__(self, engine: Engine | None = None) -> None:
        super().__init__(engine)
        self._queue = RunQueue()
        # Runs started here waiting for their turn, by run, with the flow each runs, so cancelling a
        # flow can find them.
        self._waiting_runs: dict[str, str | None] = {}
        self._run_end_listeners: list[Callable[[str], Awaitable[None]]] = []

    @property
    def queue(self) -> RunQueue:
        return self._queue

    @contextlib.asynccontextmanager
    async def run_scope(self, flow_name: str | None = None) -> AsyncIterator[None]:
        """Count everything executed inside as one run, telling each run-end listener once it returns.

        Inside a run already, joins it: a nested request is part of the run that issued it. With the
        Queue runs beta feature on, a new run first waits for its turn on this machine, and gives the
        machine up when it returns.

        Args:
            flow_name: The flow the run executes, so cancelling that flow cancels the run while it waits.

        Raises:
            NotAdmittedError: The run waited and will not start, such as when it was cancelled.
        """
        if current_run_id.get() is not None:
            yield
            return
        run_id = str(uuid.uuid4())
        queued = is_beta_enabled(RUN_QUEUE, self.engine.config_manager)
        if queued:
            await self._wait_for_turn(run_id, flow_name)
        token = current_run_id.set(run_id)
        try:
            yield
        finally:
            current_run_id.reset(token)
            if queued:
                self._queue.release(self.local_originator(), run_id)
            for listener in self._run_end_listeners:
                await listener(run_id)

    def add_run_end_listener(self, listener: Callable[[str], Awaitable[None]]) -> None:
        """Await `listener` with each run's id when a run started on this engine ends."""
        self._run_end_listeners.append(listener)

    def cancel_waiting_runs(self, flow_name: str) -> int:
        """Remove every run of `flow_name` waiting for its turn on this machine, returning how many."""
        waiting = [run_id for run_id, name in self._waiting_runs.items() if name == flow_name]
        for run_id in waiting:
            self._queue.cancel_waiting(self.local_originator(), run_id)
        return len(waiting)

    def local_originator(self) -> str:
        """The name this engine's own runs have in the run queue."""
        return self.engine.get_session_id() or self.engine.get_engine_id() or "local"

    async def _wait_for_turn(self, run_id: str, flow_name: str | None) -> None:
        self._waiting_runs[run_id] = flow_name
        try:
            await self._queue.acquire(self.local_originator(), run_id)
        finally:
            self._waiting_runs.pop(run_id, None)
