"""A worker keeps a namespace per orchestrator workflow, and requests it forwards are addressed to their workflow.

The orchestrator can hold several workflows open, and runs nodes for any of them in a worker. The
worker holds none of the orchestrator's workflows. It binds the namespace it keeps under the
orchestrator's id, so a request a node makes mid-run reaches the workflow that ran it.
"""

from __future__ import annotations

import asyncio
import threading
from dataclasses import dataclass
from typing import Any

import pytest

from griptape_nodes.retained_mode.engine import Engine
from griptape_nodes.retained_mode.events.base_events import (
    EventRequest,
    RequestPayload,
    ResultPayloadSuccess,
)
from griptape_nodes.retained_mode.events.open_workflow_events import (
    ListOpenWorkflowsResultSuccess,
    OpenWorkflowRequest,
    OpenWorkflowResultSuccess,
)
from griptape_nodes.retained_mode.managers.event_manager import ResultContext
from griptape_nodes.retained_mode.request_handlers import RequestScope
from tests.unit.worker.harness import InProcessWorkerHarness


@dataclass(kw_only=True)
class _RunNodeProbe(RequestPayload):
    """Stands in for ExecuteNodeRequest: the worker runs a node, which calls back to the orchestrator."""


@dataclass(kw_only=True)
class _CallbackProbe(RequestPayload):
    """A request a node makes mid-run, addressed to no workflow, which the worker forwards to the orchestrator."""


@dataclass(kw_only=True)
class _ProbeResult(ResultPayloadSuccess):
    pass


class _StubRequestClient:
    """Stands in for the worker's RequestClient, recording the envelope it is asked to send."""

    def __init__(self) -> None:
        self.sent: list[EventRequest] = []

    async def request_to_orchestrator(self, *, event_request: EventRequest, **_kwargs: Any) -> dict[str, Any]:
        self.sent.append(event_request)
        return {
            "event_type": "EventResultSuccess",
            "result_type": ListOpenWorkflowsResultSuccess.__name__,
            "result": {"workflows": [], "result_details": "ok"},
        }


class TestWorkerForwarding:
    @pytest.mark.asyncio
    async def test_a_forwarded_request_reaches_the_workflow_that_ran_the_node(self) -> None:
        orchestrator = Engine()
        worker = Engine()
        worker.library_manager._is_worker = True

        running = orchestrator.handle_request(OpenWorkflowRequest(display_name="Running"))
        other = orchestrator.handle_request(OpenWorkflowRequest(display_name="Other"))
        assert isinstance(running, OpenWorkflowResultSuccess)
        assert isinstance(other, OpenWorkflowResultSuccess)

        harness = InProcessWorkerHarness(orchestrator=orchestrator.event_manager, worker=worker.event_manager)
        seen_by_orchestrator: list[str] = []
        seen_by_worker: list[str] = []
        callback = _CallbackProbe()

        def on_callback(_request: _CallbackProbe) -> _ProbeResult:
            seen_by_orchestrator.append(orchestrator.current_workflow.workflow_id)
            return _ProbeResult(result_details="ok")

        async def run_node(_request: _RunNodeProbe) -> _ProbeResult:
            seen_by_worker.append(worker.current_workflow.workflow_id)
            with worker.event_manager.node_execution_scope():
                await worker.ahandle_request(callback)
            return _ProbeResult(result_details="ok")

        orchestrator.event_manager.assign_manager_to_request_type(
            _CallbackProbe, on_callback, scope=RequestScope.WORKFLOW
        )
        worker.event_manager.assign_manager_to_request_type(_RunNodeProbe, run_node, scope=RequestScope.WORKFLOW)
        harness.install_remote_handler(_CallbackProbe)

        await harness.start()
        try:
            await harness.route_to_worker(EventRequest(request=_RunNodeProbe(), workflow_id=running.workflow_id))
        finally:
            await harness.stop()

        assert seen_by_worker == [running.workflow_id]
        assert seen_by_orchestrator == [running.workflow_id]

    @pytest.mark.asyncio
    async def test_a_worker_keeps_a_namespace_per_workflow(self) -> None:
        worker = Engine()
        worker.library_manager._is_worker = True
        seen: list[object] = []

        def run_node(_request: _RunNodeProbe) -> _ProbeResult:
            seen.append(worker.current_workflow)
            return _ProbeResult(result_details="ok")

        worker.event_manager.assign_manager_to_request_type(_RunNodeProbe, run_node, scope=RequestScope.WORKFLOW)

        await worker.ahandle_request(_RunNodeProbe(), workflow_id="workflow-a")
        await worker.ahandle_request(_RunNodeProbe(), workflow_id="workflow-b")
        await worker.ahandle_request(_RunNodeProbe(), workflow_id="workflow-a")

        assert [runtime.workflow_id for runtime in worker.workflow_runtimes] == ["workflow-a", "workflow-b"]
        assert seen[0] is seen[2]
        assert seen[0] is not seen[1]


class TestForwardToOrchestratorEnvelope:
    @pytest.mark.asyncio
    async def test_the_envelope_carries_the_workflow_the_worker_is_bound_to(self) -> None:
        worker = Engine()
        worker.library_manager._is_worker = True
        client = _StubRequestClient()
        broker_loop = asyncio.new_event_loop()
        thread = threading.Thread(target=broker_loop.run_forever, daemon=True)
        thread.start()
        worker.event_manager.configure_worker_forwarding(
            request_client=client,  # type: ignore[arg-type]
            orchestrator_request_topic="orchestrator/request",
            worker_response_topic="worker/response",
            websocket_event_loop=broker_loop,
        )
        runtime = worker.open_workflow_runtime("workflow-a")
        request = _CallbackProbe()
        try:
            with worker.bind_workflow(runtime):
                await worker.event_manager.forward_to_orchestrator(request, ResultContext())
        finally:
            broker_loop.call_soon_threadsafe(broker_loop.stop)
            thread.join(timeout=5)
            broker_loop.close()

        assert [sent.workflow_id for sent in client.sent] == ["workflow-a"]
        assert client.sent[0].request is request
