"""The queue a machine keeps of the runs that use it, one run at a time.

A run is what one request starts: running a workflow, a subflow, or a single node. It takes the
machine before it executes anything and gives it back when it ends; every other run waits, in the
order it asked. The queue holds no transport and runs nothing itself: it only decides which run has
the machine.

A machine that runs nodes for other machines' orchestrators admits those nodes into the same line,
bundled by the run each belongs to: a run's nodes run as they arrive once it has the machine, several
at once if it sends several. Such a run gives the machine up when its orchestrator says the run
ended, when none of its nodes has been running for the idle timeout, or when its orchestrator goes
away, whichever comes first. A node sent without a run is a run of its own, which ends when the node
does.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

logger = logging.getLogger("griptape_nodes")

_ONE_OFF_RUN_PREFIX = "one-off:"


class NotAdmittedError(Exception):
    """Raised at a run that waited and will never get the machine, carrying why."""


@dataclass
class _WaitingNode:
    admission_id: str
    node_name: str
    admitted: asyncio.Future[None]


@dataclass
class _WaitingRun:
    originator: str
    run_id: str
    # Set for a run started on this machine, which waits as a whole; None for another machine's run,
    # whose nodes wait instead.
    acquired: asyncio.Future[None] | None = None
    nodes: list[_WaitingNode] = field(default_factory=list)
    position: int = 0

    @property
    def is_empty(self) -> bool:
        return self.acquired is None and not self.nodes


@dataclass
class _RunHoldingMachine:
    originator: str
    run_id: str
    # A run started on this machine keeps the machine until it is released, however long no node runs.
    acquired: bool
    running: set[str] = field(default_factory=set)
    idle_timer: asyncio.TimerHandle | None = None

    @property
    def is_one_off(self) -> bool:
        return self.run_id.startswith(_ONE_OFF_RUN_PREFIX)


async def _free_nothing(_incoming_originator: str) -> None:
    return


async def _tell_no_one(_originator: str, _run_id: str, _node_names: list[str], _position: int) -> None:
    return


class RunQueue:
    """Gives the machine to one run at a time, first come first served."""

    def __init__(self) -> None:
        self._holder: _RunHoldingMachine | None = None
        self._waiting: list[_WaitingRun] = []
        self._idle_timeout_s = 0.0
        self._on_handoff: Callable[[str], Awaitable[None]] = _free_nothing
        self._on_position: Callable[[str, str, list[str], int], Awaitable[None]] = _tell_no_one
        # Whose run last had the machine, so a handoff to the same orchestrator frees nothing.
        self._last_originator: str | None = None
        self._advancing = False
        self._tasks: set[asyncio.Task] = set()

    @property
    def holder(self) -> tuple[str, str] | None:
        """The orchestrator and run that have the machine, or None while it is free."""
        if self._holder is None:
            return None
        return self._holder.originator, self._holder.run_id

    def serve_other_machines(
        self,
        *,
        idle_timeout_s: float,
        on_handoff: Callable[[str], Awaitable[None]],
        on_position: Callable[[str, str, list[str], int], Awaitable[None]],
    ) -> None:
        """Set how this machine shares itself with other machines' orchestrators.

        Args:
            idle_timeout_s: How long another machine's run keeps the machine with none of its nodes running.
            on_handoff: Awaited with the incoming run's orchestrator before the machine passes to a run
                from a different orchestrator than the last one, to free what the previous one left.
            on_position: Awaited with a waiting run's orchestrator, id, the names of its waiting nodes,
                and its place in line, 1 being next, whenever that place changes, and with 0 once the
                machine takes it.
        """
        self._idle_timeout_s = idle_timeout_s
        self._on_handoff = on_handoff
        self._on_position = on_position

    async def acquire(self, originator: str, run_id: str) -> None:
        """Return once the run has the machine, waiting behind every run that asked before it.

        Raises:
            NotAdmittedError: The run will not get the machine, such as when it was cancelled while it waited.
        """
        acquired: asyncio.Future[None] = asyncio.get_running_loop().create_future()
        waiting = _WaitingRun(originator=originator, run_id=run_id, acquired=acquired)
        self._waiting.append(waiting)
        try:
            await self._advance()
            await acquired
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
        self._release_machine()

    def cancel_waiting(self, originator: str, run_id: str) -> bool:
        """Remove a waiting run from the line without giving it the machine, returning whether it waited."""
        return self._turn_away(
            lambda waiting: (waiting.originator, waiting.run_id) == (originator, run_id),
            "it was cancelled while it waited.",
        )

    async def admit(self, *, admission_id: str, originator: str, run_id: str | None, node_name: str) -> str:
        """Return once another machine's node may run, with the run it runs in.

        Raises:
            NotAdmittedError: The node will not run here; its run ended or its orchestrator went away
                while it waited.
        """
        if run_id is None:
            run_id = f"{_ONE_OFF_RUN_PREFIX}{admission_id}"
        holder = self._holder
        if holder is not None and (holder.originator, holder.run_id) == (originator, run_id):
            self._start_running(holder, admission_id)
            return run_id
        node = _WaitingNode(
            admission_id=admission_id, node_name=node_name, admitted=asyncio.get_running_loop().create_future()
        )
        waiting = self._waiting_run(originator, run_id)
        waiting.nodes.append(node)
        # A run already in line has been told its place; a node joining it hears that place itself.
        if waiting.position:
            await self._on_position(originator, run_id, [node_name], waiting.position)
        await self._advance()
        await node.admitted
        return run_id

    def node_ended(self, admission_id: str) -> None:
        """Record that another machine's node finished, or was cancelled before or while it ran."""
        for waiting in self._waiting:
            for node in waiting.nodes:
                if node.admission_id == admission_id:
                    waiting.nodes.remove(node)
                    if not node.admitted.done():
                        node.admitted.set_exception(NotAdmittedError("it was cancelled while it waited."))
                    if waiting.is_empty:
                        self._waiting.remove(waiting)
                    self._schedule(self._report_positions())
                    return
        holder = self._holder
        if holder is None or admission_id not in holder.running:
            return
        holder.running.discard(admission_id)
        if holder.running or holder.acquired:
            return
        if holder.is_one_off:
            self._release_machine()
            return
        holder.idle_timer = asyncio.get_running_loop().call_later(self._idle_timeout_s, self._end_if_idle, holder)

    def end_run(self, originator: str, run_id: str) -> None:
        """Record that another machine's run ended, freeing the machine if the run has it."""
        self._turn_away(
            lambda waiting: (waiting.originator, waiting.run_id) == (originator, run_id),
            "its run ended before the machine was free.",
        )
        self.release(originator, run_id)

    def originator_gone(self, originator: str) -> None:
        """Forget an orchestrator that went away: its waiting runs, and its run if it has the machine."""
        self._turn_away(lambda waiting: waiting.originator == originator, "its machine is no longer connected.")
        holder = self._holder
        if holder is not None and holder.originator == originator:
            self._release_machine()

    def _waiting_run(self, originator: str, run_id: str) -> _WaitingRun:
        for waiting in self._waiting:
            if (waiting.originator, waiting.run_id) == (originator, run_id) and waiting.acquired is None:
                return waiting
        waiting = _WaitingRun(originator=originator, run_id=run_id)
        self._waiting.append(waiting)
        return waiting

    def _start_running(self, holder: _RunHoldingMachine, admission_id: str) -> None:
        holder.running.add(admission_id)
        if holder.idle_timer is not None:
            holder.idle_timer.cancel()
            holder.idle_timer = None

    def _end_if_idle(self, holder: _RunHoldingMachine) -> None:
        if self._holder is holder and not holder.running:
            logger.info(
                "Run %s from %s ended after %.0f seconds with no node running here.",
                holder.run_id,
                holder.originator,
                self._idle_timeout_s,
            )
            self._release_machine()

    def _release_machine(self) -> None:
        holder = self._holder
        if holder is not None and holder.idle_timer is not None:
            holder.idle_timer.cancel()
        self._holder = None
        self._schedule(self._advance())

    def _turn_away(self, matches: Callable[[_WaitingRun], bool], reason: str) -> bool:
        turned_away = [waiting for waiting in self._waiting if matches(waiting)]
        for waiting in turned_away:
            self._waiting.remove(waiting)
            futures = [node.admitted for node in waiting.nodes]
            if waiting.acquired is not None:
                futures.append(waiting.acquired)
            for future in futures:
                if not future.done():
                    future.set_exception(NotAdmittedError(reason))
        if turned_away:
            self._schedule(self._report_positions())
        return bool(turned_away)

    async def _advance(self) -> None:
        """Give a free machine to the run that has waited longest, admitting every node of it that waits."""
        if self._advancing:
            return
        self._advancing = True
        admitted_after_waiting: list[_WaitingRun] = []
        try:
            while self._holder is None and self._waiting:
                head = self._waiting[0]
                if self._last_originator is not None and head.originator != self._last_originator:
                    logger.info(
                        "Freeing this machine before handing it from %s to %s.", self._last_originator, head.originator
                    )
                    # Freeing is best effort: a failure here must not leave the machine with no holder
                    # and every waiting run stuck until another one arrives.
                    try:
                        await self._on_handoff(head.originator)
                    except Exception:
                        logger.exception("Could not free this machine before the handoff; handing it over anyway.")
                    # Awaiting the handoff gave the head's orchestrator time to go away or end its run.
                    if not self._waiting or self._waiting[0] is not head:
                        continue
                self._waiting.pop(0)
                self._hand_to(head)
                if head.position:
                    admitted_after_waiting.append(head)
        finally:
            self._advancing = False
        for waiting in admitted_after_waiting:
            await self._on_position(waiting.originator, waiting.run_id, [node.node_name for node in waiting.nodes], 0)
        await self._report_positions()

    def _hand_to(self, waiting: _WaitingRun) -> None:
        holder = _RunHoldingMachine(
            originator=waiting.originator, run_id=waiting.run_id, acquired=waiting.acquired is not None
        )
        self._holder = holder
        self._last_originator = waiting.originator
        logger.debug("Run %s from %s has this machine.", waiting.run_id, waiting.originator)
        if waiting.acquired is not None and not waiting.acquired.done():
            waiting.acquired.set_result(None)
        for node in waiting.nodes:
            self._start_running(holder, node.admission_id)
            if not node.admitted.done():
                node.admitted.set_result(None)

    async def _report_positions(self) -> None:
        """Tell each waiting run its place in line, when that place changed."""
        for index, waiting in enumerate(self._waiting):
            position = index + 1
            if position != waiting.position:
                waiting.position = position
                await self._on_position(
                    waiting.originator, waiting.run_id, [node.node_name for node in waiting.nodes], position
                )

    def _schedule(self, coroutine: Awaitable[None]) -> None:
        task = asyncio.ensure_future(coroutine)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
