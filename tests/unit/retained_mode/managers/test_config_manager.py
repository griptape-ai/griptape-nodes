import json
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
            # Set up a temporary project directory with a project-adjacent config
            project_dir = Path(temp_dir)
            project_config_path = project_dir / "griptape_nodes_config.json"
            project_config_path.write_text('{"log_level": "ERROR"}')

            # Set environment variable that should override the project config
            with patch.dict(
                os.environ, {"GTN_CONFIG_LOG_LEVEL": "DEBUG", "GTN_CONFIG_STORAGE_BACKEND": "gtc"}, clear=True
            ):
                manager = ConfigManager()
                manager.load_project_config(project_dir)

                # Environment variable should override project config
                assert manager.get_config_value("log_level") == "DEBUG"
                assert manager.get_config_value("storage_backend") == "gtc"

    def test_load_project_config_sets_project_config_layer(self) -> None:
        """Test that load_project_config reads project-adjacent config and merges it."""
        with tempfile.TemporaryDirectory() as temp_dir:
            project_dir = Path(temp_dir)
            project_config_path = project_dir / "griptape_nodes_config.json"
            project_config_path.write_text('{"log_level": "ERROR"}')

            with patch.dict(os.environ, {}, clear=True):
                manager = ConfigManager()
                # Before loading project config, log_level is default
                assert manager.get_config_value("log_level") != "ERROR"

                manager.load_project_config(project_dir)

                # After loading, project config value takes effect
                assert manager.get_config_value("log_level") == "ERROR"
                assert manager.project_config == {"log_level": "ERROR"}

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

    def test_load_workspace_config_sets_workspace_layer(self) -> None:
        """Test that load_workspace_config reads workspace config and merges it above project config."""
        with tempfile.TemporaryDirectory() as temp_dir:
            project_dir = Path(temp_dir) / "project"
            project_dir.mkdir()
            workspace_dir = Path(temp_dir) / "workspace"
            workspace_dir.mkdir()

            (project_dir / "griptape_nodes_config.json").write_text('{"log_level": "ERROR"}')
            (workspace_dir / "griptape_nodes_config.json").write_text('{"log_level": "DEBUG"}')

            with patch.dict(os.environ, {}, clear=True):
                manager = ConfigManager()
                manager.load_project_config(project_dir)
                assert manager.get_config_value("log_level") == "ERROR"

                manager.load_workspace_config(workspace_dir)
                # Workspace config overrides project-adjacent config
                assert manager.get_config_value("log_level") == "DEBUG"
                assert manager.workspace_config == {"log_level": "DEBUG"}

    def test_load_workspace_config_skips_duplicate_when_same_as_project(self) -> None:
        """Test that workspace config is skipped when workspace dir equals project dir."""
        with tempfile.TemporaryDirectory() as temp_dir:
            project_dir = Path(temp_dir)
            (project_dir / "griptape_nodes_config.json").write_text('{"log_level": "WARNING"}')

            with patch.dict(os.environ, {}, clear=True):
                manager = ConfigManager()
                manager.load_project_config(project_dir)
                # Now load workspace config from same dir — should be skipped
                manager.load_workspace_config(project_dir)

                assert manager.get_config_value("log_level") == "WARNING"
                # workspace_config is empty because the duplicate was skipped
                assert manager.workspace_config == {}

    def test_workspace_config_overrides_project_config_but_not_env_vars(self) -> None:
        """Test that workspace config wins over project config but loses to env vars."""
        with tempfile.TemporaryDirectory() as temp_dir:
            project_dir = Path(temp_dir) / "project"
            project_dir.mkdir()
            workspace_dir = Path(temp_dir) / "workspace"
            workspace_dir.mkdir()

            (project_dir / "griptape_nodes_config.json").write_text('{"log_level": "ERROR"}')
            (workspace_dir / "griptape_nodes_config.json").write_text('{"log_level": "WARNING"}')

            with patch.dict(os.environ, {"GTN_CONFIG_LOG_LEVEL": "DEBUG"}, clear=True):
                manager = ConfigManager()
                manager.load_project_config(project_dir)
                manager.load_workspace_config(workspace_dir)

                # Env var wins over workspace config
                assert manager.get_config_value("log_level") == "DEBUG"

    def test_get_config_value_workspace_config_source(self) -> None:
        """Test that get_config_value can read from workspace_config source specifically."""
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace_dir = Path(temp_dir)
            (workspace_dir / "griptape_nodes_config.json").write_text('{"log_level": "DEBUG"}')

            with patch.dict(os.environ, {}, clear=True):
                manager = ConfigManager()
                manager.load_workspace_config(workspace_dir)

                value = manager.get_config_value("log_level", config_source="workspace_config")
                assert value == "DEBUG"

    def test_workspace_config_missing_file_is_empty(self) -> None:
        """Test that load_workspace_config with no config file results in empty workspace_config."""
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace_dir = Path(temp_dir)
            # No griptape_nodes_config.json created

            with patch.dict(os.environ, {}, clear=True):
                manager = ConfigManager()
                manager.load_workspace_config(workspace_dir)

                assert manager.workspace_config == {}

    def test_workspace_override_survives_load_configs(self) -> None:
        """Test that set_workspace_override persists through load_configs() calls."""
        with tempfile.TemporaryDirectory() as temp_dir:
            override_dir = Path(temp_dir)

            with patch.dict(os.environ, {}, clear=True):
                manager = ConfigManager()
                manager.set_workspace_override(override_dir)

                manager.load_configs()

                assert manager.workspace_path == override_dir.resolve()
                assert manager.merged_config["workspace_directory"] == str(override_dir.resolve())

    def test_workspace_override_loses_to_env_var(self) -> None:
        """Test that GTN_CONFIG_WORKSPACE_DIRECTORY still wins over the runtime override."""
        with tempfile.TemporaryDirectory() as temp_dir:
            override_dir = Path(temp_dir) / "override"
            override_dir.mkdir()
            env_dir = Path(temp_dir) / "env"
            env_dir.mkdir()

            with patch.dict(os.environ, {"GTN_CONFIG_WORKSPACE_DIRECTORY": str(env_dir)}, clear=True):
                manager = ConfigManager()
                manager.set_workspace_override(override_dir)

                manager.load_configs()

                assert manager.workspace_path == env_dir.resolve()

    def test_workspace_override_cleared_on_reset(self) -> None:
        """Test that reset_user_config clears the runtime workspace override."""
        with tempfile.TemporaryDirectory() as temp_dir:
            override_dir = Path(temp_dir)

            with patch.dict(os.environ, {}, clear=True):
                manager = ConfigManager()
                manager.set_workspace_override(override_dir)
                assert manager.workspace_path == override_dir.resolve()

                manager.reset_user_config()

                assert manager._workspace_dir_override is None
                assert manager.workspace_path != override_dir.resolve()

    def test_set_workspace_override_none_clears(self) -> None:
        """Test that set_workspace_override(None) clears a previously set override."""
        with tempfile.TemporaryDirectory() as temp_dir:
            override_dir = Path(temp_dir)

            with patch.dict(os.environ, {}, clear=True):
                manager = ConfigManager()
                default_workspace = manager.workspace_path

                manager.set_workspace_override(override_dir)
                assert manager.workspace_path == override_dir.resolve()

                manager.set_workspace_override(None)
                assert manager._workspace_dir_override is None

                manager.load_configs()
                assert manager.workspace_path == default_workspace


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

    def test_libraries_to_register_accepts_mixed_str_and_object_entries(self) -> None:
        """Settings validation accepts a mix of bare path strings and objects with `enabled`."""
        from griptape_nodes.retained_mode.managers.settings import LibraryRegistration, Settings

        validated = Settings.model_validate(
            {
                "app_events": {
                    "on_app_initialization_complete": {
                        "libraries_to_register": [
                            "/path/to/enabled.json",
                            {"path": "/path/to/disabled.json", "enabled": False},
                        ],
                    },
                },
            },
        )

        entries = validated.app_events.on_app_initialization_complete.libraries_to_register
        assert entries[0] == "/path/to/enabled.json"
        assert isinstance(entries[1], LibraryRegistration)
        assert entries[1].path == "/path/to/disabled.json"
        assert entries[1].enabled is False

        # Round-trip: bare strings stay strings, objects stay objects.
        # Object form serializes every field on LibraryRegistration; `worker_mode_override`
        # defaults to None when the user didn't set one (added alongside `enabled`).
        dumped = validated.app_events.on_app_initialization_complete.model_dump()
        assert dumped["libraries_to_register"] == [
            "/path/to/enabled.json",
            {"path": "/path/to/disabled.json", "enabled": False, "worker_mode_override": None},
        ]


@pytest.mark.skipif(
    platform.system() == "Windows", reason="xdg_base_dirs cannot find XDG_CONFIG_HOME on Windows on GitHub Actions"
)
class TestConfigManagerEventGating:
    """``ConfigChanged`` must only fire when the disk write actually landed.

    Listeners (in production: WorkerManager fans out ReloadConfigRequest to
    every registered worker) consume ConfigChanged. Emitting on a failed
    write would tell every consumer to act on a state that does not exist
    on disk -- e.g. workers reload the file and either see stale values or
    fail to find the new key.
    """

    def test_set_config_value_does_not_emit_when_write_fails(self) -> None:
        event_manager = EventManager()
        config_manager = ConfigManager(event_manager=event_manager)

        received: list[ConfigChanged] = []
        event_manager.add_listener_to_app_event(ConfigChanged, received.append)

        with patch.object(config_manager, "_write_user_config_delta", return_value=False):
            config_manager.set_config_value(key="test_key", value="new_value")

        assert received == []

    def test_set_config_value_emits_when_write_succeeds(self) -> None:
        event_manager = EventManager()
        config_manager = ConfigManager(event_manager=event_manager)

        received: list[ConfigChanged] = []
        event_manager.add_listener_to_app_event(ConfigChanged, received.append)

        with patch.object(config_manager, "_write_user_config_delta", return_value=True):
            config_manager.set_config_value(key="test_key", value="new_value")

        assert len(received) == 1
        assert received[0].key == "test_key"
        assert received[0].new_value == "new_value"

    def test_set_config_category_full_replacement_returns_failure_when_write_fails(self) -> None:
        from griptape_nodes.retained_mode.events.config_events import (
            SetConfigCategoryRequest,
            SetConfigCategoryResultFailure,
        )

        event_manager = EventManager()
        config_manager = ConfigManager(event_manager=event_manager)

        received: list[ConfigChanged] = []
        event_manager.add_listener_to_app_event(ConfigChanged, received.append)

        request = SetConfigCategoryRequest(category=None, contents={"any": "thing"})
        with patch.object(config_manager, "_write_user_config_delta", return_value=False):
            result = config_manager.on_handle_set_config_category_request(request)

        assert isinstance(result, SetConfigCategoryResultFailure)
        assert received == []

    def test_set_config_category_non_empty_category_returns_failure_when_write_fails(self) -> None:
        """The non-empty-category branch routes through ``set_config_value``; failure must propagate."""
        from griptape_nodes.retained_mode.events.config_events import (
            SetConfigCategoryRequest,
            SetConfigCategoryResultFailure,
        )

        event_manager = EventManager()
        config_manager = ConfigManager(event_manager=event_manager)

        received: list[ConfigChanged] = []
        event_manager.add_listener_to_app_event(ConfigChanged, received.append)

        request = SetConfigCategoryRequest(category="some_category", contents={"any": "thing"})
        with patch.object(config_manager, "_write_user_config_delta", return_value=False):
            result = config_manager.on_handle_set_config_category_request(request)

        assert isinstance(result, SetConfigCategoryResultFailure)
        assert received == []

    def test_set_config_value_request_returns_failure_when_write_fails(self) -> None:
        """The set-value handler must surface a failure result when the write didn't land."""
        from griptape_nodes.retained_mode.events.config_events import (
            SetConfigValueRequest,
            SetConfigValueResultFailure,
        )

        event_manager = EventManager()
        config_manager = ConfigManager(event_manager=event_manager)

        received: list[ConfigChanged] = []
        event_manager.add_listener_to_app_event(ConfigChanged, received.append)

        request = SetConfigValueRequest(category_and_key="some.key", value="v")
        with patch.object(config_manager, "_write_user_config_delta", return_value=False):
            result = config_manager.on_handle_set_config_value_request(request)

        assert isinstance(result, SetConfigValueResultFailure)
        assert received == []

    def test_set_config_value_returns_true_on_success_and_false_on_failure(self) -> None:
        """``set_config_value`` exposes the write outcome so handlers can propagate failure."""
        config_manager = ConfigManager()

        with patch.object(config_manager, "_write_user_config_delta", return_value=True):
            assert config_manager.set_config_value(key="k", value="v") is True

        with patch.object(config_manager, "_write_user_config_delta", return_value=False):
            assert config_manager.set_config_value(key="k", value="v") is False


class TestConfigManagerUtf8:
    """_load_config_from_file must read UTF-8 regardless of the platform locale."""

    def test_reads_utf8_config_when_locale_is_cp949(self, tmp_path: Path) -> None:
        config_data = {"workspace": "C:\\Users\\한국어\\griptape"}
        config_file = tmp_path / "griptape_nodes_config.json"
        config_file.write_text(json.dumps(config_data), encoding="utf-8")

        manager = ConfigManager.__new__(ConfigManager)

        with patch("locale.getpreferredencoding", return_value="cp949"):
            result = manager._load_config_from_file(config_file, "test")

        assert result == config_data

    def test_returns_empty_dict_on_unicode_decode_error(self, tmp_path: Path) -> None:
        config_file = tmp_path / "griptape_nodes_config.json"
        config_file.write_bytes(b'{"key": "\xb9\xd9"}')  # cp949-encoded bytes, not valid UTF-8

        manager = ConfigManager.__new__(ConfigManager)
        result = manager._load_config_from_file(config_file, "test")

        assert result == {}
