import asyncio
import logging
import threading
from collections.abc import AsyncGenerator, Generator
from pathlib import Path
from typing import Any

import pytest
import pytest_asyncio
from dotenv import load_dotenv

# Signal the server to shutdown gracefully using the API module function
from griptape_nodes.app.api import shutdown_server, start_api_async
from griptape_nodes.app.app import _build_static_dir
from griptape_nodes.bootstrap.workflow_executors.local_workflow_executor import LocalWorkflowExecutor
from griptape_nodes.retained_mode.events.object_events import ClearAllObjectStateRequest
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

logger = logging.getLogger(__name__)


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


load_dotenv()


@pytest.fixture(scope="session", autouse=True)
def setup_test_libraries() -> Generator[None, Any, None]:
    """Set up libraries for testing and restore original state afterwards."""
    config_manager = GriptapeNodes.ConfigManager()

    # Save the original libraries state
    original_libraries = config_manager.get_config_value(
        key="app_events.on_app_initialization_complete.libraries_to_register", default=[]
    )

    # Set the test libraries
    test_libraries = [str(lib) for lib in get_libraries()]
    config_manager.set_config_value(
        key="app_events.on_app_initialization_complete.libraries_to_register",
        value=test_libraries,
    )
    logger.info(config_manager.get_config_value("app_events.on_app_initialization_complete.libraries_to_register"))

    yield  # Run all tests

    # Restore original libraries state
    config_manager.set_config_value(
        key="app_events.on_app_initialization_complete.libraries_to_register",
        value=original_libraries,
    )


@pytest_asyncio.fixture(scope="session", autouse=True)
async def api_server() -> AsyncGenerator[None, None]:
    """Start the API server using run_coroutine_threadsafe with separate event loop."""
    # Create a new event loop for the separate thread
    new_loop = asyncio.new_event_loop()

    # Start the event loop in a separate thread
    def run_loop() -> None:
        asyncio.set_event_loop(new_loop)
        new_loop.run_forever()

    # Schedule server coroutine on the separate loop from main async context
    thread = threading.Thread(target=run_loop, daemon=True)
    thread.start()

    static_dir = _build_static_dir()
    asyncio.run_coroutine_threadsafe(start_api_async(static_dir), new_loop)

    try:
        yield
    finally:
        logger.info("Shutting down API server...")

        shutdown_server()

        # Stop the event loop
        new_loop.call_soon_threadsafe(new_loop.stop)
        thread.join(timeout=5.0)


@pytest.fixture(autouse=True)
def clear_state_before_each_test() -> Generator[None, Any, None]:
    """Clear all object state before each test to ensure clean starting conditions."""
    from griptape_nodes import GriptapeNodes

    # Clear any existing state
    clear_request = ClearAllObjectStateRequest(i_know_what_im_doing=True)
    GriptapeNodes.handle_request(clear_request)

    GriptapeNodes.ConfigManager()._set_log_level("DEBUG")

    yield  # Run the test

    # Clean up after test
    clear_request = ClearAllObjectStateRequest(i_know_what_im_doing=True)
    GriptapeNodes.handle_request(clear_request)


@pytest.mark.parametrize("workflow_path", get_workflows())
@pytest.mark.asyncio
async def test_workflow_runs(workflow_path: str) -> None:
    """Simple test to check if the workflow runs without errors."""
    runner = LocalWorkflowExecutor()
    await runner.arun(workflow_name="main", flow_input={}, workflow_path=workflow_path)
