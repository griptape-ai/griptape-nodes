"""Tests for the worker-reach-into-orchestrator strict-mode tripwire.

RemoteHandler is the single chokepoint where a worker-side ``aprocess``
reaches into orchestrator-owned state. When it forwards a request back
to the orchestrator while a strict-mode scope is active, it records a
``worker-reach-into-orchestrator`` violation. Outside of node execution
(bootstrap, LOAD_PROBE) the tripwire does not fire because the
RemoteHandler delegates to the original handler before reaching the
violation path; outside any strict-mode scope, ``report_violation`` is a
no-op and the handler still forwards without crashing.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import pytest

from griptape_nodes.app.worker_routing import RemoteHandler
from griptape_nodes.common.strict_mode import (
    StrictModeScopeKind,
    StrictModeSeverity,
    strict_mode_scope,
)
from griptape_nodes.retained_mode.events.base_events import (
    EventResultSuccess,
    RequestPayload,
    ResultPayloadSuccess,
)
from griptape_nodes.retained_mode.managers.event_manager import EventManager

if TYPE_CHECKING:
    from griptape_nodes.retained_mode.managers.event_manager import ResultContext


@dataclass(kw_only=True)
class _ProbeRequest(RequestPayload):
    """Minimal request used to exercise RemoteHandler's tripwire."""

    marker: str


@dataclass(kw_only=True)
class _ProbeResult(ResultPayloadSuccess):
    """Success payload paired with _ProbeRequest."""

    seen_by: str


def _make_handler_with_fake_forward(event_manager: EventManager) -> RemoteHandler:
    async def original(_request: _ProbeRequest) -> _ProbeResult:
        return _ProbeResult(seen_by="local", result_details="local")

    async def fake_forward(
        request: RequestPayload,
        result_context: ResultContext,  # noqa: ARG001
    ) -> EventResultSuccess:
        return EventResultSuccess(
            request=request,
            result=_ProbeResult(seen_by="orchestrator", result_details="forwarded"),
        )

    event_manager.forward_to_orchestrator = fake_forward  # type: ignore[method-assign]
    return RemoteHandler(original=original, event_manager=event_manager)


class TestWorkerReachIntoOrchestrator:
    """The tripwire records one violation per forwarded request while in scope."""

    @pytest.mark.asyncio
    async def test_in_scope_in_node_execution_records_violation(self) -> None:
        event_manager = EventManager()
        handler = _make_handler_with_fake_forward(event_manager)

        with (
            strict_mode_scope(
                kind=StrictModeScopeKind.RUNTIME_EXECUTE,
                subject="node-1",
                library_name="libA",
                is_worker=True,
            ) as scope,
            event_manager.worker_node_execution_scope(),
        ):
            result = await handler(_ProbeRequest(marker="m1"))

        assert isinstance(result, _ProbeResult)
        assert result.seen_by == "orchestrator"
        assert len(scope.violations) == 1
        violation = scope.violations[0]
        assert violation.rule_id == "worker-reach-into-orchestrator"
        assert violation.severity is StrictModeSeverity.WARNING
        assert violation.subject == "node-1"
        assert violation.library_name == "libA"
        assert "_ProbeRequest" in violation.message

    @pytest.mark.asyncio
    async def test_in_scope_out_of_node_execution_does_not_record(self) -> None:
        event_manager = EventManager()
        local_calls: list[_ProbeRequest] = []

        async def original(request: _ProbeRequest) -> _ProbeResult:
            local_calls.append(request)
            return _ProbeResult(seen_by="local", result_details="local")

        handler = RemoteHandler(original=original, event_manager=event_manager)

        with strict_mode_scope(
            kind=StrictModeScopeKind.LOAD_PROBE,
            subject="MyClass",
            library_name="libA",
            is_worker=True,
        ) as scope:
            result = await handler(_ProbeRequest(marker="m2"))

        assert isinstance(result, _ProbeResult)
        assert result.seen_by == "local"
        assert len(local_calls) == 1
        assert scope.violations == []

    @pytest.mark.asyncio
    async def test_no_scope_forwards_without_crashing(self) -> None:
        event_manager = EventManager()
        handler = _make_handler_with_fake_forward(event_manager)

        with event_manager.worker_node_execution_scope():
            result = await handler(_ProbeRequest(marker="m3"))

        assert isinstance(result, _ProbeResult)
        assert result.seen_by == "orchestrator"
