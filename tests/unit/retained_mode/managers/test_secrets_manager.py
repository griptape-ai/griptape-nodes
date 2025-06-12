import os
import platform
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from griptape_nodes.retained_mode.managers.config_manager import ConfigManager
from griptape_nodes.retained_mode.managers.secrets_manager import SecretsManager


@pytest.mark.skipif(
    platform.system() == "Windows", reason="xdg_base_dirs cannot find XDG_CONFIG_HOME on Windows on GitHub Actions"
)
class TestSecretsManager:
    """Test SecretsManager functionality including search order precedence."""

    def test_secret_search_order_env_var_highest_priority(self) -> None:
        """Test that environment variables have highest priority over .env files."""
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace_path = Path(temp_dir)

            # Create workspace .env file
            workspace_env = workspace_path / ".env"
            workspace_env.write_text("TEST_SECRET=workspace_value\n")

            # Create global .env file
            global_env = workspace_path / "global.env"  # Use temp dir for test isolation
            global_env.write_text("TEST_SECRET=global_value\n")

            # Set environment variable (should have highest priority)
            with patch.dict(os.environ, {"TEST_SECRET": "env_value"}, clear=False):
                config_manager = ConfigManager()
                config_manager.workspace_path = workspace_path

                # Patch the global env path for test isolation
                with patch("griptape_nodes.retained_mode.managers.secrets_manager.ENV_VAR_PATH", global_env):
                    secrets_manager = SecretsManager(config_manager)

                    # Environment variable should win
                    assert secrets_manager.get_secret("TEST_SECRET") == "env_value"

    def test_secret_search_order_workspace_over_global(self) -> None:
        """Test that workspace .env takes priority over global .env when no env var is set."""
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace_path = Path(temp_dir)

            # Create workspace .env file
            workspace_env = workspace_path / ".env"
            workspace_env.write_text("TEST_SECRET=workspace_value\n")

            # Create global .env file
            global_env = workspace_path / "global.env"  # Use temp dir for test isolation
            global_env.write_text("TEST_SECRET=global_value\n")

            # Ensure no environment variable is set
            with patch.dict(os.environ, {}, clear=True):
                config_manager = ConfigManager()
                config_manager.workspace_path = workspace_path

                # Patch the global env path for test isolation
                with patch("griptape_nodes.retained_mode.managers.secrets_manager.ENV_VAR_PATH", global_env):
                    secrets_manager = SecretsManager(config_manager)

                    # Workspace should win over global
                    assert secrets_manager.get_secret("TEST_SECRET") == "workspace_value"

    def test_secret_search_order_global_as_fallback(self) -> None:
        """Test that global .env is used when neither env var nor workspace .env exist."""
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace_path = Path(temp_dir)

            # Create global .env file (no workspace .env)
            global_env = workspace_path / "global.env"  # Use temp dir for test isolation
            global_env.write_text("TEST_SECRET=global_value\n")

            # Ensure no environment variable is set
            with patch.dict(os.environ, {}, clear=True):
                config_manager = ConfigManager()
                config_manager.workspace_path = workspace_path

                # Patch the global env path for test isolation
                with patch("griptape_nodes.retained_mode.managers.secrets_manager.ENV_VAR_PATH", global_env):
                    secrets_manager = SecretsManager(config_manager)

                    # Global should be used as fallback
                    assert secrets_manager.get_secret("TEST_SECRET") == "global_value"

    def test_secret_not_found_returns_none(self) -> None:
        """Test that missing secrets return None when should_error_on_not_found=False."""
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace_path = Path(temp_dir)

            # Ensure no environment variable is set and no .env files exist
            with patch.dict(os.environ, {}, clear=True):
                config_manager = ConfigManager()
                config_manager.workspace_path = workspace_path

                secrets_manager = SecretsManager(config_manager)

                # Should return None for missing secret
                assert secrets_manager.get_secret("NONEXISTENT_SECRET", should_error_on_not_found=False) is None

    def test_secret_name_compliance(self) -> None:
        """Test that secret names are properly transformed to uppercase with underscores."""
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace_path = Path(temp_dir)

            # Set environment variable with compliant name
            with patch.dict(os.environ, {"MY_TEST_SECRET": "test_value"}, clear=False):
                config_manager = ConfigManager()
                config_manager.workspace_path = workspace_path

                secrets_manager = SecretsManager(config_manager)

                # Different input formats should all resolve to the same compliant name
                assert secrets_manager.get_secret("my test secret") == "test_value"
                assert secrets_manager.get_secret("my-test-secret") == "test_value"
                assert secrets_manager.get_secret("MY_TEST_SECRET") == "test_value"

    def test_search_order_partial_overlap(self) -> None:
        """Test search order when secrets exist in some but not all sources."""
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace_path = Path(temp_dir)

            # Create workspace .env with one secret
            workspace_env = workspace_path / ".env"
            workspace_env.write_text("SECRET_A=workspace_a\nSECRET_B=workspace_b\n")

            # Create global .env with different secrets
            global_env = workspace_path / "global.env"
            global_env.write_text("SECRET_B=global_b\nSECRET_C=global_c\n")

            # Set environment variable for one secret
            with patch.dict(os.environ, {"SECRET_A": "env_a"}, clear=False):
                config_manager = ConfigManager()
                config_manager.workspace_path = workspace_path

                with patch("griptape_nodes.retained_mode.managers.secrets_manager.ENV_VAR_PATH", global_env):
                    secrets_manager = SecretsManager(config_manager)

                    # SECRET_A: env var should win
                    assert secrets_manager.get_secret("SECRET_A") == "env_a"

                    # SECRET_B: workspace should win over global
                    assert secrets_manager.get_secret("SECRET_B") == "workspace_b"

                    # SECRET_C: only in global, should use global
                    assert secrets_manager.get_secret("SECRET_C") == "global_c"
