"""Test EventManager functionality including sync/async event broadcasting."""

import asyncio
import threading
from dataclasses import dataclass
from unittest.mock import AsyncMock

import pytest

from griptape_nodes.retained_mode.events.app_events import ConfigChanged
from griptape_nodes.retained_mode.events.base_events import (
    ForwardFromWorkerMixin,
    RequestPayload,
    ResultPayloadSuccess,
)
from griptape_nodes.retained_mode.managers.event_manager import EventManager


class TestEventManagerBroadcasting:
    """Test event broadcasting functionality in EventManager."""

    @pytest.mark.asyncio
    async def test_abroadcast_app_event_calls_all_listeners(self) -> None:
        """Test that abroadcast_app_event calls all registered listeners."""
        event_manager = EventManager()

        # Create mock listeners
        listener1 = AsyncMock()
        listener2 = AsyncMock()

        # Register listeners for ConfigChanged event
        event_manager.add_listener_to_app_event(ConfigChanged, listener1)
        event_manager.add_listener_to_app_event(ConfigChanged, listener2)

        # Create and broadcast event
        event = ConfigChanged(key="test_key", old_value="old", new_value="new")
        await event_manager.abroadcast_app_event(event)

        # Verify both listeners were called
        listener1.assert_called_once_with(event)
        listener2.assert_called_once_with(event)

    @pytest.mark.asyncio
    async def test_abroadcast_app_event_with_no_listeners(self) -> None:
        """Test that abroadcast_app_event handles events with no listeners gracefully."""
        event_manager = EventManager()

        # Create event with no registered listeners
        event = ConfigChanged(key="test_key", old_value="old", new_value="new")

        # Should not raise any exceptions
        await event_manager.abroadcast_app_event(event)

    def test_broadcast_app_event_calls_all_listeners(self) -> None:
        """Test that broadcast_app_event (sync) calls all registered listeners."""
        event_manager = EventManager()

        # Create mock listeners (async functions)
        listener1 = AsyncMock()
        listener2 = AsyncMock()

        # Register listeners
        event_manager.add_listener_to_app_event(ConfigChanged, listener1)
        event_manager.add_listener_to_app_event(ConfigChanged, listener2)

        # Create and broadcast event (sync)
        event = ConfigChanged(key="test_key", old_value="old", new_value="new")
        event_manager.broadcast_app_event(event)

        # Verify both listeners were called
        listener1.assert_called_once_with(event)
        listener2.assert_called_once_with(event)

    def test_broadcast_app_event_with_no_listeners(self) -> None:
        """Test that broadcast_app_event handles events with no listeners gracefully."""
        event_manager = EventManager()

        # Create event with no registered listeners
        event = ConfigChanged(key="test_key", old_value="old", new_value="new")

        # Should not raise any exceptions
        event_manager.broadcast_app_event(event)

    @pytest.mark.asyncio
    async def test_abroadcast_app_event_handles_listener_exceptions(self) -> None:
        """Test that abroadcast_app_event raises ExceptionGroup when a listener raises an exception."""
        event_manager = EventManager()

        # Create listeners where one raises an exception
        listener1 = AsyncMock(side_effect=ValueError("Test error"))
        listener2 = AsyncMock()

        event_manager.add_listener_to_app_event(ConfigChanged, listener1)
        event_manager.add_listener_to_app_event(ConfigChanged, listener2)

        event = ConfigChanged(key="test_key", old_value="old", new_value="new")

        # TaskGroup raises ExceptionGroup when a task fails
        with pytest.raises(ExceptionGroup):
            await event_manager.abroadcast_app_event(event)

    @pytest.mark.asyncio
    async def test_abroadcast_app_event_with_mixed_listener_types(self) -> None:
        """Test that abroadcast_app_event works with both sync and async listeners."""
        event_manager = EventManager()

        # Track calls
        calls = []

        # Create async listener
        async def async_listener(event: ConfigChanged) -> None:
            calls.append(("async", event.key))

        # Create sync listener
        def sync_listener(event: ConfigChanged) -> None:
            calls.append(("sync", event.key))

        event_manager.add_listener_to_app_event(ConfigChanged, async_listener)
        event_manager.add_listener_to_app_event(ConfigChanged, sync_listener)

        event = ConfigChanged(key="test_key", old_value="old", new_value="new")
        await event_manager.abroadcast_app_event(event)

        # Verify both listeners were called
        assert len(calls) == 2  # noqa: PLR2004
        assert ("async", "test_key") in calls
        assert ("sync", "test_key") in calls

    def test_remove_listener_from_app_event(self) -> None:
        """Test that listeners can be removed and won't be called after removal."""
        event_manager = EventManager()

        listener = AsyncMock()
        event_manager.add_listener_to_app_event(ConfigChanged, listener)

        # Broadcast event - listener should be called
        event = ConfigChanged(key="test_key", old_value="old", new_value="new")
        event_manager.broadcast_app_event(event)
        listener.assert_called_once()

        # Remove listener and broadcast again
        event_manager.remove_listener_for_app_event(ConfigChanged, listener)
        listener.reset_mock()

        event2 = ConfigChanged(key="test_key2", old_value="old2", new_value="new2")
        event_manager.broadcast_app_event(event2)

        # Listener should not be called after removal
        listener.assert_not_called()

    @pytest.mark.asyncio
    async def test_abroadcast_app_event_preserves_event_data(self) -> None:
        """Test that event data is correctly passed to listeners."""
        event_manager = EventManager()

        received_events = []

        async def listener(event: ConfigChanged) -> None:
            received_events.append(event)

        event_manager.add_listener_to_app_event(ConfigChanged, listener)

        # Create event with specific data
        original_event = ConfigChanged(
            key="workspace_directory",
            old_value="/old/path",
            new_value="/new/path",
        )

        await event_manager.abroadcast_app_event(original_event)

        # Verify listener received the correct event data
        assert len(received_events) == 1
        received = received_events[0]
        assert received.key == "workspace_directory"
        assert received.old_value == "/old/path"
        assert received.new_value == "/new/path"


@dataclass(kw_only=True)
class _ProbeRequest(RequestPayload):
    """Minimal request type used only to exercise dispatch routing in tests."""


@dataclass(kw_only=True)
class _ProbeResult(ResultPayloadSuccess):
    """Minimal success payload paired with _ProbeRequest."""


class TestHandleRequestLoopSafety:
    """`handle_request` must fail loudly when invoked from a running loop with an async target.

    The failure mode replaces the silent side-loop dispatch that caused the
    worker-library-load deadlock documented in issue #4469. Tests cover:

    - An async handler reached from inside a running loop raises with a
      diagnostic that names the request type and points at ahandle_request.
    - A sync handler reached from inside a running loop still works (no async
      boundary means no deadlock hazard).
    - Outside any running loop, an async handler continues to work via
      `asyncio.run` -- preserves the startup/main-thread dispatch path.
    - `ahandle_request` remains the safe async alternative.
    """

    @pytest.mark.asyncio
    async def test_sync_dispatch_from_running_loop_raises_when_handler_is_async(self) -> None:
        event_manager = EventManager()

        async def async_handler(_request: _ProbeRequest) -> _ProbeResult:
            return _ProbeResult(result_details="ok")

        event_manager.assign_manager_to_request_type(_ProbeRequest, async_handler)

        with pytest.raises(RuntimeError) as exc_info:
            event_manager.handle_request(_ProbeRequest())
        message = str(exc_info.value)
        assert "_ProbeRequest" in message
        assert "ahandle_request" in message

    @pytest.mark.asyncio
    async def test_sync_dispatch_from_running_loop_works_when_handler_is_sync(self) -> None:
        event_manager = EventManager()

        def sync_handler(_request: _ProbeRequest) -> _ProbeResult:
            return _ProbeResult(result_details="ok")

        event_manager.assign_manager_to_request_type(_ProbeRequest, sync_handler)

        event = event_manager.handle_request(_ProbeRequest())
        assert event.result.succeeded()

    def test_sync_dispatch_outside_running_loop_drives_async_handler(self) -> None:
        event_manager = EventManager()

        async def async_handler(_request: _ProbeRequest) -> _ProbeResult:
            return _ProbeResult(result_details="ok")

        event_manager.assign_manager_to_request_type(_ProbeRequest, async_handler)

        event = event_manager.handle_request(_ProbeRequest())
        assert event.result.succeeded()

    @pytest.mark.asyncio
    async def test_ahandle_request_is_the_recommended_async_alternative(self) -> None:
        event_manager = EventManager()

        async def async_handler(_request: _ProbeRequest) -> _ProbeResult:
            return _ProbeResult(result_details="ok")

        event_manager.assign_manager_to_request_type(_ProbeRequest, async_handler)

        event = await event_manager.ahandle_request(_ProbeRequest())
        assert event.result.succeeded()


@dataclass(kw_only=True)
class _ForwardableProbeRequest(RequestPayload, ForwardFromWorkerMixin):
    """Minimal forwardable request used to drive the worker-forwarding path in tests."""


@dataclass(kw_only=True)
class _ForwardableProbeResult(ResultPayloadSuccess):
    """Minimal success payload paired with _ForwardableProbeRequest."""


class TestHandleRequestForwardingFromRunningLoop:
    """Forwarding dispatch from a running loop must succeed, not raise.

    When worker forwarding is enabled, `_forward_to_orchestrator` routes onto
    a dedicated WebSocket event loop running on a separate thread. That loop
    does not share primitives with the caller's loop, so blocking the caller
    thread on the resulting future is safe -- the #4469 deadlock shape does
    not apply. This is distinct from the local async-handler case, which
    must still fail fast because dispatching locally would block the caller's
    own loop.
    """

    @pytest.mark.asyncio
    async def test_sync_dispatch_from_running_loop_forwards_via_websocket_loop(self) -> None:
        event_manager = EventManager()

        # Spin up a dedicated loop on another thread to stand in for the websocket loop.
        ws_loop = asyncio.new_event_loop()
        ws_thread = threading.Thread(target=ws_loop.run_forever, daemon=True)
        ws_thread.start()

        captured: dict[str, object] = {}

        async def fake_forward(
            _request: RequestPayload,
            _result_context: object,
        ) -> object:
            # Record which loop actually executed the forward.
            captured["forward_loop"] = asyncio.get_running_loop()
            return _ForwardableProbeResult(result_details="forwarded")

        # Enable the forward branch by configuring just enough state.
        event_manager._worker_forwarding_enabled = True
        event_manager._websocket_event_loop = ws_loop
        event_manager._forward_to_orchestrator = fake_forward  # type: ignore[method-assign]

        try:
            with event_manager.worker_node_execution_scope():
                result = event_manager.handle_request(_ForwardableProbeRequest())
        finally:
            ws_loop.call_soon_threadsafe(ws_loop.stop)
            ws_thread.join(timeout=1.0)
            ws_loop.close()

        assert captured["forward_loop"] is ws_loop
        assert isinstance(result, _ForwardableProbeResult)
        assert "forwarded" in str(result.result_details)


class TestBroadcastAppEventLoopSafety:
    """`broadcast_app_event` uses the same fail-fast guard as handle_request."""

    @pytest.mark.asyncio
    async def test_sync_broadcast_from_running_loop_raises(self) -> None:
        event_manager = EventManager()

        async def async_listener(_event: ConfigChanged) -> None:
            return None

        event_manager.add_listener_to_app_event(ConfigChanged, async_listener)

        event = ConfigChanged(key="k", old_value="a", new_value="b")
        with pytest.raises(RuntimeError) as exc_info:
            event_manager.broadcast_app_event(event)
        message = str(exc_info.value)
        assert "ConfigChanged" in message
        assert "abroadcast_app_event" in message
