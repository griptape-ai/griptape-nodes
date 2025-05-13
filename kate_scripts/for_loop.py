from griptape_nodes.retained_mode.events.connection_events import CreateConnectionRequest
from griptape_nodes.retained_mode.events.context_events import SetWorkflowContextRequest
from griptape_nodes.retained_mode.events.execution_events import StartFlowRequest
from griptape_nodes.retained_mode.events.flow_events import CreateFlowRequest
from griptape_nodes.retained_mode.events.library_events import RegisterLibraryFromFileRequest
from griptape_nodes.retained_mode.events.node_events import CreateNodeRequest
from griptape_nodes.retained_mode.events.parameter_events import SetParameterValueRequest
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

GriptapeNodes.handle_request(RegisterLibraryFromFileRequest(file_path="/Users/kateforsberg/Griptape/griptape-nodes/libraries/griptape_nodes_library/griptape_nodes_library.json"))

GriptapeNodes.ContextManager().push_workflow("My very unique workflow name.")

GriptapeNodes.handle_request(CreateFlowRequest(flow_name="Canvas", parent_flow_name=None, set_as_new_context=True))
GriptapeNodes.handle_request(CreateFlowRequest(flow_name="SubFlow_1", set_as_new_context=True, parent_flow_name="Canvas"))

# Create an Agent node in the subflow
GriptapeNodes.handle_request(CreateNodeRequest(node_type="Agent", node_name="GPT_Agent", specific_library_name="Griptape Nodes Library"))

# Create an image generation node in the subflow
GriptapeNodes.handle_request(CreateNodeRequest(node_type="GenerateImage", node_name="Image_Generator", specific_library_name="Griptape Nodes Library"))

# Connect the Agent to the Image Generator
GriptapeNodes.handle_request(CreateConnectionRequest(source_node_name="GPT_Agent", source_parameter_name="exec_out", target_node_name="Image_Generator", target_parameter_name="exec_in"))
GriptapeNodes.handle_request(CreateConnectionRequest(source_node_name="GPT_Agent", source_parameter_name="output", target_node_name="Image_Generator", target_parameter_name="prompt"))

#Go back to Canvas
GriptapeNodes.ContextManager().pop_flow()

# Create a ForLoop node in the Canvas flow
GriptapeNodes.handle_request(CreateNodeRequest(node_type="ForLoop", node_name="Loop_Controller", specific_library_name="Griptape Nodes Library"))

# Set the flow parameter of the ForLoop to point to SubFlow_1
subflow_1 = GriptapeNodes.FlowManager().get_flow_by_name("SubFlow_1")
GriptapeNodes.handle_request(SetParameterValueRequest(node_name="Loop_Controller", parameter_name="flow", value=subflow_1))

# Set some test prompts for the loop
GriptapeNodes.handle_request(SetParameterValueRequest(node_name="Loop_Controller", parameter_name="looped_input", value=["A beautiful sunset", "A majestic mountain", "A peaceful lake"], data_type="list"))

GriptapeNodes.handle_request(StartFlowRequest(flow_name="Canvas"))
