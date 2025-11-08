# /// script
# dependencies = []
#
# [tool.griptape-nodes]
# name = "prompt_an_image"
# schema_version = "0.11.0"
# engine_version_created_with = "0.60.0"
# node_libraries_referenced = [["Griptape Nodes Library", "0.50.0"]]
# node_types_used = [["Griptape Nodes Library", "GenerateImage"], ["Griptape Nodes Library", "Note"]]
# image = "https://raw.githubusercontent.com/griptape-ai/griptape-nodes/refs/heads/main/libraries/griptape_nodes_library/workflows/templates/thumbnail_prompt_an_image.webp"
# description = "The simplest image generation workflow."
# is_griptape_provided = true
# is_template = true
# creation_date = 2025-10-22T19:04:50.774123Z
# last_modified_date = 2025-10-22T19:04:50.785949Z
#
# ///

import pickle
from griptape_nodes.node_library.library_registry import IconVariant, NodeDeprecationMetadata, NodeMetadata
from griptape_nodes.retained_mode.events.connection_events import CreateConnectionRequest
from griptape_nodes.retained_mode.events.flow_events import CreateFlowRequest
from griptape_nodes.retained_mode.events.library_events import LoadLibrariesRequest
from griptape_nodes.retained_mode.events.node_events import CreateNodeRequest
from griptape_nodes.retained_mode.events.parameter_events import (
    AddParameterToNodeRequest,
    AlterParameterDetailsRequest,
    SetParameterValueRequest,
)
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

GriptapeNodes.handle_request(LoadLibrariesRequest())

context_manager = GriptapeNodes.ContextManager()

if not context_manager.has_current_workflow():
    context_manager.push_workflow(workflow_name="prompt_an_image")

"""
1. We've collated all of the unique parameter values into a dictionary so that we do not have to duplicate them.
   This minimizes the size of the code, especially for large objects like serialized image files.
2. We're using a prefix so that it's clear which Flow these values are associated with.
3. The values are serialized using pickle, which is a binary format. This makes them harder to read, but makes
   them consistently save and load. It allows us to serialize complex objects like custom classes, which otherwise
   would be difficult to serialize.
"""
top_level_unique_values_dict = {
    "0b96379e-d109-498b-88fd-d771e2abbe8f": pickle.loads(
        b"\x80\x04\x95X\x01\x00\x00\x00\x00\x00\x00XQ\x01\x00\x00This workflow serves as the lesson material for the tutorial located at:\n\nhttps://docs.griptapenodes.com/en/stable/ftue/01_prompt_an_image/FTUE_01_prompt_an_image/\n\nThe concepts covered are:\n\n- Opening saved workflows\n- Using text prompts to generate images using the GenerateImage node\n- Running entire workflows, or just specific nodes\x94."
    ),
    "5ac44b15-d10a-462c-a6fc-29a340941b88": pickle.loads(
        b"\x80\x04\x95\xf8\x00\x00\x00\x00\x00\x00\x00\x8c\xf4If you're following along with our Getting Started tutorials, check out the next workflow: Coordinating Agents.\n\nLoad the next tutorial page here:\nhttps://docs.griptapenodes.com/en/stable/ftue/02_coordinating_agents/FTUE_02_coordinating_agents/\x94."
    ),
    "c2f329b7-aefa-4b7a-b2f3-468fcd870104": pickle.loads(
        b"\x80\x04\x95\x0f\x00\x00\x00\x00\x00\x00\x00\x8c\x0bgpt-image-1\x94."
    ),
    "d073a3b0-50fd-46a2-86b0-ef600edb20d5": pickle.loads(
        b"\x80\x04\x95#\x00\x00\x00\x00\x00\x00\x00\x8c\x1fA potato making an oil painting\x94."
    ),
    "d04343f7-5a2c-47c3-8b17-79a04769198e": pickle.loads(
        b"\x80\x04\x95\r\x00\x00\x00\x00\x00\x00\x00\x8c\t1024x1024\x94."
    ),
}

"# Create the Flow, then do work within it as context."

flow0_name = GriptapeNodes.handle_request(
    CreateFlowRequest(parent_flow_name=None, set_as_new_context=False, metadata={})
).flow_name

with GriptapeNodes.ContextManager().flow(flow0_name):
    node0_name = GriptapeNodes.handle_request(
        CreateNodeRequest(
            node_type="Note",
            specific_library_name="Griptape Nodes Library",
            node_name="ReadMe",
            metadata={
                "position": {"x": 0, "y": -400},
                "size": {"width": 1000, "height": 350},
                "library_node_metadata": NodeMetadata(
                    category="misc",
                    description="Create a note node to provide helpful context in your workflow",
                    display_name="Note",
                    tags=None,
                    icon="notepad-text",
                    color=None,
                    group="create",
                    deprecation=None,
                ),
                "library": "Griptape Nodes Library",
                "node_type": "Note",
            },
            initial_setup=True,
        )
    ).node_name
    node1_name = GriptapeNodes.handle_request(
        CreateNodeRequest(
            node_type="Note",
            specific_library_name="Griptape Nodes Library",
            node_name="NextStep",
            metadata={
                "position": {"x": 485.64269456986915, "y": 530.922994242555},
                "size": {"width": 998, "height": 234},
                "library_node_metadata": {
                    "category": "misc",
                    "description": "Create a note node to provide helpful context in your workflow",
                },
                "library": "Griptape Nodes Library",
                "node_type": "Note",
                "category": "Base",
                "showaddparameter": False,
            },
            initial_setup=True,
        )
    ).node_name
    node2_name = GriptapeNodes.handle_request(
        CreateNodeRequest(
            node_type="GenerateImage",
            specific_library_name="Griptape Nodes Library",
            node_name="GenerateImage_1",
            metadata={
                "position": {"x": 8.029015213045938, "y": 4.982630454782765},
                "tempId": "placing-1747420608205-t8bruk",
                "library_node_metadata": NodeMetadata(
                    category="image",
                    description="Generates an image using Griptape Cloud, or other provided image generation models",
                    display_name="Generate Image",
                    tags=None,
                    icon=None,
                    color=None,
                    group="create",
                    deprecation=None,
                ),
                "library": "Griptape Nodes Library",
                "node_type": "GenerateImage",
                "category": "image",
                "size": {"width": 422, "height": 725},
            },
            initial_setup=True,
        )
    ).node_name
    with GriptapeNodes.ContextManager().node(node2_name):
        GriptapeNodes.handle_request(
            AlterParameterDetailsRequest(
                parameter_name="image_size",
                ui_options={
                    "simple_dropdown": ["1024x1024", "1536x1024", "1024x1536"],
                    "show_search": True,
                    "search_filter": "",
                },
                initial_setup=True,
            )
        )
    with GriptapeNodes.ContextManager().node(node0_name):
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="note",
                node_name=node0_name,
                value=top_level_unique_values_dict["0b96379e-d109-498b-88fd-d771e2abbe8f"],
                initial_setup=True,
                is_output=False,
            )
        )
    with GriptapeNodes.ContextManager().node(node1_name):
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="note",
                node_name=node1_name,
                value=top_level_unique_values_dict["5ac44b15-d10a-462c-a6fc-29a340941b88"],
                initial_setup=True,
                is_output=False,
            )
        )
    with GriptapeNodes.ContextManager().node(node2_name):
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="model",
                node_name=node2_name,
                value=top_level_unique_values_dict["c2f329b7-aefa-4b7a-b2f3-468fcd870104"],
                initial_setup=True,
                is_output=False,
            )
        )
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="prompt",
                node_name=node2_name,
                value=top_level_unique_values_dict["d073a3b0-50fd-46a2-86b0-ef600edb20d5"],
                initial_setup=True,
                is_output=False,
            )
        )
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="image_size",
                node_name=node2_name,
                value=top_level_unique_values_dict["d04343f7-5a2c-47c3-8b17-79a04769198e"],
                initial_setup=True,
                is_output=False,
            )
        )
