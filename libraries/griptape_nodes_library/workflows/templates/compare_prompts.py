# /// script
# dependencies = []
#
# [tool.griptape-nodes]
# name = "compare_prompts"
# schema_version = "0.6.1"
# engine_version_created_with = "0.43.1"
# node_libraries_referenced = [["Griptape Nodes Library", "0.41.0"]]
# description = "See how 3 different approaches to prompts affect image generation."
# image = "https://raw.githubusercontent.com/griptape-ai/griptape-nodes/refs/heads/main/libraries/griptape_nodes_library/workflows/templates/thumbnail_compare_prompts.webp"
# is_griptape_provided = true
# is_template = true
# creation_date = 2025-05-01T01:00:00.000000+00:00
# last_modified_date = 2025-08-01T14:07:31.729030-07:00
#
# ///

import pickle

from griptape_nodes.node_library.library_registry import NodeMetadata
from griptape_nodes.retained_mode.events.connection_events import CreateConnectionRequest
from griptape_nodes.retained_mode.events.flow_events import CreateFlowRequest
from griptape_nodes.retained_mode.events.library_events import (
    GetAllInfoForAllLibrariesRequest,
    GetAllInfoForAllLibrariesResultSuccess,
)
from griptape_nodes.retained_mode.events.node_events import CreateNodeRequest
from griptape_nodes.retained_mode.events.parameter_events import (
    AlterParameterDetailsRequest,
    SetParameterValueRequest,
)
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

response = GriptapeNodes.LibraryManager().get_all_info_for_all_libraries_request(GetAllInfoForAllLibrariesRequest())

if (
    isinstance(response, GetAllInfoForAllLibrariesResultSuccess)
    and len(response.library_name_to_library_info.keys()) < 1
):
    GriptapeNodes.LibraryManager().load_all_libraries_from_config()

context_manager = GriptapeNodes.ContextManager()

if not context_manager.has_current_workflow():
    context_manager.push_workflow(workflow_name="compare_prompts_1")

"""
1. We've collated all of the unique parameter values into a dictionary so that we do not have to duplicate them.
   This minimizes the size of the code, especially for large objects like serialized image files.
2. We're using a prefix so that it's clear which Flow these values are associated with.
3. The values are serialized using pickle, which is a binary format. This makes them harder to read, but makes
   them consistently save and load. It allows us to serialize complex objects like custom classes, which otherwise
   would be difficult to serialize.
"""
top_level_unique_values_dict = {
    "625fb631-4e7d-46de-beb3-377daaf2f54f": pickle.loads(
        b'\x80\x04\x95\xbf\x01\x00\x00\x00\x00\x00\x00X\xb8\x01\x00\x00This workflow serves as the lesson material for the tutorial located at:\n\nhttps://docs.griptapenodes.com/en/stable/ftue/03_compare_prompts/FTUE_03_compare_prompts/\n\nThe concepts covered are:\n\n- How to use one TextInput node to feed to multiple other inputs\n- Different approaches to prompt engineering\n- The GenerateImage "Enhance Prompt" feature and how it works behind the scenes\n- Comparing the results of different prompting techniques\n\x94.'
    ),
    "8f23b4aa-f0df-4677-bdea-b580fca4b0d9": pickle.loads(
        b"\x80\x04\x95\xf9\x00\x00\x00\x00\x00\x00\x00\x8c\xf5If you're following along with our Getting Started tutorials, check out the next suggested template: Photography_Team.\n\nLoad the next tutorial page here:\nhttps://docs.griptapenodes.com/en/stable/ftue/04_photography_team/FTUE_04_photography_team/\x94."
    ),
    "83428258-61af-4336-8b55-135a34cf660c": pickle.loads(
        b"\x80\x04\x95\xcf\x01\x00\x00\x00\x00\x00\x00X\xc8\x01\x00\x00Enhance the following prompt for an image generation engine. Return only the image generation prompt.\nInclude unique details that make the subject stand out.\nSpecify a specific depth of field, and time of day.\nUse dust in the air to create a sense of depth.\nUse a slight vignetting on the edges of the image.\nUse a color palette that is complementary to the subject.\nFocus on qualities that will make this the most professional looking photo in the world.\n\x94."
    ),
    "5ed879bb-20cf-4479-815d-c9915fbd262b": pickle.loads(
        b"\x80\x04\x95'\x00\x00\x00\x00\x00\x00\x00\x8c#A capybara eating soup with a spoon\x94."
    ),
    "8fcd5bef-f968-40c7-ae47-f48517885ad0": pickle.loads(
        b"\x80\x04\x95\x08\x00\x00\x00\x00\x00\x00\x00\x8c\x04\\n\\n\x94."
    ),
    "844bc3fe-3f08-4d8a-bd48-147d2899a8c5": pickle.loads(b"\x80\x04\x89."),
    "a0a5d21b-2a86-420f-b337-63577863f06e": pickle.loads(
        b"\x80\x04\x95\xf9\x00\x00\x00\x00\x00\x00\x00}\x94(\x8c\x04type\x94\x8c\rImageArtifact\x94\x8c\x02id\x94\x8c a1d85e8dfa5745b7a39be55cca4660fb\x94\x8c\treference\x94N\x8c\x04meta\x94}\x94(\x8c\x05model\x94\x8c\x08dall-e-3\x94\x8c\x06prompt\x94\x8c\x1fA capybara eating with utensils\x94u\x8c\x04name\x94\x8c$image_artifact_250411205314_ll63.png\x94\x8c\x05value\x94\x8c\x00\x94\x8c\x06format\x94\x8c\x03png\x94\x8c\x05width\x94M\x00\x04\x8c\x06height\x94M\x00\x04u."
    ),
    "7dde7f2d-5a54-47dd-b2fe-3240cf0950d7": pickle.loads(b"\x80\x04\x88."),
    "8523d769-1401-4450-ab15-0c022cfefad9": pickle.loads(
        b"\x80\x04\x95\x0b\x00\x00\x00\x00\x00\x00\x00\x8c\x07gpt-4.1\x94."
    ),
    "b916be58-243a-4717-b9e5-779f37b98469": pickle.loads(b"\x80\x04]\x94."),
    "c1f87d01-c9b7-4c88-a03d-833e9bea8e43": pickle.loads(b"\x80\x04]\x94."),
}

"# Create the Flow, then do work within it as context."

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
                    category="misc",
                    description="Create a note node to provide helpful context in your workflow",
                    display_name="Note",
                    tags=None,
                    icon="notepad-text",
                    color=None,
                    group=None,
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
                "position": {"x": 1900, "y": 950},
                "size": {"width": 1100, "height": 251},
                "library_node_metadata": NodeMetadata(
                    category="misc",
                    description="Create a note node to provide helpful context in your workflow",
                    display_name="Note",
                    tags=None,
                    icon="notepad-text",
                    color=None,
                    group=None,
                ),
                "library": "Griptape Nodes Library",
                "node_type": "Note",
            },
            initial_setup=True,
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
                    category="text",
                    description="TextInput node",
                    display_name="Text Input",
                    tags=None,
                    icon="text-cursor",
                    color=None,
                    group="general",
                ),
                "library": "Griptape Nodes Library",
                "node_type": "TextInput",
            },
            initial_setup=True,
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
                    category="text",
                    description="TextInput node",
                    display_name="Text Input",
                    tags=None,
                    icon="text-cursor",
                    color=None,
                    group="general",
                ),
                "library": "Griptape Nodes Library",
                "node_type": "TextInput",
            },
            initial_setup=True,
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
                    category="text",
                    description="MergeTexts node",
                    display_name="Merge Texts",
                    tags=None,
                    icon="merge",
                    color=None,
                    group="edit",
                ),
                "library": "Griptape Nodes Library",
                "node_type": "MergeTexts",
            },
            initial_setup=True,
        )
    ).node_name
    node5_name = GriptapeNodes.handle_request(
        CreateNodeRequest(
            node_type="GenerateImage",
            specific_library_name="Griptape Nodes Library",
            node_name="basic_image",
            metadata={
                "position": {"x": 1350, "y": -700},
                "library_node_metadata": NodeMetadata(
                    category="image",
                    description="Generates an image using Griptape Cloud, or other provided image generation models",
                    display_name="Generate Image",
                    tags=None,
                    icon=None,
                    color=None,
                    group="tasks",
                ),
                "library": "Griptape Nodes Library",
                "node_type": "GenerateImage",
                "size": {"width": 400, "height": 657},
            },
            initial_setup=True,
        )
    ).node_name
    with GriptapeNodes.ContextManager().node(node5_name):
        GriptapeNodes.handle_request(
            AlterParameterDetailsRequest(parameter_name="prompt", mode_allowed_property=False, initial_setup=True)
        )
    node6_name = GriptapeNodes.handle_request(
        CreateNodeRequest(
            node_type="GenerateImage",
            specific_library_name="Griptape Nodes Library",
            node_name="enhanced_prompt_image",
            metadata={
                "position": {"x": 1350, "y": 100},
                "library_node_metadata": NodeMetadata(
                    category="image",
                    description="Generates an image using Griptape Cloud, or other provided image generation models",
                    display_name="Generate Image",
                    tags=None,
                    icon=None,
                    color=None,
                    group="tasks",
                ),
                "library": "Griptape Nodes Library",
                "node_type": "GenerateImage",
                "size": {"width": 413, "height": 672},
            },
            initial_setup=True,
        )
    ).node_name
    with GriptapeNodes.ContextManager().node(node6_name):
        GriptapeNodes.handle_request(
            AlterParameterDetailsRequest(parameter_name="prompt", mode_allowed_property=False, initial_setup=True)
        )
    node7_name = GriptapeNodes.handle_request(
        CreateNodeRequest(
            node_type="Agent",
            specific_library_name="Griptape Nodes Library",
            node_name="bespoke_prompt",
            metadata={
                "position": {"x": 650, "y": 700},
                "library_node_metadata": NodeMetadata(
                    category="agents",
                    description="Creates an AI agent with conversation memory and the ability to use tools",
                    display_name="Agent",
                    tags=None,
                    icon=None,
                    color=None,
                    group=None,
                ),
                "library": "Griptape Nodes Library",
                "node_type": "Agent",
            },
            initial_setup=True,
        )
    ).node_name
    with GriptapeNodes.ContextManager().node(node7_name):
        GriptapeNodes.handle_request(
            AlterParameterDetailsRequest(
                parameter_name="tools",
                default_value=[],
                tooltip="Connect Griptape Tools for the agent to use.\nOr connect individual tools.",
                initial_setup=True,
            )
        )
        GriptapeNodes.handle_request(
            AlterParameterDetailsRequest(
                parameter_name="rulesets",
                default_value=[],
                tooltip="Rulesets to apply to the agent to control its behavior.",
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
                "library_node_metadata": NodeMetadata(
                    category="image",
                    description="Generates an image using Griptape Cloud, or other provided image generation models",
                    display_name="Generate Image",
                    tags=None,
                    icon=None,
                    color=None,
                    group="tasks",
                ),
                "library": "Griptape Nodes Library",
                "node_type": "GenerateImage",
                "category": "image",
                "size": {"width": 408, "height": 670},
            },
            initial_setup=True,
        )
    ).node_name
    with GriptapeNodes.ContextManager().node(node8_name):
        GriptapeNodes.handle_request(
            AlterParameterDetailsRequest(parameter_name="prompt", mode_allowed_property=False, initial_setup=True)
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
                value=top_level_unique_values_dict["625fb631-4e7d-46de-beb3-377daaf2f54f"],
                initial_setup=True,
                is_output=False,
            )
        )
    with GriptapeNodes.ContextManager().node(node1_name):
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="note",
                node_name=node1_name,
                value=top_level_unique_values_dict["8f23b4aa-f0df-4677-bdea-b580fca4b0d9"],
                initial_setup=True,
                is_output=False,
            )
        )
    with GriptapeNodes.ContextManager().node(node2_name):
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="text",
                node_name=node2_name,
                value=top_level_unique_values_dict["83428258-61af-4336-8b55-135a34cf660c"],
                initial_setup=True,
                is_output=False,
            )
        )
    with GriptapeNodes.ContextManager().node(node3_name):
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="text",
                node_name=node3_name,
                value=top_level_unique_values_dict["5ed879bb-20cf-4479-815d-c9915fbd262b"],
                initial_setup=True,
                is_output=False,
            )
        )
    with GriptapeNodes.ContextManager().node(node4_name):
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="input_1",
                node_name=node4_name,
                value=top_level_unique_values_dict["83428258-61af-4336-8b55-135a34cf660c"],
                initial_setup=True,
                is_output=False,
            )
        )
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="input_2",
                node_name=node4_name,
                value=top_level_unique_values_dict["5ed879bb-20cf-4479-815d-c9915fbd262b"],
                initial_setup=True,
                is_output=False,
            )
        )
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="merge_string",
                node_name=node4_name,
                value=top_level_unique_values_dict["8fcd5bef-f968-40c7-ae47-f48517885ad0"],
                initial_setup=True,
                is_output=False,
            )
        )
    with GriptapeNodes.ContextManager().node(node5_name):
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="prompt",
                node_name=node5_name,
                value=top_level_unique_values_dict["5ed879bb-20cf-4479-815d-c9915fbd262b"],
                initial_setup=True,
                is_output=False,
            )
        )
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="enhance_prompt",
                node_name=node5_name,
                value=top_level_unique_values_dict["844bc3fe-3f08-4d8a-bd48-147d2899a8c5"],
                initial_setup=True,
                is_output=False,
            )
        )
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="output",
                node_name=node5_name,
                value=top_level_unique_values_dict["a0a5d21b-2a86-420f-b337-63577863f06e"],
                initial_setup=True,
                is_output=False,
            )
        )
    with GriptapeNodes.ContextManager().node(node6_name):
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="prompt",
                node_name=node6_name,
                value=top_level_unique_values_dict["5ed879bb-20cf-4479-815d-c9915fbd262b"],
                initial_setup=True,
                is_output=False,
            )
        )
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="enhance_prompt",
                node_name=node6_name,
                value=top_level_unique_values_dict["7dde7f2d-5a54-47dd-b2fe-3240cf0950d7"],
                initial_setup=True,
                is_output=False,
            )
        )
    with GriptapeNodes.ContextManager().node(node7_name):
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="model",
                node_name=node7_name,
                value=top_level_unique_values_dict["8523d769-1401-4450-ab15-0c022cfefad9"],
                initial_setup=True,
                is_output=False,
            )
        )
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="tools",
                node_name=node7_name,
                value=top_level_unique_values_dict["b916be58-243a-4717-b9e5-779f37b98469"],
                initial_setup=True,
                is_output=False,
            )
        )
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="rulesets",
                node_name=node7_name,
                value=top_level_unique_values_dict["c1f87d01-c9b7-4c88-a03d-833e9bea8e43"],
                initial_setup=True,
                is_output=False,
            )
        )
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="include_details",
                node_name=node7_name,
                value=top_level_unique_values_dict["844bc3fe-3f08-4d8a-bd48-147d2899a8c5"],
                initial_setup=True,
                is_output=False,
            )
        )
    with GriptapeNodes.ContextManager().node(node8_name):
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="enhance_prompt",
                node_name=node8_name,
                value=top_level_unique_values_dict["844bc3fe-3f08-4d8a-bd48-147d2899a8c5"],
                initial_setup=True,
                is_output=False,
            )
        )
