# /// script
# dependencies = []
# 
# [tool.griptape-nodes]
# name = "griptape_cloud_published_workflow_template"
# schema_version = "0.14.0"
# engine_version_created_with = "0.67.0"
# node_libraries_referenced = [["Griptape Cloud Library", "0.67.0"], ["Griptape Nodes Library", "0.56.1"]]
# node_types_used = [["Griptape Cloud Library", "GriptapeCloudEndFlow"], ["Griptape Cloud Library", "GriptapeCloudStartFlow"], ["Griptape Nodes Library", "Agent"], ["Griptape Nodes Library", "MergeTexts"], ["Griptape Nodes Library", "Note"], ["Griptape Nodes Library", "SeedreamImageGeneration"]]
# description = "Example image generation workflow that can be published to Griptape Cloud."
# image = "https://raw.githubusercontent.com/griptape-ai/griptape-nodes/refs/heads/main/libraries/griptape_cloud/workflows/templates/thumbnail_griptape_cloud_published_workflow_template.webp"
# is_griptape_provided = true
# is_template = true
# creation_date = 2026-01-09T17:35:29.610973Z
# last_modified_date = 2026-01-09T17:44:12.416006Z
# workflow_shape = "{\"inputs\":{\"Griptape Cloud Start Flow\":{\"exec_out\":{\"name\":\"exec_out\",\"tooltip\":\"Connection to the next node in the execution chain\",\"type\":\"parametercontroltype\",\"input_types\":[\"parametercontroltype\"],\"output_type\":\"parametercontroltype\",\"default_value\":null,\"tooltip_as_input\":null,\"tooltip_as_property\":null,\"tooltip_as_output\":null,\"ui_options\":{\"display_name\":\"Flow Out\"},\"settable\":true,\"is_user_defined\":true,\"private\":false,\"parent_container_name\":null,\"parent_element_name\":null},\"structure_id\":{\"name\":\"structure_id\",\"tooltip\":\"The structure ID of the published workflow\",\"type\":\"str\",\"input_types\":[\"str\"],\"output_type\":\"str\",\"default_value\":null,\"tooltip_as_input\":null,\"tooltip_as_property\":null,\"tooltip_as_output\":null,\"ui_options\":{\"button_label\":\"\",\"variant\":\"secondary\",\"size\":\"default\",\"state\":\"normal\",\"full_width\":false,\"button_icon\":\"link\",\"iconPosition\":\"left\",\"tooltip\":\"View Structure in Griptape Cloud\",\"hide\":true},\"settable\":true,\"is_user_defined\":true,\"private\":false,\"parent_container_name\":null,\"parent_element_name\":null},\"structure_name\":{\"name\":\"structure_name\",\"tooltip\":\"The name for the Griptape Cloud Structure.\",\"type\":\"str\",\"input_types\":[\"str\"],\"output_type\":\"str\",\"default_value\":null,\"tooltip_as_input\":null,\"tooltip_as_property\":null,\"tooltip_as_output\":null,\"ui_options\":{},\"settable\":true,\"is_user_defined\":true,\"private\":false,\"parent_container_name\":null,\"parent_element_name\":null},\"structure_description\":{\"name\":\"structure_description\",\"tooltip\":\"The description for the Griptape Cloud Structure.\",\"type\":\"str\",\"input_types\":[\"str\"],\"output_type\":\"str\",\"default_value\":null,\"tooltip_as_input\":null,\"tooltip_as_property\":null,\"tooltip_as_output\":null,\"ui_options\":{},\"settable\":true,\"is_user_defined\":true,\"private\":false,\"parent_container_name\":null,\"parent_element_name\":null},\"enable_webhook_integration\":{\"name\":\"enable_webhook_integration\",\"tooltip\":\"Whether to enable a webhook integration for the Structure.\",\"type\":\"bool\",\"input_types\":[\"bool\"],\"output_type\":\"bool\",\"default_value\":false,\"tooltip_as_input\":null,\"tooltip_as_property\":null,\"tooltip_as_output\":null,\"ui_options\":{},\"settable\":true,\"is_user_defined\":true,\"private\":false,\"parent_container_name\":null,\"parent_element_name\":null},\"webhook_url\":{\"name\":\"webhook_url\",\"tooltip\":\"The webhook URL for the published workflow\",\"type\":\"str\",\"input_types\":[\"str\"],\"output_type\":\"str\",\"default_value\":null,\"tooltip_as_input\":null,\"tooltip_as_property\":null,\"tooltip_as_output\":null,\"ui_options\":{\"button_label\":\"\",\"variant\":\"secondary\",\"size\":\"default\",\"state\":\"normal\",\"full_width\":false,\"button_icon\":\"webhook\",\"iconPosition\":\"left\",\"tooltip\":\"Get Webhook URL\",\"placeholder_text\":\"Click button to retrieve webhook URL after publishing\",\"hide\":true},\"settable\":true,\"is_user_defined\":true,\"private\":false,\"parent_container_name\":null,\"parent_element_name\":null},\"integration_id\":{\"name\":\"integration_id\",\"tooltip\":\"The integration ID of the published workflow\",\"type\":\"str\",\"input_types\":[\"str\"],\"output_type\":\"str\",\"default_value\":null,\"tooltip_as_input\":null,\"tooltip_as_property\":null,\"tooltip_as_output\":null,\"ui_options\":{\"button_label\":\"\",\"variant\":\"secondary\",\"size\":\"default\",\"state\":\"normal\",\"full_width\":false,\"button_icon\":\"link\",\"iconPosition\":\"left\",\"tooltip\":\"View Integration in Griptape Cloud\",\"hide\":true},\"settable\":true,\"is_user_defined\":true,\"private\":false,\"parent_container_name\":null,\"parent_element_name\":null},\"payload\":{\"name\":\"payload\",\"tooltip\":\"The payload for the webhook integration.\",\"type\":\"json\",\"input_types\":[\"json\",\"str\",\"dict\"],\"output_type\":\"json\",\"default_value\":null,\"tooltip_as_input\":null,\"tooltip_as_property\":null,\"tooltip_as_output\":null,\"ui_options\":{\"display_name\":\"Webhook Payload\",\"hide\":true},\"settable\":true,\"is_user_defined\":true,\"private\":false,\"parent_container_name\":null,\"parent_element_name\":null},\"query_params\":{\"name\":\"query_params\",\"tooltip\":\"The query parameters for the webhook integration.\",\"type\":\"json\",\"input_types\":[\"json\",\"str\",\"dict\"],\"output_type\":\"json\",\"default_value\":null,\"tooltip_as_input\":null,\"tooltip_as_property\":null,\"tooltip_as_output\":null,\"ui_options\":{\"display_name\":\"Webhook Query Params\",\"hide\":true},\"settable\":true,\"is_user_defined\":true,\"private\":false,\"parent_container_name\":null,\"parent_element_name\":null},\"headers\":{\"name\":\"headers\",\"tooltip\":\"The headers for the webhook integration.\",\"type\":\"json\",\"input_types\":[\"json\",\"str\",\"dict\"],\"output_type\":\"json\",\"default_value\":null,\"tooltip_as_input\":null,\"tooltip_as_property\":null,\"tooltip_as_output\":null,\"ui_options\":{\"display_name\":\"Webhook Headers\",\"hide\":true},\"settable\":true,\"is_user_defined\":true,\"private\":false,\"parent_container_name\":null,\"parent_element_name\":null},\"prompt\":{\"name\":\"prompt\",\"tooltip\":\"Enter text/string for prompt.\",\"type\":\"str\",\"input_types\":[\"str\"],\"output_type\":\"str\",\"default_value\":\"skateboard\",\"tooltip_as_input\":null,\"tooltip_as_property\":null,\"tooltip_as_output\":null,\"ui_options\":{\"is_custom\":true,\"is_user_added\":true},\"settable\":true,\"is_user_defined\":true,\"private\":false,\"parent_container_name\":null,\"parent_element_name\":null}}},\"outputs\":{\"Griptape Cloud End Flow\":{\"exec_in\":{\"name\":\"exec_in\",\"tooltip\":\"Control path when the flow completed successfully\",\"type\":\"parametercontroltype\",\"input_types\":[\"parametercontroltype\"],\"output_type\":\"parametercontroltype\",\"default_value\":null,\"tooltip_as_input\":null,\"tooltip_as_property\":null,\"tooltip_as_output\":null,\"ui_options\":{\"display_name\":\"Succeeded\"},\"settable\":true,\"is_user_defined\":true,\"private\":false,\"parent_container_name\":null,\"parent_element_name\":null},\"failed\":{\"name\":\"failed\",\"tooltip\":\"Control path when the flow failed\",\"type\":\"parametercontroltype\",\"input_types\":[\"parametercontroltype\"],\"output_type\":\"parametercontroltype\",\"default_value\":null,\"tooltip_as_input\":null,\"tooltip_as_property\":null,\"tooltip_as_output\":null,\"ui_options\":{\"display_name\":\"Failed\"},\"settable\":true,\"is_user_defined\":true,\"private\":false,\"parent_container_name\":null,\"parent_element_name\":null},\"was_successful\":{\"name\":\"was_successful\",\"tooltip\":\"Indicates whether it completed without errors.\",\"type\":\"bool\",\"input_types\":[\"bool\"],\"output_type\":\"bool\",\"default_value\":false,\"tooltip_as_input\":null,\"tooltip_as_property\":null,\"tooltip_as_output\":null,\"ui_options\":{},\"settable\":false,\"is_user_defined\":true,\"private\":false,\"parent_container_name\":null,\"parent_element_name\":null},\"result_details\":{\"name\":\"result_details\",\"tooltip\":\"Details about the operation result\",\"type\":\"str\",\"input_types\":[\"str\"],\"output_type\":\"str\",\"default_value\":null,\"tooltip_as_input\":null,\"tooltip_as_property\":null,\"tooltip_as_output\":null,\"ui_options\":{\"multiline\":true,\"placeholder_text\":\"Details about the completion or failure will be shown here.\"},\"settable\":false,\"is_user_defined\":true,\"private\":false,\"parent_container_name\":null,\"parent_element_name\":null},\"image_prompt\":{\"name\":\"image_prompt\",\"tooltip\":\"Enter text/string for image_prompt.\",\"type\":\"str\",\"input_types\":[\"str\"],\"output_type\":\"str\",\"default_value\":null,\"tooltip_as_input\":null,\"tooltip_as_property\":null,\"tooltip_as_output\":null,\"ui_options\":{\"is_custom\":true,\"is_user_added\":true},\"settable\":true,\"is_user_defined\":true,\"private\":false,\"parent_container_name\":null,\"parent_element_name\":null},\"image\":{\"name\":\"image\",\"tooltip\":\"Enter ImageArtifact for image. Accepts: ImageArtifact, ImageUrlArtifact.\",\"type\":\"ImageArtifact\",\"input_types\":[\"ImageArtifact\",\"ImageUrlArtifact\"],\"output_type\":\"ImageArtifact\",\"default_value\":null,\"tooltip_as_input\":null,\"tooltip_as_property\":null,\"tooltip_as_output\":null,\"ui_options\":{\"is_custom\":true,\"is_user_added\":true},\"settable\":true,\"is_user_defined\":true,\"private\":false,\"parent_container_name\":null,\"parent_element_name\":null}}}}"
# 
# ///

import argparse
import asyncio
import json
import pickle
from griptape_nodes.bootstrap.workflow_executors.local_workflow_executor import LocalWorkflowExecutor
from griptape_nodes.bootstrap.workflow_executors.workflow_executor import WorkflowExecutor
from griptape_nodes.drivers.storage.storage_backend import StorageBackend
from griptape_nodes.node_library.library_registry import IconVariant, NodeDeprecationMetadata, NodeMetadata
from griptape_nodes.retained_mode.events.connection_events import CreateConnectionRequest
from griptape_nodes.retained_mode.events.flow_events import CreateFlowRequest, GetTopLevelFlowRequest, GetTopLevelFlowResultSuccess
from griptape_nodes.retained_mode.events.library_events import LoadLibrariesRequest
from griptape_nodes.retained_mode.events.node_events import CreateNodeRequest
from griptape_nodes.retained_mode.events.parameter_events import AddParameterToNodeRequest, AlterParameterDetailsRequest, AlterParameterGroupDetailsRequest, SetParameterValueRequest
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

GriptapeNodes.handle_request(LoadLibrariesRequest())

context_manager = GriptapeNodes.ContextManager()

if not context_manager.has_current_workflow():
    context_manager.push_workflow(workflow_name='griptape_cloud_published_workflow_template')

"""
1. We've collated all of the unique parameter values into a dictionary so that we do not have to duplicate them.
   This minimizes the size of the code, especially for large objects like serialized image files.
2. We're using a prefix so that it's clear which Flow these values are associated with.
3. The values are serialized using pickle, which is a binary format. This makes them harder to read, but makes
   them consistently save and load. It allows us to serialize complex objects like custom classes, which otherwise
   would be difficult to serialize.
"""
top_level_unique_values_dict = {'d952dbe5-800c-4dec-a886-58f9a569670b': pickle.loads(b'\x80\x04\x89.'), '1fd31c15-998b-4a69-b3cb-8674c7e54a57': pickle.loads(b'\x80\x04\x95\x0e\x00\x00\x00\x00\x00\x00\x00\x8c\nskateboard\x94.'), '8c1ed10f-1d41-4bf9-810b-0146073840eb': pickle.loads(b'\x80\x04\x95]\x00\x00\x00\x00\x00\x00\x00\x8cYTake the following input prompt, and use it to create a detailed image generation prompt:\x94.'), 'c0a19e15-4ef8-4f83-96c5-7734712607b1': pickle.loads(b'\x80\x04\x95\x08\x00\x00\x00\x00\x00\x00\x00\x8c\x04\\n\\n\x94.'), '87dfa916-f702-4690-93c7-052480303020': pickle.loads(b'\x80\x04\x95i\x00\x00\x00\x00\x00\x00\x00\x8ceTake the following input prompt, and use it to create a detailed image generation prompt:\n\nskateboard\x94.'), '81df0436-3724-4519-8e77-0dd3c7a5788d': pickle.loads(b'\x80\x04\x95\x0b\x00\x00\x00\x00\x00\x00\x00\x8c\x07gpt-4.1\x94.'), '27b40cc4-c661-4e82-9797-21e8d2745295': pickle.loads(b'\x80\x04}\x94.'), 'a987dd01-7e90-42a6-9342-b49b0147539c': pickle.loads(b'\x80\x04\x95\x04\x00\x00\x00\x00\x00\x00\x00\x8c\x00\x94.'), 'a4b0107d-bf0d-4d28-b784-ebda04a6e475': pickle.loads(b'\x80\x04]\x94.'), '691c108e-9b9b-48d8-82db-44839715d330': pickle.loads(b'\x80\x04]\x94.'), '6f4e6184-6fa0-4c4e-a13f-b23ad9348702': pickle.loads(b'\x80\x04\x95\x10\x00\x00\x00\x00\x00\x00\x00\x8c\x0cseedream-4.5\x94.'), '69212678-daf6-4e86-a8f1-6b855dd238f3': pickle.loads(b'\x80\x04]\x94.'), 'a55b2392-8baf-4fe2-a54d-83e78b158d9c': pickle.loads(b'\x80\x04\x95\x06\x00\x00\x00\x00\x00\x00\x00\x8c\x022K\x94.'), 'fe316ba4-2da9-4903-8d9c-32fcc9e73c20': pickle.loads(b'\x80\x04\x95\x06\x00\x00\x00\x00\x00\x00\x00J\xff\xff\xff\xff.'), '15628486-9135-493f-a579-d3e84880227a': pickle.loads(b'\x80\x04K\n.'), '63471b96-a12a-4078-aaf2-75d276fd1afd': pickle.loads(b'\x80\x04\x95\n\x00\x00\x00\x00\x00\x00\x00G@\x04\x00\x00\x00\x00\x00\x00.'), '5329398a-218a-4fc4-ba42-75c1fadf1f74': pickle.loads(b'\x80\x04\x95\xe4\x00\x00\x00\x00\x00\x00\x00\x8c\xe0The Griptape Cloud Start Flow node here exposes the input parameters that can be supplied for the workflow. \n\nA Start Flow node is a required node to have before publishing, and should be placed at the beginning of the flow.\x94.'), '0331ef2d-e679-45d9-ba67-5327992354ed': pickle.loads(b'\x80\x04\x95\xc7\x00\x00\x00\x00\x00\x00\x00\x8c\xc3This section of the workflow is just an example. This logic will be bundled up as a result of publishing, like a black box. The Start Flow inputs will be exposed, as well as the End Flow outputs.\x94.'), 'd3e1211b-0bb3-4518-99d6-63314de3f272': pickle.loads(b'\x80\x04\x95g\x00\x00\x00\x00\x00\x00\x00\x8ccThe End Flow node here exposes the outputs for this workflow. It is a required node for publishing.\x94.'), '2fd0a7af-7421-4c14-9f26-073329f3a326': pickle.loads(b'\x80\x04\x95a\x00\x00\x00\x00\x00\x00\x00\x8c]To publish this workflow, click the top right rocket icon, and choose Griptape Cloud Library!\x94.')}

'# Create the Flow, then do work within it as context.'

flow0_name = GriptapeNodes.handle_request(CreateFlowRequest(parent_flow_name=None, flow_name='ControlFlow_1', set_as_new_context=False, metadata={})).flow_name

with GriptapeNodes.ContextManager().flow(flow0_name):
    node0_name = GriptapeNodes.handle_request(CreateNodeRequest(node_type='GriptapeCloudStartFlow', specific_library_name='Griptape Cloud Library', node_name='Griptape Cloud Start Flow', metadata={'position': {'x': -223.91570464903003, 'y': 932}, 'tempId': 'placing-1767980322092-l6jan9', 'library_node_metadata': {'category': 'griptape_cloud/published_workflows', 'description': 'Node that defines the start of a workflow and passes parameters for a flow on Griptape Cloud.'}, 'library': 'Griptape Cloud Library', 'node_type': 'GriptapeCloudStartFlow', 'showaddparameter': True, 'size': {'width': 600, 'height': 827}, 'category': 'griptape_cloud/published_workflows'}, initial_setup=True)).node_name
    with GriptapeNodes.ContextManager().node(node0_name):
        GriptapeNodes.handle_request(AddParameterToNodeRequest(parameter_name='prompt', default_value='skateboard', tooltip='Enter text/string for prompt.', type='str', input_types=['str'], output_type='str', ui_options={'is_custom': True, 'is_user_added': True}, mode_allowed_input=False, mode_allowed_property=True, mode_allowed_output=True, initial_setup=True))
        GriptapeNodes.handle_request(AlterParameterGroupDetailsRequest(group_name='Structure Config', ui_options={'hide': False, 'collapsed': True}, initial_setup=True))
    node1_name = GriptapeNodes.handle_request(CreateNodeRequest(node_type='MergeTexts', specific_library_name='Griptape Nodes Library', node_name='Merge Texts', metadata={'position': {'x': 550, 'y': 932}, 'tempId': 'placing-1767980369997-kufb8', 'library_node_metadata': {'category': 'text', 'description': 'MergeTexts node'}, 'library': 'Griptape Nodes Library', 'node_type': 'MergeTexts', 'showaddparameter': False, 'size': {'width': 607, 'height': 846}, 'category': 'text'}, initial_setup=True)).node_name
    node2_name = GriptapeNodes.handle_request(CreateNodeRequest(node_type='Agent', specific_library_name='Griptape Nodes Library', node_name='Agent', metadata={'position': {'x': 1221.5, 'y': 928.1247767177401}, 'tempId': 'placing-1767980394742-4ko2uw', 'library_node_metadata': {'category': 'agents', 'description': 'Creates an AI agent with conversation memory and the ability to use tools'}, 'library': 'Griptape Nodes Library', 'node_type': 'Agent', 'showaddparameter': False, 'size': {'width': 600, 'height': 864}, 'category': 'agents'}, initial_setup=True)).node_name
    node3_name = GriptapeNodes.handle_request(CreateNodeRequest(node_type='SeedreamImageGeneration', specific_library_name='Griptape Nodes Library', node_name='Seedream Image Generation', metadata={'position': {'x': 1895.07724076892, 'y': 932}, 'tempId': 'placing-1767980431215-rtbbo', 'library_node_metadata': {'category': 'image', 'description': 'Generate images using Seedream models (seedream-4.0, seedream-3.0-t2i) via Griptape model proxy'}, 'library': 'Griptape Nodes Library', 'node_type': 'SeedreamImageGeneration', 'showaddparameter': False, 'size': {'width': 600, 'height': 858}, 'category': 'image'}, initial_setup=True)).node_name
    with GriptapeNodes.ContextManager().node(node3_name):
        GriptapeNodes.handle_request(AlterParameterGroupDetailsRequest(group_name='Status', ui_options={'collapsed': True}, initial_setup=True))
    node4_name = GriptapeNodes.handle_request(CreateNodeRequest(node_type='GriptapeCloudEndFlow', specific_library_name='Griptape Cloud Library', node_name='Griptape Cloud End Flow', metadata={'position': {'x': 2768.0107547629596, 'y': 948.6247767177402}, 'tempId': 'placing-1767980468862-m0twjm', 'library_node_metadata': {'category': 'griptape_cloud/published_workflows', 'description': 'Node that defines the end of a workflow and passes parameters for a flow on Griptape Cloud.'}, 'library': 'Griptape Cloud Library', 'node_type': 'GriptapeCloudEndFlow', 'showaddparameter': True, 'size': {'width': 600, 'height': 823}, 'category': 'griptape_cloud/published_workflows'}, initial_setup=True)).node_name
    with GriptapeNodes.ContextManager().node(node4_name):
        GriptapeNodes.handle_request(AddParameterToNodeRequest(parameter_name='image_prompt', tooltip='Enter text/string for image_prompt.', type='str', input_types=['str'], output_type='str', ui_options={'is_custom': True, 'is_user_added': True}, mode_allowed_input=True, mode_allowed_property=True, mode_allowed_output=False, initial_setup=True))
        GriptapeNodes.handle_request(AddParameterToNodeRequest(parameter_name='image', tooltip='Enter ImageArtifact for image. Accepts: ImageArtifact, ImageUrlArtifact.', type='ImageArtifact', input_types=['ImageArtifact', 'ImageUrlArtifact'], output_type='ImageArtifact', ui_options={'is_custom': True, 'is_user_added': True}, mode_allowed_input=True, mode_allowed_property=True, mode_allowed_output=False, initial_setup=True))
        GriptapeNodes.handle_request(AlterParameterGroupDetailsRequest(group_name='Status', ui_options={'collapsed': True}, initial_setup=True))
    node5_name = GriptapeNodes.handle_request(CreateNodeRequest(node_type='Note', specific_library_name='Griptape Nodes Library', node_name='Workflow Start', metadata={'position': {'x': -223.91570464903003, 'y': 489.38316050831463}, 'tempId': 'placing-1759960199321-1cotty', 'library_node_metadata': {'category': 'misc', 'description': 'Create a note node to provide helpful context in your workflow'}, 'library': 'Griptape Nodes Library', 'node_type': 'Note', 'showaddparameter': False, 'category': 'misc', 'size': {'width': 600, 'height': 356}}, initial_setup=True)).node_name
    node6_name = GriptapeNodes.handle_request(CreateNodeRequest(node_type='Note', specific_library_name='Griptape Nodes Library', node_name='Workflow Body', metadata={'position': {'x': 550, 'y': 500.3831605083146}, 'tempId': 'placing-1759960275375-u04md', 'library_node_metadata': {'category': 'misc', 'description': 'Create a note node to provide helpful context in your workflow'}, 'library': 'Griptape Nodes Library', 'node_type': 'Note', 'showaddparameter': False, 'size': {'width': 1943, 'height': 336}, 'category': 'misc'}, initial_setup=True)).node_name
    node7_name = GriptapeNodes.handle_request(CreateNodeRequest(node_type='Note', specific_library_name='Griptape Nodes Library', node_name='Workflow Output', metadata={'position': {'x': 2768.0107547629596, 'y': 500.3831605083146}, 'tempId': 'placing-1759960354172-8aukc', 'library_node_metadata': {'category': 'misc', 'description': 'Create a note node to provide helpful context in your workflow'}, 'library': 'Griptape Nodes Library', 'node_type': 'Note', 'showaddparameter': False, 'category': 'misc', 'size': {'width': 600, 'height': 334}}, initial_setup=True)).node_name
    node8_name = GriptapeNodes.handle_request(CreateNodeRequest(node_type='Note', specific_library_name='Griptape Nodes Library', node_name='Publishing', metadata={'position': {'x': 2768.0107547629596, 'y': 125.2367588211529}, 'tempId': 'placing-1759960393090-qtlpje', 'library_node_metadata': {'category': 'misc', 'description': 'Create a note node to provide helpful context in your workflow'}, 'library': 'Griptape Nodes Library', 'node_type': 'Note', 'showaddparameter': False, 'size': {'width': 600, 'height': 319}, 'category': 'misc'}, initial_setup=True)).node_name
    GriptapeNodes.handle_request(CreateConnectionRequest(source_node_name=node0_name, source_parameter_name='prompt', target_node_name=node1_name, target_parameter_name='input_2', initial_setup=True))
    GriptapeNodes.handle_request(CreateConnectionRequest(source_node_name=node1_name, source_parameter_name='output', target_node_name=node2_name, target_parameter_name='prompt', initial_setup=True))
    GriptapeNodes.handle_request(CreateConnectionRequest(source_node_name=node2_name, source_parameter_name='output', target_node_name=node4_name, target_parameter_name='image_prompt', initial_setup=True))
    GriptapeNodes.handle_request(CreateConnectionRequest(source_node_name=node2_name, source_parameter_name='output', target_node_name=node3_name, target_parameter_name='prompt', initial_setup=True))
    GriptapeNodes.handle_request(CreateConnectionRequest(source_node_name=node3_name, source_parameter_name='image_url', target_node_name=node4_name, target_parameter_name='image', initial_setup=True))
    with GriptapeNodes.ContextManager().node(node0_name):
        GriptapeNodes.handle_request(SetParameterValueRequest(parameter_name='enable_webhook_integration', node_name=node0_name, value=top_level_unique_values_dict['d952dbe5-800c-4dec-a886-58f9a569670b'], initial_setup=True, is_output=False))
        GriptapeNodes.handle_request(SetParameterValueRequest(parameter_name='prompt', node_name=node0_name, value=top_level_unique_values_dict['1fd31c15-998b-4a69-b3cb-8674c7e54a57'], initial_setup=True, is_output=False))
    with GriptapeNodes.ContextManager().node(node1_name):
        GriptapeNodes.handle_request(SetParameterValueRequest(parameter_name='input_1', node_name=node1_name, value=top_level_unique_values_dict['8c1ed10f-1d41-4bf9-810b-0146073840eb'], initial_setup=True, is_output=False))
        GriptapeNodes.handle_request(SetParameterValueRequest(parameter_name='input_2', node_name=node1_name, value=top_level_unique_values_dict['1fd31c15-998b-4a69-b3cb-8674c7e54a57'], initial_setup=True, is_output=False))
        GriptapeNodes.handle_request(SetParameterValueRequest(parameter_name='merge_string', node_name=node1_name, value=top_level_unique_values_dict['c0a19e15-4ef8-4f83-96c5-7734712607b1'], initial_setup=True, is_output=False))
        GriptapeNodes.handle_request(SetParameterValueRequest(parameter_name='whitespace', node_name=node1_name, value=top_level_unique_values_dict['d952dbe5-800c-4dec-a886-58f9a569670b'], initial_setup=True, is_output=False))
        GriptapeNodes.handle_request(SetParameterValueRequest(parameter_name='output', node_name=node1_name, value=top_level_unique_values_dict['87dfa916-f702-4690-93c7-052480303020'], initial_setup=True, is_output=False))
        GriptapeNodes.handle_request(SetParameterValueRequest(parameter_name='output', node_name=node1_name, value=top_level_unique_values_dict['87dfa916-f702-4690-93c7-052480303020'], initial_setup=True, is_output=True))
    with GriptapeNodes.ContextManager().node(node2_name):
        GriptapeNodes.handle_request(SetParameterValueRequest(parameter_name='model', node_name=node2_name, value=top_level_unique_values_dict['81df0436-3724-4519-8e77-0dd3c7a5788d'], initial_setup=True, is_output=False))
        GriptapeNodes.handle_request(SetParameterValueRequest(parameter_name='agent_memory', node_name=node2_name, value=top_level_unique_values_dict['27b40cc4-c661-4e82-9797-21e8d2745295'], initial_setup=True, is_output=False))
        GriptapeNodes.handle_request(SetParameterValueRequest(parameter_name='prompt', node_name=node2_name, value=top_level_unique_values_dict['87dfa916-f702-4690-93c7-052480303020'], initial_setup=True, is_output=False))
        GriptapeNodes.handle_request(SetParameterValueRequest(parameter_name='additional_context', node_name=node2_name, value=top_level_unique_values_dict['a987dd01-7e90-42a6-9342-b49b0147539c'], initial_setup=True, is_output=False))
        GriptapeNodes.handle_request(SetParameterValueRequest(parameter_name='tools', node_name=node2_name, value=top_level_unique_values_dict['a4b0107d-bf0d-4d28-b784-ebda04a6e475'], initial_setup=True, is_output=False))
        GriptapeNodes.handle_request(SetParameterValueRequest(parameter_name='rulesets', node_name=node2_name, value=top_level_unique_values_dict['691c108e-9b9b-48d8-82db-44839715d330'], initial_setup=True, is_output=False))
        GriptapeNodes.handle_request(SetParameterValueRequest(parameter_name='output', node_name=node2_name, value=top_level_unique_values_dict['a987dd01-7e90-42a6-9342-b49b0147539c'], initial_setup=True, is_output=False))
        GriptapeNodes.handle_request(SetParameterValueRequest(parameter_name='include_details', node_name=node2_name, value=top_level_unique_values_dict['d952dbe5-800c-4dec-a886-58f9a569670b'], initial_setup=True, is_output=False))
    with GriptapeNodes.ContextManager().node(node3_name):
        GriptapeNodes.handle_request(SetParameterValueRequest(parameter_name='model', node_name=node3_name, value=top_level_unique_values_dict['6f4e6184-6fa0-4c4e-a13f-b23ad9348702'], initial_setup=True, is_output=False))
        GriptapeNodes.handle_request(SetParameterValueRequest(parameter_name='prompt', node_name=node3_name, value=top_level_unique_values_dict['a987dd01-7e90-42a6-9342-b49b0147539c'], initial_setup=True, is_output=False))
        GriptapeNodes.handle_request(SetParameterValueRequest(parameter_name='images', node_name=node3_name, value=top_level_unique_values_dict['69212678-daf6-4e86-a8f1-6b855dd238f3'], initial_setup=True, is_output=False))
        GriptapeNodes.handle_request(SetParameterValueRequest(parameter_name='size', node_name=node3_name, value=top_level_unique_values_dict['a55b2392-8baf-4fe2-a54d-83e78b158d9c'], initial_setup=True, is_output=False))
        GriptapeNodes.handle_request(SetParameterValueRequest(parameter_name='seed', node_name=node3_name, value=top_level_unique_values_dict['fe316ba4-2da9-4903-8d9c-32fcc9e73c20'], initial_setup=True, is_output=False))
        GriptapeNodes.handle_request(SetParameterValueRequest(parameter_name='max_images', node_name=node3_name, value=top_level_unique_values_dict['15628486-9135-493f-a579-d3e84880227a'], initial_setup=True, is_output=False))
        GriptapeNodes.handle_request(SetParameterValueRequest(parameter_name='guidance_scale', node_name=node3_name, value=top_level_unique_values_dict['63471b96-a12a-4078-aaf2-75d276fd1afd'], initial_setup=True, is_output=False))
        GriptapeNodes.handle_request(SetParameterValueRequest(parameter_name='was_successful', node_name=node3_name, value=top_level_unique_values_dict['d952dbe5-800c-4dec-a886-58f9a569670b'], initial_setup=True, is_output=False))
    with GriptapeNodes.ContextManager().node(node4_name):
        GriptapeNodes.handle_request(SetParameterValueRequest(parameter_name='was_successful', node_name=node4_name, value=top_level_unique_values_dict['d952dbe5-800c-4dec-a886-58f9a569670b'], initial_setup=True, is_output=False))
    with GriptapeNodes.ContextManager().node(node5_name):
        GriptapeNodes.handle_request(SetParameterValueRequest(parameter_name='note', node_name=node5_name, value=top_level_unique_values_dict['5329398a-218a-4fc4-ba42-75c1fadf1f74'], initial_setup=True, is_output=False))
    with GriptapeNodes.ContextManager().node(node6_name):
        GriptapeNodes.handle_request(SetParameterValueRequest(parameter_name='note', node_name=node6_name, value=top_level_unique_values_dict['0331ef2d-e679-45d9-ba67-5327992354ed'], initial_setup=True, is_output=False))
    with GriptapeNodes.ContextManager().node(node7_name):
        GriptapeNodes.handle_request(SetParameterValueRequest(parameter_name='note', node_name=node7_name, value=top_level_unique_values_dict['d3e1211b-0bb3-4518-99d6-63314de3f272'], initial_setup=True, is_output=False))
    with GriptapeNodes.ContextManager().node(node8_name):
        GriptapeNodes.handle_request(SetParameterValueRequest(parameter_name='note', node_name=node8_name, value=top_level_unique_values_dict['2fd0a7af-7421-4c14-9f26-073329f3a326'], initial_setup=True, is_output=False))

def _ensure_workflow_context():
    context_manager = GriptapeNodes.ContextManager()
    if not context_manager.has_current_flow():
        top_level_flow_request = GetTopLevelFlowRequest()
        top_level_flow_result = GriptapeNodes.handle_request(top_level_flow_request)
        if isinstance(top_level_flow_result, GetTopLevelFlowResultSuccess) and top_level_flow_result.flow_name is not None:
            flow_manager = GriptapeNodes.FlowManager()
            flow_obj = flow_manager.get_flow_by_name(top_level_flow_result.flow_name)
            context_manager.push_flow(flow_obj)

def execute_workflow(input: dict, storage_backend: str='local', workflow_executor: WorkflowExecutor | None=None, pickle_control_flow_result: bool=False) -> dict | None:
    return asyncio.run(aexecute_workflow(input=input, storage_backend=storage_backend, workflow_executor=workflow_executor, pickle_control_flow_result=pickle_control_flow_result))

async def aexecute_workflow(input: dict, storage_backend: str='local', workflow_executor: WorkflowExecutor | None=None, pickle_control_flow_result: bool=False) -> dict | None:
    _ensure_workflow_context()
    storage_backend_enum = StorageBackend(storage_backend)
    workflow_executor = workflow_executor or LocalWorkflowExecutor(storage_backend=storage_backend_enum)
    async with workflow_executor as executor:
        await executor.arun(flow_input=input, pickle_control_flow_result=pickle_control_flow_result)
    return executor.output

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--storage-backend', choices=['local', 'gtc'], default='local', help="Storage backend to use: 'local' for local filesystem or 'gtc' for Griptape Cloud")
    parser.add_argument('--json-input', default=None, help='JSON string containing parameter values. Takes precedence over individual parameter arguments if provided.')
    parser.add_argument('--exec_out', default=None, help='Connection to the next node in the execution chain')
    parser.add_argument('--structure_id', default=None, help='The structure ID of the published workflow')
    parser.add_argument('--structure_name', default=None, help='The name for the Griptape Cloud Structure.')
    parser.add_argument('--structure_description', default=None, help='The description for the Griptape Cloud Structure.')
    parser.add_argument('--enable_webhook_integration', default=None, help='Whether to enable a webhook integration for the Structure.')
    parser.add_argument('--webhook_url', default=None, help='The webhook URL for the published workflow')
    parser.add_argument('--integration_id', default=None, help='The integration ID of the published workflow')
    parser.add_argument('--payload', default=None, help='The payload for the webhook integration.')
    parser.add_argument('--query_params', default=None, help='The query parameters for the webhook integration.')
    parser.add_argument('--headers', default=None, help='The headers for the webhook integration.')
    parser.add_argument('--prompt', default=None, help='Enter text/string for prompt.')
    args = parser.parse_args()
    flow_input = {}
    if args.json_input is not None:
        flow_input = json.loads(args.json_input)
    if args.json_input is None:
        if 'Griptape Cloud Start Flow' not in flow_input:
            flow_input['Griptape Cloud Start Flow'] = {}
        if args.exec_out is not None:
            flow_input['Griptape Cloud Start Flow']['exec_out'] = args.exec_out
        if args.structure_id is not None:
            flow_input['Griptape Cloud Start Flow']['structure_id'] = args.structure_id
        if args.structure_name is not None:
            flow_input['Griptape Cloud Start Flow']['structure_name'] = args.structure_name
        if args.structure_description is not None:
            flow_input['Griptape Cloud Start Flow']['structure_description'] = args.structure_description
        if args.enable_webhook_integration is not None:
            flow_input['Griptape Cloud Start Flow']['enable_webhook_integration'] = args.enable_webhook_integration
        if args.webhook_url is not None:
            flow_input['Griptape Cloud Start Flow']['webhook_url'] = args.webhook_url
        if args.integration_id is not None:
            flow_input['Griptape Cloud Start Flow']['integration_id'] = args.integration_id
        if args.payload is not None:
            flow_input['Griptape Cloud Start Flow']['payload'] = args.payload
        if args.query_params is not None:
            flow_input['Griptape Cloud Start Flow']['query_params'] = args.query_params
        if args.headers is not None:
            flow_input['Griptape Cloud Start Flow']['headers'] = args.headers
        if args.prompt is not None:
            flow_input['Griptape Cloud Start Flow']['prompt'] = args.prompt
    workflow_output = execute_workflow(input=flow_input, storage_backend=args.storage_backend)
    print(workflow_output)
