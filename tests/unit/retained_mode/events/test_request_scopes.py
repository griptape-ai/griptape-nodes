"""Every request the engine handles has a scope, and no request names its workflow in its own fields."""

from __future__ import annotations

import dataclasses
from typing import TYPE_CHECKING

import griptape_nodes.app.worker_routing
import griptape_nodes.retained_mode.engine  # Imports every event module the engine registers.
from griptape_nodes.retained_mode.events.base_events import RequestPayload
from griptape_nodes.retained_mode.events.payload_registry import PayloadRegistry
from griptape_nodes.retained_mode.request_handlers import RequestScope, handler_scope

if TYPE_CHECKING:
    from griptape_nodes.retained_mode.engine import Engine


def _engine_request_types() -> list[type[RequestPayload]]:
    return [
        payload
        for payload in PayloadRegistry.get_registry().values()
        if isinstance(payload, type)
        and issubclass(payload, RequestPayload)
        and payload.__module__.startswith("griptape_nodes.")
    ]


def test_every_registered_request_has_a_scope(engine: Engine) -> None:
    """A scope is declared by the handler, so a request with a handler can't be dispatched without one."""
    event_manager = engine.event_manager
    registered = event_manager.registered_request_types()

    assert registered
    for request_type in registered:
        assert isinstance(event_manager.scope_for(request_type), RequestScope), request_type.__name__


def test_only_handlers_that_cannot_take_their_workflow_declare_a_scope(engine: Engine) -> None:
    """`scope=` is for a handler that depends on a workflow only through code that reads the binding.

    Everything else declares its scope by its signature, so a new entry here is a decision to review.
    """
    event_manager = engine.event_manager
    declared = sorted(
        request_type.__name__
        for request_type in event_manager.registered_request_types()
        if handler_scope(_unwrapped(event_manager.get_manager_for_request_type(request_type))) is not None
    )

    assert declared == [
        # The new workflow file's sidecar is placed through the library File API, which resolves
        # `{workflow_dir}` against the bound workflow.
        "BranchWorkflowRequest",
        "CreateWorkflowFromTemplateRequest",
        # The library File API resolves the directory's macros against the bound workflow.
        "ListDirectoryRequest",
        "ListDirectorySequencesRequest",
        # Model access is evaluated for a node, and authorization hooks may read its workflow.
        "QueryModelAccessForNodeRequest",
        # Runs user code, which reaches the workflow through the GriptapeNodes facade.
        "RunArbitraryPythonStringRequest",
    ]


def _unwrapped(handler: object) -> object:
    """The handler a RemoteHandler replaced, so a worker's registrations read like the orchestrator's."""
    return getattr(handler, "original", handler)


def test_no_engine_request_names_its_workflow_in_a_field() -> None:
    """A workflow is addressed on the `EventRequest` envelope, never by a field of the request."""
    with_workflow_id = sorted(
        request_type.__name__
        for request_type in _engine_request_types()
        if "workflow_id" in {field.name for field in dataclasses.fields(request_type)}
    )

    assert with_workflow_id == []


def test_worker_routing_requests_are_registered() -> None:
    """The requests defined outside the events package are covered too."""
    assert griptape_nodes.app.worker_routing.DropWorkflowLocalObjectsRequest in _engine_request_types()
