"""Tests for RunQueue: one run has the machine at a time, the rest wait in the order they asked."""

from __future__ import annotations

import asyncio

import pytest

from griptape_nodes.retained_mode.managers.run_queue import RunQueue


async def _settle() -> None:
    for _ in range(5):
        await asyncio.sleep(0)


class TestRunQueue:
    @pytest.mark.asyncio
    async def test_a_free_machine_goes_to_the_first_run_at_once(self) -> None:
        queue = RunQueue()

        await queue.acquire("r1")

        assert queue.holder == "r1"

    @pytest.mark.asyncio
    async def test_another_run_waits_until_the_run_holding_the_machine_releases_it(self) -> None:
        queue = RunQueue()
        await queue.acquire("r1")

        waiting = asyncio.ensure_future(queue.acquire("r2"))
        await _settle()
        assert not waiting.done()

        queue.release("r1")
        await asyncio.wait_for(waiting, timeout=1.0)

        assert queue.holder == "r2"

    @pytest.mark.asyncio
    async def test_waiting_runs_get_the_machine_in_the_order_they_asked(self) -> None:
        queue = RunQueue()
        await queue.acquire("first")
        second = asyncio.ensure_future(queue.acquire("second"))
        await _settle()
        third = asyncio.ensure_future(queue.acquire("third"))
        await _settle()

        queue.release("first")
        await asyncio.wait_for(second, timeout=1.0)
        assert not third.done()
        queue.release("second")
        await asyncio.wait_for(third, timeout=1.0)

        assert queue.holder == "third"

    @pytest.mark.asyncio
    async def test_a_release_from_a_run_without_the_machine_changes_nothing(self) -> None:
        queue = RunQueue()
        await queue.acquire("r1")
        waiting = asyncio.ensure_future(queue.acquire("r2"))
        await _settle()

        queue.release("r2")
        await _settle()

        assert queue.holder == "r1"
        assert not waiting.done()
        queue.release("r1")
        await asyncio.wait_for(waiting, timeout=1.0)

    @pytest.mark.asyncio
    async def test_a_run_that_stops_waiting_leaves_the_line_and_the_next_one_gets_the_machine(self) -> None:
        queue = RunQueue()
        await queue.acquire("first")
        cancelled = asyncio.ensure_future(queue.acquire("cancelled"))
        await _settle()
        after = asyncio.ensure_future(queue.acquire("after"))
        await _settle()

        cancelled.cancel()
        await asyncio.gather(cancelled, return_exceptions=True)
        queue.release("first")
        await asyncio.wait_for(after, timeout=1.0)

        assert queue.holder == "after"

    @pytest.mark.asyncio
    async def test_a_run_whose_wait_is_cancelled_as_it_gets_the_machine_gives_it_back(self) -> None:
        """Otherwise it would hold the machine with nothing left to release it, and every later run would wait."""
        queue = RunQueue()
        await queue.acquire("first")
        cancelled = asyncio.ensure_future(queue.acquire("cancelled"))
        await _settle()
        after = asyncio.ensure_future(queue.acquire("after"))
        await _settle()

        queue.release("first")
        cancelled.cancel()
        await asyncio.gather(cancelled, return_exceptions=True)
        await asyncio.wait_for(after, timeout=1.0)

        assert queue.holder == "after"

    @pytest.mark.asyncio
    async def test_releasing_with_no_one_waiting_frees_the_machine(self) -> None:
        queue = RunQueue()
        await queue.acquire("r1")

        queue.release("r1")

        assert queue.holder is None


class TestPlaceInLine:
    """Each waiting run hears its place in line when it changes, and 0 once it stops waiting."""

    @staticmethod
    def _queue() -> tuple[RunQueue, list[tuple[str, int]]]:
        heard: list[tuple[str, int]] = []
        queue = RunQueue(on_position=lambda run_id, position: heard.append((run_id, position)))
        return queue, heard

    @pytest.mark.asyncio
    async def test_a_run_that_gets_a_free_machine_hears_nothing(self) -> None:
        queue, heard = self._queue()

        await queue.acquire("r1")

        assert heard == []

    @pytest.mark.asyncio
    async def test_waiting_runs_hear_their_place_and_move_up_as_the_line_moves(self) -> None:
        queue, heard = self._queue()
        await queue.acquire("first")
        second = asyncio.ensure_future(queue.acquire("second"))
        third = asyncio.ensure_future(queue.acquire("third"))
        await _settle()
        assert heard == [("second", 1), ("third", 2)]

        queue.release("first")
        await asyncio.wait_for(second, timeout=1.0)

        assert heard[2:] == [("second", 0), ("third", 1)]
        queue.release("second")
        await asyncio.wait_for(third, timeout=1.0)
        assert heard[-1] == ("third", 0)

    @pytest.mark.asyncio
    async def test_a_run_that_stops_waiting_hears_0_and_the_runs_behind_it_move_up(self) -> None:
        queue, heard = self._queue()
        await queue.acquire("first")
        cancelled = asyncio.ensure_future(queue.acquire("cancelled"))
        behind = asyncio.ensure_future(queue.acquire("behind"))
        await _settle()

        cancelled.cancel()
        await asyncio.gather(cancelled, return_exceptions=True)

        assert heard[2:] == [("cancelled", 0), ("behind", 1)]
        queue.release("first")
        await asyncio.wait_for(behind, timeout=1.0)
