import pytest  # type: ignore[reportMissingImports]

from griptape_nodes.retained_mode.events.flow_events import CreateFlowRequest, CreateFlowResultSuccess
from griptape_nodes.retained_mode.events.library_events import RegisterLibraryFromFileRequest
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
from griptape_nodes.utils import install_file_url_support

# Install file:// URL support for httpx/requests in integration tests
install_file_url_support()


@pytest.fixture
def flow() -> CreateFlowResultSuccess:
    """Fixture to create a flow for testing."""
    request = RegisterLibraryFromFileRequest(
        file_path="../griptape-nodes/libraries/griptape_nodes_library/griptape_nodes_library.json"
    )
    result = GriptapeNodes.handle_request(request)

    # Create a canvas (flow with no parents)
    request = CreateFlowRequest(parent_flow_name=None, flow_name="canvas")
    result = GriptapeNodes.handle_request(request)

    assert isinstance(result, CreateFlowResultSuccess)

    return result
