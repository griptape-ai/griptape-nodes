"""Tests for LogHandlerEvent."""

from griptape_nodes.retained_mode.events.logger_events import LogHandlerEvent


class TestLogHandlerEvent:
    def test_node_name_defaults_to_none(self) -> None:
        event = LogHandlerEvent(message="hello", levelname="INFO", created=1234567890.0)

        assert event.node_name is None

    def test_node_name_can_be_set(self) -> None:
        event = LogHandlerEvent(message="hello", levelname="INFO", created=1234567890.0, node_name="MyNode")

        assert event.node_name == "MyNode"

    def test_required_fields_are_stored(self) -> None:
        timestamp = 1234567890.0
        event = LogHandlerEvent(message="test message", levelname="WARNING", created=timestamp)

        assert event.message == "test message"
        assert event.levelname == "WARNING"
        assert event.created == timestamp
