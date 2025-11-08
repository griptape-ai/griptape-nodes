# /// script
# dependencies = []
#
# [tool.griptape-nodes]
# name = "griptape_cloud_published_workflow_template"
# schema_version = "0.9.0"
# engine_version_created_with = "0.58.0"
# node_libraries_referenced = [["Griptape Nodes Library", "0.50.0"]]
# node_types_used = [["Griptape Nodes Library", "Agent"], ["Griptape Nodes Library", "EndFlow"], ["Griptape Nodes Library", "MergeTexts"], ["Griptape Nodes Library", "SeedreamImageGeneration"], ["Griptape Nodes Library", "StartFlow"]]
# description = "Example image generation workflow that can be published to Griptape Cloud."
# image = "https://raw.githubusercontent.com/griptape-ai/griptape-nodes/refs/heads/main/libraries/griptape_cloud/workflows/templates/thumbnail_griptape_cloud_published_workflow_template.webp"
# is_griptape_provided = true
# is_template = true
# creation_date = 2025-10-08T21:42:01.632901Z
# last_modified_date = 2025-10-08T21:42:01.645111Z
# workflow_shape = "{\"inputs\":{\"Start Flow\":{\"execution_environment\":{\"name\":\"execution_environment\",\"tooltip\":\"Environment that the node should execute in\",\"type\":\"str\",\"input_types\":[\"str\"],\"output_type\":\"str\",\"default_value\":\"Local Execution\",\"tooltip_as_input\":null,\"tooltip_as_property\":null,\"tooltip_as_output\":null,\"ui_options\":{\"simple_dropdown\":[\"Local Execution\",\"Private Execution\",\"AWS Deadline Cloud Library\",\"Griptape Cloud Library\"],\"show_search\":true,\"search_filter\":\"\",\"hide\":true},\"settable\":true,\"is_user_defined\":true},\"exec_out\":{\"name\":\"exec_out\",\"tooltip\":\"Connection to the next node in the execution chain\",\"type\":\"parametercontroltype\",\"input_types\":[\"parametercontroltype\"],\"output_type\":\"parametercontroltype\",\"default_value\":null,\"tooltip_as_input\":null,\"tooltip_as_property\":null,\"tooltip_as_output\":null,\"ui_options\":{\"display_name\":\"Flow Out\"},\"settable\":true,\"is_user_defined\":true},\"prompt\":{\"name\":\"prompt\",\"tooltip\":\"\",\"type\":\"str\",\"input_types\":[\"str\"],\"output_type\":\"str\",\"default_value\":\"skateboard\",\"tooltip_as_input\":null,\"tooltip_as_property\":null,\"tooltip_as_output\":null,\"ui_options\":{\"is_custom\":true,\"is_user_added\":true},\"settable\":true,\"is_user_defined\":true}}},\"outputs\":{\"End Flow\":{\"execution_environment\":{\"name\":\"execution_environment\",\"tooltip\":\"Environment that the node should execute in\",\"type\":\"str\",\"input_types\":[\"str\"],\"output_type\":\"str\",\"default_value\":\"Local Execution\",\"tooltip_as_input\":null,\"tooltip_as_property\":null,\"tooltip_as_output\":null,\"ui_options\":{\"simple_dropdown\":[\"Local Execution\",\"Private Execution\",\"AWS Deadline Cloud Library\",\"Griptape Cloud Library\"],\"show_search\":true,\"search_filter\":\"\",\"hide\":true},\"settable\":true,\"is_user_defined\":true},\"exec_in\":{\"name\":\"exec_in\",\"tooltip\":\"Control path when the flow completed successfully\",\"type\":\"parametercontroltype\",\"input_types\":[\"parametercontroltype\"],\"output_type\":\"parametercontroltype\",\"default_value\":null,\"tooltip_as_input\":null,\"tooltip_as_property\":null,\"tooltip_as_output\":null,\"ui_options\":{\"display_name\":\"Succeeded\"},\"settable\":true,\"is_user_defined\":true},\"failed\":{\"name\":\"failed\",\"tooltip\":\"Control path when the flow failed\",\"type\":\"parametercontroltype\",\"input_types\":[\"parametercontroltype\"],\"output_type\":\"parametercontroltype\",\"default_value\":null,\"tooltip_as_input\":null,\"tooltip_as_property\":null,\"tooltip_as_output\":null,\"ui_options\":{\"display_name\":\"Failed\"},\"settable\":true,\"is_user_defined\":true},\"was_successful\":{\"name\":\"was_successful\",\"tooltip\":\"Indicates whether it completed without errors.\",\"type\":\"bool\",\"input_types\":[\"bool\"],\"output_type\":\"bool\",\"default_value\":false,\"tooltip_as_input\":null,\"tooltip_as_property\":null,\"tooltip_as_output\":null,\"ui_options\":{},\"settable\":false,\"is_user_defined\":true},\"result_details\":{\"name\":\"result_details\",\"tooltip\":\"Details about the operation result\",\"type\":\"str\",\"input_types\":[\"str\"],\"output_type\":\"str\",\"default_value\":null,\"tooltip_as_input\":null,\"tooltip_as_property\":null,\"tooltip_as_output\":null,\"ui_options\":{\"multiline\":true,\"placeholder_text\":\"Details about the completion or failure will be shown here.\"},\"settable\":false,\"is_user_defined\":true},\"image_prompt\":{\"name\":\"image_prompt\",\"tooltip\":\"\",\"type\":\"str\",\"input_types\":[\"str\"],\"output_type\":\"str\",\"default_value\":null,\"tooltip_as_input\":null,\"tooltip_as_property\":null,\"tooltip_as_output\":null,\"ui_options\":{\"is_custom\":true,\"is_user_added\":true},\"settable\":true,\"is_user_defined\":true},\"image_url\":{\"name\":\"image_url\",\"tooltip\":\"New parameter\",\"type\":\"ImageUrlArtifact\",\"input_types\":[\"ImageUrlArtifact\"],\"output_type\":\"ImageUrlArtifact\",\"default_value\":\"\",\"tooltip_as_input\":null,\"tooltip_as_property\":null,\"tooltip_as_output\":null,\"ui_options\":{\"is_full_width\":true,\"pulse_on_run\":true,\"is_custom\":true,\"is_user_added\":true},\"settable\":true,\"is_user_defined\":true}}}}"
#
# ///

import argparse
import asyncio
import json
import pickle

from griptape_nodes.bootstrap.workflow_executors.local_workflow_executor import LocalWorkflowExecutor
from griptape_nodes.bootstrap.workflow_executors.workflow_executor import WorkflowExecutor
from griptape_nodes.drivers.storage.storage_backend import StorageBackend
from griptape_nodes.retained_mode.events.connection_events import CreateConnectionRequest
from griptape_nodes.retained_mode.events.flow_events import (
    CreateFlowRequest,
    GetTopLevelFlowRequest,
    GetTopLevelFlowResultSuccess,
)
from griptape_nodes.retained_mode.events.library_events import LoadLibrariesRequest
from griptape_nodes.retained_mode.events.node_events import CreateNodeRequest
from griptape_nodes.retained_mode.events.parameter_events import (
    AddParameterToNodeRequest,
    SetParameterValueRequest,
)
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

GriptapeNodes.handle_request(LoadLibrariesRequest())

context_manager = GriptapeNodes.ContextManager()

if not context_manager.has_current_workflow():
    context_manager.push_workflow(workflow_name="griptape_cloud_published_workflow_template_1")

"""
1. We've collated all of the unique parameter values into a dictionary so that we do not have to duplicate them.
   This minimizes the size of the code, especially for large objects like serialized image files.
2. We're using a prefix so that it's clear which Flow these values are associated with.
3. The values are serialized using pickle, which is a binary format. This makes them harder to read, but makes
   them consistently save and load. It allows us to serialize complex objects like custom classes, which otherwise
   would be difficult to serialize.
"""
top_level_unique_values_dict = {
    "6fa7a8a8-515e-43a1-9f6b-2ba771141b2c": pickle.loads(
        b"\x80\x04\x95\x13\x00\x00\x00\x00\x00\x00\x00\x8c\x0fLocal Execution\x94."
    ),
    "79e352a2-1ef6-4917-a3d6-0ec5f713921e": pickle.loads(b"\x80\x04\x88."),
    "0b717a7e-dd8e-4b9f-aa32-711ba297644c": pickle.loads(
        b"\x80\x04\x95R\x00\x00\x00\x00\x00\x00\x00\x8cN[SUCCEEDED] No connection provided for success or failure, assuming successful\x94."
    ),
    "1234fafb-7772-46da-8e3d-cad0e51b2105": pickle.loads(
        b"\x80\x04\x95\x9b\x02\x00\x00\x00\x00\x00\x00X\x94\x02\x00\x00Create a detailed image of a skateboard in an urban environment. The skateboard should be a classic design with a wooden deck featuring vibrant, colorful graffiti-style artwork. The wheels are bright red and slightly worn, showing signs of frequent use. Place the skateboard resting on a cracked concrete sidewalk near a graffiti-covered brick wall. The scene is set during golden hour, with warm sunlight casting long shadows. Include subtle details like scattered leaves, a metal drain grate nearby, and a few skateboarding stickers on the wall. The overall mood is energetic and youthful, capturing the essence of street culture and skateboarding lifestyle.\x94."
    ),
    "845a9f2b-cdb5-433f-97de-90cd748f1b07": pickle.loads(
        b"\x80\x04\x95\x91\x01\x00\x00\x00\x00\x00\x00\x8c%griptape.artifacts.image_url_artifact\x94\x8c\x10ImageUrlArtifact\x94\x93\x94)\x81\x94}\x94(\x8c\x04type\x94\x8c\x10ImageUrlArtifact\x94\x8c\x0bmodule_name\x94\x8c%griptape.artifacts.image_url_artifact\x94\x8c\x02id\x94\x8c 83d6ee878d534ea3af388a9997873fa8\x94\x8c\treference\x94N\x8c\x04meta\x94}\x94\x8c\x04name\x94\x8c\x1dseedream_image_1759959659.jpg\x94\x8c\x16encoding_error_handler\x94\x8c\x06strict\x94\x8c\x08encoding\x94\x8c\x05utf-8\x94\x8c\x05value\x94\x8cVhttp://localhost:8124/workspace/staticfiles/seedream_image_1759959659.jpg?t=1759959659\x94ub."
    ),
    "f63f0839-949f-406b-81a0-bff6fa6d859e": pickle.loads(
        b"\x80\x04\x95C\x06\x00\x00\x00\x00\x00\x00}\x94(\x8c\x04type\x94\x8c\x12GriptapeNodesAgent\x94\x8c\x08rulesets\x94]\x94\x8c\x05rules\x94]\x94\x8c\x02id\x94\x8c 697dca94533546b48f8bb1bf10e19f05\x94\x8c\x13conversation_memory\x94}\x94(h\x01\x8c\x12ConversationMemory\x94\x8c\x04runs\x94]\x94}\x94(h\x01\x8c\x03Run\x94h\x07\x8c 304c0ea47a8142eca1732df5c584a004\x94\x8c\x04meta\x94N\x8c\x05input\x94}\x94(h\x01\x8c\x0cTextArtifact\x94h\x07\x8c 263566d9fccf4c51ad2b83aa3dc645c8\x94\x8c\treference\x94Nh\x11}\x94\x8c\x04name\x94h\x15\x8c\x05value\x94\x8ceTake the following input prompt, and use it to create a detailed image generation prompt:\n\nskateboard\x94u\x8c\x06output\x94}\x94(h\x01h\x14h\x07\x8c d58acc345f2346f68326b4eaf4d3298b\x94h\x16Nh\x11}\x94\x8c\x0fis_react_prompt\x94\x89sh\x18h\x1dh\x19X\x94\x02\x00\x00Create a detailed image of a skateboard in an urban environment. The skateboard should be a classic design with a wooden deck featuring vibrant, colorful graffiti-style artwork. The wheels are bright red and slightly worn, showing signs of frequent use. Place the skateboard resting on a cracked concrete sidewalk near a graffiti-covered brick wall. The scene is set during golden hour, with warm sunlight casting long shadows. Include subtle details like scattered leaves, a metal drain grate nearby, and a few skateboarding stickers on the wall. The overall mood is energetic and youthful, capturing the essence of street culture and skateboarding lifestyle.\x94uuah\x11}\x94\x8c\x08max_runs\x94Nu\x8c\x1cconversation_memory_strategy\x94\x8c\rper_structure\x94\x8c\x05tasks\x94]\x94}\x94(h\x01\x8c\nPromptTask\x94h\x03]\x94h\x05]\x94h\x07\x8c 335e533dcd684cedb8bd38515ede534d\x94\x8c\x05state\x94\x8c\x0eState.FINISHED\x94\x8c\nparent_ids\x94]\x94\x8c\tchild_ids\x94]\x94\x8c\x17max_meta_memory_entries\x94K\x14\x8c\x07context\x94}\x94\x8c\rprompt_driver\x94}\x94(h\x01\x8c\x19GriptapeCloudPromptDriver\x94\x8c\x0btemperature\x94G?\xb9\x99\x99\x99\x99\x99\x9a\x8c\nmax_tokens\x94N\x8c\x06stream\x94\x88\x8c\x0cextra_params\x94}\x94\x8c\x05model\x94\x8c\x0cgpt-4.1-mini\x94\x8c\x1astructured_output_strategy\x94\x8c\x06native\x94u\x8c\x05tools\x94]\x94\x8c\x0cmax_subtasks\x94K\x14uau."
    ),
    "1fc6ab62-8439-4499-9358-8bcd9819c7eb": pickle.loads(
        b"\x80\x04\x95i\x00\x00\x00\x00\x00\x00\x00\x8ceTake the following input prompt, and use it to create a detailed image generation prompt:\n\nskateboard\x94."
    ),
    "c87340a7-8c44-47c0-a2c5-3cc53c50c286": pickle.loads(
        b"\x80\x04\x95N\x00\x00\x00\x00\x00\x00\x00\x8cJ[Processing..]\n[Started processing agent..]\n\n[Finished processing agent.]\n\x94."
    ),
    "c9c71f19-98c1-4ebf-bbe7-a03b2665067d": pickle.loads(
        b"\x80\x04\x95]\x00\x00\x00\x00\x00\x00\x00\x8cYTake the following input prompt, and use it to create a detailed image generation prompt:\x94."
    ),
    "b965f8df-6b8d-411a-b673-b039719d9b3e": pickle.loads(
        b"\x80\x04\x95\x0e\x00\x00\x00\x00\x00\x00\x00\x8c\nskateboard\x94."
    ),
    "c0b45e30-9499-42e1-9908-bb654b0fb44e": pickle.loads(
        b"\x80\x04\x95\x0e\x00\x00\x00\x00\x00\x00\x00\x8c\n1759959655\x94."
    ),
    "f558141e-6d21-424e-bbf9-1aabed63cedd": pickle.loads(
        b"\x80\x04\x95e\x02\x00\x00\x00\x00\x00\x00}\x94(\x8c\x05model\x94\x8c\x13seedream-4-0-250828\x94\x8c\x07created\x94Jg\xda\xe6h\x8c\x04data\x94]\x94}\x94(\x8c\x03url\x94X\xc0\x01\x00\x00https://ark-content-generation-v2-ap-southeast-1.tos-ap-southeast-1.volces.com/seedream-4-0/0217599596494851ec9e5690c54b8a82a7926bf2c1a02f3be0c3d_0.jpeg?X-Tos-Algorithm=TOS4-HMAC-SHA256&X-Tos-Credential=AKLTYWJkZTExNjA1ZDUyNDc3YzhjNTM5OGIyNjBhNDcyOTQ%2F20251008%2Fap-southeast-1%2Ftos%2Frequest&X-Tos-Date=20251008T214055Z&X-Tos-Expires=86400&X-Tos-Signature=532a09b9fb9d65082497b35b29aff51ad7f37238b275e67f2fbd79c19472dbbc&X-Tos-SignedHeaders=host\x94\x8c\x04size\x94\x8c\t2048x2048\x94ua\x8c\x05usage\x94}\x94(\x8c\x10generated_images\x94K\x01\x8c\routput_tokens\x94M\x00@\x8c\x0ctotal_tokens\x94M\x00@uu."
    ),
    "b1f5965a-ee22-4f90-bca2-dee7c4e57d90": pickle.loads(
        b"\x80\x04\x95\xc8\x00\x00\x00\x00\x00\x00\x00\x8c\xc4The Start Flow node here exposes the input parameters that can be supplied for the workflow. \n\nThis is a required Node to have before publishing, and should be placed at the beginning of the flow.\x94."
    ),
    "c9341f6b-4600-444a-8b15-cd7da50f23af": pickle.loads(
        b"\x80\x04\x95\xc7\x00\x00\x00\x00\x00\x00\x00\x8c\xc3This section of the workflow is just an example. This logic will be bundled up as a result of publishing, like a black box. The Start Flow inputs will be exposed, as well as the End Flow outputs.\x94."
    ),
    "889cd4e5-fa3b-435e-abd2-dd555f138a21": pickle.loads(
        b"\x80\x04\x95g\x00\x00\x00\x00\x00\x00\x00\x8ccThe End Flow node here exposes the outputs for this workflow. It is a required node for publishing.\x94."
    ),
    "b8fc72a5-c887-442a-b5b8-526967e7eb5a": pickle.loads(
        b"\x80\x04\x95a\x00\x00\x00\x00\x00\x00\x00\x8c]To publish this workflow, click the top right rocket icon, and choose Griptape Cloud Library!\x94."
    ),
}

"# Create the Flow, then do work within it as context."

flow0_name = GriptapeNodes.handle_request(
    CreateFlowRequest(parent_flow_name=None, set_as_new_context=False, metadata={})
).flow_name

with GriptapeNodes.ContextManager().flow(flow0_name):
    node0_name = GriptapeNodes.handle_request(
        CreateNodeRequest(
            node_type="StartFlow",
            specific_library_name="Griptape Nodes Library",
            node_name="Start Flow",
            metadata={
                "position": {"x": 35.58844749420206, "y": 943},
                "tempId": "placing-1759959404818-5yakob",
                "library_node_metadata": {
                    "category": "workflows",
                    "description": "Define the start of a workflow and pass parameters into the flow",
                },
                "library": "Griptape Nodes Library",
                "node_type": "StartFlow",
                "showaddparameter": True,
                "category": "workflows",
                "size": {"width": 417, "height": 183},
            },
            resolution="resolved",
            initial_setup=True,
        )
    ).node_name
    with GriptapeNodes.ContextManager().node(node0_name):
        GriptapeNodes.handle_request(
            AddParameterToNodeRequest(
                parameter_name="prompt",
                default_value="skateboard",
                tooltip="",
                type="str",
                input_types=["str"],
                output_type="str",
                ui_options={"is_custom": True, "is_user_added": True},
                mode_allowed_input=False,
                mode_allowed_property=True,
                mode_allowed_output=True,
                initial_setup=True,
            )
        )
    node1_name = GriptapeNodes.handle_request(
        CreateNodeRequest(
            node_type="EndFlow",
            specific_library_name="Griptape Nodes Library",
            node_name="End Flow",
            metadata={
                "position": {"x": 2553, "y": 932},
                "tempId": "placing-1759959408085-zqmiiw",
                "library_node_metadata": {
                    "category": "workflows",
                    "description": "Define the end of a workflow and return parameters from the flow",
                },
                "library": "Griptape Nodes Library",
                "node_type": "EndFlow",
                "showaddparameter": True,
                "category": "workflows",
                "size": {"width": 400, "height": 650},
            },
            resolution="resolved",
            initial_setup=True,
        )
    ).node_name
    with GriptapeNodes.ContextManager().node(node1_name):
        GriptapeNodes.handle_request(
            AddParameterToNodeRequest(
                parameter_name="image_prompt",
                tooltip="",
                type="str",
                input_types=["str"],
                output_type="str",
                ui_options={"is_custom": True, "is_user_added": True},
                mode_allowed_input=True,
                mode_allowed_property=True,
                mode_allowed_output=False,
                initial_setup=True,
            )
        )
        GriptapeNodes.handle_request(
            AddParameterToNodeRequest(
                parameter_name="image_url",
                default_value="",
                tooltip="New parameter",
                type="ImageUrlArtifact",
                input_types=["ImageUrlArtifact"],
                output_type="ImageUrlArtifact",
                ui_options={"is_full_width": True, "pulse_on_run": True, "is_custom": True, "is_user_added": True},
                mode_allowed_input=True,
                mode_allowed_property=True,
                mode_allowed_output=True,
                parent_container_name="",
                initial_setup=True,
            )
        )
    node2_name = GriptapeNodes.handle_request(
        CreateNodeRequest(
            node_type="Agent",
            specific_library_name="Griptape Nodes Library",
            node_name="Agent",
            metadata={
                "position": {"x": 1239, "y": 931},
                "tempId": "placing-1759959430688-4oujv",
                "library_node_metadata": {
                    "category": "agents",
                    "description": "Creates an AI agent with conversation memory and the ability to use tools",
                },
                "library": "Griptape Nodes Library",
                "node_type": "Agent",
                "showaddparameter": False,
                "category": "agents",
                "size": {"width": 400, "height": 544},
            },
            resolution="resolved",
            initial_setup=True,
        )
    ).node_name
    node3_name = GriptapeNodes.handle_request(
        CreateNodeRequest(
            node_type="MergeTexts",
            specific_library_name="Griptape Nodes Library",
            node_name="Merge Texts",
            metadata={
                "position": {"x": 619, "y": 943},
                "tempId": "placing-1759959443495-q9sw4b",
                "library_node_metadata": {"category": "text", "description": "MergeTexts node"},
                "library": "Griptape Nodes Library",
                "node_type": "MergeTexts",
                "showaddparameter": False,
                "category": "text",
                "size": {"width": 430, "height": 506},
            },
            resolution="resolved",
            initial_setup=True,
        )
    ).node_name
    node4_name = GriptapeNodes.handle_request(
        CreateNodeRequest(
            node_type="SeedreamImageGeneration",
            specific_library_name="Griptape Nodes Library",
            node_name="Seedream Image Generation",
            metadata={
                "position": {"x": 1829, "y": 932},
                "tempId": "placing-1759959575211-n83qy",
                "library_node_metadata": {
                    "category": "image",
                    "description": "Generate images using Seedream models (seedream-4.0, seedream-3.0-t2i) via Griptape model proxy",
                },
                "library": "Griptape Nodes Library",
                "node_type": "SeedreamImageGeneration",
                "showaddparameter": False,
                "category": "image",
                "size": {"width": 534, "height": 658},
            },
            resolution="resolved",
            initial_setup=True,
        )
    ).node_name
    node5_name = GriptapeNodes.handle_request(
        CreateNodeRequest(
            node_type="Note",
            specific_library_name="Griptape Nodes Library",
            node_name="Note",
            metadata={
                "position": {"x": 35.58844749420206, "y": 485.3831605083146},
                "tempId": "placing-1759960199321-1cotty",
                "library_node_metadata": {
                    "category": "misc",
                    "description": "Create a note node to provide helpful context in your workflow",
                },
                "library": "Griptape Nodes Library",
                "node_type": "Note",
                "showaddparameter": False,
                "category": "misc",
                "size": {"width": 423, "height": 356},
            },
            initial_setup=True,
        )
    ).node_name
    node6_name = GriptapeNodes.handle_request(
        CreateNodeRequest(
            node_type="Note",
            specific_library_name="Griptape Nodes Library",
            node_name="Note_1",
            metadata={
                "position": {"x": 691, "y": 485.3831605083146},
                "tempId": "placing-1759960275375-u04md",
                "library_node_metadata": {
                    "category": "misc",
                    "description": "Create a note node to provide helpful context in your workflow",
                },
                "library": "Griptape Nodes Library",
                "node_type": "Note",
                "showaddparameter": False,
                "size": {"width": 1672, "height": 384},
                "category": "misc",
            },
            initial_setup=True,
        )
    ).node_name
    node7_name = GriptapeNodes.handle_request(
        CreateNodeRequest(
            node_type="Note",
            specific_library_name="Griptape Nodes Library",
            node_name="Note_2",
            metadata={
                "position": {"x": 2547, "y": 485.3831605083146},
                "tempId": "placing-1759960354172-8aukc",
                "library_node_metadata": {
                    "category": "misc",
                    "description": "Create a note node to provide helpful context in your workflow",
                },
                "library": "Griptape Nodes Library",
                "node_type": "Note",
                "showaddparameter": False,
                "category": "misc",
                "size": {"width": 412, "height": 393},
            },
            initial_setup=True,
        )
    ).node_name
    node8_name = GriptapeNodes.handle_request(
        CreateNodeRequest(
            node_type="Note",
            specific_library_name="Griptape Nodes Library",
            node_name="Note_3",
            metadata={
                "position": {"x": 2547, "y": -61.50506349833027},
                "tempId": "placing-1759960393090-qtlpje",
                "library_node_metadata": {
                    "category": "misc",
                    "description": "Create a note node to provide helpful context in your workflow",
                },
                "library": "Griptape Nodes Library",
                "node_type": "Note",
                "showaddparameter": False,
                "size": {"width": 472, "height": 319},
                "category": "misc",
            },
            initial_setup=True,
        )
    ).node_name
    GriptapeNodes.handle_request(
        CreateConnectionRequest(
            source_node_name=node0_name,
            source_parameter_name="prompt",
            target_node_name=node3_name,
            target_parameter_name="input_2",
            initial_setup=True,
        )
    )
    GriptapeNodes.handle_request(
        CreateConnectionRequest(
            source_node_name=node3_name,
            source_parameter_name="output",
            target_node_name=node2_name,
            target_parameter_name="prompt",
            initial_setup=True,
        )
    )
    GriptapeNodes.handle_request(
        CreateConnectionRequest(
            source_node_name=node2_name,
            source_parameter_name="output",
            target_node_name=node4_name,
            target_parameter_name="prompt",
            initial_setup=True,
        )
    )
    GriptapeNodes.handle_request(
        CreateConnectionRequest(
            source_node_name=node2_name,
            source_parameter_name="output",
            target_node_name=node1_name,
            target_parameter_name="image_prompt",
            initial_setup=True,
        )
    )
    GriptapeNodes.handle_request(
        CreateConnectionRequest(
            source_node_name=node4_name,
            source_parameter_name="image_url",
            target_node_name=node1_name,
            target_parameter_name="image_url",
            initial_setup=True,
        )
    )
    with GriptapeNodes.ContextManager().node(node1_name):
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="execution_environment",
                node_name=node1_name,
                value=top_level_unique_values_dict["6fa7a8a8-515e-43a1-9f6b-2ba771141b2c"],
                initial_setup=True,
                is_output=True,
            )
        )
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="was_successful",
                node_name=node1_name,
                value=top_level_unique_values_dict["79e352a2-1ef6-4917-a3d6-0ec5f713921e"],
                initial_setup=True,
                is_output=False,
            )
        )
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="was_successful",
                node_name=node1_name,
                value=top_level_unique_values_dict["79e352a2-1ef6-4917-a3d6-0ec5f713921e"],
                initial_setup=True,
                is_output=True,
            )
        )
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="result_details",
                node_name=node1_name,
                value=top_level_unique_values_dict["0b717a7e-dd8e-4b9f-aa32-711ba297644c"],
                initial_setup=True,
                is_output=False,
            )
        )
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="result_details",
                node_name=node1_name,
                value=top_level_unique_values_dict["0b717a7e-dd8e-4b9f-aa32-711ba297644c"],
                initial_setup=True,
                is_output=True,
            )
        )
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="image_prompt",
                node_name=node1_name,
                value=top_level_unique_values_dict["1234fafb-7772-46da-8e3d-cad0e51b2105"],
                initial_setup=True,
                is_output=False,
            )
        )
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="image_prompt",
                node_name=node1_name,
                value=top_level_unique_values_dict["1234fafb-7772-46da-8e3d-cad0e51b2105"],
                initial_setup=True,
                is_output=True,
            )
        )
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="image_url",
                node_name=node1_name,
                value=top_level_unique_values_dict["845a9f2b-cdb5-433f-97de-90cd748f1b07"],
                initial_setup=True,
                is_output=False,
            )
        )
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="image_url",
                node_name=node1_name,
                value=top_level_unique_values_dict["845a9f2b-cdb5-433f-97de-90cd748f1b07"],
                initial_setup=True,
                is_output=True,
            )
        )
    with GriptapeNodes.ContextManager().node(node2_name):
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="agent",
                node_name=node2_name,
                value=top_level_unique_values_dict["f63f0839-949f-406b-81a0-bff6fa6d859e"],
                initial_setup=True,
                is_output=True,
            )
        )
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="prompt",
                node_name=node2_name,
                value=top_level_unique_values_dict["1fc6ab62-8439-4499-9358-8bcd9819c7eb"],
                initial_setup=True,
                is_output=False,
            )
        )
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="output",
                node_name=node2_name,
                value=top_level_unique_values_dict["1234fafb-7772-46da-8e3d-cad0e51b2105"],
                initial_setup=True,
                is_output=True,
            )
        )
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="logs",
                node_name=node2_name,
                value=top_level_unique_values_dict["c87340a7-8c44-47c0-a2c5-3cc53c50c286"],
                initial_setup=True,
                is_output=True,
            )
        )
    with GriptapeNodes.ContextManager().node(node3_name):
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="input_1",
                node_name=node3_name,
                value=top_level_unique_values_dict["c9c71f19-98c1-4ebf-bbe7-a03b2665067d"],
                initial_setup=True,
                is_output=False,
            )
        )
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="input_2",
                node_name=node3_name,
                value=top_level_unique_values_dict["b965f8df-6b8d-411a-b673-b039719d9b3e"],
                initial_setup=True,
                is_output=False,
            )
        )
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="output",
                node_name=node3_name,
                value=top_level_unique_values_dict["1fc6ab62-8439-4499-9358-8bcd9819c7eb"],
                initial_setup=True,
                is_output=False,
            )
        )
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="output",
                node_name=node3_name,
                value=top_level_unique_values_dict["1fc6ab62-8439-4499-9358-8bcd9819c7eb"],
                initial_setup=True,
                is_output=True,
            )
        )
    with GriptapeNodes.ContextManager().node(node4_name):
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="prompt",
                node_name=node4_name,
                value=top_level_unique_values_dict["1234fafb-7772-46da-8e3d-cad0e51b2105"],
                initial_setup=True,
                is_output=False,
            )
        )
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="generation_id",
                node_name=node4_name,
                value=top_level_unique_values_dict["c0b45e30-9499-42e1-9908-bb654b0fb44e"],
                initial_setup=True,
                is_output=True,
            )
        )
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="provider_response",
                node_name=node4_name,
                value=top_level_unique_values_dict["f558141e-6d21-424e-bbf9-1aabed63cedd"],
                initial_setup=True,
                is_output=True,
            )
        )
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="image_url",
                node_name=node4_name,
                value=top_level_unique_values_dict["845a9f2b-cdb5-433f-97de-90cd748f1b07"],
                initial_setup=True,
                is_output=True,
            )
        )
    with GriptapeNodes.ContextManager().node(node5_name):
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="note",
                node_name=node5_name,
                value=top_level_unique_values_dict["b1f5965a-ee22-4f90-bca2-dee7c4e57d90"],
                initial_setup=True,
                is_output=False,
            )
        )
    with GriptapeNodes.ContextManager().node(node6_name):
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="note",
                node_name=node6_name,
                value=top_level_unique_values_dict["c9341f6b-4600-444a-8b15-cd7da50f23af"],
                initial_setup=True,
                is_output=False,
            )
        )
    with GriptapeNodes.ContextManager().node(node7_name):
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="note",
                node_name=node7_name,
                value=top_level_unique_values_dict["889cd4e5-fa3b-435e-abd2-dd555f138a21"],
                initial_setup=True,
                is_output=False,
            )
        )
    with GriptapeNodes.ContextManager().node(node8_name):
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="note",
                node_name=node8_name,
                value=top_level_unique_values_dict["b8fc72a5-c887-442a-b5b8-526967e7eb5a"],
                initial_setup=True,
                is_output=False,
            )
        )


def _ensure_workflow_context():
    context_manager = GriptapeNodes.ContextManager()
    if not context_manager.has_current_flow():
        top_level_flow_request = GetTopLevelFlowRequest()
        top_level_flow_result = GriptapeNodes.handle_request(top_level_flow_request)
        if (
            isinstance(top_level_flow_result, GetTopLevelFlowResultSuccess)
            and top_level_flow_result.flow_name is not None
        ):
            flow_manager = GriptapeNodes.FlowManager()
            flow_obj = flow_manager.get_flow_by_name(top_level_flow_result.flow_name)
            context_manager.push_flow(flow_obj)


def execute_workflow(
    input: dict,
    storage_backend: str = "local",
    workflow_executor: WorkflowExecutor | None = None,
    pickle_control_flow_result: bool = False,
) -> dict | None:
    return asyncio.run(
        aexecute_workflow(
            input=input,
            storage_backend=storage_backend,
            workflow_executor=workflow_executor,
            pickle_control_flow_result=pickle_control_flow_result,
        )
    )


async def aexecute_workflow(
    input: dict,
    storage_backend: str = "local",
    workflow_executor: WorkflowExecutor | None = None,
    pickle_control_flow_result: bool = False,
) -> dict | None:
    _ensure_workflow_context()
    storage_backend_enum = StorageBackend(storage_backend)
    workflow_executor = workflow_executor or LocalWorkflowExecutor(storage_backend=storage_backend_enum)
    async with workflow_executor as executor:
        await executor.arun(
            workflow_name="ControlFlow_1", flow_input=input, pickle_control_flow_result=pickle_control_flow_result
        )
    return executor.output


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--storage-backend",
        choices=["local", "gtc"],
        default="local",
        help="Storage backend to use: 'local' for local filesystem or 'gtc' for Griptape Cloud",
    )
    parser.add_argument(
        "--json-input",
        default=None,
        help="JSON string containing parameter values. Takes precedence over individual parameter arguments if provided.",
    )
    parser.add_argument("--execution_environment", default=None, help="Environment that the node should execute in")
    parser.add_argument("--exec_out", default=None, help="Connection to the next node in the execution chain")
    parser.add_argument("--prompt", default=None, help="")
    args = parser.parse_args()
    flow_input = {}
    if args.json_input is not None:
        flow_input = json.loads(args.json_input)
    if args.json_input is None:
        if "Start Flow" not in flow_input:
            flow_input["Start Flow"] = {}
        if args.execution_environment is not None:
            flow_input["Start Flow"]["execution_environment"] = args.execution_environment
        if args.exec_out is not None:
            flow_input["Start Flow"]["exec_out"] = args.exec_out
        if args.prompt is not None:
            flow_input["Start Flow"]["prompt"] = args.prompt
    workflow_output = execute_workflow(input=flow_input, storage_backend=args.storage_backend)
    print(workflow_output)
