"""Tests for RunQueue: one run has the machine at a time, the rest wait in the order they asked."""

from __future__ import annotations

import asyncio

import pytest

from griptape_nodes.retained_mode.managers.run_queue import NotAdmittedError, RunQueue

_A = "session-a"
_B = "session-b"


async def _settle() -> None:
    for _ in range(5):
        await asyncio.sleep(0)


class TestRunQueue:
    @pytest.mark.asyncio
    async def test_a_free_machine_goes_to_the_first_run_at_once(self) -> None:
        queue = RunQueue()

        await queue.acquire(_A, "r1")

        assert queue.holder == (_A, "r1")

    @pytest.mark.asyncio
    async def test_another_run_waits_until_the_run_holding_the_machine_releases_it(self) -> None:
        queue = RunQueue()
        await queue.acquire(_A, "r1")

        waiting = asyncio.ensure_future(queue.acquire(_B, "r2"))
        await _settle()
        assert not waiting.done()

        queue.release(_A, "r1")
        await asyncio.wait_for(waiting, timeout=1.0)

        assert queue.holder == (_B, "r2")

    @pytest.mark.asyncio
    async def test_waiting_runs_get_the_machine_in_the_order_they_asked(self) -> None:
        queue = RunQueue()
        await queue.acquire(_A, "first")
        second = asyncio.ensure_future(queue.acquire(_A, "second"))
        await _settle()
        third = asyncio.ensure_future(queue.acquire(_B, "third"))
        await _settle()

        queue.release(_A, "first")
        await asyncio.wait_for(second, timeout=1.0)
        assert not third.done()
        queue.release(_A, "second")
        await asyncio.wait_for(third, timeout=1.0)

        assert queue.holder == (_B, "third")

    @pytest.mark.asyncio
    async def test_a_cancelled_waiting_run_never_gets_the_machine_and_the_next_one_does(self) -> None:
        queue = RunQueue()
        await queue.acquire(_A, "first")
        cancelled = asyncio.ensure_future(queue.acquire(_A, "cancelled"))
        await _settle()
        after = asyncio.ensure_future(queue.acquire(_B, "after"))
        await _settle()

        assert queue.cancel_waiting(_A, "cancelled") is True
        with pytest.raises(NotAdmittedError, match="cancelled"):
            await cancelled
        queue.release(_A, "first")
        await asyncio.wait_for(after, timeout=1.0)

        assert queue.holder == (_B, "after")

    @pytest.mark.asyncio
    async def test_cancelling_a_run_that_is_not_waiting_changes_nothing(self) -> None:
        queue = RunQueue()
        await queue.acquire(_A, "r1")

        assert queue.cancel_waiting(_A, "r1") is False
        assert queue.holder == (_A, "r1")

    @pytest.mark.asyncio
    async def test_a_release_from_a_run_without_the_machine_changes_nothing(self) -> None:
        queue = RunQueue()
        await queue.acquire(_A, "r1")
        waiting = asyncio.ensure_future(queue.acquire(_B, "r2"))
        await _settle()

        queue.release(_B, "r2")
        await _settle()

        assert queue.holder == (_A, "r1")
        assert not waiting.done()
        queue.release(_A, "r1")
        await asyncio.wait_for(waiting, timeout=1.0)

    @pytest.mark.asyncio
    async def test_a_run_whose_wait_is_cancelled_as_it_gets_the_machine_gives_it_back(self) -> None:
        """Otherwise it would hold the machine with nothing left to release it, and every later run would wait."""
        queue = RunQueue()
        await queue.acquire(_A, "first")
        cancelled = asyncio.ensure_future(queue.acquire(_A, "cancelled"))
        await _settle()
        after = asyncio.ensure_future(queue.acquire(_B, "after"))
        await _settle()

        queue.release(_A, "first")
        cancelled.cancel()
        await asyncio.gather(cancelled, return_exceptions=True)
        await asyncio.wait_for(after, timeout=1.0)

        assert queue.holder == (_B, "after")

    @pytest.mark.asyncio
    async def test_releasing_with_no_one_waiting_frees_the_machine(self) -> None:
        queue = RunQueue()
        await queue.acquire(_A, "r1")

        queue.release(_A, "r1")

        assert queue.holder is None


class _Recorder:
    """Records the hooks a machine serving other machines sets on its queue."""

    def __init__(self) -> None:
        self.handoffs: list[str] = []
        self.positions: list[tuple[str, str, int]] = []

    async def on_handoff(self, incoming: str) -> None:
        self.handoffs.append(incoming)

    async def on_position(self, originator: str, _run_id: str, node_names: list[str], position: int) -> None:
        self.positions.extend((originator, node_name, position) for node_name in node_names)


def _serving(recorder: _Recorder, *, idle_timeout_s: float = 60.0) -> RunQueue:
    queue = RunQueue()
    queue.serve_other_machines(
        idle_timeout_s=idle_timeout_s, on_handoff=recorder.on_handoff, on_position=recorder.on_position
    )
    return queue


def _admit(queue: RunQueue, admission_id: str, originator: str, run_id: str | None) -> asyncio.Task[str]:
    return asyncio.ensure_future(
        queue.admit(admission_id=admission_id, originator=originator, run_id=run_id, node_name=f"node-{admission_id}")
    )


class TestOtherMachinesNodesShareTheQueue:
    @pytest.mark.asyncio
    async def test_a_free_machine_admits_at_once(self) -> None:
        queue = _serving(_Recorder())

        run = await queue.admit(admission_id="1", originator=_A, run_id="r1", node_name="n")

        assert run == "r1"
        assert queue.holder == (_A, "r1")

    @pytest.mark.asyncio
    async def test_another_run_waits_until_the_run_holding_the_machine_ends(self) -> None:
        recorder = _Recorder()
        queue = _serving(recorder)
        await queue.admit(admission_id="1", originator=_A, run_id="r1", node_name="n")

        waiting = _admit(queue, "2", _B, "r9")
        await _settle()
        assert not waiting.done()
        assert recorder.positions == [(_B, "node-2", 1)]

        queue.end_run(_A, "r1")
        await _settle()

        assert await waiting == "r9"
        assert queue.holder == (_B, "r9")
        assert recorder.positions[-1] == (_B, "node-2", 0), "B was not told its wait was over"

    @pytest.mark.asyncio
    async def test_the_holding_runs_later_nodes_run_while_another_run_waits(self) -> None:
        queue = _serving(_Recorder())
        await queue.admit(admission_id="1", originator=_A, run_id="r1", node_name="n")
        waiting = _admit(queue, "2", _B, "r9")
        await _settle()

        run = await queue.admit(admission_id="3", originator=_A, run_id="r1", node_name="later")

        assert run == "r1"
        assert not waiting.done()
        queue.end_run(_A, "r1")
        await waiting

    @pytest.mark.asyncio
    async def test_every_waiting_node_of_the_next_run_is_admitted_together(self) -> None:
        queue = _serving(_Recorder())
        await queue.admit(admission_id="1", originator=_A, run_id="r1", node_name="n")
        first = _admit(queue, "2", _B, "r9")
        second = _admit(queue, "3", _B, "r9")
        await _settle()

        queue.end_run(_A, "r1")
        await _settle()

        assert first.done()
        assert second.done()

    @pytest.mark.asyncio
    async def test_a_node_joining_a_waiting_run_is_told_its_place(self) -> None:
        recorder = _Recorder()
        queue = _serving(recorder)
        await queue.admit(admission_id="1", originator=_A, run_id="r1", node_name="n")
        _admit(queue, "2", _B, "r9")
        await _settle()

        _admit(queue, "3", _B, "r9")
        await _settle()

        assert (_B, "node-3", 1) in recorder.positions

    @pytest.mark.asyncio
    async def test_runs_take_the_machine_in_the_order_they_first_asked(self) -> None:
        recorder = _Recorder()
        queue = _serving(recorder)
        await queue.admit(admission_id="1", originator=_A, run_id="r1", node_name="n")
        b_waits = _admit(queue, "2", _B, "r9")
        c_waits = _admit(queue, "3", "session-c", "r5")
        await _settle()
        assert (_B, "node-2", 1) in recorder.positions
        assert ("session-c", "node-3", 2) in recorder.positions

        queue.end_run(_A, "r1")
        await _settle()

        assert b_waits.done()
        assert not c_waits.done()
        assert ("session-c", "node-3", 1) in recorder.positions

    @pytest.mark.asyncio
    async def test_a_run_started_here_waits_in_the_same_line_as_other_machines_runs(self) -> None:
        queue = _serving(_Recorder())
        await queue.admit(admission_id="1", originator=_A, run_id="r1", node_name="n")
        local = asyncio.ensure_future(queue.acquire("this-machine", "local-run"))
        await _settle()
        assert not local.done()

        queue.end_run(_A, "r1")
        await asyncio.wait_for(local, timeout=1.0)

        assert queue.holder == ("this-machine", "local-run")

    @pytest.mark.asyncio
    async def test_the_machine_is_freed_only_when_it_passes_to_another_orchestrator(self) -> None:
        recorder = _Recorder()
        queue = _serving(recorder)
        await queue.admit(admission_id="1", originator=_A, run_id="r1", node_name="n")
        queue.end_run(_A, "r1")
        await _settle()

        await queue.admit(admission_id="2", originator=_A, run_id="r2", node_name="n")
        assert recorder.handoffs == [], "the same artist's next run must not free its own models"

        waiting = _admit(queue, "3", _B, "r9")
        queue.end_run(_A, "r2")
        await waiting

        assert recorder.handoffs == [_B]

    @pytest.mark.asyncio
    async def test_a_run_started_here_after_another_machines_run_frees_the_machine_first(self) -> None:
        recorder = _Recorder()
        queue = _serving(recorder)
        await queue.admit(admission_id="1", originator=_A, run_id="r1", node_name="n")
        queue.end_run(_A, "r1")
        await _settle()

        await queue.acquire("this-machine", "local-run")

        assert recorder.handoffs == ["this-machine"]

    @pytest.mark.asyncio
    async def test_a_handoff_that_fails_still_hands_the_machine_over(self) -> None:
        recorder = _Recorder()

        async def fail_to_free(incoming: str) -> None:
            recorder.handoffs.append(incoming)
            msg = "the connection is re-establishing"
            raise ConnectionError(msg)

        queue = RunQueue()
        queue.serve_other_machines(idle_timeout_s=60.0, on_handoff=fail_to_free, on_position=recorder.on_position)
        await queue.admit(admission_id="1", originator=_A, run_id="r1", node_name="n")
        waiting = _admit(queue, "2", _B, "r9")
        await _settle()

        queue.end_run(_A, "r1")

        assert await asyncio.wait_for(waiting, timeout=1.0) == "r9"
        assert recorder.handoffs == [_B]
        assert queue.holder == (_B, "r9")

    @pytest.mark.asyncio
    async def test_a_run_with_no_node_running_lets_go_after_the_idle_timeout(self) -> None:
        queue = _serving(_Recorder(), idle_timeout_s=0.05)
        await queue.admit(admission_id="1", originator=_A, run_id="r1", node_name="n")
        waiting = _admit(queue, "2", _B, "r9")

        queue.node_ended("1")
        await asyncio.wait_for(waiting, timeout=1)

        assert queue.holder == (_B, "r9")

    @pytest.mark.asyncio
    async def test_a_running_node_keeps_the_machine_past_the_idle_timeout(self) -> None:
        """A node that runs longer than the timeout is not idle: the timeout counts from the last one ending."""
        queue = _serving(_Recorder(), idle_timeout_s=0.05)
        await queue.admit(admission_id="1", originator=_A, run_id="r1", node_name="n")
        waiting = _admit(queue, "2", _B, "r9")

        await asyncio.sleep(0.15)

        assert not waiting.done()
        queue.end_run(_A, "r1")
        await waiting

    @pytest.mark.asyncio
    async def test_a_run_started_here_keeps_the_machine_however_long_no_node_runs(self) -> None:
        queue = _serving(_Recorder(), idle_timeout_s=0.05)
        await queue.acquire("this-machine", "local-run")
        waiting = _admit(queue, "2", _B, "r9")

        await asyncio.sleep(0.15)

        assert not waiting.done()
        queue.release("this-machine", "local-run")
        await asyncio.wait_for(waiting, timeout=1.0)

    @pytest.mark.asyncio
    async def test_a_node_sent_without_a_run_holds_the_machine_only_while_it_runs(self) -> None:
        queue = _serving(_Recorder())
        run = await queue.admit(admission_id="1", originator=_A, run_id=None, node_name="n")
        waiting = _admit(queue, "2", _B, "r9")
        await _settle()
        assert not waiting.done()

        queue.node_ended("1")
        await asyncio.wait_for(waiting, timeout=1)

        assert run.startswith("one-off:")

    @pytest.mark.asyncio
    async def test_two_nodes_sent_without_a_run_are_separate_runs(self) -> None:
        queue = _serving(_Recorder())
        await queue.admit(admission_id="1", originator=_A, run_id=None, node_name="n")

        second = _admit(queue, "2", _A, None)
        await _settle()

        assert not second.done()
        queue.node_ended("1")
        await asyncio.wait_for(second, timeout=1)

    @pytest.mark.asyncio
    async def test_an_orchestrator_going_away_frees_the_machine_and_turns_its_waiting_runs_away(self) -> None:
        queue = _serving(_Recorder())
        await queue.admit(admission_id="1", originator=_A, run_id="r1", node_name="n")
        b_waits = _admit(queue, "2", _B, "r9")
        another_a = _admit(queue, "3", _A, "r2")
        await _settle()

        queue.originator_gone(_A)
        await _settle()

        assert b_waits.done()
        with pytest.raises(NotAdmittedError):
            await another_a

    @pytest.mark.asyncio
    async def test_a_waiting_node_cancelled_stops_waiting_and_moves_the_line_up(self) -> None:
        recorder = _Recorder()
        queue = _serving(recorder)
        await queue.admit(admission_id="1", originator=_A, run_id="r1", node_name="n")
        b_waits = _admit(queue, "2", _B, "r9")
        c_waits = _admit(queue, "3", "session-c", "r5")
        await _settle()

        queue.node_ended("2")
        await _settle()

        with pytest.raises(NotAdmittedError):
            await b_waits
        assert ("session-c", "node-3", 1) in recorder.positions
        queue.end_run(_A, "r1")
        await c_waits
