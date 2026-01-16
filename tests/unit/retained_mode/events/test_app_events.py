"""Test app event payloads including ConfigChanged."""

from griptape_nodes.retained_mode.events.app_events import ConfigChanged


class TestConfigChangedEvent:
    """Test ConfigChanged event payload."""

    def test_config_changed_event_creation(self) -> None:
        """Test that ConfigChanged event can be created with required fields."""
        event = ConfigChanged(key="test_key", old_value="old", new_value="new")

        assert event.key == "test_key"
        assert event.old_value == "old"
        assert event.new_value == "new"
        assert event.category is None

    def test_config_changed_event_with_category(self) -> None:
        """Test ConfigChanged event with category field."""
        event = ConfigChanged(key="test_key", old_value="old", new_value="new", category="storage")

        assert event.key == "test_key"
        assert event.old_value == "old"
        assert event.new_value == "new"
        assert event.category == "storage"

    def test_config_changed_event_with_none_values(self) -> None:
        """Test ConfigChanged event with None values."""
        event = ConfigChanged(key="test_key", old_value=None, new_value="new")

        assert event.key == "test_key"
        assert event.old_value is None
        assert event.new_value == "new"

    def test_config_changed_event_with_complex_values(self) -> None:
        """Test ConfigChanged event with complex values (dicts, lists)."""
        old_value = {"nested": {"key": "value1"}}
        new_value = {"nested": {"key": "value2"}}

        event = ConfigChanged(key="complex_key", old_value=old_value, new_value=new_value)

        assert event.key == "complex_key"
        assert event.old_value == old_value
        assert event.new_value == new_value

    def test_config_changed_event_with_list_values(self) -> None:
        """Test ConfigChanged event with list values."""
        old_value = ["/path/1", "/path/2"]
        new_value = ["/path/1", "/path/2", "/path/3"]

        event = ConfigChanged(key="libraries_to_register", old_value=old_value, new_value=new_value)

        assert event.key == "libraries_to_register"
        assert event.old_value == old_value
        assert event.new_value == new_value
        assert len(event.new_value) == 3  # noqa: PLR2004

    def test_config_changed_event_key_cannot_be_none(self) -> None:
        """Test that ConfigChanged event requires a key (cannot be None)."""
        # This should work - key is provided
        event = ConfigChanged(key="test_key", old_value="old", new_value="new")
        assert event.key == "test_key"

    def test_config_changed_event_with_empty_key(self) -> None:
        """Test ConfigChanged event with empty string key (for full config replacement)."""
        event = ConfigChanged(key="", old_value={}, new_value={"foo": "bar"})

        assert event.key == ""
        assert event.old_value == {}
        assert event.new_value == {"foo": "bar"}

    def test_config_changed_event_with_nested_key_path(self) -> None:
        """Test ConfigChanged event with nested dot-notation key path."""
        event = ConfigChanged(
            key="app_events.on_app_initialization_complete.libraries_to_register",
            old_value=["/old/path"],
            new_value=["/new/path"],
        )

        assert event.key == "app_events.on_app_initialization_complete.libraries_to_register"
        assert "." in event.key  # Contains nested path separator

    def test_config_changed_event_preserves_value_types(self) -> None:
        """Test that ConfigChanged event preserves the types of old_value and new_value."""
        # Test with different types
        test_cases = [
            ("string_key", "old_str", "new_str"),
            ("int_key", 42, 100),
            ("bool_key", True, False),
            ("float_key", 3.14, 2.71),
            ("list_key", [1, 2, 3], [4, 5, 6]),
            ("dict_key", {"a": 1}, {"b": 2}),
        ]

        for key, old, new in test_cases:
            event = ConfigChanged(key=key, old_value=old, new_value=new)
            assert event.old_value == old
            assert event.new_value == new
            assert type(event.old_value) == type(old)  # noqa: E721
            assert type(event.new_value) == type(new)  # noqa: E721

    def test_config_changed_event_with_same_old_and_new_values(self) -> None:
        """Test ConfigChanged event when old and new values are the same."""
        # The event should still be created even if values are the same
        # (the caller decides whether to emit based on value changes)
        event = ConfigChanged(key="test_key", old_value="same", new_value="same")

        assert event.key == "test_key"
        assert event.old_value == event.new_value
        assert event.old_value == "same"
