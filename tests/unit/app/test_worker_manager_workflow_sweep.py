"""The orchestrator's half of the workflow sweep: name the open workflows to each worker, and keep the answers off the GUI."""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from griptape_nodes.retained_mode.events import converters, worker_events
from griptape_nodes.retained_mode.managers.worker_manager import WorkerManager, WorkerRegistration

_SESSION = "sess-abc"
_WORKER = "eng-xyz"
_WORKER_REQUEST_TOPIC = f"sessions/{_SESSION}/workers/{_WORKER}/request"
_WORKER_RESPONSE_TOPIC = f"sessions/{_SESSION}/workers/{_WORKER}/response"


def _runtime(workflow_id: str) -> MagicMock:
    runtime = MagicMock()
    runtime.workflow_id = workflow_id
    return runtime


@pytest.fixture
def worker_manager() -> WorkerManager:
    """A WorkerManager for an engine with two open workflows, one registered worker, and a mock transport."""
    engine = MagicMock()
    engine.get_session_id.return_value = _SESSION
    engine.get_engine_id.return_value = _WORKER
    engine.config_manager.get_config_value.side_effect = lambda _key, default, cast_type=None: (
        default if cast_type is None else cast_type(default)
    )
    engine.workflow_runtimes = [_runtime("workflow-a"), _runtime("workflow-b")]
    manager = WorkerManager(engine=engine, event_manager=MagicMock())
    manager.attach_transport(
        send_message=AsyncMock(),
        subscribe_to_topic=AsyncMock(),
        unsubscribe_from_topic=AsyncMock(),
        request_client=MagicMock(),
    )
    manager._workers[_WORKER] = WorkerRegistration(request_topic=_WORKER_REQUEST_TOPIC, worker_key=None)
    return manager


def _sweeps_sent(worker_manager: WorkerManager) -> list[dict]:
    sent = []
    for call in worker_manager._tx.send_message.call_args_list:  # type: ignore[union-attr]
        message = json.loads(call.args[1])
        if message["request_type"] == worker_events.SweepWorkflowRuntimesRequest.__name__:
            sent.append(message)
    return sent


class TestSendWorkflowRuntimeSweep:
    @pytest.mark.asyncio
    async def test_the_heartbeat_loop_names_the_open_workflows_to_each_worker(
        self, worker_manager: WorkerManager, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(worker_manager, "heartbeat_interval_s", 0.01)

        task = asyncio.create_task(worker_manager.orchestrator_heartbeat_loop())
        await asyncio.sleep(0.05)
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)

        sweeps = _sweeps_sent(worker_manager)
        assert sweeps, "guard: the loop must have swept"
        assert sweeps[0]["request"]["open_workflow_ids"] == ["workflow-a", "workflow-b"]
        topics = {call.args[2] for call in worker_manager._tx.send_message.call_args_list}  # type: ignore[union-attr]
        assert topics == {_WORKER_REQUEST_TOPIC}

    @pytest.mark.asyncio
    async def test_a_failed_send_does_not_end_the_loop(
        self, worker_manager: WorkerManager, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(worker_manager, "heartbeat_interval_s", 0.01)
        worker_manager._tx.send_message.side_effect = ConnectionError("reconnecting")  # type: ignore[union-attr]

        task = asyncio.create_task(worker_manager.orchestrator_heartbeat_loop())
        await asyncio.sleep(0.05)
        still_running = not task.done()
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)

        assert still_running


class TestRelayOfSweepResults:
    @pytest.mark.asyncio
    async def test_a_success_stays_off_the_gui_topic(self, worker_manager: WorkerManager) -> None:
        payload = {
            "event_type": "EventResultSuccess",
            "result_type": worker_events.SweepWorkflowRuntimesResultSuccess.__name__,
            "result": {"result_details": "Released 0 workflow(s) the orchestrator no longer holds open."},
            "response_topic": _WORKER_RESPONSE_TOPIC,
        }

        await worker_manager.relay_worker_result(payload)

        worker_manager._tx.send_message.assert_not_called()  # type: ignore[union-attr]

    @pytest.mark.asyncio
    async def test_a_failure_is_logged_and_stays_off_the_gui_topic(
        self, worker_manager: WorkerManager, caplog: pytest.LogCaptureFixture
    ) -> None:
        payload = {
            "event_type": "EventResultFailure",
            "result_type": worker_events.SweepWorkflowRuntimesResultFailure.__name__,
            "result": {"result_details": "Failed for 1 of 1"},
            "response_topic": _WORKER_RESPONSE_TOPIC,
        }

        with caplog.at_level("WARNING", logger="griptape_nodes"):
            await worker_manager.relay_worker_result(payload)

        worker_manager._tx.send_message.assert_not_called()  # type: ignore[union-attr]
        assert "Failed for 1 of 1" in caplog.text


class TestSweepRequestWire:
    def test_the_open_workflow_ids_survive_the_wire(self) -> None:
        request = worker_events.SweepWorkflowRuntimesRequest(open_workflow_ids=["workflow-a"])

        restored = converters.engine.loads(converters.engine.dumps(request), worker_events.SweepWorkflowRuntimesRequest)

        assert restored.open_workflow_ids == ["workflow-a"]
