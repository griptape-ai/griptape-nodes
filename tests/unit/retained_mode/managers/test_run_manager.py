"""Tests for RunManager: a run is one request, and with the run queue on, runs here take turns."""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import MagicMock

import pytest

from griptape_nodes.retained_mode.beta_features import RUN_QUEUE
from griptape_nodes.retained_mode.managers.run_manager import RunManager, current_run_id, runs_as_one_run
from griptape_nodes.retained_mode.managers.run_queue import NotAdmittedError


def _run_manager(*, run_queue: bool) -> RunManager:
    engine = MagicMock()
    engine.get_session_id.return_value = "sess-abc"
    engine.config_manager.get_config_value.side_effect = lambda key, default=None, **_: (
        run_queue if key == RUN_QUEUE.config_key else default
    )
    manager = RunManager(engine=engine)
    engine.run_manager = manager
    return manager


async def _settle() -> None:
    for _ in range(10):
        await asyncio.sleep(0)


class TestARunIsOneRequest:
    @pytest.mark.asyncio
    async def test_everything_inside_a_run_sees_its_id(self) -> None:
        manager = _run_manager(run_queue=False)

        async with manager.run_scope("flow"):
            run_id = current_run_id.get()

        assert run_id is not None
        assert current_run_id.get() is None

    @pytest.mark.asyncio
    async def test_a_run_inside_a_run_joins_it(self) -> None:
        manager = _run_manager(run_queue=True)

        async with manager.run_scope("outer"):
            outer = current_run_id.get()
            async with manager.run_scope("inner"):
                inner = current_run_id.get()

        assert inner == outer

    @pytest.mark.asyncio
    async def test_each_listener_hears_a_run_end_once(self) -> None:
        manager = _run_manager(run_queue=False)
        ended: list[str] = []

        async def listen(run_id: str) -> None:
            ended.append(run_id)

        manager.add_run_end_listener(listen)
        async with manager.run_scope("outer"):
            run_id = current_run_id.get()
            async with manager.run_scope("inner"):
                pass

        assert ended == [run_id]


class TestRunsOnThisMachineTakeTurns:
    @pytest.mark.asyncio
    async def test_a_second_run_waits_until_the_first_ends(self) -> None:
        manager = _run_manager(run_queue=True)
        first_done = asyncio.Event()
        order: list[str] = []

        async def run(name: str, hold: asyncio.Event | None) -> None:
            async with manager.run_scope(name):
                order.append(f"{name} started")
                if hold is not None:
                    await hold.wait()
                order.append(f"{name} ended")

        first = asyncio.ensure_future(run("first", first_done))
        await _settle()
        second = asyncio.ensure_future(run("second", None))
        await _settle()
        assert order == ["first started"]

        first_done.set()
        await asyncio.gather(first, second)

        assert order == ["first started", "first ended", "second started", "second ended"]

    @pytest.mark.asyncio
    async def test_with_the_beta_feature_off_runs_do_not_wait(self) -> None:
        manager = _run_manager(run_queue=False)
        hold = asyncio.Event()
        started: list[str] = []

        async def run(name: str) -> None:
            async with manager.run_scope(name):
                started.append(name)
                await hold.wait()

        runs = [asyncio.ensure_future(run("first")), asyncio.ensure_future(run("second"))]
        await _settle()
        assert started == ["first", "second"]

        hold.set()
        await asyncio.gather(*runs)

    @pytest.mark.asyncio
    async def test_cancelling_a_waiting_runs_flow_removes_it_without_starting_it(self) -> None:
        manager = _run_manager(run_queue=True)
        hold = asyncio.Event()
        ran: list[str] = []

        async def run(name: str) -> None:
            async with manager.run_scope(name):
                ran.append(name)
                await hold.wait()

        first = asyncio.ensure_future(run("first"))
        await _settle()
        waiting = asyncio.ensure_future(run("waiting"))
        await _settle()

        assert manager.cancel_waiting_runs("waiting") == 1
        with pytest.raises(NotAdmittedError, match="cancelled"):
            await waiting
        assert manager.cancel_waiting_runs("first") == 0, "a run that started is not waiting"

        hold.set()
        await first
        assert ran == ["first"]

    @pytest.mark.asyncio
    async def test_a_handler_whose_run_was_cancelled_while_it_waited_returns_its_failure(self) -> None:
        manager = _run_manager(run_queue=True)
        failures: list[dict[str, Any]] = []

        class Handler:
            engine = manager.engine

            @runs_as_one_run(lambda **fields: failures.append(fields) or "failed", lambda _self, request: request)
            async def handle(self, request: str) -> str:
                return f"ran {request}"

        handler = Handler()
        await manager.queue.acquire(manager.local_originator(), "held")
        waiting = asyncio.ensure_future(handler.handle("flow"))
        await _settle()

        manager.cancel_waiting_runs("flow")

        assert await waiting == "failed"
        assert "cancelled" in str(failures[0]["result_details"])
