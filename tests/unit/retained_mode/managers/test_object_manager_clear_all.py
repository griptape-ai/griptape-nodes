"""Clearing all object state must cancel an in-flight run before tearing it down.

`reset_global_execution_state()` drops the run's task bookkeeping and nulls its
machine state, which makes the flow look idle. Anything that cancels on the
strength of `check_for_existing_running_flow()` afterwards -- including
`Engine.close_workflow_state` -- is then a no-op, and the previous run's node
tasks carry on: still billing API calls, and still
emitting parameter updates keyed by node name that land on the same-named nodes
of whatever run is loaded next.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, patch

import pytest

from griptape_nodes.retained_mode.events.object_events import (
    ClearAllObjectStateRequest,
    ClearAllObjectStateResultSuccess,
)
from tests.workflow_context import push_unsaved_workflow

if TYPE_CHECKING:
    from griptape_nodes.retained_mode.engine import Engine


class RunningFlowStub:
    """Stands in for a running flow: running until its cancel is awaited, recording each step."""

    def __init__(self, calls: list[str]) -> None:
        self.calls = calls
        self.running = True

    def check_for_existing_running_flow(self) -> bool:
        return self.running

    async def cancel_flow_run(self) -> None:
        self.calls.append("cancel")
        self.running = False


class TestClearAllObjectStateCancelsFirst:
    @pytest.mark.parametrize("workflow_open", [True, False])
    def test_running_flow_is_cancelled_before_execution_state_is_reset(
        self, engine: Engine, *, workflow_open: bool
    ) -> None:
        if workflow_open:
            push_unsaved_workflow(engine)
        calls: list[str] = []
        flow = RunningFlowStub(calls)
        flow_manager = engine.flow_manager
        reset = flow_manager.reset_global_execution_state
        clear_top_entry = engine._clear_top_workflow_entry

        def record_reset() -> None:
            calls.append("reset")
            reset()

        def record_teardown() -> None:
            calls.append("teardown")
            clear_top_entry()

        with (
            patch.object(
                flow_manager, "check_for_existing_running_flow", side_effect=flow.check_for_existing_running_flow
            ),
            patch.object(flow_manager, "cancel_flow_run", side_effect=flow.cancel_flow_run),
            patch.object(flow_manager, "reset_global_execution_state", side_effect=record_reset),
            patch.object(engine, "_clear_top_workflow_entry", side_effect=record_teardown),
        ):
            result = engine.handle_request(ClearAllObjectStateRequest(i_know_what_im_doing=True))

        assert isinstance(result, ClearAllObjectStateResultSuccess)
        expected = ["cancel", "reset"]
        if workflow_open:
            expected.append("teardown")
        assert calls == expected, "the reset must not run ahead of the cancel"
        assert engine.open_workflows.sole_workflow_or_none() is None


class TestCancelRunningFlowBeforeTeardown:
    @pytest.mark.asyncio
    async def test_idle_engine_is_not_cancelled(self, engine: Engine) -> None:
        flow_manager = engine.flow_manager

        with patch.object(flow_manager, "cancel_flow_run", AsyncMock()) as cancel:
            await flow_manager.cancel_running_flow_before_teardown()

        assert not flow_manager.check_for_existing_running_flow()
        cancel.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_running_flow_is_cancelled(self, engine: Engine) -> None:
        flow_manager = engine.flow_manager

        with (
            patch.object(flow_manager, "check_for_existing_running_flow", return_value=True),
            patch.object(flow_manager, "cancel_flow_run", AsyncMock()) as cancel,
        ):
            await flow_manager.cancel_running_flow_before_teardown()

        cancel.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_a_failed_cancel_does_not_block_the_teardown(
        self, engine: Engine, caplog: pytest.LogCaptureFixture
    ) -> None:
        flow_manager = engine.flow_manager

        with (
            patch.object(flow_manager, "check_for_existing_running_flow", return_value=True),
            patch.object(flow_manager, "cancel_flow_run", AsyncMock(side_effect=RuntimeError("stuck node"))),
        ):
            await flow_manager.cancel_running_flow_before_teardown()

        assert "Could not cancel the running workflow" in caplog.text
