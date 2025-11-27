# /// script
# dependencies = []
# 
# [tool.griptape-nodes]
# name = "prompt an image"
# schema_version = "0.13.0"
# engine_version_created_with = "0.64.1"
# node_libraries_referenced = [["Griptape Nodes Library", "0.51.1"]]
# node_types_used = [["Griptape Nodes Library", "GenerateImage"], ["Griptape Nodes Library", "Note"]]
# image = "https://raw.githubusercontent.com/griptape-ai/griptape-nodes/refs/heads/main/libraries/griptape_nodes_library/workflows/templates/thumbnail_prompt_an_image.webp"
# description = "The simplest image generation workflow."
# is_griptape_provided = true
# is_template = true
# creation_date = 2025-11-27T16:07:21.820471Z
# last_modified_date = 2025-11-27T16:07:21.837083Z
# 
# ///

import pickle
from griptape_nodes.node_library.library_registry import IconVariant, NodeDeprecationMetadata, NodeMetadata
from griptape_nodes.retained_mode.events.connection_events import CreateConnectionRequest
from griptape_nodes.retained_mode.events.flow_events import CreateFlowRequest
from griptape_nodes.retained_mode.events.library_events import LoadLibrariesRequest
from griptape_nodes.retained_mode.events.node_events import CreateNodeGroupRequest, CreateNodeRequest
from griptape_nodes.retained_mode.events.parameter_events import AddParameterToNodeRequest, AlterParameterDetailsRequest, SetParameterValueRequest
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

GriptapeNodes.handle_request(LoadLibrariesRequest())

context_manager = GriptapeNodes.ContextManager()

if not context_manager.has_current_workflow():
    context_manager.push_workflow(workflow_name='prompt_an_image_1')

"""
1. We've collated all of the unique parameter values into a dictionary so that we do not have to duplicate them.
   This minimizes the size of the code, especially for large objects like serialized image files.
2. We're using a prefix so that it's clear which Flow these values are associated with.
3. The values are serialized using pickle, which is a binary format. This makes them harder to read, but makes
   them consistently save and load. It allows us to serialize complex objects like custom classes, which otherwise
   would be difficult to serialize.
"""
top_level_unique_values_dict = {'8ec41c1b-7620-4b10-a589-7a1c731dcefb': pickle.loads(b'\x80\x04\x95X\x01\x00\x00\x00\x00\x00\x00XQ\x01\x00\x00This workflow serves as the lesson material for the tutorial located at:\n\nhttps://docs.griptapenodes.com/en/stable/ftue/01_prompt_an_image/FTUE_01_prompt_an_image/\n\nThe concepts covered are:\n\n- Opening saved workflows\n- Using text prompts to generate images using the GenerateImage node\n- Running entire workflows, or just specific nodes\x94.'), 'e2affafd-7c82-4fda-a7e9-536ebc374b61': pickle.loads(b"\x80\x04\x95\xf8\x00\x00\x00\x00\x00\x00\x00\x8c\xf4If you're following along with our Getting Started tutorials, check out the next workflow: Coordinating Agents.\n\nLoad the next tutorial page here:\nhttps://docs.griptapenodes.com/en/stable/ftue/02_coordinating_agents/FTUE_02_coordinating_agents/\x94."), '8d318a1b-af24-4e5c-9133-7dc5f61e85bc': pickle.loads(b'\x80\x04\x95\x0f\x00\x00\x00\x00\x00\x00\x00\x8c\x0bgpt-image-1\x94.'), '06d28896-9104-44d5-8a8a-63d9f686bda2': pickle.loads(b'\x80\x04\x95#\x00\x00\x00\x00\x00\x00\x00\x8c\x1fA potato making an oil painting\x94.'), '258c1bbf-6475-4c32-89d2-92dd01401a0d': pickle.loads(b'\x80\x04\x95\r\x00\x00\x00\x00\x00\x00\x00\x8c\t1024x1024\x94.')}

'# Create the Flow, then do work within it as context.'

flow0_name = GriptapeNodes.handle_request(CreateFlowRequest(parent_flow_name=None, set_as_new_context=False, metadata={})).flow_name

with GriptapeNodes.ContextManager().flow(flow0_name):
    node0_name = GriptapeNodes.handle_request(CreateNodeRequest(node_type='Note', specific_library_name='Griptape Nodes Library', node_name='ReadMe', metadata={'position': {'x': 0, 'y': -400}, 'size': {'width': 1000, 'height': 350}, 'library_node_metadata': NodeMetadata(category='misc', description='Create a note node to provide helpful context in your workflow', display_name='Note', tags=None, icon='notepad-text', color=None, group='create', deprecation=None), 'library': 'Griptape Nodes Library', 'node_type': 'Note'}, initial_setup=True)).node_name
    node1_name = GriptapeNodes.handle_request(CreateNodeRequest(node_type='Note', specific_library_name='Griptape Nodes Library', node_name='NextStep', metadata={'position': {'x': 676.5930043339541, 'y': 495.9826304547828}, 'size': {'width': 998, 'height': 234}, 'library_node_metadata': {'category': 'misc', 'description': 'Create a note node to provide helpful context in your workflow'}, 'library': 'Griptape Nodes Library', 'node_type': 'Note', 'category': 'misc', 'showaddparameter': False}, initial_setup=True)).node_name
    node2_name = GriptapeNodes.handle_request(CreateNodeRequest(node_type='GenerateImage', specific_library_name='Griptape Nodes Library', node_name='GenerateImage_1', metadata={'position': {'x': 8.029015213045938, 'y': 4.982630454782765}, 'tempId': 'placing-1747420608205-t8bruk', 'library_node_metadata': NodeMetadata(category='image', description='Generates an image using Griptape Cloud, or other provided image generation models', display_name='Generate Image', tags=None, icon=None, color=None, group='create', deprecation=None), 'library': 'Griptape Nodes Library', 'node_type': 'GenerateImage', 'category': 'image', 'size': {'width': 422, 'height': 725}}, initial_setup=True)).node_name
    with GriptapeNodes.ContextManager().node(node2_name):
        GriptapeNodes.handle_request(AlterParameterDetailsRequest(parameter_name='image_size', ui_options={'simple_dropdown': ['1024x1024', '1536x1024', '1024x1536'], 'show_search': True, 'search_filter': ''}, initial_setup=True))
    with GriptapeNodes.ContextManager().node(node0_name):
        GriptapeNodes.handle_request(SetParameterValueRequest(parameter_name='note', node_name=node0_name, value=top_level_unique_values_dict['8ec41c1b-7620-4b10-a589-7a1c731dcefb'], initial_setup=True, is_output=False))
    with GriptapeNodes.ContextManager().node(node1_name):
        GriptapeNodes.handle_request(SetParameterValueRequest(parameter_name='note', node_name=node1_name, value=top_level_unique_values_dict['e2affafd-7c82-4fda-a7e9-536ebc374b61'], initial_setup=True, is_output=False))
    with GriptapeNodes.ContextManager().node(node2_name):
        GriptapeNodes.handle_request(SetParameterValueRequest(parameter_name='model', node_name=node2_name, value=top_level_unique_values_dict['8d318a1b-af24-4e5c-9133-7dc5f61e85bc'], initial_setup=True, is_output=False))
        GriptapeNodes.handle_request(SetParameterValueRequest(parameter_name='prompt', node_name=node2_name, value=top_level_unique_values_dict['06d28896-9104-44d5-8a8a-63d9f686bda2'], initial_setup=True, is_output=False))
        GriptapeNodes.handle_request(SetParameterValueRequest(parameter_name='image_size', node_name=node2_name, value=top_level_unique_values_dict['258c1bbf-6475-4c32-89d2-92dd01401a0d'], initial_setup=True, is_output=False))
