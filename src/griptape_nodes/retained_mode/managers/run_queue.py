"""The queue a machine keeps of the runs that use it, one run at a time.

A run is what one request starts: running a workflow, a subflow, or a single node. It takes the
machine before it executes anything and gives it back when it ends; every other run waits, in the
order it asked. The queue holds no transport and runs nothing itself: it only decides which run has
the machine.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

logger = logging.getLogger("griptape_nodes")


@dataclass(frozen=True)
class RunHoldingMachine:
    """The run that has the machine, and the session that started it."""

    session: str
    run_id: str


@dataclass
class _WaitingRun:
    session: str
    run_id: str
    admitted: asyncio.Future[None]


class RunQueue:
    """Gives the machine to one run at a time, first come first served."""

    def __init__(self) -> None:
        self._holder: RunHoldingMachine | None = None
        self._waiting: list[_WaitingRun] = []

    @property
    def holder(self) -> RunHoldingMachine | None:
        """The run that has the machine, or None while it is free."""
        return self._holder

    async def acquire(self, session: str, run_id: str) -> None:
        """Return once the run has the machine, waiting behind every run that asked before it."""
        if self._holder is None and not self._waiting:
            self._hand_to(session, run_id)
            return
        waiting = _WaitingRun(session=session, run_id=run_id, admitted=asyncio.get_running_loop().create_future())
        self._waiting.append(waiting)
        try:
            await waiting.admitted
        except asyncio.CancelledError:
            # The caller stopped waiting, perhaps just as the machine passed to it. Either way it will
            # never release the machine, so it must not keep it or its place in line.
            if waiting in self._waiting:
                self._waiting.remove(waiting)
            self.release(session, run_id)
            raise

    def release(self, session: str, run_id: str) -> None:
        """Give the machine back after a run ends, to the run that has waited longest."""
        if self._holder != RunHoldingMachine(session=session, run_id=run_id):
            return
        self._holder = None
        self._advance()

    def _advance(self) -> None:
        while self._holder is None and self._waiting:
            head = self._waiting.pop(0)
            # A waiter whose wait was cancelled already left; the machine passes to the next one.
            if head.admitted.done():
                continue
            self._hand_to(head.session, head.run_id)
            head.admitted.set_result(None)

    def _hand_to(self, session: str, run_id: str) -> None:
        self._holder = RunHoldingMachine(session=session, run_id=run_id)
        logger.debug("Run %s from %s has this machine.", run_id, session)
