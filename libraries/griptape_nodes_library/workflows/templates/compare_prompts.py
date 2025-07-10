# /// script
# dependencies = []
#
# [tool.griptape-nodes]
# name = "compare_prompts"
# schema_version = "0.4.0"
# engine_version_created_with = "0.41.0"
# node_libraries_referenced = [["Griptape Nodes Library", "0.41.0"]]
# description = "See how 3 different approaches to prompts affect image generation."
# image = "https://raw.githubusercontent.com/griptape-ai/griptape-nodes/refs/heads/main/libraries/griptape_nodes_library/workflows/templates/thumbnail_compare_prompts.webp"
# is_griptape_provided = true
# is_template = true
# creation_date = 2025-05-01T01:00:00.000000+00:00
# last_modified_date = 2025-07-07T13:38:11.127592-07:00
#
# ///

import pickle
from griptape_nodes.node_library.library_registry import IconVariant, NodeMetadata
from griptape_nodes.retained_mode.events.connection_events import CreateConnectionRequest
from griptape_nodes.retained_mode.events.flow_events import CreateFlowRequest
from griptape_nodes.retained_mode.events.library_events import (
    GetAllInfoForAllLibrariesRequest,
    GetAllInfoForAllLibrariesResultSuccess,
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
    "f8c9f713-3d05-4ea0-900a-c5e9136edde7": pickle.loads(
        b'\x80\x04\x95\xbf\x01\x00\x00\x00\x00\x00\x00X\xb8\x01\x00\x00This workflow serves as the lesson material for the tutorial located at:\n\nhttps://docs.griptapenodes.com/en/stable/ftue/03_compare_prompts/FTUE_03_compare_prompts/\n\nThe concepts covered are:\n\n- How to use one TextInput node to feed to multiple other inputs\n- Different approaches to prompt engineering\n- The GenerateImage "Enhance Prompt" feature and how it works behind the scenes\n- Comparing the results of different prompting techniques\n\x94.'
    ),
    "8b76f498-6c37-4f08-8394-8dfa44698f17": pickle.loads(
        b"\x80\x04\x95\xf9\x00\x00\x00\x00\x00\x00\x00\x8c\xf5If you're following along with our Getting Started tutorials, check out the next suggested template: Photography_Team.\n\nLoad the next tutorial page here:\nhttps://docs.griptapenodes.com/en/stable/ftue/04_photography_team/FTUE_04_photography_team/\x94."
    ),
    "a61dfec1-ae9f-4413-9d85-954b57438a54": pickle.loads(
        b"\x80\x04\x95\xcf\x01\x00\x00\x00\x00\x00\x00X\xc8\x01\x00\x00Enhance the following prompt for an image generation engine. Return only the image generation prompt.\nInclude unique details that make the subject stand out.\nSpecify a specific depth of field, and time of day.\nUse dust in the air to create a sense of depth.\nUse a slight vignetting on the edges of the image.\nUse a color palette that is complementary to the subject.\nFocus on qualities that will make this the most professional looking photo in the world.\n\x94."
    ),
    "1c8e89e3-370a-4287-86a4-d2022ba244d6": pickle.loads(
        b"\x80\x04\x95#\x00\x00\x00\x00\x00\x00\x00\x8c\x1fA capybara eating with utensils\x94."
    ),
    "0d853469-86a3-4494-97ba-633657f9508e": pickle.loads(
        b"\x80\x04\x95\x08\x00\x00\x00\x00\x00\x00\x00\x8c\x04\\n\\n\x94."
    ),
    "fd1e4b05-2e4a-4972-953d-78ea33041b09": pickle.loads(b"\x80\x04\x89."),
    "b809636d-09a6-4259-b903-53d44eda0d0b": pickle.loads(
        b"\x80\x04\x95\xf9\x00\x00\x00\x00\x00\x00\x00}\x94(\x8c\x04type\x94\x8c\rImageArtifact\x94\x8c\x02id\x94\x8c a1d85e8dfa5745b7a39be55cca4660fb\x94\x8c\treference\x94N\x8c\x04meta\x94}\x94(\x8c\x05model\x94\x8c\x08dall-e-3\x94\x8c\x06prompt\x94\x8c\x1fA capybara eating with utensils\x94u\x8c\x04name\x94\x8c$image_artifact_250411205314_ll63.png\x94\x8c\x05value\x94\x8c\x00\x94\x8c\x06format\x94\x8c\x03png\x94\x8c\x05width\x94M\x00\x04\x8c\x06height\x94M\x00\x04u."
    ),
    "c19c655b-0e1b-4a91-9803-a80461e956f9": pickle.loads(b"\x80\x04\x88."),
    "de286745-1f22-4914-85af-425fb857cd7d": pickle.loads(
        b"\x80\x04\x95\x0b\x00\x00\x00\x00\x00\x00\x00\x8c\x07gpt-4.1\x94."
    ),
    "dc7015b3-00a2-4c8a-a247-16d18dd72e26": pickle.loads(b"\x80\x04]\x94."),
    "e7d259cf-ceba-411c-af5c-0527191a7044": pickle.loads(b"\x80\x04]\x94."),
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
            value=top_level_unique_values_dict["f8c9f713-3d05-4ea0-900a-c5e9136edde7"],
            initial_setup=True,
            is_output=False,
        )
    )

with GriptapeNodes.ContextManager().node(node1_name):
    GriptapeNodes.handle_request(
        SetParameterValueRequest(
            parameter_name="note",
            node_name=node1_name,
            value=top_level_unique_values_dict["8b76f498-6c37-4f08-8394-8dfa44698f17"],
            initial_setup=True,
            is_output=False,
        )
    )

with GriptapeNodes.ContextManager().node(node2_name):
    GriptapeNodes.handle_request(
        SetParameterValueRequest(
            parameter_name="text",
            node_name=node2_name,
            value=top_level_unique_values_dict["a61dfec1-ae9f-4413-9d85-954b57438a54"],
            initial_setup=True,
            is_output=False,
        )
    )

with GriptapeNodes.ContextManager().node(node3_name):
    GriptapeNodes.handle_request(
        SetParameterValueRequest(
            parameter_name="text",
            node_name=node3_name,
            value=top_level_unique_values_dict["1c8e89e3-370a-4287-86a4-d2022ba244d6"],
            initial_setup=True,
            is_output=False,
        )
    )

with GriptapeNodes.ContextManager().node(node4_name):
    GriptapeNodes.handle_request(
        SetParameterValueRequest(
            parameter_name="input_1",
            node_name=node4_name,
            value=top_level_unique_values_dict["a61dfec1-ae9f-4413-9d85-954b57438a54"],
            initial_setup=True,
            is_output=False,
        )
    )
    GriptapeNodes.handle_request(
        SetParameterValueRequest(
            parameter_name="input_2",
            node_name=node4_name,
            value=top_level_unique_values_dict["1c8e89e3-370a-4287-86a4-d2022ba244d6"],
            initial_setup=True,
            is_output=False,
        )
    )
    GriptapeNodes.handle_request(
        SetParameterValueRequest(
            parameter_name="merge_string",
            node_name=node4_name,
            value=top_level_unique_values_dict["0d853469-86a3-4494-97ba-633657f9508e"],
            initial_setup=True,
            is_output=False,
        )
    )

with GriptapeNodes.ContextManager().node(node5_name):
    GriptapeNodes.handle_request(
        SetParameterValueRequest(
            parameter_name="prompt",
            node_name=node5_name,
            value=top_level_unique_values_dict["1c8e89e3-370a-4287-86a4-d2022ba244d6"],
            initial_setup=True,
            is_output=False,
        )
    )
    GriptapeNodes.handle_request(
        SetParameterValueRequest(
            parameter_name="enhance_prompt",
            node_name=node5_name,
            value=top_level_unique_values_dict["fd1e4b05-2e4a-4972-953d-78ea33041b09"],
            initial_setup=True,
            is_output=False,
        )
    )
    GriptapeNodes.handle_request(
        SetParameterValueRequest(
            parameter_name="output",
            node_name=node5_name,
            value=top_level_unique_values_dict["b809636d-09a6-4259-b903-53d44eda0d0b"],
            initial_setup=True,
            is_output=False,
        )
    )

with GriptapeNodes.ContextManager().node(node6_name):
    GriptapeNodes.handle_request(
        SetParameterValueRequest(
            parameter_name="prompt",
            node_name=node6_name,
            value=top_level_unique_values_dict["1c8e89e3-370a-4287-86a4-d2022ba244d6"],
            initial_setup=True,
            is_output=False,
        )
    )
    GriptapeNodes.handle_request(
        SetParameterValueRequest(
            parameter_name="enhance_prompt",
            node_name=node6_name,
            value=top_level_unique_values_dict["c19c655b-0e1b-4a91-9803-a80461e956f9"],
            initial_setup=True,
            is_output=False,
        )
    )

with GriptapeNodes.ContextManager().node(node7_name):
    GriptapeNodes.handle_request(
        SetParameterValueRequest(
            parameter_name="model",
            node_name=node7_name,
            value=top_level_unique_values_dict["de286745-1f22-4914-85af-425fb857cd7d"],
            initial_setup=True,
            is_output=False,
        )
    )
    GriptapeNodes.handle_request(
        SetParameterValueRequest(
            parameter_name="tools",
            node_name=node7_name,
            value=top_level_unique_values_dict["dc7015b3-00a2-4c8a-a247-16d18dd72e26"],
            initial_setup=True,
            is_output=False,
        )
    )
    GriptapeNodes.handle_request(
        SetParameterValueRequest(
            parameter_name="rulesets",
            node_name=node7_name,
            value=top_level_unique_values_dict["e7d259cf-ceba-411c-af5c-0527191a7044"],
            initial_setup=True,
            is_output=False,
        )
    )
    GriptapeNodes.handle_request(
        SetParameterValueRequest(
            parameter_name="include_details",
            node_name=node7_name,
            value=top_level_unique_values_dict["fd1e4b05-2e4a-4972-953d-78ea33041b09"],
            initial_setup=True,
            is_output=False,
        )
    )

with GriptapeNodes.ContextManager().node(node8_name):
    GriptapeNodes.handle_request(
        SetParameterValueRequest(
            parameter_name="enhance_prompt",
            node_name=node8_name,
            value=top_level_unique_values_dict["fd1e4b05-2e4a-4972-953d-78ea33041b09"],
            initial_setup=True,
            is_output=False,
        )
    )