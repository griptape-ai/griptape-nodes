from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
GriptapeNodes().handle_request(CreateFlowRequest(request_id=None, parent_flow_name=None, flow_name='ollama'))
GriptapeNodes().handle_request(CreateNodeRequest(request_id=None, node_type='OllamaPromptDriverNode', specific_library_name=None, node_name='OllamaPromptDriverNode_1', override_parent_flow_name='ollama', metadata={'position': {'x': 290, 'y': 316}, 'library_node_metadata': {'category': 'Drivers', 'description': 'Prompt driver for Ollama (local!)', 'display_name': 'Ollama Prompt Driver'}, 'library': 'Griptape Nodes Library', 'node_type': 'OllamaPromptDriverNode'}))
GriptapeNodes().handle_request(AlterParameterDetailsRequest(request_id=None, parameter_name='prompt_driver', node_name='OllamaPromptDriverNode_1', type=None, input_types=None, output_type=None, default_value=None, tooltip=None, tooltip_as_input=None, tooltip_as_property=None, tooltip_as_output=None, mode_allowed_input=None, mode_allowed_property=None, mode_allowed_output=None, ui_options=None))
GriptapeNodes().handle_request(AlterParameterDetailsRequest(request_id=None, parameter_name='model', node_name='OllamaPromptDriverNode_1', type=None, input_types=None, output_type=None, default_value=None, tooltip=None, tooltip_as_input=None, tooltip_as_property=None, tooltip_as_output=None, mode_allowed_input=None, mode_allowed_property=None, mode_allowed_output=None, ui_options=None))
GriptapeNodes().handle_request(SetParameterValueRequest(request_id=None, parameter_name='model', node_name='OllamaPromptDriverNode_1', value='llama3.2', data_type=None))
GriptapeNodes().handle_request(AlterParameterDetailsRequest(request_id=None, parameter_name='max_attempts_on_fail', node_name='OllamaPromptDriverNode_1', type=None, input_types=None, output_type=None, default_value=None, tooltip=None, tooltip_as_input=None, tooltip_as_property=None, tooltip_as_output=None, mode_allowed_input=None, mode_allowed_property=None, mode_allowed_output=None, ui_options=None))
GriptapeNodes().handle_request(AlterParameterDetailsRequest(request_id=None, parameter_name='min_p', node_name='OllamaPromptDriverNode_1', type=None, input_types=None, output_type=None, default_value=None, tooltip=None, tooltip_as_input=None, tooltip_as_property=None, tooltip_as_output=None, mode_allowed_input=None, mode_allowed_property=None, mode_allowed_output=None, ui_options=None))
GriptapeNodes().handle_request(AlterParameterDetailsRequest(request_id=None, parameter_name='top_k', node_name='OllamaPromptDriverNode_1', type=None, input_types=None, output_type=None, default_value=None, tooltip=None, tooltip_as_input=None, tooltip_as_property=None, tooltip_as_output=None, mode_allowed_input=None, mode_allowed_property=None, mode_allowed_output=None, ui_options=None))
GriptapeNodes().handle_request(AlterParameterDetailsRequest(request_id=None, parameter_name='temperature', node_name='OllamaPromptDriverNode_1', type=None, input_types=None, output_type=None, default_value=None, tooltip=None, tooltip_as_input=None, tooltip_as_property=None, tooltip_as_output=None, mode_allowed_input=None, mode_allowed_property=None, mode_allowed_output=None, ui_options=None))
GriptapeNodes().handle_request(AlterParameterDetailsRequest(request_id=None, parameter_name='seed', node_name='OllamaPromptDriverNode_1', type=None, input_types=None, output_type=None, default_value=None, tooltip=None, tooltip_as_input=None, tooltip_as_property=None, tooltip_as_output=None, mode_allowed_input=None, mode_allowed_property=None, mode_allowed_output=None, ui_options=None))
GriptapeNodes().handle_request(AlterParameterDetailsRequest(request_id=None, parameter_name='use_native_tools', node_name='OllamaPromptDriverNode_1', type=None, input_types=None, output_type=None, default_value=None, tooltip=None, tooltip_as_input=None, tooltip_as_property=None, tooltip_as_output=None, mode_allowed_input=None, mode_allowed_property=None, mode_allowed_output=None, ui_options=None))
GriptapeNodes().handle_request(AlterParameterDetailsRequest(request_id=None, parameter_name='max_tokens', node_name='OllamaPromptDriverNode_1', type=None, input_types=None, output_type=None, default_value=None, tooltip=None, tooltip_as_input=None, tooltip_as_property=None, tooltip_as_output=None, mode_allowed_input=None, mode_allowed_property=None, mode_allowed_output=None, ui_options=None))
GriptapeNodes().handle_request(AlterParameterDetailsRequest(request_id=None, parameter_name='stream', node_name='OllamaPromptDriverNode_1', type=None, input_types=None, output_type=None, default_value=None, tooltip=None, tooltip_as_input=None, tooltip_as_property=None, tooltip_as_output=None, mode_allowed_input=None, mode_allowed_property=None, mode_allowed_output=None, ui_options=None))
GriptapeNodes().handle_request(AlterParameterDetailsRequest(request_id=None, parameter_name='base_url', node_name='OllamaPromptDriverNode_1', type=None, input_types=None, output_type=None, default_value=None, tooltip=None, tooltip_as_input=None, tooltip_as_property=None, tooltip_as_output=None, mode_allowed_input=None, mode_allowed_property=None, mode_allowed_output=None, ui_options=None))
GriptapeNodes().handle_request(SetParameterValueRequest(request_id=None, parameter_name='base_url', node_name='OllamaPromptDriverNode_1', value='http://127.0.0.1', data_type=None))
GriptapeNodes().handle_request(AlterParameterDetailsRequest(request_id=None, parameter_name='port', node_name='OllamaPromptDriverNode_1', type=None, input_types=None, output_type=None, default_value=None, tooltip=None, tooltip_as_input=None, tooltip_as_property=None, tooltip_as_output=None, mode_allowed_input=None, mode_allowed_property=None, mode_allowed_output=None, ui_options=None))
GriptapeNodes().handle_request(SetParameterValueRequest(request_id=None, parameter_name='port', node_name='OllamaPromptDriverNode_1', value='11434', data_type=None))
GriptapeNodes().handle_request(CreateNodeRequest(request_id=None, node_type='CreateAgentNode', specific_library_name=None, node_name='CreateAgentNode_1', override_parent_flow_name='ollama', metadata={'position': {'x': 927, 'y': 355}, 'library_node_metadata': {'category': 'Agent', 'description': 'Griptape Agent that can execute prompts and use tools', 'display_name': 'Create Agent'}, 'library': 'Griptape Nodes Library', 'node_type': 'CreateAgentNode'}))
GriptapeNodes().handle_request(AlterParameterDetailsRequest(request_id=None, parameter_name='exec_in', node_name='CreateAgentNode_1', type=None, input_types=None, output_type=None, default_value=None, tooltip=None, tooltip_as_input=None, tooltip_as_property=None, tooltip_as_output=None, mode_allowed_input=None, mode_allowed_property=None, mode_allowed_output=None, ui_options=None))
GriptapeNodes().handle_request(AlterParameterDetailsRequest(request_id=None, parameter_name='exec_out', node_name='CreateAgentNode_1', type=None, input_types=None, output_type=None, default_value=None, tooltip=None, tooltip_as_input=None, tooltip_as_property=None, tooltip_as_output=None, mode_allowed_input=None, mode_allowed_property=None, mode_allowed_output=None, ui_options=None))
GriptapeNodes().handle_request(AlterParameterDetailsRequest(request_id=None, parameter_name='agent', node_name='CreateAgentNode_1', type=None, input_types=None, output_type=None, default_value=None, tooltip=None, tooltip_as_input=None, tooltip_as_property=None, tooltip_as_output=None, mode_allowed_input=None, mode_allowed_property=None, mode_allowed_output=None, ui_options=None))
GriptapeNodes().handle_request(AlterParameterDetailsRequest(request_id=None, parameter_name='prompt_driver', node_name='CreateAgentNode_1', type=None, input_types=None, output_type=None, default_value=None, tooltip=None, tooltip_as_input=None, tooltip_as_property=None, tooltip_as_output=None, mode_allowed_input=None, mode_allowed_property=None, mode_allowed_output=None, ui_options=None))
GriptapeNodes().handle_request(AlterParameterDetailsRequest(request_id=None, parameter_name='tools', node_name='CreateAgentNode_1', type=None, input_types=None, output_type=None, default_value=None, tooltip=None, tooltip_as_input=None, tooltip_as_property=None, tooltip_as_output=None, mode_allowed_input=None, mode_allowed_property=None, mode_allowed_output=None, ui_options=None))
GriptapeNodes().handle_request(AlterParameterDetailsRequest(request_id=None, parameter_name='rulesets', node_name='CreateAgentNode_1', type=None, input_types=None, output_type=None, default_value=None, tooltip=None, tooltip_as_input=None, tooltip_as_property=None, tooltip_as_output=None, mode_allowed_input=None, mode_allowed_property=None, mode_allowed_output=None, ui_options=None))
GriptapeNodes().handle_request(AlterParameterDetailsRequest(request_id=None, parameter_name='prompt', node_name='CreateAgentNode_1', type=None, input_types=None, output_type=None, default_value=None, tooltip=None, tooltip_as_input=None, tooltip_as_property=None, tooltip_as_output=None, mode_allowed_input=None, mode_allowed_property=None, mode_allowed_output=None, ui_options=None))
GriptapeNodes().handle_request(SetParameterValueRequest(request_id=None, parameter_name='prompt', node_name='CreateAgentNode_1', value='hi', data_type=None))
GriptapeNodes().handle_request(AlterParameterDetailsRequest(request_id=None, parameter_name='agent_response', node_name='CreateAgentNode_1', type=None, input_types=None, output_type=None, default_value=None, tooltip=None, tooltip_as_input=None, tooltip_as_property=None, tooltip_as_output=None, mode_allowed_input=None, mode_allowed_property=None, mode_allowed_output=None, ui_options=None))
GriptapeNodes().handle_request(CreateConnectionRequest(request_id=None, source_node_name='OllamaPromptDriverNode_1', source_parameter_name='prompt_driver', target_node_name='CreateAgentNode_1', target_parameter_name='prompt_driver'))
# /// script
# dependencies = []
# 
# [tool.griptape-nodes]
# name = "ollama"
# schema_version = "0.1.0"
# engine_version_created_with = "0.7.2"
# node_libraries_referenced = [["Griptape Nodes Library", "0.1.0"]]
# 
# ///


