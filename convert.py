from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
GriptapeNodes().handle_request(CreateFlowRequest(request_id=None, parent_flow_name=None, flow_name='convert'))
GriptapeNodes().handle_request(CreateNodeRequest(request_id=None, node_type='ToText', specific_library_name=None, node_name='ToText_1', override_parent_flow_name='convert', metadata={'position': {'x': 520, 'y': 479}, 'library_node_metadata': {'category': 'Convert', 'description': 'Convert data to text'}, 'library': 'Griptape Nodes Library', 'node_type': 'ToText', 'category': 'Convert'}))
GriptapeNodes().handle_request(AlterParameterDetailsRequest(request_id=None, parameter_name='from', node_name='ToText_1', type=None, input_types=None, output_type=None, default_value=None, tooltip=None, tooltip_as_input=None, tooltip_as_property=None, tooltip_as_output=None, mode_allowed_input=None, mode_allowed_property=None, mode_allowed_output=None, ui_options=None))
GriptapeNodes().handle_request(AlterParameterDetailsRequest(request_id=None, parameter_name='output', node_name='ToText_1', type=None, input_types=None, output_type=None, default_value=None, tooltip=None, tooltip_as_input=None, tooltip_as_property=None, tooltip_as_output=None, mode_allowed_input=None, mode_allowed_property=None, mode_allowed_output=None, ui_options=None))
GriptapeNodes().handle_request(CreateNodeRequest(request_id=None, node_type='CreateFloat', specific_library_name=None, node_name='CreateFloat_1', override_parent_flow_name='convert', metadata={'position': {'x': 52, 'y': 481}, 'library_node_metadata': {'category': 'Number', 'description': 'Creates and outputs a simple float value'}, 'library': 'Griptape Nodes Library', 'node_type': 'CreateFloat', 'category': 'Number'}))
GriptapeNodes().handle_request(AlterParameterDetailsRequest(request_id=None, parameter_name='float', node_name='CreateFloat_1', type=None, input_types=None, output_type=None, default_value=None, tooltip=None, tooltip_as_input=None, tooltip_as_property=None, tooltip_as_output=None, mode_allowed_input=None, mode_allowed_property=None, mode_allowed_output=None, ui_options=None))
# /// script
# dependencies = []
# 
# [tool.griptape-nodes]
# name = "convert"
# schema_version = "0.1.0"
# engine_version_created_with = "0.11.0"
# node_libraries_referenced = [["Griptape Nodes Library", "0.1.0"]]
# 
# ///


