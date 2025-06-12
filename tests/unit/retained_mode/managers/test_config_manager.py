import os
import platform
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from griptape_nodes.retained_mode.managers.config_manager import ConfigManager


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
