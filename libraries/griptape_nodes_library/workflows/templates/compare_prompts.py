# /// script
# dependencies = []
#
# [tool.griptape-nodes]
# name = "compare_prompts"
# schema_version = "0.3.0"
# description = "See how 3 different approaches to prompts affect image generation."
# image = "https://raw.githubusercontent.com/griptape-ai/griptape-nodes/refs/heads/main/libraries/griptape_nodes_library/workflows/templates/thumbnail_compare_prompts.webp"
# engine_version_created_with = "0.33.1"
# node_libraries_referenced = [["Griptape Nodes Library", "0.34.0"]]
# is_griptape_provided = true
# is_template = true
# creation_date = 2025-05-01T01:00:00.000000+00:00
# last_modified_date = 2025-05-17T06:41:46.700578+12:00
#
# ///

import pickle

from griptape_nodes.node_library.library_registry import NodeMetadata
from griptape_nodes.retained_mode.events.connection_events import CreateConnectionRequest
from griptape_nodes.retained_mode.events.flow_events import CreateFlowRequest
from griptape_nodes.retained_mode.events.node_events import CreateNodeRequest
from griptape_nodes.retained_mode.events.parameter_events import (
    AlterParameterDetailsRequest,
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
    "36f12306-b62e-4fec-a905-2790877ee558": pickle.loads(
        b'\x80\x04\x95\xbf\x01\x00\x00\x00\x00\x00\x00X\xb8\x01\x00\x00This workflow serves as the lesson material for the tutorial located at:\n\nhttps://docs.griptapenodes.com/en/stable/ftue/03_compare_prompts/FTUE_03_compare_prompts/\n\nThe concepts covered are:\n\n- How to use one TextInput node to feed to multiple other inputs\n- Different approaches to prompt engineering\n- The GenerateImage "Enhance Prompt" feature and how it works behind the scenes\n- Comparing the results of different prompting techniques\n\x94.'
    ),
    "8cbf8e5b-a940-4db4-9bd9-194922c26cf4": pickle.loads(
        b"\x80\x04\x95\xf9\x00\x00\x00\x00\x00\x00\x00\x8c\xf5If you're following along with our Getting Started tutorials, check out the next suggested template: Photography_Team.\n\nLoad the next tutorial page here:\nhttps://docs.griptapenodes.com/en/stable/ftue/04_photography_team/FTUE_04_photography_team/\x94."
    ),
    "07a91280-653b-4bc2-8b59-984f0ed63f0e": pickle.loads(
        b"\x80\x04\x95\xcf\x01\x00\x00\x00\x00\x00\x00X\xc8\x01\x00\x00Enhance the following prompt for an image generation engine. Return only the image generation prompt.\nInclude unique details that make the subject stand out.\nSpecify a specific depth of field, and time of day.\nUse dust in the air to create a sense of depth.\nUse a slight vignetting on the edges of the image.\nUse a color palette that is complementary to the subject.\nFocus on qualities that will make this the most professional looking photo in the world.\n\x94."
    ),
    "f5810999-25c0-4230-a80d-0aa2a83d37d6": pickle.loads(
        b"\x80\x04\x95#\x00\x00\x00\x00\x00\x00\x00\x8c\x1fA capybara eating with utensils\x94."
    ),
    "8114492d-d2b1-4c0b-b04f-6e6734e15100": pickle.loads(
        b"\x80\x04\x95\x08\x00\x00\x00\x00\x00\x00\x00\x8c\x04\\n\\n\x94."
    ),
    "f4e11629-0175-4c89-9d2a-dcbc9ac362e3": pickle.loads(b"\x80\x04\x89."),
    "062d2c9c-0610-4787-896c-9c058d2b9409": pickle.loads(
        b"\x80\x04\x95\xf9\x00\x00\x00\x00\x00\x00\x00}\x94(\x8c\x04type\x94\x8c\rImageArtifact\x94\x8c\x02id\x94\x8c a1d85e8dfa5745b7a39be55cca4660fb\x94\x8c\treference\x94N\x8c\x04meta\x94}\x94(\x8c\x05model\x94\x8c\x08dall-e-3\x94\x8c\x06prompt\x94\x8c\x1fA capybara eating with utensils\x94u\x8c\x04name\x94\x8c$image_artifact_250411205314_ll63.png\x94\x8c\x05value\x94\x8c\x00\x94\x8c\x06format\x94\x8c\x03png\x94\x8c\x05width\x94M\x00\x04\x8c\x06height\x94M\x00\x04u."
    ),
    "d0c7eb94-1b4d-4389-88c3-e475d871fbf4": pickle.loads(b"\x80\x04\x88."),
    "4af42606-aaed-4af4-953c-f14036720723": pickle.loads(
        b"\x80\x04\x95\x0b\x00\x00\x00\x00\x00\x00\x00\x8c\x07gpt-4.1\x94."
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
                "position": {"x": -650, "y": -700},
                "size": {"width": 1200, "height": 400},
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
                "position": {"x": 1900, "y": 950},
                "size": {"width": 1100, "height": 251},
                "library_node_metadata": {"category": "Base", "description": "Note node"},
                "library": "Griptape Nodes Library",
                "node_type": "Note",
            },
        )
    ).node_name
    node2_name = GriptapeNodes.handle_request(
        CreateNodeRequest(
            node_type="TextInput",
            specific_library_name="Griptape Nodes Library",
            node_name="detail_prompt",
            metadata={
                "position": {"x": -650, "y": 550},
                "size": {"width": 650, "height": 330},
                "library_node_metadata": NodeMetadata(
                    category="text", description="TextInput node", display_name="Text Input", tags=None
                ),
                "library": "Griptape Nodes Library",
                "node_type": "TextInput",
            },
        )
    ).node_name
    node3_name = GriptapeNodes.handle_request(
        CreateNodeRequest(
            node_type="TextInput",
            specific_library_name="Griptape Nodes Library",
            node_name="basic_prompt",
            metadata={
                "position": {"x": -650, "y": 200},
                "library_node_metadata": NodeMetadata(
                    category="text", description="TextInput node", display_name="Text Input", tags=None
                ),
                "library": "Griptape Nodes Library",
                "node_type": "TextInput",
            },
        )
    ).node_name
    node4_name = GriptapeNodes.handle_request(
        CreateNodeRequest(
            node_type="MergeTexts",
            specific_library_name="Griptape Nodes Library",
            node_name="assemble_prompt",
            metadata={
                "position": {"x": 100, "y": 550},
                "library_node_metadata": NodeMetadata(
                    category="text", description="MergeTexts node", display_name="Merge Texts", tags=None
                ),
                "library": "Griptape Nodes Library",
                "node_type": "MergeTexts",
            },
        )
    ).node_name
    node5_name = GriptapeNodes.handle_request(
        CreateNodeRequest(
            node_type="GenerateImage",
            specific_library_name="Griptape Nodes Library",
            node_name="basic_image",
            metadata={
                "position": {"x": 1350, "y": -700},
                "library_node_metadata": {"category": "image", "description": "GenerateImage node"},
                "library": "Griptape Nodes Library",
                "node_type": "GenerateImage",
                "size": {"width": 400, "height": 657},
            },
        )
    ).node_name
    with GriptapeNodes.ContextManager().node(node5_name):
        GriptapeNodes.handle_request(
            AlterParameterDetailsRequest(
                parameter_name="prompt", node_name="basic_image", mode_allowed_property=False, initial_setup=True
            )
        )
    node6_name = GriptapeNodes.handle_request(
        CreateNodeRequest(
            node_type="GenerateImage",
            specific_library_name="Griptape Nodes Library",
            node_name="enhanced_prompt_image",
            metadata={
                "position": {"x": 1350, "y": 100},
                "library_node_metadata": {"category": "image", "description": "GenerateImage node"},
                "library": "Griptape Nodes Library",
                "node_type": "GenerateImage",
                "size": {"width": 413, "height": 672},
            },
        )
    ).node_name
    with GriptapeNodes.ContextManager().node(node6_name):
        GriptapeNodes.handle_request(
            AlterParameterDetailsRequest(
                parameter_name="prompt",
                node_name="enhanced_prompt_image",
                mode_allowed_property=False,
                initial_setup=True,
            )
        )
    node7_name = GriptapeNodes.handle_request(
        CreateNodeRequest(
            node_type="Agent",
            specific_library_name="Griptape Nodes Library",
            node_name="bespoke_prompt",
            metadata={
                "position": {"x": 650, "y": 700},
                "library_node_metadata": NodeMetadata(
                    category="agents", description="Agent node", display_name="Agent", tags=None
                ),
                "library": "Griptape Nodes Library",
                "node_type": "Agent",
            },
        )
    ).node_name
    with GriptapeNodes.ContextManager().node(node7_name):
        GriptapeNodes.handle_request(
            AlterParameterDetailsRequest(
                parameter_name="tools",
                node_name="bespoke_prompt",
                default_value=[],
                tooltip="Connect Griptape Tools for the agent to use.\nOr connect individual tools.",
                mode_allowed_input=True,
                mode_allowed_property=False,
                mode_allowed_output=False,
                initial_setup=True,
            )
        )
        GriptapeNodes.handle_request(
            AlterParameterDetailsRequest(
                parameter_name="rulesets",
                node_name="bespoke_prompt",
                default_value=[],
                tooltip="Rulesets to apply to the agent to control its behavior.",
                mode_allowed_input=True,
                mode_allowed_property=False,
                mode_allowed_output=False,
                initial_setup=True,
            )
        )
    node8_name = GriptapeNodes.handle_request(
        CreateNodeRequest(
            node_type="GenerateImage",
            specific_library_name="Griptape Nodes Library",
            node_name="bespoke_prompt_image",
            metadata={
                "position": {"x": 1350, "y": 900},
                "library_node_metadata": {"category": "image", "description": "GenerateImage node"},
                "library": "Griptape Nodes Library",
                "node_type": "GenerateImage",
                "category": "image",
                "size": {"width": 408, "height": 670},
            },
        )
    ).node_name
    with GriptapeNodes.ContextManager().node(node8_name):
        GriptapeNodes.handle_request(
            AlterParameterDetailsRequest(
                parameter_name="prompt",
                node_name="bespoke_prompt_image",
                mode_allowed_property=False,
                initial_setup=True,
            )
        )

GriptapeNodes.handle_request(
    CreateConnectionRequest(
        source_node_name=node5_name,
        source_parameter_name="exec_out",
        target_node_name=node6_name,
        target_parameter_name="exec_in",
        initial_setup=True,
    )
)

GriptapeNodes.handle_request(
    CreateConnectionRequest(
        source_node_name=node2_name,
        source_parameter_name="text",
        target_node_name=node4_name,
        target_parameter_name="input_1",
        initial_setup=True,
    )
)

GriptapeNodes.handle_request(
    CreateConnectionRequest(
        source_node_name=node6_name,
        source_parameter_name="exec_out",
        target_node_name=node7_name,
        target_parameter_name="exec_in",
        initial_setup=True,
    )
)

GriptapeNodes.handle_request(
    CreateConnectionRequest(
        source_node_name=node7_name,
        source_parameter_name="exec_out",
        target_node_name=node8_name,
        target_parameter_name="exec_in",
        initial_setup=True,
    )
)

GriptapeNodes.handle_request(
    CreateConnectionRequest(
        source_node_name=node7_name,
        source_parameter_name="output",
        target_node_name=node8_name,
        target_parameter_name="prompt",
        initial_setup=True,
    )
)

GriptapeNodes.handle_request(
    CreateConnectionRequest(
        source_node_name=node4_name,
        source_parameter_name="output",
        target_node_name=node7_name,
        target_parameter_name="prompt",
        initial_setup=True,
    )
)

GriptapeNodes.handle_request(
    CreateConnectionRequest(
        source_node_name=node3_name,
        source_parameter_name="text",
        target_node_name=node4_name,
        target_parameter_name="input_2",
        initial_setup=True,
    )
)

GriptapeNodes.handle_request(
    CreateConnectionRequest(
        source_node_name=node3_name,
        source_parameter_name="text",
        target_node_name=node6_name,
        target_parameter_name="prompt",
        initial_setup=True,
    )
)

GriptapeNodes.handle_request(
    CreateConnectionRequest(
        source_node_name=node3_name,
        source_parameter_name="text",
        target_node_name=node5_name,
        target_parameter_name="prompt",
        initial_setup=True,
    )
)

with GriptapeNodes.ContextManager().node(node0_name):
    GriptapeNodes.handle_request(
        SetParameterValueRequest(
            parameter_name="note",
            node_name=node0_name,
            value=top_level_unique_values_dict["36f12306-b62e-4fec-a905-2790877ee558"],
            initial_setup=True,
            is_output=False,
        )
    )

with GriptapeNodes.ContextManager().node(node1_name):
    GriptapeNodes.handle_request(
        SetParameterValueRequest(
            parameter_name="note",
            node_name=node1_name,
            value=top_level_unique_values_dict["8cbf8e5b-a940-4db4-9bd9-194922c26cf4"],
            initial_setup=True,
            is_output=False,
        )
    )

with GriptapeNodes.ContextManager().node(node2_name):
    GriptapeNodes.handle_request(
        SetParameterValueRequest(
            parameter_name="text",
            node_name=node2_name,
            value=top_level_unique_values_dict["07a91280-653b-4bc2-8b59-984f0ed63f0e"],
            initial_setup=True,
            is_output=False,
        )
    )

with GriptapeNodes.ContextManager().node(node3_name):
    GriptapeNodes.handle_request(
        SetParameterValueRequest(
            parameter_name="text",
            node_name=node3_name,
            value=top_level_unique_values_dict["f5810999-25c0-4230-a80d-0aa2a83d37d6"],
            initial_setup=True,
            is_output=False,
        )
    )

with GriptapeNodes.ContextManager().node(node4_name):
    GriptapeNodes.handle_request(
        SetParameterValueRequest(
            parameter_name="input_1",
            node_name=node4_name,
            value=top_level_unique_values_dict["07a91280-653b-4bc2-8b59-984f0ed63f0e"],
            initial_setup=True,
            is_output=False,
        )
    )
    GriptapeNodes.handle_request(
        SetParameterValueRequest(
            parameter_name="input_2",
            node_name=node4_name,
            value=top_level_unique_values_dict["f5810999-25c0-4230-a80d-0aa2a83d37d6"],
            initial_setup=True,
            is_output=False,
        )
    )
    GriptapeNodes.handle_request(
        SetParameterValueRequest(
            parameter_name="merge_string",
            node_name=node4_name,
            value=top_level_unique_values_dict["8114492d-d2b1-4c0b-b04f-6e6734e15100"],
            initial_setup=True,
            is_output=False,
        )
    )

with GriptapeNodes.ContextManager().node(node5_name):
    GriptapeNodes.handle_request(
        SetParameterValueRequest(
            parameter_name="prompt",
            node_name=node5_name,
            value=top_level_unique_values_dict["f5810999-25c0-4230-a80d-0aa2a83d37d6"],
            initial_setup=True,
            is_output=False,
        )
    )
    GriptapeNodes.handle_request(
        SetParameterValueRequest(
            parameter_name="enhance_prompt",
            node_name=node5_name,
            value=top_level_unique_values_dict["f4e11629-0175-4c89-9d2a-dcbc9ac362e3"],
            initial_setup=True,
            is_output=False,
        )
    )
    GriptapeNodes.handle_request(
        SetParameterValueRequest(
            parameter_name="output",
            node_name=node5_name,
            value=top_level_unique_values_dict["062d2c9c-0610-4787-896c-9c058d2b9409"],
            initial_setup=True,
            is_output=False,
        )
    )

with GriptapeNodes.ContextManager().node(node6_name):
    GriptapeNodes.handle_request(
        SetParameterValueRequest(
            parameter_name="prompt",
            node_name=node6_name,
            value=top_level_unique_values_dict["f5810999-25c0-4230-a80d-0aa2a83d37d6"],
            initial_setup=True,
            is_output=False,
        )
    )
    GriptapeNodes.handle_request(
        SetParameterValueRequest(
            parameter_name="enhance_prompt",
            node_name=node6_name,
            value=top_level_unique_values_dict["d0c7eb94-1b4d-4389-88c3-e475d871fbf4"],
            initial_setup=True,
            is_output=False,
        )
    )

with GriptapeNodes.ContextManager().node(node7_name):
    GriptapeNodes.handle_request(
        SetParameterValueRequest(
            parameter_name="model",
            node_name=node7_name,
            value=top_level_unique_values_dict["4af42606-aaed-4af4-953c-f14036720723"],
            initial_setup=True,
            is_output=False,
        )
    )
    GriptapeNodes.handle_request(
        SetParameterValueRequest(
            parameter_name="include_details",
            node_name=node7_name,
            value=top_level_unique_values_dict["f4e11629-0175-4c89-9d2a-dcbc9ac362e3"],
            initial_setup=True,
            is_output=False,
        )
    )

with GriptapeNodes.ContextManager().node(node8_name):
    GriptapeNodes.handle_request(
        SetParameterValueRequest(
            parameter_name="enhance_prompt",
            node_name=node8_name,
            value=top_level_unique_values_dict["f4e11629-0175-4c89-9d2a-dcbc9ac362e3"],
            initial_setup=True,
            is_output=False,
        )
    )
