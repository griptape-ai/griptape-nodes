from griptape_nodes.retained_mode.events.flow_events import CreateFlowRequest
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

GriptapeNodes.handle_request(CreateFlowRequest(flow_name="Canvas",set_as_new_context=True, parent_flow_name=None))
GriptapeNodes.handle_request(CreateFlowRequest(flow_name="SubFlow",set_as_new_context=True, parent_flow_name="Canvas"))
