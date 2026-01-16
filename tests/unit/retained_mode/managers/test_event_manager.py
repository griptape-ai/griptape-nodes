"""Test EventManager functionality including sync/async event broadcasting."""

from unittest.mock import AsyncMock

import pytest

from griptape_nodes.retained_mode.events.app_events import ConfigChanged
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
