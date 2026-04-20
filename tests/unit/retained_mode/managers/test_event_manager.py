"""Test EventManager functionality including sync/async event broadcasting."""

from unittest.mock import AsyncMock

import pytest

from griptape_nodes.retained_mode.events.app_events import AppConnectionEstablished
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

        # Register listeners for AppConnectionEstablished event
        event_manager.add_listener_to_app_event(AppConnectionEstablished, listener1)
        event_manager.add_listener_to_app_event(AppConnectionEstablished, listener2)

        # Create and broadcast event
        event = AppConnectionEstablished()
        await event_manager.abroadcast_app_event(event)

        # Verify both listeners were called
        listener1.assert_called_once_with(event)
        listener2.assert_called_once_with(event)

    @pytest.mark.asyncio
    async def test_abroadcast_app_event_with_no_listeners(self) -> None:
        """Test that abroadcast_app_event handles events with no listeners gracefully."""
        event_manager = EventManager()

        # Create event with no registered listeners
        event = AppConnectionEstablished()

        # Should not raise any exceptions
        await event_manager.abroadcast_app_event(event)

    def test_broadcast_app_event_calls_all_listeners(self) -> None:
        """Test that broadcast_app_event (sync) calls all registered listeners."""
        event_manager = EventManager()

        # Create mock listeners (async functions)
        listener1 = AsyncMock()
        listener2 = AsyncMock()

        # Register listeners
        event_manager.add_listener_to_app_event(AppConnectionEstablished, listener1)
        event_manager.add_listener_to_app_event(AppConnectionEstablished, listener2)

        # Create and broadcast event (sync)
        event = AppConnectionEstablished()
        event_manager.broadcast_app_event(event)

        # Verify both listeners were called
        listener1.assert_called_once_with(event)
        listener2.assert_called_once_with(event)

    def test_broadcast_app_event_with_no_listeners(self) -> None:
        """Test that broadcast_app_event handles events with no listeners gracefully."""
        event_manager = EventManager()

        # Create event with no registered listeners
        event = AppConnectionEstablished()

        # Should not raise any exceptions
        event_manager.broadcast_app_event(event)

    @pytest.mark.asyncio
    async def test_abroadcast_app_event_handles_listener_exceptions(self) -> None:
        """Test that abroadcast_app_event raises ExceptionGroup when a listener raises an exception."""
        event_manager = EventManager()

        # Create listeners where one raises an exception
        listener1 = AsyncMock(side_effect=ValueError("Test error"))
        listener2 = AsyncMock()

        event_manager.add_listener_to_app_event(AppConnectionEstablished, listener1)
        event_manager.add_listener_to_app_event(AppConnectionEstablished, listener2)

        event = AppConnectionEstablished()

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
        async def async_listener(event: AppConnectionEstablished) -> None:  # noqa: ARG001
            calls.append("async")

        # Create sync listener
        def sync_listener(event: AppConnectionEstablished) -> None:  # noqa: ARG001
            calls.append("sync")

        event_manager.add_listener_to_app_event(AppConnectionEstablished, async_listener)
        event_manager.add_listener_to_app_event(AppConnectionEstablished, sync_listener)

        event = AppConnectionEstablished()
        await event_manager.abroadcast_app_event(event)

        # Verify both listeners were called
        assert len(calls) == 2  # noqa: PLR2004
        assert "async" in calls
        assert "sync" in calls

    def test_remove_listener_from_app_event(self) -> None:
        """Test that listeners can be removed and won't be called after removal."""
        event_manager = EventManager()

        listener = AsyncMock()
        event_manager.add_listener_to_app_event(AppConnectionEstablished, listener)

        # Broadcast event - listener should be called
        event = AppConnectionEstablished()
        event_manager.broadcast_app_event(event)
        listener.assert_called_once()

        # Remove listener and broadcast again
        event_manager.remove_listener_for_app_event(AppConnectionEstablished, listener)
        listener.reset_mock()

        event2 = AppConnectionEstablished()
        event_manager.broadcast_app_event(event2)

        # Listener should not be called after removal
        listener.assert_not_called()

    @pytest.mark.asyncio
    async def test_abroadcast_app_event_preserves_event_identity(self) -> None:
        """Test that the exact event object is passed to listeners."""
        event_manager = EventManager()

        received_events = []

        async def listener(event: AppConnectionEstablished) -> None:
            received_events.append(event)

        event_manager.add_listener_to_app_event(AppConnectionEstablished, listener)

        original_event = AppConnectionEstablished()
        await event_manager.abroadcast_app_event(original_event)

        # Verify listener received the exact event object
        assert len(received_events) == 1
        assert received_events[0] is original_event
