# /// script
# dependencies = []
#
# [tool.griptape-nodes]
# name = "prompt_an_image"
# image = "https://raw.githubusercontent.com/griptape-ai/griptape-nodes/refs/heads/main/libraries/griptape_nodes_library/workflows/templates/thumbnail_prompt_an_image.webp"
# description = "The simplest image generation workflow."
# schema_version = "0.3.0"
# engine_version_created_with = "0.33.1"
# node_libraries_referenced = [["Griptape Nodes Library", "0.34.0"]]
# is_griptape_provided = true
# is_template = true
# creation_date = 2025-05-01T03:00:00.000000+00:00
# last_modified_date = 2025-05-18T06:42:57.915422+12:00
#
# ///

import pickle

from griptape_nodes.node_library.library_registry import NodeMetadata
from griptape_nodes.retained_mode.events.flow_events import CreateFlowRequest
from griptape_nodes.retained_mode.events.node_events import CreateNodeRequest
from griptape_nodes.retained_mode.events.parameter_events import (
    SetParameterValueRequest,
)
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

"""
1. We've collated all of the unique parameter values into a dictionary so that we do not have to duplicate them.
   This minimizes the size of the code, especially for large objects like serialized image files.
2. We're using a prefix so that it's clear which Flow these values are associated with.
3. The values are serialized using pickle, which is a binary format. This makes them harder to read, but makes
   them consistently save and load. It allows us to serialize complex objects like custom classes, which otherwise
   would be difficult to serialize.
"""
top_level_unique_values_dict = {
    "67e24d2c-ea73-445d-854e-86414469075b": pickle.loads(
        b"\x80\x04\x95X\x01\x00\x00\x00\x00\x00\x00XQ\x01\x00\x00This workflow serves as the lesson material for the tutorial located at:\n\nhttps://docs.griptapenodes.com/en/stable/ftue/01_prompt_an_image/FTUE_01_prompt_an_image/\n\nThe concepts covered are:\n\n- Opening saved workflows\n- Using text prompts to generate images using the GenerateImage node\n- Running entire workflows, or just specific nodes\x94."
    ),
    "dfc1b718-92fc-450f-b4b8-53964c394721": pickle.loads(
        b"\x80\x04\x95\xf8\x00\x00\x00\x00\x00\x00\x00\x8c\xf4If you're following along with our Getting Started tutorials, check out the next workflow: Coordinating Agents.\n\nLoad the next tutorial page here:\nhttps://docs.griptapenodes.com/en/stable/ftue/02_coordinating_agents/FTUE_02_coordinating_agents/\x94."
    ),
    "11f349d6-79e4-49fb-9eb0-9567ae7aa424": pickle.loads(
        b"\x80\x04\x95#\x00\x00\x00\x00\x00\x00\x00\x8c\x1fA potato making an oil painting\x94."
    ),
}

flow0_name = GriptapeNodes.handle_request(CreateFlowRequest(parent_flow_name=None)).flow_name

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
                    category="Base", description="Note node", display_name="Note", tags=None
                ),
                "library": "Griptape Nodes Library",
                "node_type": "Note",
            },
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
                    category="Base", description="Note node", display_name="Note", tags=None
                ),
                "library": "Griptape Nodes Library",
                "node_type": "Note",
                "category": "Base",
            },
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
                "library_node_metadata": {"category": "image", "description": "GenerateImage node"},
                "library": "Griptape Nodes Library",
                "node_type": "GenerateImage",
                "category": "image",
                "size": {"width": 422, "height": 725},
            },
        )
    ).node_name

with GriptapeNodes.ContextManager().node(node0_name):
    GriptapeNodes.handle_request(
        SetParameterValueRequest(
            parameter_name="note",
            node_name=node0_name,
            value=top_level_unique_values_dict["67e24d2c-ea73-445d-854e-86414469075b"],
            initial_setup=True,
            is_output=False,
        )
    )

with GriptapeNodes.ContextManager().node(node1_name):
    GriptapeNodes.handle_request(
        SetParameterValueRequest(
            parameter_name="note",
            node_name=node1_name,
            value=top_level_unique_values_dict["dfc1b718-92fc-450f-b4b8-53964c394721"],
            initial_setup=True,
            is_output=False,
        )
    )

with GriptapeNodes.ContextManager().node(node2_name):
    GriptapeNodes.handle_request(
        SetParameterValueRequest(
            parameter_name="prompt",
            node_name=node2_name,
            value=top_level_unique_values_dict["11f349d6-79e4-49fb-9eb0-9567ae7aa424"],
            initial_setup=True,
            is_output=False,
        )
    )
