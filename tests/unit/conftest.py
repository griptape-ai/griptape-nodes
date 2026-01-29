"""Shared fixtures for unit tests."""

import json
import tempfile
from collections.abc import Generator
from pathlib import Path
from unittest.mock import patch

import pytest

from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes


@pytest.fixture(autouse=True)
def isolate_user_config() -> Generator[Path, None, None]:
    """Isolate the user config file during tests to prevent pollution of the real config."""
    import griptape_nodes.retained_mode.managers.config_manager as config_manager_module
    from griptape_nodes.utils.metaclasses import SingletonMeta

    # Clear any existing singleton instances to force re-initialization with patched config
    SingletonMeta._instances.clear()

    # Create a temporary directory for the test config
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_config_path = Path(temp_dir) / "griptape_nodes_config.json"

        # Initialize with an empty config
        temp_config_path.write_text(json.dumps({}, indent=2))

        # Patch the USER_CONFIG_PATH constant to point to our temp file
        with patch.object(config_manager_module, "USER_CONFIG_PATH", temp_config_path):
            yield temp_config_path

            # Clear singleton instances after test to ensure clean state
            SingletonMeta._instances.clear()


@pytest.fixture
def griptape_nodes() -> GriptapeNodes:
    """Provide a properly initialized GriptapeNodes instance for testing."""
    # Initialize GriptapeNodes (it's a singleton, so this returns the existing instance)
    return GriptapeNodes()
