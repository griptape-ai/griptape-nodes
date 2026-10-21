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


class NotAdmittedError(Exception):
    """Raised at a run that waited and will never get the machine, carrying why."""


@dataclass
class _WaitingRun:
    originator: str
    run_id: str
    admitted: asyncio.Future[None]


@dataclass
class _RunHoldingMachine:
    originator: str
    run_id: str


class RunQueue:
    """Gives the machine to one run at a time, first come first served."""

    def __init__(self) -> None:
        self._holder: _RunHoldingMachine | None = None
        self._waiting: list[_WaitingRun] = []

    @property
    def holder(self) -> tuple[str, str] | None:
        """The orchestrator and run that have the machine, or None while it is free."""
        if self._holder is None:
            return None
        return self._holder.originator, self._holder.run_id

    async def acquire(self, originator: str, run_id: str) -> None:
        """Return once the run has the machine, waiting behind every run that asked before it.

        Raises:
            NotAdmittedError: The run will not get the machine, such as when it was cancelled while it waited.
        """
        if self._holder is None and not self._waiting:
            self._hand_to(originator, run_id)
            return
        waiting = _WaitingRun(originator=originator, run_id=run_id, admitted=asyncio.get_running_loop().create_future())
        self._waiting.append(waiting)
        try:
            await waiting.admitted
        except asyncio.CancelledError:
            # The caller stopped waiting, perhaps just as the machine passed to it. Either way it will
            # never release the machine, so it must not keep it or its place in line.
            if waiting in self._waiting:
                self._waiting.remove(waiting)
            self.release(originator, run_id)
            raise

    def release(self, originator: str, run_id: str) -> None:
        """Give the machine back after a run ends, to the run that has waited longest."""
        holder = self._holder
        if holder is None or (holder.originator, holder.run_id) != (originator, run_id):
            return
        self._holder = None
        self._advance()

    def cancel_waiting(self, originator: str, run_id: str) -> bool:
        """Remove a waiting run from the line without giving it the machine, returning whether it waited."""
        for waiting in self._waiting:
            if (waiting.originator, waiting.run_id) == (originator, run_id):
                self._waiting.remove(waiting)
                if not waiting.admitted.done():
                    waiting.admitted.set_exception(NotAdmittedError("it was cancelled while it waited."))
                return True
        return False

    def _advance(self) -> None:
        while self._holder is None and self._waiting:
            head = self._waiting.pop(0)
            # A waiter whose wait was cancelled already left; the machine passes to the next one.
            if head.admitted.done():
                continue
            self._hand_to(head.originator, head.run_id)
            head.admitted.set_result(None)

    def _hand_to(self, originator: str, run_id: str) -> None:
        self._holder = _RunHoldingMachine(originator=originator, run_id=run_id)
        logger.debug("Run %s from %s has this machine.", run_id, originator)
