from collections.abc import Generator
from pathlib import Path
from typing import Any

import pytest
from dotenv import load_dotenv

from griptape_nodes.bootstrap.workflow_executors.subprocess_workflow_executor import SubprocessWorkflowExecutor
from griptape_nodes.retained_mode.events.object_events import ClearAllObjectStateRequest


def get_libraries_dir() -> Path:
    """Get the path to the libraries directory in the repo root."""
    return Path(__file__).parent.parent.parent / "libraries"


def get_libraries() -> list[Path]:
    """Get all libraries required for testing."""
    libraries_dir = get_libraries_dir()
    return [
        libraries_dir / "griptape_nodes_library" / "griptape_nodes_library.json",
        # TODO: https://github.com/griptape-ai/griptape-nodes/issues/1313
        #       libraries_dir / "griptape_nodes_advanced_media_library" / "griptape_nodes_library.json",
    ]


def get_workflows() -> list[str]:
    """Get all workflows to be tested."""
    libraries_dir = Path(get_libraries_dir())
    workflow_dirs = [
        libraries_dir / "griptape_nodes_library" / "workflows" / "templates",
        # TODO: https://github.com/griptape-ai/griptape-nodes/issues/1313
        #       libraries_dir / "griptape_nodes_advanced_media_library" / "workflows" / "templates",
    ]

    workflows = []
    for d in workflow_dirs:
        for f in d.iterdir():
            if f.is_file() and f.suffix == ".py" and not f.name.startswith("__"):
                workflows.extend([str(f)])
    return workflows


def set_libraries(libraries: list[str]) -> None:
    """Set the libraries to be registered for testing if not already set.

    Parameters
    ----------
    libraries : list[str]
        List of library paths to register.
    """
    from griptape_nodes.retained_mode.managers.config_manager import ConfigManager

    config_manager = ConfigManager()

    libraries_to_register = config_manager.get_config_value(
        key="app_events.on_app_initialization_complete.libraries_to_register", default=[]
    )

    if len(libraries_to_register) < 1:
        config_manager.set_config_value(
            key="app_events.on_app_initialization_complete.libraries_to_register",
            value=libraries,
        )


load_dotenv()
set_libraries([str(lib) for lib in get_libraries()])


@pytest.fixture(autouse=True)
def clear_state_before_each_test() -> Generator[None, Any, None]:
    """Clear all object state before each test to ensure clean starting conditions."""
    from griptape_nodes import GriptapeNodes

    # Clear any existing state
    clear_request = ClearAllObjectStateRequest(i_know_what_im_doing=True)
    GriptapeNodes.handle_request(clear_request)

    GriptapeNodes.ConfigManager()._set_log_level("INFO")

    yield  # Run the test

    # Clean up after test
    clear_request = ClearAllObjectStateRequest(i_know_what_im_doing=True)
    GriptapeNodes.handle_request(clear_request)


@pytest.mark.parametrize("workflow_path", get_workflows())
def test_workflow_runs(workflow_path: str) -> None:
    """Simple test to check if the workflow runs without errors."""
    # Run in subprocess - it will load the workflow in the subprocess
    runner = SubprocessWorkflowExecutor()
    runner.run(workflow_name="main", flow_input={}, workflow_path=workflow_path)
