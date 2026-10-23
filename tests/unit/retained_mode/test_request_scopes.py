"""Dispatch hands a handler the workflow its scope takes, from the request envelope's workflow id."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

import pytest

from griptape_nodes.app.worker_routing import RemoteHandler
from griptape_nodes.retained_mode.events.base_events import (
    EventResultSuccess,
    RequestPayload,
    ResultPayload,
    ResultPayloadSuccess,
)
from griptape_nodes.retained_mode.events.generic_events import GenericResultFailure
from griptape_nodes.retained_mode.request_handlers import RequestScope
from tests.workflow_context import push_unsaved_workflow

if TYPE_CHECKING:
    from griptape_nodes.retained_mode.engine import Engine
    from griptape_nodes.retained_mode.managers.event_manager import ResultContext
    from griptape_nodes.retained_mode.runtime.workflow_runtime import WorkflowRuntime

NOT_OPEN_ID = "0000000000000000000000000000dead"


@dataclass(kw_only=True)
class _ScopeProbeRequest(RequestPayload):
    pass


@dataclass(kw_only=True)
class _ScopeProbeResult(ResultPayloadSuccess):
    workflow: WorkflowRuntime | None = None


class _Calls:
    """Records what each probe handler was called with."""

    def __init__(self) -> None:
        self.workflows: list[WorkflowRuntime | None] = []
        self.calls = 0

    def workflow_handler(self, request: _ScopeProbeRequest, workflow: WorkflowRuntime) -> ResultPayload:  # noqa: ARG002
        self.workflows.append(workflow)
        return _ScopeProbeResult(workflow=workflow, result_details="ran")

    async def optional_handler(
        self,
        request: _ScopeProbeRequest,  # noqa: ARG002
        workflow: WorkflowRuntime | None = None,
    ) -> ResultPayload:
        self.workflows.append(workflow)
        return _ScopeProbeResult(workflow=workflow, result_details="ran")

    def unscoped_handler(self, request: _ScopeProbeRequest) -> ResultPayload:  # noqa: ARG002
        self.calls += 1
        return _ScopeProbeResult(result_details="ran")


@pytest.fixture
def calls() -> _Calls:
    """A fresh record of probe handler calls."""
    return _Calls()


def _register(engine: Engine, calls: _Calls, scope: RequestScope | None) -> None:
    event_manager = engine.event_manager
    match scope:
        case RequestScope.WORKFLOW:
            event_manager.assign_manager_to_request_type(_ScopeProbeRequest, calls.workflow_handler, scope=scope)
        case RequestScope.OPTIONAL_WORKFLOW:
            event_manager.assign_manager_to_request_type(_ScopeProbeRequest, calls.optional_handler, scope=scope)
        case _:
            event_manager.assign_manager_to_request_type(_ScopeProbeRequest, calls.unscoped_handler, scope=scope)


class TestWorkflowScopes:
    @pytest.mark.parametrize("scope", [RequestScope.WORKFLOW, RequestScope.OPTIONAL_WORKFLOW])
    @pytest.mark.asyncio
    async def test_the_envelope_id_names_the_workflow_passed(
        self, engine: Engine, calls: _Calls, scope: RequestScope
    ) -> None:
        workflow = push_unsaved_workflow(engine)
        _register(engine, calls, scope)

        result_event = await engine.event_manager.ahandle_request(
            _ScopeProbeRequest(), workflow_id=workflow.workflow_id
        )

        assert result_event.succeeded()
        assert calls.workflows == [engine.open_workflows.get(workflow.workflow_id)]

    @pytest.mark.parametrize("scope", [RequestScope.WORKFLOW, RequestScope.OPTIONAL_WORKFLOW])
    @pytest.mark.asyncio
    async def test_an_envelope_id_that_is_not_open_fails(
        self, engine: Engine, calls: _Calls, scope: RequestScope
    ) -> None:
        push_unsaved_workflow(engine)
        _register(engine, calls, scope)

        result_event = await engine.event_manager.ahandle_request(_ScopeProbeRequest(), workflow_id=NOT_OPEN_ID)

        assert isinstance(result_event.result, GenericResultFailure)
        assert str(result_event.result.result_details) == (
            f"Attempted to run _ScopeProbeRequest in workflow '{NOT_OPEN_ID}'. Failed because that workflow isn't open."
        )
        assert result_event.workflow_id == NOT_OPEN_ID
        assert calls.workflows == []

    @pytest.mark.parametrize("scope", [RequestScope.WORKFLOW, RequestScope.OPTIONAL_WORKFLOW])
    @pytest.mark.asyncio
    async def test_no_envelope_id_gets_the_open_workflow(
        self, engine: Engine, calls: _Calls, scope: RequestScope
    ) -> None:
        workflow = push_unsaved_workflow(engine)
        _register(engine, calls, scope)

        result_event = await engine.event_manager.ahandle_request(_ScopeProbeRequest())

        assert result_event.succeeded()
        assert calls.workflows == [engine.open_workflows.get(workflow.workflow_id)]

    @pytest.mark.asyncio
    async def test_workflow_scope_with_no_envelope_id_and_none_open_fails(self, engine: Engine, calls: _Calls) -> None:
        _register(engine, calls, RequestScope.WORKFLOW)

        result_event = await engine.event_manager.ahandle_request(_ScopeProbeRequest())

        assert isinstance(result_event.result, GenericResultFailure)
        assert "names no workflow and none is open" in str(result_event.result.result_details)
        assert calls.workflows == []

    @pytest.mark.asyncio
    async def test_optional_workflow_scope_with_no_envelope_id_and_none_open_gets_none(
        self, engine: Engine, calls: _Calls
    ) -> None:
        _register(engine, calls, RequestScope.OPTIONAL_WORKFLOW)

        result_event = await engine.event_manager.ahandle_request(_ScopeProbeRequest())

        assert result_event.succeeded()
        assert calls.workflows == [None]

    def test_the_sync_path_passes_the_workflow_too(self, engine: Engine, calls: _Calls) -> None:
        workflow = push_unsaved_workflow(engine)
        _register(engine, calls, RequestScope.OPTIONAL_WORKFLOW)

        result_event = engine.event_manager.handle_request(_ScopeProbeRequest(), workflow_id=workflow.workflow_id)

        assert result_event.succeeded()
        assert calls.workflows == [engine.open_workflows.get(workflow.workflow_id)]

    def test_the_sync_path_fails_an_envelope_id_that_is_not_open(self, engine: Engine, calls: _Calls) -> None:
        _register(engine, calls, RequestScope.WORKFLOW)

        result_event = engine.event_manager.handle_request(_ScopeProbeRequest(), workflow_id=NOT_OPEN_ID)

        assert isinstance(result_event.result, GenericResultFailure)
        assert calls.workflows == []


class TestHostAndUndeclaredScopes:
    @pytest.mark.parametrize("scope", [RequestScope.HOST, None])
    @pytest.mark.asyncio
    async def test_an_envelope_id_that_is_not_open_is_never_rejected(
        self, engine: Engine, calls: _Calls, scope: RequestScope | None
    ) -> None:
        _register(engine, calls, scope)

        result_event = await engine.event_manager.ahandle_request(_ScopeProbeRequest(), workflow_id=NOT_OPEN_ID)

        assert result_event.succeeded()
        assert result_event.workflow_id == NOT_OPEN_ID
        assert calls.calls == 1

    @pytest.mark.asyncio
    async def test_host_scope_ignores_the_envelope_id_silently(
        self, engine: Engine, calls: _Calls, caplog: pytest.LogCaptureFixture
    ) -> None:
        _register(engine, calls, RequestScope.HOST)

        with caplog.at_level(logging.DEBUG, logger="griptape_nodes"):
            await engine.event_manager.ahandle_request(_ScopeProbeRequest(), workflow_id=NOT_OPEN_ID)

        assert not [record for record in caplog.records if NOT_OPEN_ID in record.getMessage()]

    @pytest.mark.asyncio
    async def test_an_undeclared_scope_logs_an_id_other_than_the_open_workflow(
        self, engine: Engine, calls: _Calls, caplog: pytest.LogCaptureFixture
    ) -> None:
        push_unsaved_workflow(engine)
        _register(engine, calls, None)

        with caplog.at_level(logging.DEBUG, logger="griptape_nodes"):
            await engine.event_manager.ahandle_request(_ScopeProbeRequest(), workflow_id=NOT_OPEN_ID)

        mismatches = [record for record in caplog.records if NOT_OPEN_ID in record.getMessage()]
        assert [record.levelno for record in mismatches] == [logging.DEBUG]


class TestForwardedRequests:
    """On a worker, which opens no workflow, a forwarded request is resolved where it is forwarded to."""

    @pytest.mark.asyncio
    async def test_a_workflow_request_forwarded_from_node_code_does_not_fail_at_dispatch(
        self, engine: Engine, calls: _Calls
    ) -> None:
        event_manager = engine.event_manager
        _register(engine, calls, RequestScope.WORKFLOW)
        forwarded: list[RequestPayload] = []

        async def fake_forward(request: RequestPayload, result_context: ResultContext) -> EventResultSuccess:  # noqa: ARG001
            forwarded.append(request)
            return EventResultSuccess(request=request, result=_ScopeProbeResult(result_details="forwarded"))

        event_manager.forward_to_orchestrator = fake_forward  # type: ignore[method-assign]
        original = event_manager.get_manager_for_request_type(_ScopeProbeRequest)
        event_manager.replace_manager_for_request_type(
            _ScopeProbeRequest, RemoteHandler(original=original, event_manager=event_manager)
        )

        with event_manager.node_execution_scope():
            result_event = await event_manager.ahandle_request(_ScopeProbeRequest())

        assert result_event.succeeded()
        assert len(forwarded) == 1
        assert calls.workflows == []

    @pytest.mark.asyncio
    async def test_outside_node_execution_it_takes_the_local_path_and_fails_at_dispatch(
        self, engine: Engine, calls: _Calls
    ) -> None:
        event_manager = engine.event_manager
        _register(engine, calls, RequestScope.WORKFLOW)
        original = event_manager.get_manager_for_request_type(_ScopeProbeRequest)
        event_manager.replace_manager_for_request_type(
            _ScopeProbeRequest, RemoteHandler(original=original, event_manager=event_manager)
        )

        result_event = await event_manager.ahandle_request(_ScopeProbeRequest())

        assert isinstance(result_event.result, GenericResultFailure)
        assert "names no workflow" in str(result_event.result.result_details)
        assert calls.workflows == []

    @pytest.mark.asyncio
    async def test_on_its_local_path_the_wrapper_passes_the_workflow_through(
        self, engine: Engine, calls: _Calls
    ) -> None:
        event_manager = engine.event_manager
        workflow = push_unsaved_workflow(engine)
        _register(engine, calls, RequestScope.WORKFLOW)
        original = event_manager.get_manager_for_request_type(_ScopeProbeRequest)
        event_manager.replace_manager_for_request_type(
            _ScopeProbeRequest, RemoteHandler(original=original, event_manager=event_manager)
        )

        result_event = await event_manager.ahandle_request(_ScopeProbeRequest(), workflow_id=workflow.workflow_id)

        assert result_event.succeeded()
        assert calls.workflows == [engine.open_workflows.get(workflow.workflow_id)]


class TestNestedRequests:
    """A runtime's requests name that runtime's workflow on their envelope."""

    @pytest.mark.asyncio
    async def test_a_runtime_addresses_its_requests_to_its_workflow(self, engine: Engine, calls: _Calls) -> None:
        workflow = engine.open_workflows.get(push_unsaved_workflow(engine).workflow_id)
        _register(engine, calls, RequestScope.WORKFLOW)

        sync_result = workflow.handle_request(_ScopeProbeRequest())
        async_result = await workflow.ahandle_request(_ScopeProbeRequest())

        assert sync_result.succeeded()
        assert async_result.succeeded()
        assert calls.workflows == [workflow, workflow]

    @pytest.mark.asyncio
    async def test_a_closed_runtime_does_not_reach_the_open_workflow(self, engine: Engine, calls: _Calls) -> None:
        """Its requests name its own workflow, so they never fall through to whichever one is open."""
        closed = engine.open_workflows.get(push_unsaved_workflow(engine).workflow_id)
        await engine.close_workflow_state(closed)
        push_unsaved_workflow(engine)
        _register(engine, calls, RequestScope.WORKFLOW)

        result = await closed.ahandle_request(_ScopeProbeRequest())

        assert isinstance(result, GenericResultFailure)
        assert f"in workflow '{closed.workflow_id}'" in str(result.result_details)
        assert calls.workflows == []
