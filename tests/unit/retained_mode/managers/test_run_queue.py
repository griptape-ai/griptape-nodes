"""Tests for RunQueue: one run has the machine at a time, the rest wait in the order they asked."""

from __future__ import annotations

import asyncio

import pytest

from griptape_nodes.retained_mode.managers.run_queue import RunHoldingMachine, RunQueue

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

        assert queue.holder == RunHoldingMachine(session=_A, run_id="r1")

    @pytest.mark.asyncio
    async def test_another_run_waits_until_the_run_holding_the_machine_releases_it(self) -> None:
        queue = RunQueue()
        await queue.acquire(_A, "r1")

        waiting = asyncio.ensure_future(queue.acquire(_B, "r2"))
        await _settle()
        assert not waiting.done()

        queue.release(_A, "r1")
        await asyncio.wait_for(waiting, timeout=1.0)

        assert queue.holder == RunHoldingMachine(session=_B, run_id="r2")

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

        assert queue.holder == RunHoldingMachine(session=_B, run_id="third")

    @pytest.mark.asyncio
    async def test_a_release_from_a_run_without_the_machine_changes_nothing(self) -> None:
        queue = RunQueue()
        await queue.acquire(_A, "r1")
        waiting = asyncio.ensure_future(queue.acquire(_B, "r2"))
        await _settle()

        queue.release(_B, "r2")
        await _settle()

        assert queue.holder == RunHoldingMachine(session=_A, run_id="r1")
        assert not waiting.done()
        queue.release(_A, "r1")
        await asyncio.wait_for(waiting, timeout=1.0)

    @pytest.mark.asyncio
    async def test_a_run_that_stops_waiting_leaves_the_line_and_the_next_one_gets_the_machine(self) -> None:
        queue = RunQueue()
        await queue.acquire(_A, "first")
        cancelled = asyncio.ensure_future(queue.acquire(_A, "cancelled"))
        await _settle()
        after = asyncio.ensure_future(queue.acquire(_B, "after"))
        await _settle()

        cancelled.cancel()
        await asyncio.gather(cancelled, return_exceptions=True)
        queue.release(_A, "first")
        await asyncio.wait_for(after, timeout=1.0)

        assert queue.holder == RunHoldingMachine(session=_B, run_id="after")

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

        assert queue.holder == RunHoldingMachine(session=_B, run_id="after")

    @pytest.mark.asyncio
    async def test_releasing_with_no_one_waiting_frees_the_machine(self) -> None:
        queue = RunQueue()
        await queue.acquire(_A, "r1")

        queue.release(_A, "r1")

        assert queue.holder is None
