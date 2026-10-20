"""Every request the engine handles has a scope, and no request names its workflow in its own fields."""

from __future__ import annotations

import dataclasses
from typing import TYPE_CHECKING

import griptape_nodes.app.worker_routing
import griptape_nodes.retained_mode.engine  # Imports every event module the engine registers.
from griptape_nodes.retained_mode.events.base_events import RequestPayload
from griptape_nodes.retained_mode.events.payload_registry import PayloadRegistry
from griptape_nodes.retained_mode.request_handlers import RequestScope

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


def test_handlers_that_read_the_bound_workflow_take_it(engine: Engine) -> None:
    """A handler that depends on a workflow only through code that reads the binding takes it and binds it.

    The File API, authorization hooks, and user code read the binding, so these handlers take `workflow`
    and bind it around that code. A new entry here is a decision to review.
    """
    event_manager = engine.event_manager
    scopes = {
        # The library File API places the new workflow file against `{workflow_dir}` of the bound workflow.
        "BranchWorkflowRequest": RequestScope.OPTIONAL_WORKFLOW,
        "CreateWorkflowFromTemplateRequest": RequestScope.OPTIONAL_WORKFLOW,
        # The library File API resolves the directory's macros against the bound workflow.
        "ListDirectoryRequest": RequestScope.OPTIONAL_WORKFLOW,
        "ListDirectorySequencesRequest": RequestScope.OPTIONAL_WORKFLOW,
        # Authorization hooks may read the workflow of the node the model is queried for.
        "QueryModelAccessForNodeRequest": RequestScope.WORKFLOW,
        # Runs user code, which reaches the workflow through the GriptapeNodes facade.
        "RunArbitraryPythonStringRequest": RequestScope.WORKFLOW,
    }
    by_name = {request_type.__name__: request_type for request_type in event_manager.registered_request_types()}

    for name, scope in scopes.items():
        request_type = by_name[name]
        assert event_manager.scope_for(request_type) is scope, name
        assert request_type in event_manager._request_types_taking_workflow, name


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
