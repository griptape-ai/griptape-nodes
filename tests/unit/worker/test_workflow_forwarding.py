"""Requests a worker forwards while running a node act on the workflow that ran it.

The orchestrator can hold several workflows open, and the user can switch to another while a node
runs in a worker. The worker doesn't hold the orchestrator's workflows, so it must carry the id of the
workflow it is running for onto everything it sends back.
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from griptape_nodes.retained_mode.engine import Engine
from griptape_nodes.retained_mode.events.base_events import EventRequest, RequestPayload, ResultPayloadSuccess
from griptape_nodes.retained_mode.events.open_workflow_events import OpenWorkflowRequest, OpenWorkflowResultSuccess
from tests.unit.worker.harness import InProcessWorkerHarness


@dataclass(kw_only=True)
class _RunNodeProbe(RequestPayload):
    """Stands in for ExecuteNodeRequest: the worker runs a node, which calls back to the orchestrator."""


@dataclass(kw_only=True)
class _CallbackProbe(RequestPayload):
    """A request a node makes mid-run, which the worker forwards to the orchestrator."""


@dataclass(kw_only=True)
class _ProbeResult(ResultPayloadSuccess):
    workflow_id: str | None = None


class TestWorkerForwarding:
    @pytest.mark.asyncio
    async def test_a_forwarded_request_reaches_the_workflow_that_ran_the_node(self) -> None:
        orchestrator = Engine()
        worker = Engine()
        worker.library_manager._is_worker = True

        running = orchestrator.handle_request(OpenWorkflowRequest(display_name="Running"))
        on_screen = orchestrator.handle_request(OpenWorkflowRequest(display_name="On screen"))
        assert isinstance(running, OpenWorkflowResultSuccess)
        assert isinstance(on_screen, OpenWorkflowResultSuccess)

        harness = InProcessWorkerHarness(orchestrator=orchestrator.event_manager, worker=worker.event_manager)
        seen_by_orchestrator: list[str] = []

        def on_callback(_request: _CallbackProbe) -> _ProbeResult:
            seen_by_orchestrator.append(orchestrator.workflow_binding.workflow_id)
            return _ProbeResult(result_details="ok")

        async def run_node(_request: _RunNodeProbe) -> _ProbeResult:
            with worker.event_manager.node_execution_scope():
                await worker.ahandle_request(_CallbackProbe())
            return _ProbeResult(result_details="ok")

        orchestrator.event_manager.assign_manager_to_request_type(_CallbackProbe, on_callback)
        worker.event_manager.assign_manager_to_request_type(_RunNodeProbe, run_node)
        harness.install_remote_handler(_CallbackProbe)

        await harness.start()
        try:
            # The orchestrator names the workflow on the requests it sends, as dispatch does.
            await harness.route_to_worker(EventRequest(request=_RunNodeProbe(workflow_id=running.workflow_id)))
        finally:
            await harness.stop()

        assert seen_by_orchestrator == [running.workflow_id]
        assert orchestrator.active_workflow_runtime.workflow_id == on_screen.workflow_id
