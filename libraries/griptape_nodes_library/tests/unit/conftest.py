"""Shared fixtures and setup for library unit tests."""

import json
import tempfile
from collections.abc import Generator
from pathlib import Path
from unittest.mock import patch

import pytest

from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes


def pytest_configure(config: pytest.Config) -> None:  # noqa: ARG001
    """Register library before test collection to install pip dependencies and extend sys.path.

    Mirrors what the engine does at runtime: installs the library's pip dependencies
    into the library's own .venv and adds that venv's site-packages to sys.path.
    Must run before collection so that library dependency imports succeed.
    """
    from griptape_nodes.retained_mode.events.library_events import RegisterLibraryFromFileRequest

    library_json = str(Path(__file__).parents[2] / "griptape_nodes_library.json")
    GriptapeNodes.handle_request(RegisterLibraryFromFileRequest(file_path=library_json))


@pytest.fixture(autouse=True)
def isolate_user_config() -> Generator[Path, None, None]:
    """Isolate the user config file during tests to prevent pollution of the real config."""
    import griptape_nodes.retained_mode.managers.config_manager as config_manager_module
    from griptape_nodes.utils.metaclasses import SingletonMeta

    SingletonMeta._instances.clear()

    with tempfile.TemporaryDirectory() as temp_dir:
        temp_config_path = Path(temp_dir) / "griptape_nodes_config.json"
        temp_config_path.write_text(json.dumps({}, indent=2))

        with patch.object(config_manager_module, "USER_CONFIG_PATH", temp_config_path):
            yield temp_config_path

            SingletonMeta._instances.clear()


@pytest.fixture
def griptape_nodes() -> GriptapeNodes:
    """Provide a properly initialized GriptapeNodes instance for testing."""
    return GriptapeNodes()
