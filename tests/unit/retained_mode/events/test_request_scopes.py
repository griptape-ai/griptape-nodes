"""Every request the engine handles has a scope, and no request names its workflow in its own fields."""

from __future__ import annotations

import dataclasses
from typing import TYPE_CHECKING

import griptape_nodes.app.worker_routing
import griptape_nodes.retained_mode.engine  # Imports every event module the engine registers.
from griptape_nodes.retained_mode.events.base_events import RequestPayload
from griptape_nodes.retained_mode.events.payload_registry import PayloadRegistry
from griptape_nodes.retained_mode.request_handlers import RequestScope, handler_scope, handler_takes_workflow

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


def test_every_workflow_handler_declares_its_workflow_where_it_is_defined(engine: Engine) -> None:
    """A handler that acts on a workflow says so itself, by its signature or by @handles(scope=...).

    So reading a handler is enough to know whether it depends on a workflow, and none inherits that
    from a class default.
    """
    event_manager = engine.event_manager
    undeclared = []
    for request_type in event_manager.registered_request_types():
        if event_manager.scope_for(request_type) is RequestScope.HOST:
            continue
        handler = event_manager.get_manager_for_request_type(request_type)
        assert handler is not None
        if handler_takes_workflow(handler):
            continue
        if handler_scope(getattr(handler, "original", handler)) is None:
            undeclared.append(request_type.__name__)

    assert undeclared == []


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
