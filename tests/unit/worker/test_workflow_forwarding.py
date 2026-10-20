"""A worker keeps a namespace per orchestrator workflow, and requests it forwards are addressed to their workflow.

The orchestrator can hold several workflows open, and runs nodes for any of them in a worker. The
worker holds none of the orchestrator's workflows. It binds the namespace it keeps under the
orchestrator's id, so a request a node makes mid-run reaches the workflow that ran it.
"""

from __future__ import annotations

import asyncio
import threading
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import pytest

from griptape_nodes.retained_mode.engine import Engine
from griptape_nodes.retained_mode.events.base_events import (
    EventRequest,
    RequestPayload,
    ResultPayloadSuccess,
)
from griptape_nodes.retained_mode.events.execution_events import ExecuteNodeRequest
from griptape_nodes.retained_mode.events.open_workflow_events import (
    ListOpenWorkflowsRequest,
    ListOpenWorkflowsResultSuccess,
    OpenWorkflowRequest,
    OpenWorkflowResultSuccess,
)
from griptape_nodes.retained_mode.events.worker_events import DropWorkflowLocalObjectsRequest
from griptape_nodes.retained_mode.managers.event_manager import ResultContext
from griptape_nodes.retained_mode.request_handlers import RequestScope
from griptape_nodes.retained_mode.runtime.binding import NO_WORKFLOW, WorkflowNotOpenError
from griptape_nodes.retained_mode.runtime.workflow_runtime import RuntimeKind
from tests.unit.worker.harness import InProcessWorkerHarness

if TYPE_CHECKING:
    from griptape_nodes.retained_mode.runtime.workflow_runtime import WorkflowRuntime


@dataclass(kw_only=True)
class _RunNodeProbe(ExecuteNodeRequest):
    """Stands in for the node execution the worker runs, which calls back to the orchestrator.

    An ExecuteNodeRequest because that is the request a worker makes a namespace for.
    """


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

        def on_callback(_request: _CallbackProbe, workflow: WorkflowRuntime) -> _ProbeResult:  # noqa: ARG001
            seen_by_orchestrator.append(orchestrator.current_workflow.workflow_id)
            return _ProbeResult(result_details="ok")

        async def run_node(_request: _RunNodeProbe, workflow: WorkflowRuntime) -> _ProbeResult:  # noqa: ARG001
            seen_by_worker.append(worker.current_workflow.workflow_id)
            with worker.event_manager.node_execution_scope():
                await worker.ahandle_request(callback)
            return _ProbeResult(result_details="ok")

        orchestrator.event_manager.assign_manager_to_request_type(_CallbackProbe, on_callback)
        worker.event_manager.assign_manager_to_request_type(_RunNodeProbe, run_node)
        harness.install_remote_handler(_CallbackProbe)

        await harness.start()
        try:
            await harness.route_to_worker(
                EventRequest(request=_RunNodeProbe(node_name="probe"), workflow_id=running.workflow_id)
            )
        finally:
            await harness.stop()

        assert seen_by_worker == [running.workflow_id]
        assert seen_by_orchestrator == [running.workflow_id]

    @pytest.mark.asyncio
    async def test_a_worker_keeps_a_namespace_per_workflow(self) -> None:
        worker = Engine()
        worker.library_manager._is_worker = True
        seen: list[object] = []

        def run_node(_request: _RunNodeProbe, workflow: WorkflowRuntime) -> _ProbeResult:  # noqa: ARG001
            seen.append(worker.current_workflow)
            return _ProbeResult(result_details="ok")

        worker.event_manager.assign_manager_to_request_type(_RunNodeProbe, run_node)

        await worker.ahandle_request(_RunNodeProbe(node_name="probe"), workflow_id="workflow-a")
        await worker.ahandle_request(_RunNodeProbe(node_name="probe"), workflow_id="workflow-b")
        await worker.ahandle_request(_RunNodeProbe(node_name="probe"), workflow_id="workflow-a")

        assert [runtime.workflow_id for runtime in worker.worker_namespaces] == ["workflow-a", "workflow-b"]
        assert worker.workflow_runtimes == []
        assert seen[0] is seen[2]
        assert seen[0] is not seen[1]


class TestWorkerRuntimeCreation:
    """A worker makes a namespace only for the requests that end with a drop from the orchestrator."""

    @pytest.mark.asyncio
    async def test_a_request_naming_an_unknown_workflow_fails_and_makes_no_namespace(self) -> None:
        worker = Engine()
        worker.library_manager._is_worker = True

        def callback(_request: _CallbackProbe, workflow: WorkflowRuntime) -> _ProbeResult:  # noqa: ARG001
            return _ProbeResult(result_details="ok")

        worker.event_manager.assign_manager_to_request_type(_CallbackProbe, callback)

        with pytest.raises(WorkflowNotOpenError, match="_CallbackProbe"):
            worker.runtime_for_request(_CallbackProbe(), RequestScope.WORKFLOW, "gone")
        result = await worker.ahandle_request(_CallbackProbe(), workflow_id="gone")

        assert result.failed()
        assert worker.workflow_runtimes == []
        assert worker.worker_namespaces == []

    @pytest.mark.asyncio
    async def test_a_request_naming_a_held_namespace_runs_in_it(self) -> None:
        worker = Engine()
        worker.library_manager._is_worker = True
        held = worker.worker_namespace("workflow-a")
        seen: list[object] = []

        def callback(_request: _CallbackProbe, workflow: WorkflowRuntime) -> _ProbeResult:  # noqa: ARG001
            seen.append(worker.current_workflow)
            return _ProbeResult(result_details="ok")

        worker.event_manager.assign_manager_to_request_type(_CallbackProbe, callback)

        result = await worker.ahandle_request(_CallbackProbe(), workflow_id="workflow-a")

        assert result.succeeded()
        assert seen == [held]

    def test_node_execution_makes_a_namespace_for_an_unknown_workflow(self) -> None:
        worker = Engine()
        worker.library_manager._is_worker = True

        runtime = worker.runtime_for_request(ExecuteNodeRequest(node_name="node"), RequestScope.WORKFLOW, "workflow-a")

        assert [held.workflow_id for held in worker.worker_namespaces] == ["workflow-a"]
        assert runtime is worker.worker_namespaces[0]
        assert worker.worker_namespaces[0].kind is RuntimeKind.WORKER_NAMESPACE
        assert worker.workflow_runtimes == []

    def test_a_drop_makes_a_namespace_for_the_handler_to_release(self) -> None:
        worker = Engine()
        worker.library_manager._is_worker = True

        runtime = worker.runtime_for_request(DropWorkflowLocalObjectsRequest(), RequestScope.WORKFLOW, "workflow-a")

        assert runtime is worker.worker_namespace("workflow-a")
        assert worker.find_workflow_runtime("workflow-a") is None

    @pytest.mark.asyncio
    async def test_a_namespace_is_not_an_open_workflow(self) -> None:
        worker = Engine()
        worker.library_manager._is_worker = True
        worker.worker_namespace("workflow-a")

        result = await worker.ahandle_request(ListOpenWorkflowsRequest())

        assert isinstance(result, ListOpenWorkflowsResultSuccess)
        assert result.workflows == []
        assert worker.describe_open_workflows()["open_workflows"] == []

    def test_a_worker_fails_an_unaddressed_workflow_request_instead_of_opening_a_workflow(self) -> None:
        worker = Engine()
        worker.library_manager._is_worker = True
        worker.worker_namespace("workflow-a")

        with pytest.raises(WorkflowNotOpenError, match="in a worker"):
            worker.runtime_for_request(_CallbackProbe(), RequestScope.WORKFLOW, None)

        assert worker.workflow_runtimes == []

    def test_a_worker_runs_an_unaddressed_optional_request_with_no_workflow(self) -> None:
        worker = Engine()
        worker.library_manager._is_worker = True
        worker.worker_namespace("workflow-a")

        assert worker.runtime_for_request(_CallbackProbe(), RequestScope.OPTIONAL_WORKFLOW, None) is NO_WORKFLOW
        assert worker.workflow_runtimes == []

    def test_an_unbound_read_on_a_worker_fails_instead_of_opening_a_workflow(self) -> None:
        worker = Engine()
        worker.library_manager._is_worker = True
        worker.worker_namespace("workflow-a")

        with pytest.raises(WorkflowNotOpenError, match="in a worker"):
            _ = worker.current_workflow

        assert worker.workflow_runtimes == []

    def test_the_orchestrator_fails_a_request_naming_an_unknown_workflow(self) -> None:
        orchestrator = Engine()

        with pytest.raises(WorkflowNotOpenError, match="isn't open anymore"):
            orchestrator.runtime_for_request(ExecuteNodeRequest(node_name="node"), RequestScope.WORKFLOW, "gone")


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
        runtime = worker.worker_namespace("workflow-a")
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
