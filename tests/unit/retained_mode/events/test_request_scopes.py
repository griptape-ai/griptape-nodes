"""Every request the engine defines says whether it acts on the host or on one open workflow."""

from __future__ import annotations

import griptape_nodes.app.worker_routing
import griptape_nodes.retained_mode.engine  # Imports every event module the engine registers.
from griptape_nodes.retained_mode.events.base_events import HostRequest, RequestPayload, WorkflowRequest
from griptape_nodes.retained_mode.events.payload_registry import PayloadRegistry


def _engine_request_types() -> list[type[RequestPayload]]:
    return [
        payload
        for payload in PayloadRegistry.get_registry().values()
        if isinstance(payload, type)
        and issubclass(payload, RequestPayload)
        and payload.__module__.startswith("griptape_nodes.")
    ]


def test_every_engine_request_declares_its_scope() -> None:
    """A request that declares neither is dispatched as a host request, which may not be what it means."""
    unscoped = sorted(
        request_type.__name__
        for request_type in _engine_request_types()
        if not issubclass(request_type, (HostRequest, WorkflowRequest))
    )

    assert unscoped == []


def test_only_workflow_requests_carry_a_workflow_id() -> None:
    """A host request names no workflow, so a stale id on one can't make it fail."""
    host_with_id = sorted(
        request_type.__name__
        for request_type in _engine_request_types()
        if issubclass(request_type, HostRequest) and "workflow_id" in request_type.__dataclass_fields__
    )

    assert host_with_id == []


def test_worker_routing_requests_are_registered() -> None:
    """The requests defined outside the events package are covered too."""
    assert griptape_nodes.app.worker_routing.DropWorkflowLocalObjectsRequest in _engine_request_types()
