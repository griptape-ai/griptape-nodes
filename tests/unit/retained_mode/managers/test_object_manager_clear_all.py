"""Clearing all object state must cancel an in-flight run before tearing it down.

`reset_global_execution_state()` drops the run's task bookkeeping and nulls its
machine state, which makes the flow look idle. Anything that cancels on the
strength of `check_for_existing_running_flow()` afterwards -- including
`Engine.close_workflow_state` -- is then a no-op, and the previous run's node
tasks carry on: still billing API calls, and still
emitting parameter updates keyed by node name that land on the same-named nodes
of whatever run is loaded next.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from griptape_nodes.retained_mode.events.object_events import (
    ClearAllObjectStateRequest,
    ClearAllObjectStateResultSuccess,
)
from griptape_nodes.retained_mode.managers.flow_manager import FlowManager
from griptape_nodes.retained_mode.managers.object_manager import ObjectManager


class TestClearAllObjectStateCancelsFirst:
    @pytest.mark.asyncio
    async def test_running_flow_is_cancelled_before_execution_state_is_reset(self) -> None:
        calls: list[str] = []

        engine = MagicMock()
        engine.flow_manager.cancel_running_flow_before_teardown = AsyncMock(side_effect=lambda: calls.append("cancel"))
        engine.flow_manager.reset_global_execution_state = MagicMock(side_effect=lambda: calls.append("reset"))
        # Awaited by the handler to release objects libraries parked in workers.
        engine.worker_manager.broadcast_local_object_teardown = AsyncMock()
        engine.open_workflows.sole_workflow_or_none.return_value = None

        object_manager = ObjectManager(MagicMock(), engine=engine)
        result = await object_manager.on_clear_all_object_state_request(
            ClearAllObjectStateRequest(i_know_what_im_doing=True)
        )

        assert isinstance(result, ClearAllObjectStateResultSuccess)
        assert calls == ["cancel", "reset"], "the reset must not run ahead of the cancel"


class TestCancelRunningFlowBeforeTeardown:
    @pytest.mark.asyncio
    async def test_idle_engine_is_not_cancelled(self) -> None:
        flow_manager = MagicMock()
        flow_manager.check_for_existing_running_flow.return_value = False
        flow_manager.cancel_flow_run = AsyncMock()

        await FlowManager.cancel_running_flow_before_teardown(flow_manager)

        flow_manager.cancel_flow_run.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_running_flow_is_cancelled(self) -> None:
        flow_manager = MagicMock()
        flow_manager.check_for_existing_running_flow.return_value = True
        flow_manager.cancel_flow_run = AsyncMock()

        await FlowManager.cancel_running_flow_before_teardown(flow_manager)

        flow_manager.cancel_flow_run.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_a_failed_cancel_does_not_block_the_teardown(self, caplog: pytest.LogCaptureFixture) -> None:
        flow_manager = MagicMock()
        flow_manager.check_for_existing_running_flow.return_value = True
        flow_manager.cancel_flow_run = AsyncMock(side_effect=RuntimeError("stuck node"))

        await FlowManager.cancel_running_flow_before_teardown(flow_manager)

        assert "Could not cancel the running workflow" in caplog.text
