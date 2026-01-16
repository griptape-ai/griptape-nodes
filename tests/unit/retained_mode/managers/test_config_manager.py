import os
import platform
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from griptape_nodes.retained_mode.events.app_events import ConfigChanged
from griptape_nodes.retained_mode.managers.config_manager import ConfigManager
from griptape_nodes.retained_mode.managers.event_manager import EventManager


@pytest.mark.skipif(
    platform.system() == "Windows", reason="xdg_base_dirs cannot find XDG_CONFIG_HOME on Windows on GitHub Actions"
)
class TestConfigManager:
    """Test ConfigManager functionality including environment variable loading."""

    def test_load_config_from_env_vars_empty(self) -> None:
        """Test that no GTN_CONFIG_ env vars returns empty dict."""
        with patch.dict(os.environ, {}, clear=True):
            manager = ConfigManager()
            env_config = manager._load_config_from_env_vars()
            assert env_config == {}

    def test_load_config_from_env_vars_single(self) -> None:
        """Test loading a single GTN_CONFIG_ environment variable."""
        with patch.dict(os.environ, {"GTN_CONFIG_FOO": "bar"}, clear=True):
            manager = ConfigManager()
            env_config = manager._load_config_from_env_vars()
            assert env_config == {"foo": "bar"}

    def test_load_config_from_env_vars_multiple(self) -> None:
        """Test loading multiple GTN_CONFIG_ environment variables."""
        with patch.dict(
            os.environ,
            {
                "GTN_CONFIG_FOO": "bar",
                "GTN_CONFIG_STORAGE_BACKEND": "gtc",
                "GTN_CONFIG_LOG_LEVEL": "DEBUG",
                "REGULAR_ENV_VAR": "ignored",
            },
            clear=True,
        ):
            manager = ConfigManager()
            env_config = manager._load_config_from_env_vars()
            assert env_config == {"foo": "bar", "storage_backend": "gtc", "log_level": "DEBUG"}

    def test_load_config_from_env_vars_key_conversion(self) -> None:
        """Test that GTN_CONFIG_ prefix is removed and keys are lowercased."""
        with patch.dict(
            os.environ,
            {
                "GTN_CONFIG_SOME_LONG_KEY_NAME": "value1",
                "GTN_CONFIG_API_KEY": "value2",
                "GTN_CONFIG_123_NUMERIC": "value3",
            },
            clear=True,
        ):
            manager = ConfigManager()
            env_config = manager._load_config_from_env_vars()
            assert env_config == {"some_long_key_name": "value1", "api_key": "value2", "123_numeric": "value3"}

    def test_config_integration_with_env_vars(self) -> None:
        """Test that environment variables are integrated into merged config with highest priority."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Set up a temporary workspace
            workspace_path = Path(temp_dir)

            # Create a workspace config file with a value
            workspace_config_path = workspace_path / "griptape_nodes_config.json"
            workspace_config_path.write_text('{"log_level": "ERROR"}')

            # Set environment variable that should override the workspace config
            with patch.dict(
                os.environ, {"GTN_CONFIG_LOG_LEVEL": "DEBUG", "GTN_CONFIG_STORAGE_BACKEND": "gtc"}, clear=True
            ):
                manager = ConfigManager()
                # Set the workspace path to our temp directory
                manager.workspace_path = workspace_path
                manager.load_configs()

                # Environment variable should override workspace config
                assert manager.get_config_value("log_level") == "DEBUG"
                assert manager.get_config_value("storage_backend") == "gtc"

    def test_non_gtn_config_env_vars_ignored(self) -> None:
        """Test that environment variables not starting with GTN_CONFIG_ are ignored."""
        with patch.dict(
            os.environ,
            {
                "CONFIG_FOO": "should_be_ignored",
                "GTN_FOO": "should_be_ignored",
                "GTN_CONFIG_BAR": "should_be_loaded",
                "SOME_OTHER_VAR": "should_be_ignored",
            },
            clear=True,
        ):
            manager = ConfigManager()
            env_config = manager._load_config_from_env_vars()
            assert env_config == {"bar": "should_be_loaded"}

    def test_workspace_path_reassigned_after_env_var_override(self) -> None:
        """Test that workspace path is reassigned after environment variable config is loaded."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create initial workspace directory
            initial_workspace = Path(temp_dir) / "initial_workspace"
            initial_workspace.mkdir()

            # Create override workspace directory
            override_workspace = Path(temp_dir) / "override_workspace"
            override_workspace.mkdir()

            # Set environment variable to override workspace directory
            with patch.dict(os.environ, {"GTN_CONFIG_WORKSPACE_DIRECTORY": str(override_workspace)}, clear=True):
                manager = ConfigManager()
                # Initially set workspace to the initial directory
                manager.workspace_path = initial_workspace

                # Load configs which should reassign workspace path from env var
                manager.load_configs()

                # Verify workspace path was reassigned to the env var value
                assert manager.workspace_path == override_workspace.resolve()
                assert manager.get_config_value("workspace_directory") == str(override_workspace)

    def test_coerce_to_type_bool_from_string(self) -> None:
        """Test that _coerce_to_type correctly converts string values to bool."""
        manager = ConfigManager()

        # Truthy string values
        assert manager._coerce_to_type("true", bool) is True
        assert manager._coerce_to_type("True", bool) is True
        assert manager._coerce_to_type("TRUE", bool) is True
        assert manager._coerce_to_type("yes", bool) is True
        assert manager._coerce_to_type("1", bool) is True
        assert manager._coerce_to_type("anything", bool) is True

        # Falsy string values
        assert manager._coerce_to_type("false", bool) is False
        assert manager._coerce_to_type("False", bool) is False
        assert manager._coerce_to_type("FALSE", bool) is False
        assert manager._coerce_to_type("no", bool) is False
        assert manager._coerce_to_type("No", bool) is False
        assert manager._coerce_to_type("0", bool) is False
        assert manager._coerce_to_type("", bool) is False

    def test_coerce_to_type_bool_from_bool(self) -> None:
        """Test that _coerce_to_type returns bool values unchanged."""
        manager = ConfigManager()

        assert manager._coerce_to_type(True, bool) is True
        assert manager._coerce_to_type(False, bool) is False

    def test_coerce_to_type_int(self) -> None:
        """Test that _coerce_to_type correctly converts string values to int."""
        manager = ConfigManager()

        assert manager._coerce_to_type("42", int) == int("42")
        assert manager._coerce_to_type("0", int) == int("0")
        assert manager._coerce_to_type("-10", int) == int("-10")

    def test_coerce_to_type_float(self) -> None:
        """Test that _coerce_to_type correctly converts string values to float."""
        manager = ConfigManager()

        assert manager._coerce_to_type("3.14", float) == float("3.14")
        assert manager._coerce_to_type("0.0", float) == float("0.0")
        assert manager._coerce_to_type("-2.5", float) == float("-2.5")
        assert manager._coerce_to_type("42", float) == float("42")

    def test_coerce_to_type_str(self) -> None:
        """Test that _coerce_to_type returns string values unchanged."""
        manager = ConfigManager()

        assert manager._coerce_to_type("hello", str) == "hello"
        assert manager._coerce_to_type("", str) == ""

    def test_get_config_value_with_cast_type_bool(self) -> None:
        """Test get_config_value with cast_type=bool for env var string values."""
        with patch.dict(os.environ, {"GTN_CONFIG_ENABLE_FEATURE": "false"}, clear=True):
            manager = ConfigManager()
            manager.load_configs()

            # Without cast_type, returns the string "false" (truthy)
            value_no_cast = manager.get_config_value("enable_feature")
            assert value_no_cast == "false"
            assert bool(value_no_cast) is True  # String "false" is truthy!

            # With cast_type=bool, returns False
            value_with_cast = manager.get_config_value("enable_feature", cast_type=bool)
            assert value_with_cast is False

    def test_get_config_value_with_cast_type_int(self) -> None:
        """Test get_config_value with cast_type=int for env var string values."""
        with patch.dict(os.environ, {"GTN_CONFIG_MAX_COUNT": "100"}, clear=True):
            manager = ConfigManager()
            manager.load_configs()

            # Without cast_type, returns the string "100"
            value_no_cast = manager.get_config_value("max_count")
            assert value_no_cast == "100"

            # With cast_type=int, returns 100
            value_with_cast = manager.get_config_value("max_count", cast_type=int)
            assert value_with_cast == int("100")
            assert isinstance(value_with_cast, int)


@pytest.mark.skipif(
    platform.system() == "Windows", reason="xdg_base_dirs cannot find XDG_CONFIG_HOME on Windows on GitHub Actions"
)
class TestConfigManagerEventEmission:
    """Test that ConfigManager emits ConfigChanged events when config values change."""

    def test_set_config_value_emits_config_changed_event(self) -> None:
        """Test that set_config_value emits a ConfigChanged event."""
        event_manager = EventManager()
        config_manager = ConfigManager(event_manager=event_manager)

        received_events = []

        def listener(event: ConfigChanged) -> None:
            received_events.append(event)

        event_manager.add_listener_to_app_event(ConfigChanged, listener)

        # Set a config value
        config_manager.set_config_value(key="test_key", value="new_value")

        # Verify event was emitted
        assert len(received_events) == 1
        event = received_events[0]
        assert event.key == "test_key"
        assert event.new_value == "new_value"
        assert event.category is None

    def test_set_config_value_captures_old_value(self) -> None:
        """Test that ConfigChanged event contains the old value before the change."""
        event_manager = EventManager()
        config_manager = ConfigManager(event_manager=event_manager)

        received_events = []

        def listener(event: ConfigChanged) -> None:
            received_events.append(event)

        event_manager.add_listener_to_app_event(ConfigChanged, listener)

        # Set initial value
        config_manager.set_config_value(key="test_key", value="initial_value")

        # Update to new value
        config_manager.set_config_value(key="test_key", value="updated_value")

        # Verify the second event has the correct old_value
        assert len(received_events) == 2  # noqa: PLR2004
        second_event = received_events[1]
        assert second_event.key == "test_key"
        assert second_event.old_value == "initial_value"
        assert second_event.new_value == "updated_value"

    def test_set_config_category_emits_config_changed_event(self) -> None:
        """Test that set_config_category emits a ConfigChanged event."""
        event_manager = EventManager()
        config_manager = ConfigManager(event_manager=event_manager)

        received_events = []

        def listener(event: ConfigChanged) -> None:
            received_events.append(event)

        event_manager.add_listener_to_app_event(ConfigChanged, listener)

        # Set a config category
        from griptape_nodes.retained_mode.events.config_events import SetConfigCategoryRequest

        request = SetConfigCategoryRequest(category="test_category", contents={"key1": "value1", "key2": "value2"})
        config_manager.on_handle_set_config_category_request(request)

        # Verify event was emitted
        assert len(received_events) == 1
        event = received_events[0]
        assert event.key == "test_category"
        assert event.new_value == {"key1": "value1", "key2": "value2"}
        # Category field is None when setting a specific category (only set for full config replacement)
        assert event.category is None

    def test_set_config_value_no_event_when_event_manager_is_none(self) -> None:
        """Test that no event is emitted when event_manager is None."""
        config_manager = ConfigManager(event_manager=None)

        # This should not raise any exceptions
        config_manager.set_config_value(key="test_key", value="new_value")

    def test_set_config_category_full_config_replacement_emits_event(self) -> None:
        """Test that setting the entire config (category=None) emits an event."""
        event_manager = EventManager()
        config_manager = ConfigManager(event_manager=event_manager)

        received_events = []

        def listener(event: ConfigChanged) -> None:
            received_events.append(event)

        event_manager.add_listener_to_app_event(ConfigChanged, listener)

        # Set entire config
        from griptape_nodes.retained_mode.events.config_events import SetConfigCategoryRequest

        full_config = {"workspace_directory": "/test/path", "log_level": "DEBUG"}
        request = SetConfigCategoryRequest(category=None, contents=full_config)
        config_manager.on_handle_set_config_category_request(request)

        # Verify event was emitted
        assert len(received_events) == 1
        event = received_events[0]
        assert event.key == ""
        assert event.new_value == full_config
        assert event.category is None

    def test_multiple_config_changes_emit_multiple_events(self) -> None:
        """Test that multiple config changes emit separate events."""
        event_manager = EventManager()
        config_manager = ConfigManager(event_manager=event_manager)

        received_events = []

        def listener(event: ConfigChanged) -> None:
            received_events.append(event)

        event_manager.add_listener_to_app_event(ConfigChanged, listener)

        # Make multiple changes
        config_manager.set_config_value(key="key1", value="value1")
        config_manager.set_config_value(key="key2", value="value2")
        config_manager.set_config_value(key="key3", value="value3")

        # Verify all events were emitted
        assert len(received_events) == 3  # noqa: PLR2004
        assert received_events[0].key == "key1"
        assert received_events[1].key == "key2"
        assert received_events[2].key == "key3"

    def test_config_changed_event_includes_nested_key(self) -> None:
        """Test that ConfigChanged event correctly handles nested config keys."""
        event_manager = EventManager()
        config_manager = ConfigManager(event_manager=event_manager)

        received_events = []

        def listener(event: ConfigChanged) -> None:
            received_events.append(event)

        event_manager.add_listener_to_app_event(ConfigChanged, listener)

        # Set a nested config value
        config_manager.set_config_value(
            key="app_events.on_app_initialization_complete.libraries_to_register", value=["/path/to/lib"]
        )

        # Verify event has the full nested key
        assert len(received_events) == 1
        event = received_events[0]
        assert event.key == "app_events.on_app_initialization_complete.libraries_to_register"
        assert event.new_value == ["/path/to/lib"]
