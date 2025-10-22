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
# creation_date = 2025-10-22T16:57:58.748591Z
# last_modified_date = 2025-10-22T16:57:58.757066Z
#
# ///

import pickle
from griptape_nodes.node_library.library_registry import IconVariant, NodeDeprecationMetadata, NodeMetadata
from griptape_nodes.retained_mode.events.connection_events import CreateConnectionRequest
from griptape_nodes.retained_mode.events.flow_events import CreateFlowRequest
from griptape_nodes.retained_mode.events.library_events import (
    GetAllInfoForAllLibrariesRequest,
    GetAllInfoForAllLibrariesResultSuccess,
    ReloadAllLibrariesRequest,
)
from griptape_nodes.retained_mode.events.node_events import CreateNodeRequest
from griptape_nodes.retained_mode.events.parameter_events import (
    AddParameterToNodeRequest,
    AlterParameterDetailsRequest,
    SetParameterValueRequest,
)
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

response = GriptapeNodes.LibraryManager().get_all_info_for_all_libraries_request(GetAllInfoForAllLibrariesRequest())

if (
    isinstance(response, GetAllInfoForAllLibrariesResultSuccess)
    and len(response.library_name_to_library_info.keys()) < 1
):
    GriptapeNodes.handle_request(ReloadAllLibrariesRequest())

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
    "9b34f7fb-2c5a-4488-9128-b591e8aa44da": pickle.loads(
        b"\x80\x04\x95X\x01\x00\x00\x00\x00\x00\x00XQ\x01\x00\x00This workflow serves as the lesson material for the tutorial located at:\n\nhttps://docs.griptapenodes.com/en/stable/ftue/01_prompt_an_image/FTUE_01_prompt_an_image/\n\nThe concepts covered are:\n\n- Opening saved workflows\n- Using text prompts to generate images using the GenerateImage node\n- Running entire workflows, or just specific nodes\x94."
    ),
    "1461ef2b-c432-40a6-8532-87a71079e988": pickle.loads(
        b"\x80\x04\x95\xf8\x00\x00\x00\x00\x00\x00\x00\x8c\xf4If you're following along with our Getting Started tutorials, check out the next workflow: Coordinating Agents.\n\nLoad the next tutorial page here:\nhttps://docs.griptapenodes.com/en/stable/ftue/02_coordinating_agents/FTUE_02_coordinating_agents/\x94."
    ),
    "28910b35-948a-4ae9-84f7-67f30075193b": pickle.loads(
        b"\x80\x04\x95#\x00\x00\x00\x00\x00\x00\x00\x8c\x1fA potato making an oil painting\x94."
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
                "size": {"width": 1000, "height": 200},
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
                "category": "Base",
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
    with GriptapeNodes.ContextManager().node(node0_name):
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="note",
                node_name=node0_name,
                value=top_level_unique_values_dict["9b34f7fb-2c5a-4488-9128-b591e8aa44da"],
                initial_setup=True,
                is_output=False,
            )
        )
    with GriptapeNodes.ContextManager().node(node1_name):
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="note",
                node_name=node1_name,
                value=top_level_unique_values_dict["1461ef2b-c432-40a6-8532-87a71079e988"],
                initial_setup=True,
                is_output=False,
            )
        )
    with GriptapeNodes.ContextManager().node(node2_name):
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="prompt",
                node_name=node2_name,
                value=top_level_unique_values_dict["28910b35-948a-4ae9-84f7-67f30075193b"],
                initial_setup=True,
                is_output=False,
            )
        )
