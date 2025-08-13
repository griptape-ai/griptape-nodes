# /// script
# dependencies = []
# 
# [tool.griptape-nodes]
# name = "local_executor_test"
# schema_version = "0.7.0"
# engine_version_created_with = "0.47.0"
# node_libraries_referenced = [["Griptape Nodes Library", "0.41.0"]]
# image = "local_executor_test_branch_1-thumbnail-2025-08-13.png"
# is_griptape_provided = false
# is_template = false
# creation_date = 2025-08-13T16:27:05.404301Z
# last_modified_date = 2025-08-13T16:45:16.407261Z
# 
# ///

import argparse
import json
import pickle
from griptape.artifacts.image_url_artifact import ImageUrlArtifact
from griptape_nodes.bootstrap.workflow_executors.local_workflow_executor import LocalWorkflowExecutor
from griptape_nodes.bootstrap.workflow_executors.workflow_executor import WorkflowExecutor
from griptape_nodes.node_library.library_registry import IconVariant, NodeMetadata
from griptape_nodes.retained_mode.events.connection_events import CreateConnectionRequest
from griptape_nodes.retained_mode.events.flow_events import CreateFlowRequest, GetTopLevelFlowRequest, GetTopLevelFlowResultSuccess
from griptape_nodes.retained_mode.events.library_events import GetAllInfoForAllLibrariesRequest, GetAllInfoForAllLibrariesResultSuccess
from griptape_nodes.retained_mode.events.node_events import CreateNodeRequest
from griptape_nodes.retained_mode.events.parameter_events import AddParameterToNodeRequest, AlterParameterDetailsRequest, SetParameterValueRequest
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

response = GriptapeNodes.LibraryManager().get_all_info_for_all_libraries_request(GetAllInfoForAllLibrariesRequest())

if isinstance(response, GetAllInfoForAllLibrariesResultSuccess) and len(response.library_name_to_library_info.keys()) < 1:
    GriptapeNodes.LibraryManager().load_all_libraries_from_config()

context_manager = GriptapeNodes.ContextManager()

if not context_manager.has_current_workflow():
    context_manager.push_workflow(workflow_name='local_executor_test')

"""
1. We've collated all of the unique parameter values into a dictionary so that we do not have to duplicate them.
   This minimizes the size of the code, especially for large objects like serialized image files.
2. We're using a prefix so that it's clear which Flow these values are associated with.
3. The values are serialized using pickle, which is a binary format. This makes them harder to read, but makes
   them consistently save and load. It allows us to serialize complex objects like custom classes, which otherwise
   would be difficult to serialize.
"""
top_level_unique_values_dict = {'45c4f65f-d2cc-460a-a3cf-bd32794756bf': pickle.loads(b'\x80\x04\x95\x0f\x00\x00\x00\x00\x00\x00\x00\x8c\x0ba small cat\x94.'), 'b0fe2cab-a90c-4f2c-91c7-e18b61ce798d': pickle.loads(b'\x80\x04\x95S\x01\x00\x00\x00\x00\x00\x00XL\x01\x00\x00A small cat is often referred to as a kitten if it is young, or simply a small-sized domestic cat if it is fully grown but petite. Small cats are known for their agility, playful behavior, and affectionate nature. If you want, I can provide information on caring for small cats, different small cat breeds, or anything else related!\x94.'), 'd716d214-35cd-4c36-8155-d5e23f7bb8f4': pickle.loads(b'\x80\x04\x95o\x01\x00\x00\x00\x00\x00\x00\x8c%griptape.artifacts.image_url_artifact\x94\x8c\x10ImageUrlArtifact\x94\x93\x94)\x81\x94}\x94(\x8c\x04type\x94\x8c\x10ImageUrlArtifact\x94\x8c\x0bmodule_name\x94\x8c%griptape.artifacts.image_url_artifact\x94\x8c\x02id\x94\x8c 19482b5e2458454c8a45bee46d9ae1db\x94\x8c\treference\x94N\x8c\x04meta\x94}\x94\x8c\x04name\x94h\n\x8c\x16encoding_error_handler\x94\x8c\x06strict\x94\x8c\x08encoding\x94\x8c\x05utf-8\x94\x8c\x05value\x94\x8cRhttp://localhost:8124/static/27065efa-c8e0-4129-a7aa-419b882dc434.png?t=1755102381\x94ub.'), 'f29e8644-90a7-4a03-a18c-980f87bf2691': pickle.loads(b'\x80\x04\x95\x10\x00\x00\x00\x00\x00\x00\x00\x8c\x0cgpt-4.1-mini\x94.'), '79f75ca3-6e5f-46c7-94fa-fc02928119a5': pickle.loads(b'\x80\x04\x95\x04\x00\x00\x00\x00\x00\x00\x00\x8c\x00\x94.'), '5c7cee06-4e26-4a04-8c81-b2aa051eda42': pickle.loads(b'\x80\x04]\x94.'), 'dfb23919-18cd-4bdd-a06d-0bff8c67d898': pickle.loads(b'\x80\x04]\x94.'), '0538a850-9895-46de-b7ba-f48faf755ac3': pickle.loads(b'\x80\x04\x89.'), '44c68b3b-cfed-4211-bd98-d041dbd02440': pickle.loads(b'\x80\x04\x95\x0c\x00\x00\x00\x00\x00\x00\x00\x8c\x08dall-e-3\x94.'), 'dca13c47-bca4-42cb-a5d9-17ff684205b8': pickle.loads(b'\x80\x04\x95\r\x00\x00\x00\x00\x00\x00\x00\x8c\t1024x1024\x94.')}

'# Create the Flow, then do work within it as context.'

flow0_name = GriptapeNodes.handle_request(CreateFlowRequest(parent_flow_name=None, set_as_new_context=False, metadata={})).flow_name

with GriptapeNodes.ContextManager().flow(flow0_name):
    node0_name = GriptapeNodes.handle_request(CreateNodeRequest(node_type='StartFlow', specific_library_name='Griptape Nodes Library', node_name='Start Flow', metadata={'position': {'x': 321.0677083333334, 'y': 685.3333333333333}, 'tempId': 'placing-1755102279886-wwehbm', 'library_node_metadata': NodeMetadata(category='workflows', description='Define the start of a workflow and pass parameters into the flow', display_name='Start Flow', tags=None, icon=None, color=None, group=None), 'library': 'Griptape Nodes Library', 'node_type': 'StartFlow', 'showaddparameter': True, 'category': 'workflows', 'size': {'width': 401, 'height': 217}}, initial_setup=True)).node_name
    with GriptapeNodes.ContextManager().node(node0_name):
        GriptapeNodes.handle_request(AddParameterToNodeRequest(parameter_name='prompt', default_value='', tooltip='New parameter', type='str', input_types=['str'], output_type='str', ui_options={'multiline': True, 'placeholder_text': 'Talk with the Agent.', 'is_custom': True, 'is_user_added': True}, mode_allowed_input=True, mode_allowed_property=True, mode_allowed_output=True, parent_container_name='', initial_setup=True))
    node1_name = GriptapeNodes.handle_request(CreateNodeRequest(node_type='EndFlow', specific_library_name='Griptape Nodes Library', node_name='End Flow', metadata={'position': {'x': 1629.0677083333333, 'y': 685.3333333333333}, 'tempId': 'placing-1755102285321-ds1gk9', 'library_node_metadata': NodeMetadata(category='workflows', description='Define the end of a workflow and return parameters from the flow', display_name='End Flow', tags=None, icon=None, color=None, group=None), 'library': 'Griptape Nodes Library', 'node_type': 'EndFlow', 'showaddparameter': True, 'category': 'workflows', 'size': {'width': 437, 'height': 445}}, initial_setup=True)).node_name
    with GriptapeNodes.ContextManager().node(node1_name):
        GriptapeNodes.handle_request(AddParameterToNodeRequest(parameter_name='output', default_value='', tooltip='New parameter', type='str', input_types=['str'], output_type='str', ui_options={'multiline': True, 'placeholder_text': 'Agent response', 'markdown': False, 'is_custom': True, 'is_user_added': True}, mode_allowed_input=True, mode_allowed_property=True, mode_allowed_output=True, parent_container_name='', initial_setup=True))
        GriptapeNodes.handle_request(AddParameterToNodeRequest(parameter_name='output_1', default_value='', tooltip='New parameter', type='ImageUrlArtifact', input_types=['ImageArtifact', 'ImageUrlArtifact'], output_type='ImageUrlArtifact', ui_options={'pulse_on_run': True, 'is_custom': True, 'is_user_added': True}, mode_allowed_input=True, mode_allowed_property=True, mode_allowed_output=True, parent_container_name='', initial_setup=True))
    node2_name = GriptapeNodes.handle_request(CreateNodeRequest(node_type='Agent', specific_library_name='Griptape Nodes Library', node_name='Agent', metadata={'position': {'x': 1019.7343749999998, 'y': 194.66666666666674}, 'tempId': 'placing-1755102288879-fc9hag', 'library_node_metadata': NodeMetadata(category='agents', description='Creates an AI agent with conversation memory and the ability to use tools', display_name='Agent', tags=None, icon=None, color=None, group=None), 'library': 'Griptape Nodes Library', 'node_type': 'Agent', 'showaddparameter': False, 'category': 'agents', 'size': {'width': 402, 'height': 544}}, initial_setup=True)).node_name
    node3_name = GriptapeNodes.handle_request(CreateNodeRequest(node_type='GenerateImage', specific_library_name='Griptape Nodes Library', node_name='Generate Image', metadata={'position': {'x': 1019.7343749999998, 'y': 812.0000000000001}, 'tempId': 'placing-1755102324455-3v9t4i', 'library_node_metadata': NodeMetadata(category='image', description='Generates an image using Griptape Cloud, or other provided image generation models', display_name='Generate Image', tags=None, icon=None, color=None, group='tasks'), 'library': 'Griptape Nodes Library', 'node_type': 'GenerateImage', 'showaddparameter': False, 'category': 'image', 'size': {'width': 402, 'height': 566}}, initial_setup=True)).node_name
    with GriptapeNodes.ContextManager().node(node3_name):
        GriptapeNodes.handle_request(AlterParameterDetailsRequest(parameter_name='prompt', mode_allowed_property=False, initial_setup=True))
    GriptapeNodes.handle_request(CreateConnectionRequest(source_node_name=node2_name, source_parameter_name='output', target_node_name=node1_name, target_parameter_name='output', initial_setup=True))
    GriptapeNodes.handle_request(CreateConnectionRequest(source_node_name=node0_name, source_parameter_name='prompt', target_node_name=node2_name, target_parameter_name='prompt', initial_setup=True))
    GriptapeNodes.handle_request(CreateConnectionRequest(source_node_name=node3_name, source_parameter_name='output', target_node_name=node1_name, target_parameter_name='output_1', initial_setup=True))
    GriptapeNodes.handle_request(CreateConnectionRequest(source_node_name=node0_name, source_parameter_name='prompt', target_node_name=node3_name, target_parameter_name='prompt', initial_setup=True))
    GriptapeNodes.handle_request(CreateConnectionRequest(source_node_name=node0_name, source_parameter_name='exec_out', target_node_name=node3_name, target_parameter_name='exec_in', initial_setup=True))
    GriptapeNodes.handle_request(CreateConnectionRequest(source_node_name=node3_name, source_parameter_name='exec_out', target_node_name=node1_name, target_parameter_name='exec_in', initial_setup=True))
    GriptapeNodes.handle_request(CreateConnectionRequest(source_node_name=node2_name, source_parameter_name='exec_out', target_node_name=node1_name, target_parameter_name='exec_in', initial_setup=True))
    with GriptapeNodes.ContextManager().node(node0_name):
        GriptapeNodes.handle_request(SetParameterValueRequest(parameter_name='prompt', node_name=node0_name, value=top_level_unique_values_dict['45c4f65f-d2cc-460a-a3cf-bd32794756bf'], initial_setup=True, is_output=False))
    with GriptapeNodes.ContextManager().node(node1_name):
        GriptapeNodes.handle_request(SetParameterValueRequest(parameter_name='output', node_name=node1_name, value=top_level_unique_values_dict['b0fe2cab-a90c-4f2c-91c7-e18b61ce798d'], initial_setup=True, is_output=False))
        GriptapeNodes.handle_request(SetParameterValueRequest(parameter_name='output_1', node_name=node1_name, value=top_level_unique_values_dict['d716d214-35cd-4c36-8155-d5e23f7bb8f4'], initial_setup=True, is_output=False))
    with GriptapeNodes.ContextManager().node(node2_name):
        GriptapeNodes.handle_request(SetParameterValueRequest(parameter_name='model', node_name=node2_name, value=top_level_unique_values_dict['f29e8644-90a7-4a03-a18c-980f87bf2691'], initial_setup=True, is_output=False))
        GriptapeNodes.handle_request(SetParameterValueRequest(parameter_name='prompt', node_name=node2_name, value=top_level_unique_values_dict['45c4f65f-d2cc-460a-a3cf-bd32794756bf'], initial_setup=True, is_output=False))
        GriptapeNodes.handle_request(SetParameterValueRequest(parameter_name='additional_context', node_name=node2_name, value=top_level_unique_values_dict['79f75ca3-6e5f-46c7-94fa-fc02928119a5'], initial_setup=True, is_output=False))
        GriptapeNodes.handle_request(SetParameterValueRequest(parameter_name='tools', node_name=node2_name, value=top_level_unique_values_dict['5c7cee06-4e26-4a04-8c81-b2aa051eda42'], initial_setup=True, is_output=False))
        GriptapeNodes.handle_request(SetParameterValueRequest(parameter_name='rulesets', node_name=node2_name, value=top_level_unique_values_dict['dfb23919-18cd-4bdd-a06d-0bff8c67d898'], initial_setup=True, is_output=False))
        GriptapeNodes.handle_request(SetParameterValueRequest(parameter_name='output', node_name=node2_name, value=top_level_unique_values_dict['79f75ca3-6e5f-46c7-94fa-fc02928119a5'], initial_setup=True, is_output=False))
        GriptapeNodes.handle_request(SetParameterValueRequest(parameter_name='include_details', node_name=node2_name, value=top_level_unique_values_dict['0538a850-9895-46de-b7ba-f48faf755ac3'], initial_setup=True, is_output=False))
    with GriptapeNodes.ContextManager().node(node3_name):
        GriptapeNodes.handle_request(SetParameterValueRequest(parameter_name='model', node_name=node3_name, value=top_level_unique_values_dict['44c68b3b-cfed-4211-bd98-d041dbd02440'], initial_setup=True, is_output=False))
        GriptapeNodes.handle_request(SetParameterValueRequest(parameter_name='prompt', node_name=node3_name, value=top_level_unique_values_dict['45c4f65f-d2cc-460a-a3cf-bd32794756bf'], initial_setup=True, is_output=False))
        GriptapeNodes.handle_request(SetParameterValueRequest(parameter_name='image_size', node_name=node3_name, value=top_level_unique_values_dict['dca13c47-bca4-42cb-a5d9-17ff684205b8'], initial_setup=True, is_output=False))
        GriptapeNodes.handle_request(SetParameterValueRequest(parameter_name='enhance_prompt', node_name=node3_name, value=top_level_unique_values_dict['0538a850-9895-46de-b7ba-f48faf755ac3'], initial_setup=True, is_output=False))
        GriptapeNodes.handle_request(SetParameterValueRequest(parameter_name='include_details', node_name=node3_name, value=top_level_unique_values_dict['0538a850-9895-46de-b7ba-f48faf755ac3'], initial_setup=True, is_output=False))

def _ensure_workflow_context():
    context_manager = GriptapeNodes.ContextManager()
    if not context_manager.has_current_flow():
        top_level_flow_request = GetTopLevelFlowRequest()
        top_level_flow_result = GriptapeNodes.handle_request(top_level_flow_request)
        if isinstance(top_level_flow_result, GetTopLevelFlowResultSuccess) and top_level_flow_result.flow_name is not None:
            flow_manager = GriptapeNodes.FlowManager()
            flow_obj = flow_manager.get_flow_by_name(top_level_flow_result.flow_name)
            context_manager.push_flow(flow_obj)

def execute_workflow(input: dict, storage_backend: str='local', workflow_executor: WorkflowExecutor | None=None) -> dict | None:
    _ensure_workflow_context()
    workflow_executor = workflow_executor or LocalWorkflowExecutor()
    workflow_executor.run(workflow_name='ControlFlow_1', flow_input=input, storage_backend=storage_backend)
    return workflow_executor.output

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--storage-backend', choices=['local', 'gtc'], default='local', help="Storage backend to use: 'local' for local filesystem or 'gtc' for Griptape Cloud")
    parser.add_argument('--json-input', default=None, help='JSON string containing parameter values. Takes precedence over individual parameter arguments if provided.')
    parser.add_argument('--prompt', default=None, help='New parameter')
    args = parser.parse_args()
    flow_input = {}
    if args.json_input is not None:
        flow_input = json.loads(args.json_input)
    if args.json_input is None:
        if 'Start Flow' not in flow_input:
            flow_input['Start Flow'] = {}
        if args.prompt is not None:
            flow_input['Start Flow']['prompt'] = args.prompt
    workflow_output = execute_workflow(input=flow_input, storage_backend=args.storage_backend)
    print(workflow_output)
