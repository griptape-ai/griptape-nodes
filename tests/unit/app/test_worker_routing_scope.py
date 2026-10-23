"""Tests for when RemoteHandler forwards versus answers locally.

RemoteHandler is the single chokepoint where a worker services a request whose authoritative state
lives on the orchestrator. What decides its behavior is one thing: whether the worker is inside a
node-execution scope. Inside, it forwards; outside (bootstrap, library load, node construction) it
delegates to the handler it replaced, so a node's ``__init__`` can still call ``add_parameter``.
"""

from __future__ import annotations

import asyncio
import threading
from dataclasses import dataclass
from typing import TYPE_CHECKING

import pytest

from griptape_nodes.app.worker_routing import (
    LOCAL_ONLY_REQUEST_TYPES,
    RemoteHandler,
    register_remote_handlers,
)
from griptape_nodes.retained_mode.events.base_events import (
    EventResultSuccess,
    RequestPayload,
    ResultPayloadSuccess,
)
from griptape_nodes.retained_mode.events.connection_events import (
    DeleteConnectionRequest,
    DeleteConnectionResultFailure,
    ListConnectionsForNodeRequest,
    ListConnectionsForNodeResultSuccess,
)
from griptape_nodes.retained_mode.events.parameter_events import (
    AddParameterToNodeRequest,
    AddParameterToNodeResultFailure,
    AlterParameterDetailsRequest,
    AlterParameterDetailsResultFailure,
    SetParameterValueRequest,
    SetParameterValueResultFailure,
)
from griptape_nodes.retained_mode.managers.event_manager import EventManager

if TYPE_CHECKING:
    from griptape_nodes.retained_mode.managers.event_manager import ResultContext


def _forwarded_sample() -> tuple[type, ...]:
    """A few representative types that forward (i.e. are not local-only)."""
    from griptape_nodes.retained_mode.events.node_events import CreateNodeRequest
    from griptape_nodes.retained_mode.events.parameter_events import AddParameterToNodeRequest

    sample = (CreateNodeRequest, AddParameterToNodeRequest)
    assert not set(sample) & LOCAL_ONLY_REQUEST_TYPES
    return sample


@dataclass(kw_only=True)
class _ProbeRequest(RequestPayload):
    """Minimal request used to exercise RemoteHandler's routing decision."""

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


class TestRemoteHandlerRouting:
    """Node-execution scope is the whole routing decision."""

    @pytest.mark.asyncio
    async def test_in_node_execution_forwards(self) -> None:
        event_manager = EventManager()
        handler = _make_handler_with_fake_forward(event_manager)

        with event_manager.node_execution_scope():
            result = await handler(_ProbeRequest(marker="m1"))

        assert isinstance(result, _ProbeResult)
        assert result.seen_by == "orchestrator"

    @pytest.mark.asyncio
    async def test_out_of_node_execution_delegates_locally(self) -> None:
        """Bootstrap and library load must keep working against the replaced handler."""
        event_manager = EventManager()
        local_calls: list[_ProbeRequest] = []

        async def original(request: _ProbeRequest) -> _ProbeResult:
            local_calls.append(request)
            return _ProbeResult(seen_by="local", result_details="local")

        handler = RemoteHandler(original=original, event_manager=event_manager)

        result = await handler(_ProbeRequest(marker="m2"))

        assert isinstance(result, _ProbeResult)
        assert result.seen_by == "local"
        assert len(local_calls) == 1

    @pytest.mark.asyncio
    async def test_forwards_during_hydration_not_only_aprocess(self) -> None:
        """The gate is deliberately wider than ``aprocess``.

        ``node_execution_scope`` is opened by ``_hydrate_and_run_node_inner`` around BOTH
        hydration and aprocess, so a request issued from ``before/after_value_set`` forwards too.
        No ``aprocess_scope()`` is entered here; only the refcount is active.
        """
        event_manager = EventManager()
        handler = _make_handler_with_fake_forward(event_manager)

        with event_manager.node_execution_scope():
            result = await handler(_ProbeRequest(marker="hydrate"))

        assert isinstance(result, _ProbeResult)
        assert result.seen_by == "orchestrator"

    @pytest.mark.asyncio
    async def test_every_call_forwards_independently(self) -> None:
        event_manager = EventManager()
        forwarded: list[RequestPayload] = []

        async def original(_request: _ProbeRequest) -> _ProbeResult:
            return _ProbeResult(seen_by="local", result_details="local")

        async def fake_forward(
            request: RequestPayload,
            result_context: ResultContext,  # noqa: ARG001
        ) -> EventResultSuccess:
            forwarded.append(request)
            return EventResultSuccess(
                request=request,
                result=_ProbeResult(seen_by="orchestrator", result_details="forwarded"),
            )

        event_manager.forward_to_orchestrator = fake_forward  # type: ignore[method-assign]
        handler = RemoteHandler(original=original, event_manager=event_manager)

        with event_manager.node_execution_scope():
            await handler(_ProbeRequest(marker="first"))
            await handler(_ProbeRequest(marker="second"))

        expected_forwards = 2
        assert len(forwarded) == expected_forwards

    @pytest.mark.asyncio
    async def test_real_forwarded_type_goes_through_the_swap_and_shim(self) -> None:
        """End-to-end: ``register_remote_handlers`` swaps a real forwarded type and it forwards.

        Locks in the ``LOCAL_ONLY_REQUEST_TYPES`` <-> ``RemoteHandler`` integration. This stays
        green only while ``ListConnectionsForNodeRequest`` is still NOT local-only -- connections
        are authoritative orchestrator state, so it must keep forwarding.
        """
        event_manager = EventManager()
        forwarded_calls: list[RequestPayload] = []

        async def fake_forward(
            request: RequestPayload,
            result_context: ResultContext,  # noqa: ARG001
        ) -> EventResultSuccess:
            forwarded_calls.append(request)
            return EventResultSuccess(
                request=request,
                result=ListConnectionsForNodeResultSuccess(
                    incoming_connections=[],
                    outgoing_connections=[],
                    result_details="forwarded",
                ),
            )

        event_manager.forward_to_orchestrator = fake_forward  # type: ignore[method-assign]

        # register_remote_handlers swaps whatever is registered, so the type this test
        # asserts on has to be registered first. Stub it plus a couple of representatives.
        for request_type in (ListConnectionsForNodeRequest, *_forwarded_sample()):

            async def stub(_request: RequestPayload) -> ResultPayloadSuccess:
                return ListConnectionsForNodeResultSuccess(
                    incoming_connections=[],
                    outgoing_connections=[],
                    result_details="local",
                )

            event_manager.assign_manager_to_request_type(request_type, stub)

        register_remote_handlers(event_manager)

        installed = event_manager.get_manager_for_request_type(ListConnectionsForNodeRequest)
        assert isinstance(installed, RemoteHandler)

        with event_manager.node_execution_scope():
            result = await installed(ListConnectionsForNodeRequest(node_name="some-node"))

        assert isinstance(result, ListConnectionsForNodeResultSuccess)
        assert len(forwarded_calls) == 1
        assert isinstance(forwarded_calls[0], ListConnectionsForNodeRequest)


REBUILT = "Load Component"


def _drop_own_wire() -> DeleteConnectionRequest:
    """What Load Pipeline Component sends from its value hook when its component changes."""
    return DeleteConnectionRequest(
        source_node_name=REBUILT,
        source_parameter_name="component_output",
        target_node_name="Pipeline Builder",
        target_parameter_name="component_vae",
    )


def _handler_recording_forwards(event_manager: EventManager, forwarded: list[RequestPayload]) -> RemoteHandler:
    async def original(_request: RequestPayload) -> ResultPayloadSuccess:
        return ListConnectionsForNodeResultSuccess(
            incoming_connections=[], outgoing_connections=[], result_details="local"
        )

    async def fake_forward(
        request: RequestPayload,
        result_context: ResultContext,  # noqa: ARG001
    ) -> EventResultSuccess:
        forwarded.append(request)
        return EventResultSuccess(
            request=request,
            result=ListConnectionsForNodeResultSuccess(
                incoming_connections=[], outgoing_connections=[], result_details="forwarded"
            ),
        )

    event_manager.forward_to_orchestrator = fake_forward  # type: ignore[method-assign]
    return RemoteHandler(original=original, event_manager=event_manager)


class TestEditsToTheNodeBeingRebuilt:
    """A worker rebuilding a node must not repeat that node's own edits on the orchestrator.

    Hydration replays each value through the node's hooks. A hook that drops or rebuilds its own wires
    when its value changes did that on the orchestrator when the user made the change, so a forwarded
    replay deletes real connections from a copy that has none of its own.
    """

    @pytest.mark.asyncio
    async def test_an_edit_to_the_rebuilt_node_is_refused(self) -> None:
        event_manager = EventManager()
        forwarded: list[RequestPayload] = []
        handler = _handler_recording_forwards(event_manager, forwarded)

        with event_manager.node_execution_scope(), event_manager.hydration_scope(REBUILT):
            delete_result = await handler(_drop_own_wire())
            add_result = await handler(AddParameterToNodeRequest(node_name=REBUILT, parent_container_name="items"))
            set_result = await handler(SetParameterValueRequest(parameter_name="status", node_name=REBUILT, value="x"))

        assert isinstance(delete_result, DeleteConnectionResultFailure)
        assert isinstance(add_result, AddParameterToNodeResultFailure)
        assert isinstance(set_result, SetParameterValueResultFailure)
        assert forwarded == []

    @pytest.mark.asyncio
    async def test_an_edit_that_leaves_its_node_to_the_current_context_is_refused(self) -> None:
        """On the orchestrator the current context is some other node, never the one being rebuilt here."""
        event_manager = EventManager()
        forwarded: list[RequestPayload] = []
        handler = _handler_recording_forwards(event_manager, forwarded)

        with event_manager.node_execution_scope(), event_manager.hydration_scope(REBUILT):
            result = await handler(AlterParameterDetailsRequest(parameter_name="component_output", type="Vae"))

        assert isinstance(result, AlterParameterDetailsResultFailure)
        assert forwarded == []

    @pytest.mark.asyncio
    async def test_an_edit_to_another_node_still_forwards(self) -> None:
        event_manager = EventManager()
        forwarded: list[RequestPayload] = []
        handler = _handler_recording_forwards(event_manager, forwarded)

        with event_manager.node_execution_scope(), event_manager.hydration_scope(REBUILT):
            await handler(SetParameterValueRequest(parameter_name="status", node_name="Tracker", value="x"))

        assert len(forwarded) == 1

    @pytest.mark.asyncio
    async def test_a_read_about_the_rebuilt_node_still_forwards(self) -> None:
        """Hooks still need the orchestrator's answers while hydrating, such as whether a list is connected."""
        event_manager = EventManager()
        forwarded: list[RequestPayload] = []
        handler = _handler_recording_forwards(event_manager, forwarded)

        with event_manager.node_execution_scope(), event_manager.hydration_scope(REBUILT):
            await handler(ListConnectionsForNodeRequest(node_name=REBUILT))

        assert len(forwarded) == 1

    @pytest.mark.asyncio
    async def test_an_edit_still_forwards_while_the_node_runs(self) -> None:
        """Once hydration is over, an edit is the node's own and belongs to the orchestrator."""
        event_manager = EventManager()
        forwarded: list[RequestPayload] = []
        handler = _handler_recording_forwards(event_manager, forwarded)

        with event_manager.node_execution_scope():
            await handler(_drop_own_wire())

        assert len(forwarded) == 1

    @pytest.mark.asyncio
    async def test_a_sync_hook_is_refused_although_the_handler_runs_on_another_loop(self) -> None:
        """Value hooks call `handle_request` synchronously, which runs the handler on the websocket loop.

        The node being rebuilt is a context variable, so this holds only while that hop carries the
        caller's context with it.
        """
        event_manager = EventManager()
        forwarded: list[RequestPayload] = []
        handler = _handler_recording_forwards(event_manager, forwarded)
        event_manager.assign_manager_to_request_type(DeleteConnectionRequest, handler)

        ws_loop = asyncio.new_event_loop()
        ws_thread = threading.Thread(target=ws_loop.run_forever, daemon=True)
        ws_thread.start()
        event_manager._websocket_event_loop = ws_loop
        try:
            with event_manager.node_execution_scope(), event_manager.hydration_scope(REBUILT):
                result = event_manager.handle_request(_drop_own_wire())
        finally:
            ws_loop.call_soon_threadsafe(ws_loop.stop)
            ws_thread.join(timeout=1.0)
            ws_loop.close()

        assert isinstance(result.result, DeleteConnectionResultFailure)
        assert forwarded == []
