# /// script
# dependencies = []
#
# [tool.griptape-nodes]
# name = "compare_prompts"
# schema_version = "0.11.0"
# engine_version_created_with = "0.60.0"
# node_libraries_referenced = [["Griptape Nodes Library", "0.50.0"]]
# node_types_used = [["Griptape Nodes Library", "Agent"], ["Griptape Nodes Library", "GenerateImage"], ["Griptape Nodes Library", "MergeTexts"], ["Griptape Nodes Library", "Note"], ["Griptape Nodes Library", "TextInput"]]
# description = "See how 3 different approaches to prompts affect image generation."
# image = "https://raw.githubusercontent.com/griptape-ai/griptape-nodes/refs/heads/main/libraries/griptape_nodes_library/workflows/templates/thumbnail_compare_prompts.webp"
# is_griptape_provided = true
# is_template = true
# creation_date = 2025-10-22T19:01:21.850102Z
# last_modified_date = 2025-10-22T19:01:21.871889Z
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
    context_manager.push_workflow(workflow_name="compare_prompts")

"""
1. We've collated all of the unique parameter values into a dictionary so that we do not have to duplicate them.
   This minimizes the size of the code, especially for large objects like serialized image files.
2. We're using a prefix so that it's clear which Flow these values are associated with.
3. The values are serialized using pickle, which is a binary format. This makes them harder to read, but makes
   them consistently save and load. It allows us to serialize complex objects like custom classes, which otherwise
   would be difficult to serialize.
"""
top_level_unique_values_dict = {
    "2a9064eb-faee-45fd-9c98-de4e25a6bc88": pickle.loads(
        b'\x80\x04\x95\xbf\x01\x00\x00\x00\x00\x00\x00X\xb8\x01\x00\x00This workflow serves as the lesson material for the tutorial located at:\n\nhttps://docs.griptapenodes.com/en/stable/ftue/03_compare_prompts/FTUE_03_compare_prompts/\n\nThe concepts covered are:\n\n- How to use one TextInput node to feed to multiple other inputs\n- Different approaches to prompt engineering\n- The GenerateImage "Enhance Prompt" feature and how it works behind the scenes\n- Comparing the results of different prompting techniques\n\x94.'
    ),
    "d71c5fe2-e415-4ad3-8de9-c6130f94a6ac": pickle.loads(
        b"\x80\x04\x95\xf9\x00\x00\x00\x00\x00\x00\x00\x8c\xf5If you're following along with our Getting Started tutorials, check out the next suggested template: Photography_Team.\n\nLoad the next tutorial page here:\nhttps://docs.griptapenodes.com/en/stable/ftue/04_photography_team/FTUE_04_photography_team/\x94."
    ),
    "95fa4cd4-64b2-41dd-996f-9b46a68fff88": pickle.loads(
        b"\x80\x04\x95\xcf\x01\x00\x00\x00\x00\x00\x00X\xc8\x01\x00\x00Enhance the following prompt for an image generation engine. Return only the image generation prompt.\nInclude unique details that make the subject stand out.\nSpecify a specific depth of field, and time of day.\nUse dust in the air to create a sense of depth.\nUse a slight vignetting on the edges of the image.\nUse a color palette that is complementary to the subject.\nFocus on qualities that will make this the most professional looking photo in the world.\n\x94."
    ),
    "b255b95e-5e8b-4c84-9a6f-b03ead6b1762": pickle.loads(
        b"\x80\x04\x95\x15\x00\x00\x00\x00\x00\x00\x00\x8c\x11A happy capybara.\x94."
    ),
    "bbf89366-a744-4d6e-a668-c6c905684e76": pickle.loads(
        b"\x80\x04\x95\x08\x00\x00\x00\x00\x00\x00\x00\x8c\x04\\n\\n\x94."
    ),
    "cfef17cb-67b8-4235-a32f-fa5d02a42d3c": pickle.loads(
        b"\x80\x04\x95\x0f\x00\x00\x00\x00\x00\x00\x00\x8c\x0bgpt-image-1\x94."
    ),
    "741cb1ff-40ac-4d59-8f54-db99a188d2b3": pickle.loads(
        b"\x80\x04\x95\r\x00\x00\x00\x00\x00\x00\x00\x8c\t1024x1024\x94."
    ),
    "88b883b3-c763-4dd2-9e7d-532e7ed9c770": pickle.loads(b"\x80\x04\x89."),
    "50cfc69d-7249-49ee-8ba8-78cc99e5eeba": pickle.loads(
        b"\x80\x04\x95\xf9\x00\x00\x00\x00\x00\x00\x00}\x94(\x8c\x04type\x94\x8c\rImageArtifact\x94\x8c\x02id\x94\x8c a1d85e8dfa5745b7a39be55cca4660fb\x94\x8c\treference\x94N\x8c\x04meta\x94}\x94(\x8c\x05model\x94\x8c\x08dall-e-3\x94\x8c\x06prompt\x94\x8c\x1fA capybara eating with utensils\x94u\x8c\x04name\x94\x8c$image_artifact_250411205314_ll63.png\x94\x8c\x05value\x94\x8c\x00\x94\x8c\x06format\x94\x8c\x03png\x94\x8c\x05width\x94M\x00\x04\x8c\x06height\x94M\x00\x04u."
    ),
    "66e58f56-335e-4cc4-842f-e91bfbb223fa": pickle.loads(b"\x80\x04\x88."),
    "ee960a17-0772-4d53-98ea-e6a0b33fcb80": pickle.loads(
        b"\x80\x04\x95\x0b\x00\x00\x00\x00\x00\x00\x00\x8c\x07gpt-4.1\x94."
    ),
    "2548e719-3326-4a65-bd08-a5969b688fa6": pickle.loads(b"\x80\x04]\x94."),
    "c64c6c18-b6b3-4f4e-8adf-93a4ee90e241": pickle.loads(b"\x80\x04]\x94."),
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
                "position": {"x": -650, "y": -700},
                "size": {"width": 1200, "height": 400},
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
                "position": {"x": 2676.8992404526084, "y": 1346.9869745169922},
                "size": {"width": 1100, "height": 251},
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
                "showaddparameter": False,
                "category": "misc",
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
                    group="create",
                    deprecation=None,
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
                    group="create",
                    deprecation=None,
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
                    group="merge",
                    deprecation=None,
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
                "position": {"x": 842.0274197040637, "y": -467.35709557875185},
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
                "size": {"width": 400, "height": 657},
                "showaddparameter": False,
                "category": "image",
            },
            initial_setup=True,
        )
    ).node_name
    with GriptapeNodes.ContextManager().node(node5_name):
        GriptapeNodes.handle_request(
            AlterParameterDetailsRequest(parameter_name="prompt", mode_allowed_property=False, initial_setup=True)
        )
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
    node6_name = GriptapeNodes.handle_request(
        CreateNodeRequest(
            node_type="GenerateImage",
            specific_library_name="Griptape Nodes Library",
            node_name="enhanced_prompt_image",
            metadata={
                "position": {"x": 1401.2241257441278, "y": 117.07470858137603},
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
                "size": {"width": 413, "height": 672},
                "showaddparameter": False,
                "category": "image",
            },
            initial_setup=True,
        )
    ).node_name
    with GriptapeNodes.ContextManager().node(node6_name):
        GriptapeNodes.handle_request(
            AlterParameterDetailsRequest(parameter_name="prompt", mode_allowed_property=False, initial_setup=True)
        )
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
    node7_name = GriptapeNodes.handle_request(
        CreateNodeRequest(
            node_type="Agent",
            specific_library_name="Griptape Nodes Library",
            node_name="bespoke_prompt",
            metadata={
                "position": {"x": 2060.797796536193, "y": 386},
                "library_node_metadata": NodeMetadata(
                    category="agents",
                    description="Creates an AI agent with conversation memory and the ability to use tools",
                    display_name="Agent",
                    tags=None,
                    icon=None,
                    color=None,
                    group="create",
                    deprecation=None,
                ),
                "library": "Griptape Nodes Library",
                "node_type": "Agent",
                "showaddparameter": False,
                "category": "agents",
                "size": {"width": 400, "height": 620},
            },
            initial_setup=True,
        )
    ).node_name
    node8_name = GriptapeNodes.handle_request(
        CreateNodeRequest(
            node_type="GenerateImage",
            specific_library_name="Griptape Nodes Library",
            node_name="bespoke_prompt_image",
            metadata={
                "position": {"x": 2676.8992404526084, "y": 605.4612769712638},
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
                "size": {"width": 408, "height": 670},
                "showaddparameter": False,
            },
            initial_setup=True,
        )
    ).node_name
    with GriptapeNodes.ContextManager().node(node8_name):
        GriptapeNodes.handle_request(
            AlterParameterDetailsRequest(parameter_name="prompt", mode_allowed_property=False, initial_setup=True)
        )
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
                value=top_level_unique_values_dict["2a9064eb-faee-45fd-9c98-de4e25a6bc88"],
                initial_setup=True,
                is_output=False,
            )
        )
    with GriptapeNodes.ContextManager().node(node1_name):
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="note",
                node_name=node1_name,
                value=top_level_unique_values_dict["d71c5fe2-e415-4ad3-8de9-c6130f94a6ac"],
                initial_setup=True,
                is_output=False,
            )
        )
    with GriptapeNodes.ContextManager().node(node2_name):
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="text",
                node_name=node2_name,
                value=top_level_unique_values_dict["95fa4cd4-64b2-41dd-996f-9b46a68fff88"],
                initial_setup=True,
                is_output=False,
            )
        )
    with GriptapeNodes.ContextManager().node(node3_name):
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="text",
                node_name=node3_name,
                value=top_level_unique_values_dict["b255b95e-5e8b-4c84-9a6f-b03ead6b1762"],
                initial_setup=True,
                is_output=False,
            )
        )
    with GriptapeNodes.ContextManager().node(node4_name):
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="input_1",
                node_name=node4_name,
                value=top_level_unique_values_dict["95fa4cd4-64b2-41dd-996f-9b46a68fff88"],
                initial_setup=True,
                is_output=False,
            )
        )
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="input_2",
                node_name=node4_name,
                value=top_level_unique_values_dict["b255b95e-5e8b-4c84-9a6f-b03ead6b1762"],
                initial_setup=True,
                is_output=False,
            )
        )
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="merge_string",
                node_name=node4_name,
                value=top_level_unique_values_dict["bbf89366-a744-4d6e-a668-c6c905684e76"],
                initial_setup=True,
                is_output=False,
            )
        )
    with GriptapeNodes.ContextManager().node(node5_name):
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="model",
                node_name=node5_name,
                value=top_level_unique_values_dict["cfef17cb-67b8-4235-a32f-fa5d02a42d3c"],
                initial_setup=True,
                is_output=False,
            )
        )
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="prompt",
                node_name=node5_name,
                value=top_level_unique_values_dict["b255b95e-5e8b-4c84-9a6f-b03ead6b1762"],
                initial_setup=True,
                is_output=False,
            )
        )
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="image_size",
                node_name=node5_name,
                value=top_level_unique_values_dict["741cb1ff-40ac-4d59-8f54-db99a188d2b3"],
                initial_setup=True,
                is_output=False,
            )
        )
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="enhance_prompt",
                node_name=node5_name,
                value=top_level_unique_values_dict["88b883b3-c763-4dd2-9e7d-532e7ed9c770"],
                initial_setup=True,
                is_output=False,
            )
        )
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="output",
                node_name=node5_name,
                value=top_level_unique_values_dict["50cfc69d-7249-49ee-8ba8-78cc99e5eeba"],
                initial_setup=True,
                is_output=False,
            )
        )
    with GriptapeNodes.ContextManager().node(node6_name):
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="model",
                node_name=node6_name,
                value=top_level_unique_values_dict["cfef17cb-67b8-4235-a32f-fa5d02a42d3c"],
                initial_setup=True,
                is_output=False,
            )
        )
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="prompt",
                node_name=node6_name,
                value=top_level_unique_values_dict["b255b95e-5e8b-4c84-9a6f-b03ead6b1762"],
                initial_setup=True,
                is_output=False,
            )
        )
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="image_size",
                node_name=node6_name,
                value=top_level_unique_values_dict["741cb1ff-40ac-4d59-8f54-db99a188d2b3"],
                initial_setup=True,
                is_output=False,
            )
        )
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="enhance_prompt",
                node_name=node6_name,
                value=top_level_unique_values_dict["66e58f56-335e-4cc4-842f-e91bfbb223fa"],
                initial_setup=True,
                is_output=False,
            )
        )
    with GriptapeNodes.ContextManager().node(node7_name):
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="model",
                node_name=node7_name,
                value=top_level_unique_values_dict["ee960a17-0772-4d53-98ea-e6a0b33fcb80"],
                initial_setup=True,
                is_output=False,
            )
        )
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="tools",
                node_name=node7_name,
                value=top_level_unique_values_dict["2548e719-3326-4a65-bd08-a5969b688fa6"],
                initial_setup=True,
                is_output=False,
            )
        )
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="rulesets",
                node_name=node7_name,
                value=top_level_unique_values_dict["c64c6c18-b6b3-4f4e-8adf-93a4ee90e241"],
                initial_setup=True,
                is_output=False,
            )
        )
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="include_details",
                node_name=node7_name,
                value=top_level_unique_values_dict["88b883b3-c763-4dd2-9e7d-532e7ed9c770"],
                initial_setup=True,
                is_output=False,
            )
        )
    with GriptapeNodes.ContextManager().node(node8_name):
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="model",
                node_name=node8_name,
                value=top_level_unique_values_dict["cfef17cb-67b8-4235-a32f-fa5d02a42d3c"],
                initial_setup=True,
                is_output=False,
            )
        )
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="image_size",
                node_name=node8_name,
                value=top_level_unique_values_dict["741cb1ff-40ac-4d59-8f54-db99a188d2b3"],
                initial_setup=True,
                is_output=False,
            )
        )
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="enhance_prompt",
                node_name=node8_name,
                value=top_level_unique_values_dict["88b883b3-c763-4dd2-9e7d-532e7ed9c770"],
                initial_setup=True,
                is_output=False,
            )
        )
