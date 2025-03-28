import pytest

from griptape_nodes.retained_mode.events.flow_events import CreateFlowRequest, CreateFlowResult_Success
from griptape_nodes.retained_mode.events.library_events import RegisterLibraryFromFileRequest
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes


@pytest.fixture
def flow() -> CreateFlowResult_Success:
    request = RegisterLibraryFromFileRequest("../griptape-nodes/nodes/griptape_nodes_library.json")
    result = GriptapeNodes.handle_request(request)

    # Create a canvas (flow with no parents)
    request = CreateFlowRequest(parent_flow_name=None, flow_name="canvas")
    result = GriptapeNodes.handle_request(request)

    assert isinstance(result, CreateFlowResult_Success)

    return result
