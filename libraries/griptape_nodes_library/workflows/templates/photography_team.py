# /// script
# dependencies = []
#
# [tool.griptape-nodes]
# name = "photography_team"
# schema_version = "0.11.0"
# engine_version_created_with = "0.60.0"
# node_libraries_referenced = [["Griptape Nodes Library", "0.50.0"]]
# node_types_used = [["Griptape Nodes Library", "Agent"], ["Griptape Nodes Library", "AgentToTool"], ["Griptape Nodes Library", "GenerateImage"], ["Griptape Nodes Library", "Note"], ["Griptape Nodes Library", "Ruleset"], ["Griptape Nodes Library", "ToolList"]]
# description = "A team of experts develop a prompt."
# image = "https://raw.githubusercontent.com/griptape-ai/griptape-nodes/refs/heads/main/libraries/griptape_nodes_library/workflows/templates/thumbnail_photography_team.webp"
# is_griptape_provided = true
# is_template = true
# creation_date = 2025-10-22T19:00:07.437329Z
# last_modified_date = 2025-10-22T19:00:07.472708Z
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
    context_manager.push_workflow(workflow_name="photography_team")

"""
1. We've collated all of the unique parameter values into a dictionary so that we do not have to duplicate them.
   This minimizes the size of the code, especially for large objects like serialized image files.
2. We're using a prefix so that it's clear which Flow these values are associated with.
3. The values are serialized using pickle, which is a binary format. This makes them harder to read, but makes
   them consistently save and load. It allows us to serialize complex objects like custom classes, which otherwise
   would be difficult to serialize.
"""
top_level_unique_values_dict = {
    "2b8a7fba-8ef1-4166-8c5e-3cace5689e98": pickle.loads(
        b'\x80\x04\x95\xbd\x01\x00\x00\x00\x00\x00\x00X\xb6\x01\x00\x00This workflow serves as the lesson material for the tutorial located at:\n\nhttps://docs.griptapenodes.com/en/stable/ftue/04_photography_team/FTUE_04_photography_team/\n\nThe concepts covered are:\n\n- Incorporating key upgrades available to agents:\n    - Rulesets to define and manage agent behaviors\n    - Tools to give agents more abilities\n- Converting agents into tools\n- Creating and orchestrating a team of "experts" with specific roles\n\x94.'
    ),
    "439d8114-af3d-46ec-aba7-55804fd4ebae": pickle.loads(
        b'\x80\x04\x95F\x00\x00\x00\x00\x00\x00\x00\x8cBGood job. You\'ve completed our "Getting Started" set of tutorials!\x94.'
    ),
    "4b104fbe-3cde-4dce-b4bf-2eba7b198ecc": pickle.loads(
        b"\x80\x04\x95\x0b\x00\x00\x00\x00\x00\x00\x00\x8c\x07gpt-4.1\x94."
    ),
    "e961cf26-1982-4359-9a42-e4b829adf0e7": pickle.loads(b"\x80\x04]\x94."),
    "0ba6d1b4-c664-4ea5-90ae-246f563c398e": pickle.loads(b"\x80\x04\x89."),
    "8f28a114-be7f-4195-b427-c1351662c946": pickle.loads(
        b"\x80\x04\x95\x13\x00\x00\x00\x00\x00\x00\x00\x8c\x0fCinematographer\x94."
    ),
    "93726ae5-1598-4cbd-a204-76dada3317fc": pickle.loads(
        b"\x80\x04\x95)\x00\x00\x00\x00\x00\x00\x00\x8c%This agent understands cinematography\x94."
    ),
    "e704c528-9b99-4326-b295-3673536fe508": pickle.loads(b"\x80\x04]\x94."),
    "897470c4-e12b-42cb-a42d-b223d612371a": pickle.loads(
        b"\x80\x04\x95\x12\x00\x00\x00\x00\x00\x00\x00\x8c\x0eColor_Theorist\x94."
    ),
    "aa63c100-140a-4e93-80c1-ff40350956d9": pickle.loads(
        b"\x80\x04\x954\x00\x00\x00\x00\x00\x00\x00\x8c0This agent can be used to ensure the best colors\x94."
    ),
    "4b36180b-e4e2-4341-bbd9-c3d9aace7f08": pickle.loads(b"\x80\x04]\x94."),
    "f1cd4774-dcc5-44df-96f2-fc583011f712": pickle.loads(
        b"\x80\x04\x95\x15\x00\x00\x00\x00\x00\x00\x00\x8c\x11Detail_Enthusiast\x94."
    ),
    "9979f689-3750-4b70-8603-55999afada8c": pickle.loads(
        b"\x80\x04\x95n\x00\x00\x00\x00\x00\x00\x00\x8cjThis agent is into the fine details of an image. Use it to make sure descriptions are specific and unique.\x94."
    ),
    "4575c024-e57a-4bc6-8323-c9032568b877": pickle.loads(b"\x80\x04]\x94."),
    "7c262406-997c-49c6-9cda-be04e8cb4ba2": pickle.loads(
        b"\x80\x04\x95\x1f\x00\x00\x00\x00\x00\x00\x00\x8c\x1bImage_Generation_Specialist\x94."
    ),
    "f1a53150-a9fd-490d-b010-224e2f588dd9": pickle.loads(
        b'\x80\x04\x95\x9a\x00\x00\x00\x00\x00\x00\x00\x8c\x96Use all the tools at your disposal to create a spectacular image generation prompt about "a skateboarding lion", that is no longer than 500 characters\x94.'
    ),
    "d3065ce1-f20e-4d42-9768-a7a9bca0e33b": pickle.loads(b"\x80\x04\x95\x06\x00\x00\x00\x00\x00\x00\x00]\x94]\x94a."),
    "e552e43e-7cbe-4ba8-a34a-a1d209979848": pickle.loads(b"\x80\x04\x95\x06\x00\x00\x00\x00\x00\x00\x00]\x94]\x94a."),
    "aff2a758-4ff4-4ec9-96ec-1d29037db7b7": pickle.loads(
        b"\x80\x04\x95\x0f\x00\x00\x00\x00\x00\x00\x00\x8c\x0bgpt-image-1\x94."
    ),
    "f66f1f2c-3803-4fe6-9bd8-af69979c96b9": pickle.loads(
        b"\x80\x04\x95\r\x00\x00\x00\x00\x00\x00\x00\x8c\t1024x1024\x94."
    ),
    "aa22e757-1c83-4954-a384-130b5ff86b22": pickle.loads(
        b"\x80\x04\x95\x1d\x00\x00\x00\x00\x00\x00\x00\x8c\x19Detail_Enthusiast Ruleset\x94."
    ),
    "c844b511-2b49-4d6a-b307-1cbda24cbaae": pickle.loads(
        b'\x80\x04\x95\xa3\x01\x00\x00\x00\x00\x00\x00X\x9c\x01\x00\x00You care about the unique details and specific descriptions of items.\nWhen describing things, call out specific details and don\'t be generic. Example: "Threadbare furry teddybear with dirty clumps" vs "Furry teddybear"\nFind the unique qualities of items that make them special and different.\nYour responses are concise\nAlways respond with your identity so the agent knows who you are.\nKeep your responses brief.\n\x94.'
    ),
    "8d4b681d-ee90-4ee4-a2b0-1d1667f5886c": pickle.loads(
        b"\x80\x04\x95\x1b\x00\x00\x00\x00\x00\x00\x00\x8c\x17Cinematographer Ruleset\x94."
    ),
    "49075693-5915-49ff-bfcf-5f805e16a0aa": pickle.loads(
        b"\x80\x04\x95\xf0\x02\x00\x00\x00\x00\x00\x00X\xe9\x02\x00\x00You identify as a cinematographer\nThe main subject of the image should be well framed\nIf no environment is specified, set the image in a location that will evoke a deep and meaningful connection to the viewer.\nYou care deeply about light, shadow, color, and composition\nWhen coming up with image prompts, you always specify the position of the camera, the lens, and the color\nYou are specific about the technical details of a shot.\nYou like to add atmosphere to your shots, so you include depth of field, haze, dust particles in the air close to and far away from camera, and the way lighting reacts with each item.\nYour responses are brief and concise\nAlways respond with your identity so the agent knows who you are.\nKeep your responses brief.\x94."
    ),
    "b35f7c84-a8d8-49c2-93c1-30b8dca6f89d": pickle.loads(
        b"\x80\x04\x95\x1a\x00\x00\x00\x00\x00\x00\x00\x8c\x16Color_Theorist Ruleset\x94."
    ),
    "c1b2a335-4c41-475a-aa93-c7568a28d99f": pickle.loads(
        b"\x80\x04\x95'\x01\x00\x00\x00\x00\x00\x00X \x01\x00\x00You identify as an expert in color theory\nYou have a deep understanding of how color impacts one's psychological outlook\nYou are a fan of non-standard colors\nYour responses are brief and concise\nAlways respond with your identity  so the agent knows who you are.\nKeep your responses brief.\x94."
    ),
    "a3714836-36f4-48b1-840a-7818e5453ddd": pickle.loads(
        b"\x80\x04\x95'\x00\x00\x00\x00\x00\x00\x00\x8c#Image_Generation_Specialist Ruleset\x94."
    ),
    "51b6e013-d252-41ba-954f-2d749e20635d": pickle.loads(
        b"\x80\x04\x95Q\x02\x00\x00\x00\x00\x00\x00XJ\x02\x00\x00You are an expert in creating prompts for image generation engines\nYou use the latest knowledge available to you to generate the best prompts.\nYou create prompts that are direct and succinct and you understand they need to be under 800 characters long\nAlways include the following: subject, attributes of subject, visual characteristics of the image, film grain, camera angle, lighting, art style, color scheme, surrounding environment, camera used (ex: Nikon d850 film stock, polaroid, etc).\nAlways respond with your identity so the agent knows who you are.\nKeep your responses brief.\n\x94."
    ),
    "fbba38a0-e5cd-4ad6-af91-ad0c5541a6f6": pickle.loads(
        b"\x80\x04\x95\x0f\x00\x00\x00\x00\x00\x00\x00\x8c\x0bAgent Rules\x94."
    ),
    "303283f5-54bb-4d20-9089-20bf65cfea7a": pickle.loads(
        b"\x80\x04\x95\xac\x02\x00\x00\x00\x00\x00\x00X\xa5\x02\x00\x00You are creating a prompt for an image generation engine.\nYou have access to topic experts in their respective fields\nWork with the experts to get the results you need\nYou facilitate communication between them.\nIf they ask for feedback, you can provide it.\nAsk the Image_Generation_Specialist for the final prompt.\nOutput only the final image generation prompt. Do not wrap in markdown context.\nKeep your responses brief.\nIMPORTANT: Always ensure image generation prompts are completely free of sexual, violent, hateful, or politically divisive content. When in doubt, err on the side of caution and choose wholesome, neutral themes that would be appropriate for all audiences.\x94."
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
                "position": {"x": -500, "y": -500},
                "size": {"width": 1000, "height": 450},
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
            node_name="Congratulations",
            metadata={
                "position": {"x": 5100, "y": 1500},
                "size": {"width": 650, "height": 150},
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
    node2_name = GriptapeNodes.handle_request(
        CreateNodeRequest(
            node_type="Agent",
            specific_library_name="Griptape Nodes Library",
            node_name="Cinematographer",
            metadata={
                "position": {"x": 1000, "y": 0},
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
            },
            initial_setup=True,
        )
    ).node_name
    with GriptapeNodes.ContextManager().node(node2_name):
        GriptapeNodes.handle_request(
            AddParameterToNodeRequest(
                parameter_name="rulesets_ParameterListUniqueParamID_2eadbf6ecaac46a7beb1ad1ae7c4b085",
                default_value=[],
                tooltip="Rulesets to apply to the agent to control its behavior.",
                type="Ruleset",
                input_types=["Ruleset", "list[Ruleset]"],
                output_type="Ruleset",
                ui_options={},
                mode_allowed_input=True,
                mode_allowed_property=False,
                mode_allowed_output=False,
                parent_container_name="rulesets",
                initial_setup=True,
            )
        )
    node3_name = GriptapeNodes.handle_request(
        CreateNodeRequest(
            node_type="AgentToTool",
            specific_library_name="Griptape Nodes Library",
            node_name="Cinematographer_asTool",
            metadata={
                "position": {"x": 1500, "y": 0},
                "library_node_metadata": NodeMetadata(
                    category="convert",
                    description="Convert an agent into a tool that another agent can use",
                    display_name="Agent To Tool",
                    tags=None,
                    icon=None,
                    color=None,
                    group="edit",
                    deprecation=None,
                ),
                "library": "Griptape Nodes Library",
                "node_type": "AgentToTool",
            },
            initial_setup=True,
        )
    ).node_name
    node4_name = GriptapeNodes.handle_request(
        CreateNodeRequest(
            node_type="Agent",
            specific_library_name="Griptape Nodes Library",
            node_name="Color_Theorist",
            metadata={
                "position": {"x": 1000, "y": 600},
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
            },
            initial_setup=True,
        )
    ).node_name
    with GriptapeNodes.ContextManager().node(node4_name):
        GriptapeNodes.handle_request(
            AddParameterToNodeRequest(
                parameter_name="rulesets_ParameterListUniqueParamID_bda37a1a564c496da5d47bfbee59d572",
                default_value=[],
                tooltip="Rulesets to apply to the agent to control its behavior.",
                type="Ruleset",
                input_types=["Ruleset", "list[Ruleset]"],
                output_type="Ruleset",
                ui_options={},
                mode_allowed_input=True,
                mode_allowed_property=False,
                mode_allowed_output=False,
                parent_container_name="rulesets",
                initial_setup=True,
            )
        )
    node5_name = GriptapeNodes.handle_request(
        CreateNodeRequest(
            node_type="AgentToTool",
            specific_library_name="Griptape Nodes Library",
            node_name="Color_Theorist_asTool",
            metadata={
                "position": {"x": 1500, "y": 600},
                "library_node_metadata": NodeMetadata(
                    category="convert",
                    description="Convert an agent into a tool that another agent can use",
                    display_name="Agent To Tool",
                    tags=None,
                    icon=None,
                    color=None,
                    group="edit",
                    deprecation=None,
                ),
                "library": "Griptape Nodes Library",
                "node_type": "AgentToTool",
            },
            initial_setup=True,
        )
    ).node_name
    node6_name = GriptapeNodes.handle_request(
        CreateNodeRequest(
            node_type="Agent",
            specific_library_name="Griptape Nodes Library",
            node_name="Detail_Enthusiast",
            metadata={
                "position": {"x": 1000, "y": 1200},
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
            },
            initial_setup=True,
        )
    ).node_name
    with GriptapeNodes.ContextManager().node(node6_name):
        GriptapeNodes.handle_request(
            AddParameterToNodeRequest(
                parameter_name="rulesets_ParameterListUniqueParamID_bbba9d0539324d21bec72679f8034624",
                default_value=[],
                tooltip="Rulesets to apply to the agent to control its behavior.",
                type="Ruleset",
                input_types=["Ruleset", "list[Ruleset]"],
                output_type="Ruleset",
                ui_options={},
                mode_allowed_input=True,
                mode_allowed_property=False,
                mode_allowed_output=False,
                parent_container_name="rulesets",
                initial_setup=True,
            )
        )
    node7_name = GriptapeNodes.handle_request(
        CreateNodeRequest(
            node_type="AgentToTool",
            specific_library_name="Griptape Nodes Library",
            node_name="Detail_Enthusiast_asTool",
            metadata={
                "position": {"x": 1500, "y": 1200},
                "library_node_metadata": NodeMetadata(
                    category="convert",
                    description="Convert an agent into a tool that another agent can use",
                    display_name="Agent To Tool",
                    tags=None,
                    icon=None,
                    color=None,
                    group="edit",
                    deprecation=None,
                ),
                "library": "Griptape Nodes Library",
                "node_type": "AgentToTool",
            },
            initial_setup=True,
        )
    ).node_name
    node8_name = GriptapeNodes.handle_request(
        CreateNodeRequest(
            node_type="Agent",
            specific_library_name="Griptape Nodes Library",
            node_name="Image_Generation_Specialist",
            metadata={
                "position": {"x": 1000, "y": 1800},
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
            },
            initial_setup=True,
        )
    ).node_name
    with GriptapeNodes.ContextManager().node(node8_name):
        GriptapeNodes.handle_request(
            AddParameterToNodeRequest(
                parameter_name="rulesets_ParameterListUniqueParamID_7193b2c58028446c88eb62836380",
                default_value=[],
                tooltip="Rulesets to apply to the agent to control its behavior.",
                type="Ruleset",
                input_types=["Ruleset", "list[Ruleset]"],
                output_type="Ruleset",
                ui_options={},
                mode_allowed_input=True,
                mode_allowed_property=False,
                mode_allowed_output=False,
                parent_container_name="rulesets",
                initial_setup=True,
            )
        )
    node9_name = GriptapeNodes.handle_request(
        CreateNodeRequest(
            node_type="AgentToTool",
            specific_library_name="Griptape Nodes Library",
            node_name="Image_Generation_Specialist_asTool",
            metadata={
                "position": {"x": 1500, "y": 1800},
                "library_node_metadata": NodeMetadata(
                    category="convert",
                    description="Convert an agent into a tool that another agent can use",
                    display_name="Agent To Tool",
                    tags=None,
                    icon=None,
                    color=None,
                    group="edit",
                    deprecation=None,
                ),
                "library": "Griptape Nodes Library",
                "node_type": "AgentToTool",
            },
            initial_setup=True,
        )
    ).node_name
    node10_name = GriptapeNodes.handle_request(
        CreateNodeRequest(
            node_type="Agent",
            specific_library_name="Griptape Nodes Library",
            node_name="Orchestrator",
            metadata={
                "position": {"x": 4000, "y": 800},
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
            },
            initial_setup=True,
        )
    ).node_name
    with GriptapeNodes.ContextManager().node(node10_name):
        GriptapeNodes.handle_request(
            AddParameterToNodeRequest(
                parameter_name="tools_ParameterListUniqueParamID_b4d4b9d18fd342179cce723c48902d6f",
                default_value=[],
                tooltip="Connect Griptape Tools for the agent to use.\nOr connect individual tools.",
                type="Tool",
                input_types=["Tool", "list[Tool]"],
                output_type="Tool",
                ui_options={},
                mode_allowed_input=True,
                mode_allowed_property=False,
                mode_allowed_output=False,
                parent_container_name="tools",
                initial_setup=True,
            )
        )
        GriptapeNodes.handle_request(
            AddParameterToNodeRequest(
                parameter_name="rulesets_ParameterListUniqueParamID_86508cce964947b58c4618e7a27dadb4",
                default_value=[],
                tooltip="Rulesets to apply to the agent to control its behavior.",
                type="Ruleset",
                input_types=["Ruleset", "list[Ruleset]"],
                output_type="Ruleset",
                ui_options={},
                mode_allowed_input=True,
                mode_allowed_property=False,
                mode_allowed_output=False,
                is_user_defined=True,
                settable=True,
                parent_container_name="rulesets",
                initial_setup=True,
            )
        )
    node11_name = GriptapeNodes.handle_request(
        CreateNodeRequest(
            node_type="GenerateImage",
            specific_library_name="Griptape Nodes Library",
            node_name="GenerateImage_1",
            metadata={
                "position": {"x": 4600, "y": 1050},
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
                "size": {"width": 427, "height": 609},
            },
            initial_setup=True,
        )
    ).node_name
    with GriptapeNodes.ContextManager().node(node11_name):
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
    node12_name = GriptapeNodes.handle_request(
        CreateNodeRequest(
            node_type="Ruleset",
            specific_library_name="Griptape Nodes Library",
            node_name="Detail_Enthusiast_Ruleset",
            metadata={
                "position": {"x": -500, "y": 1200},
                "size": {"width": 900, "height": 450},
                "library_node_metadata": NodeMetadata(
                    category="agents/rules",
                    description="Give an agent a set of rules and behaviors to follow",
                    display_name="Ruleset",
                    tags=None,
                    icon=None,
                    color=None,
                    group="create",
                    deprecation=None,
                ),
                "library": "Griptape Nodes Library",
                "node_type": "Ruleset",
            },
            initial_setup=True,
        )
    ).node_name
    node13_name = GriptapeNodes.handle_request(
        CreateNodeRequest(
            node_type="Ruleset",
            specific_library_name="Griptape Nodes Library",
            node_name="Cinematographer_Ruleset",
            metadata={
                "position": {"x": -500, "y": 0},
                "size": {"width": 900, "height": 450},
                "library_node_metadata": NodeMetadata(
                    category="agents/rules",
                    description="Give an agent a set of rules and behaviors to follow",
                    display_name="Ruleset",
                    tags=None,
                    icon=None,
                    color=None,
                    group="create",
                    deprecation=None,
                ),
                "library": "Griptape Nodes Library",
                "node_type": "Ruleset",
            },
            initial_setup=True,
        )
    ).node_name
    node14_name = GriptapeNodes.handle_request(
        CreateNodeRequest(
            node_type="Ruleset",
            specific_library_name="Griptape Nodes Library",
            node_name="Color_Theorist_Ruleset",
            metadata={
                "position": {"x": -500, "y": 600},
                "size": {"width": 900, "height": 450},
                "library_node_metadata": NodeMetadata(
                    category="agents/rules",
                    description="Give an agent a set of rules and behaviors to follow",
                    display_name="Ruleset",
                    tags=None,
                    icon=None,
                    color=None,
                    group="create",
                    deprecation=None,
                ),
                "library": "Griptape Nodes Library",
                "node_type": "Ruleset",
            },
            initial_setup=True,
        )
    ).node_name
    node15_name = GriptapeNodes.handle_request(
        CreateNodeRequest(
            node_type="Ruleset",
            specific_library_name="Griptape Nodes Library",
            node_name="Image_Generation_Specialist_Ruleset",
            metadata={
                "position": {"x": -500, "y": 1800},
                "size": {"width": 900, "height": 450},
                "library_node_metadata": NodeMetadata(
                    category="agents/rules",
                    description="Give an agent a set of rules and behaviors to follow",
                    display_name="Ruleset",
                    tags=None,
                    icon=None,
                    color=None,
                    group="create",
                    deprecation=None,
                ),
                "library": "Griptape Nodes Library",
                "node_type": "Ruleset",
            },
            initial_setup=True,
        )
    ).node_name
    node16_name = GriptapeNodes.handle_request(
        CreateNodeRequest(
            node_type="Ruleset",
            specific_library_name="Griptape Nodes Library",
            node_name="Agent_Ruleset",
            metadata={
                "position": {"x": 2500, "y": 1500},
                "size": {"width": 900, "height": 450},
                "library_node_metadata": NodeMetadata(
                    category="agents/rules",
                    description="Give an agent a set of rules and behaviors to follow",
                    display_name="Ruleset",
                    tags=None,
                    icon=None,
                    color=None,
                    group="create",
                    deprecation=None,
                ),
                "library": "Griptape Nodes Library",
                "node_type": "Ruleset",
            },
            initial_setup=True,
        )
    ).node_name
    node17_name = GriptapeNodes.handle_request(
        CreateNodeRequest(
            node_type="ToolList",
            specific_library_name="Griptape Nodes Library",
            node_name="Tool List",
            metadata={
                "position": {"x": 2417.651397079312, "y": 911.8291653090869},
                "tempId": "placing-1751039730073-cvtnt6",
                "library_node_metadata": NodeMetadata(
                    category="agents/tools",
                    description="Combine tools to give an agent a more complex set of tools",
                    display_name="Tool List",
                    tags=None,
                    icon="list-check",
                    color=None,
                    group="create",
                    deprecation=None,
                ),
                "library": "Griptape Nodes Library",
                "node_type": "ToolList",
            },
            initial_setup=True,
        )
    ).node_name
    GriptapeNodes.handle_request(
        CreateConnectionRequest(
            source_node_name=node2_name,
            source_parameter_name="agent",
            target_node_name=node3_name,
            target_parameter_name="agent",
            initial_setup=True,
        )
    )
    GriptapeNodes.handle_request(
        CreateConnectionRequest(
            source_node_name=node4_name,
            source_parameter_name="agent",
            target_node_name=node5_name,
            target_parameter_name="agent",
            initial_setup=True,
        )
    )
    GriptapeNodes.handle_request(
        CreateConnectionRequest(
            source_node_name=node6_name,
            source_parameter_name="agent",
            target_node_name=node7_name,
            target_parameter_name="agent",
            initial_setup=True,
        )
    )
    GriptapeNodes.handle_request(
        CreateConnectionRequest(
            source_node_name=node8_name,
            source_parameter_name="agent",
            target_node_name=node9_name,
            target_parameter_name="agent",
            initial_setup=True,
        )
    )
    GriptapeNodes.handle_request(
        CreateConnectionRequest(
            source_node_name=node10_name,
            source_parameter_name="output",
            target_node_name=node11_name,
            target_parameter_name="prompt",
            initial_setup=True,
        )
    )
    GriptapeNodes.handle_request(
        CreateConnectionRequest(
            source_node_name=node3_name,
            source_parameter_name="tool",
            target_node_name=node17_name,
            target_parameter_name="tool_1",
            initial_setup=True,
        )
    )
    GriptapeNodes.handle_request(
        CreateConnectionRequest(
            source_node_name=node5_name,
            source_parameter_name="tool",
            target_node_name=node17_name,
            target_parameter_name="tool_2",
            initial_setup=True,
        )
    )
    GriptapeNodes.handle_request(
        CreateConnectionRequest(
            source_node_name=node7_name,
            source_parameter_name="tool",
            target_node_name=node17_name,
            target_parameter_name="tool_3",
            initial_setup=True,
        )
    )
    GriptapeNodes.handle_request(
        CreateConnectionRequest(
            source_node_name=node9_name,
            source_parameter_name="tool",
            target_node_name=node17_name,
            target_parameter_name="tool_4",
            initial_setup=True,
        )
    )
    GriptapeNodes.handle_request(
        CreateConnectionRequest(
            source_node_name=node17_name,
            source_parameter_name="tool_list",
            target_node_name=node10_name,
            target_parameter_name="tools_ParameterListUniqueParamID_b4d4b9d18fd342179cce723c48902d6f",
            initial_setup=True,
        )
    )
    GriptapeNodes.handle_request(
        CreateConnectionRequest(
            source_node_name=node15_name,
            source_parameter_name="ruleset",
            target_node_name=node8_name,
            target_parameter_name="rulesets_ParameterListUniqueParamID_7193b2c58028446c88eb62836380",
            initial_setup=True,
        )
    )
    GriptapeNodes.handle_request(
        CreateConnectionRequest(
            source_node_name=node12_name,
            source_parameter_name="ruleset",
            target_node_name=node6_name,
            target_parameter_name="rulesets_ParameterListUniqueParamID_bbba9d0539324d21bec72679f8034624",
            initial_setup=True,
        )
    )
    GriptapeNodes.handle_request(
        CreateConnectionRequest(
            source_node_name=node14_name,
            source_parameter_name="ruleset",
            target_node_name=node4_name,
            target_parameter_name="rulesets_ParameterListUniqueParamID_bda37a1a564c496da5d47bfbee59d572",
            initial_setup=True,
        )
    )
    GriptapeNodes.handle_request(
        CreateConnectionRequest(
            source_node_name=node13_name,
            source_parameter_name="ruleset",
            target_node_name=node2_name,
            target_parameter_name="rulesets_ParameterListUniqueParamID_2eadbf6ecaac46a7beb1ad1ae7c4b085",
            initial_setup=True,
        )
    )
    GriptapeNodes.handle_request(
        CreateConnectionRequest(
            source_node_name=node16_name,
            source_parameter_name="ruleset",
            target_node_name=node10_name,
            target_parameter_name="rulesets_ParameterListUniqueParamID_86508cce964947b58c4618e7a27dadb4",
            initial_setup=True,
        )
    )
    with GriptapeNodes.ContextManager().node(node0_name):
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="note",
                node_name=node0_name,
                value=top_level_unique_values_dict["2b8a7fba-8ef1-4166-8c5e-3cace5689e98"],
                initial_setup=True,
                is_output=False,
            )
        )
    with GriptapeNodes.ContextManager().node(node1_name):
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="note",
                node_name=node1_name,
                value=top_level_unique_values_dict["439d8114-af3d-46ec-aba7-55804fd4ebae"],
                initial_setup=True,
                is_output=False,
            )
        )
    with GriptapeNodes.ContextManager().node(node2_name):
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="model",
                node_name=node2_name,
                value=top_level_unique_values_dict["4b104fbe-3cde-4dce-b4bf-2eba7b198ecc"],
                initial_setup=True,
                is_output=False,
            )
        )
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="tools",
                node_name=node2_name,
                value=top_level_unique_values_dict["e961cf26-1982-4359-9a42-e4b829adf0e7"],
                initial_setup=True,
                is_output=False,
            )
        )
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="include_details",
                node_name=node2_name,
                value=top_level_unique_values_dict["0ba6d1b4-c664-4ea5-90ae-246f563c398e"],
                initial_setup=True,
                is_output=False,
            )
        )
    with GriptapeNodes.ContextManager().node(node3_name):
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="name",
                node_name=node3_name,
                value=top_level_unique_values_dict["8f28a114-be7f-4195-b427-c1351662c946"],
                initial_setup=True,
                is_output=False,
            )
        )
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="description",
                node_name=node3_name,
                value=top_level_unique_values_dict["93726ae5-1598-4cbd-a204-76dada3317fc"],
                initial_setup=True,
                is_output=False,
            )
        )
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="off_prompt",
                node_name=node3_name,
                value=top_level_unique_values_dict["0ba6d1b4-c664-4ea5-90ae-246f563c398e"],
                initial_setup=True,
                is_output=False,
            )
        )
    with GriptapeNodes.ContextManager().node(node4_name):
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="model",
                node_name=node4_name,
                value=top_level_unique_values_dict["4b104fbe-3cde-4dce-b4bf-2eba7b198ecc"],
                initial_setup=True,
                is_output=False,
            )
        )
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="tools",
                node_name=node4_name,
                value=top_level_unique_values_dict["e704c528-9b99-4326-b295-3673536fe508"],
                initial_setup=True,
                is_output=False,
            )
        )
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="include_details",
                node_name=node4_name,
                value=top_level_unique_values_dict["0ba6d1b4-c664-4ea5-90ae-246f563c398e"],
                initial_setup=True,
                is_output=False,
            )
        )
    with GriptapeNodes.ContextManager().node(node5_name):
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="name",
                node_name=node5_name,
                value=top_level_unique_values_dict["897470c4-e12b-42cb-a42d-b223d612371a"],
                initial_setup=True,
                is_output=False,
            )
        )
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="description",
                node_name=node5_name,
                value=top_level_unique_values_dict["aa63c100-140a-4e93-80c1-ff40350956d9"],
                initial_setup=True,
                is_output=False,
            )
        )
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="off_prompt",
                node_name=node5_name,
                value=top_level_unique_values_dict["0ba6d1b4-c664-4ea5-90ae-246f563c398e"],
                initial_setup=True,
                is_output=False,
            )
        )
    with GriptapeNodes.ContextManager().node(node6_name):
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="model",
                node_name=node6_name,
                value=top_level_unique_values_dict["4b104fbe-3cde-4dce-b4bf-2eba7b198ecc"],
                initial_setup=True,
                is_output=False,
            )
        )
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="tools",
                node_name=node6_name,
                value=top_level_unique_values_dict["4b36180b-e4e2-4341-bbd9-c3d9aace7f08"],
                initial_setup=True,
                is_output=False,
            )
        )
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="include_details",
                node_name=node6_name,
                value=top_level_unique_values_dict["0ba6d1b4-c664-4ea5-90ae-246f563c398e"],
                initial_setup=True,
                is_output=False,
            )
        )
    with GriptapeNodes.ContextManager().node(node7_name):
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="name",
                node_name=node7_name,
                value=top_level_unique_values_dict["f1cd4774-dcc5-44df-96f2-fc583011f712"],
                initial_setup=True,
                is_output=False,
            )
        )
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="description",
                node_name=node7_name,
                value=top_level_unique_values_dict["9979f689-3750-4b70-8603-55999afada8c"],
                initial_setup=True,
                is_output=False,
            )
        )
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="off_prompt",
                node_name=node7_name,
                value=top_level_unique_values_dict["0ba6d1b4-c664-4ea5-90ae-246f563c398e"],
                initial_setup=True,
                is_output=False,
            )
        )
    with GriptapeNodes.ContextManager().node(node8_name):
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="model",
                node_name=node8_name,
                value=top_level_unique_values_dict["4b104fbe-3cde-4dce-b4bf-2eba7b198ecc"],
                initial_setup=True,
                is_output=False,
            )
        )
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="tools",
                node_name=node8_name,
                value=top_level_unique_values_dict["4575c024-e57a-4bc6-8323-c9032568b877"],
                initial_setup=True,
                is_output=False,
            )
        )
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="include_details",
                node_name=node8_name,
                value=top_level_unique_values_dict["0ba6d1b4-c664-4ea5-90ae-246f563c398e"],
                initial_setup=True,
                is_output=False,
            )
        )
    with GriptapeNodes.ContextManager().node(node9_name):
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="name",
                node_name=node9_name,
                value=top_level_unique_values_dict["7c262406-997c-49c6-9cda-be04e8cb4ba2"],
                initial_setup=True,
                is_output=False,
            )
        )
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="description",
                node_name=node9_name,
                value=top_level_unique_values_dict["9979f689-3750-4b70-8603-55999afada8c"],
                initial_setup=True,
                is_output=False,
            )
        )
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="off_prompt",
                node_name=node9_name,
                value=top_level_unique_values_dict["0ba6d1b4-c664-4ea5-90ae-246f563c398e"],
                initial_setup=True,
                is_output=False,
            )
        )
    with GriptapeNodes.ContextManager().node(node10_name):
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="model",
                node_name=node10_name,
                value=top_level_unique_values_dict["4b104fbe-3cde-4dce-b4bf-2eba7b198ecc"],
                initial_setup=True,
                is_output=False,
            )
        )
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="prompt",
                node_name=node10_name,
                value=top_level_unique_values_dict["f1a53150-a9fd-490d-b010-224e2f588dd9"],
                initial_setup=True,
                is_output=False,
            )
        )
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="tools",
                node_name=node10_name,
                value=top_level_unique_values_dict["d3065ce1-f20e-4d42-9768-a7a9bca0e33b"],
                initial_setup=True,
                is_output=False,
            )
        )
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="rulesets",
                node_name=node10_name,
                value=top_level_unique_values_dict["e552e43e-7cbe-4ba8-a34a-a1d209979848"],
                initial_setup=True,
                is_output=False,
            )
        )
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="include_details",
                node_name=node10_name,
                value=top_level_unique_values_dict["0ba6d1b4-c664-4ea5-90ae-246f563c398e"],
                initial_setup=True,
                is_output=False,
            )
        )
    with GriptapeNodes.ContextManager().node(node11_name):
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="model",
                node_name=node11_name,
                value=top_level_unique_values_dict["aff2a758-4ff4-4ec9-96ec-1d29037db7b7"],
                initial_setup=True,
                is_output=False,
            )
        )
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="image_size",
                node_name=node11_name,
                value=top_level_unique_values_dict["f66f1f2c-3803-4fe6-9bd8-af69979c96b9"],
                initial_setup=True,
                is_output=False,
            )
        )
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="enhance_prompt",
                node_name=node11_name,
                value=top_level_unique_values_dict["0ba6d1b4-c664-4ea5-90ae-246f563c398e"],
                initial_setup=True,
                is_output=False,
            )
        )
    with GriptapeNodes.ContextManager().node(node12_name):
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="name",
                node_name=node12_name,
                value=top_level_unique_values_dict["aa22e757-1c83-4954-a384-130b5ff86b22"],
                initial_setup=True,
                is_output=False,
            )
        )
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="rules",
                node_name=node12_name,
                value=top_level_unique_values_dict["c844b511-2b49-4d6a-b307-1cbda24cbaae"],
                initial_setup=True,
                is_output=False,
            )
        )
    with GriptapeNodes.ContextManager().node(node13_name):
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="name",
                node_name=node13_name,
                value=top_level_unique_values_dict["8d4b681d-ee90-4ee4-a2b0-1d1667f5886c"],
                initial_setup=True,
                is_output=False,
            )
        )
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="rules",
                node_name=node13_name,
                value=top_level_unique_values_dict["49075693-5915-49ff-bfcf-5f805e16a0aa"],
                initial_setup=True,
                is_output=False,
            )
        )
    with GriptapeNodes.ContextManager().node(node14_name):
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="name",
                node_name=node14_name,
                value=top_level_unique_values_dict["b35f7c84-a8d8-49c2-93c1-30b8dca6f89d"],
                initial_setup=True,
                is_output=False,
            )
        )
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="rules",
                node_name=node14_name,
                value=top_level_unique_values_dict["c1b2a335-4c41-475a-aa93-c7568a28d99f"],
                initial_setup=True,
                is_output=False,
            )
        )
    with GriptapeNodes.ContextManager().node(node15_name):
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="name",
                node_name=node15_name,
                value=top_level_unique_values_dict["a3714836-36f4-48b1-840a-7818e5453ddd"],
                initial_setup=True,
                is_output=False,
            )
        )
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="rules",
                node_name=node15_name,
                value=top_level_unique_values_dict["51b6e013-d252-41ba-954f-2d749e20635d"],
                initial_setup=True,
                is_output=False,
            )
        )
    with GriptapeNodes.ContextManager().node(node16_name):
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="name",
                node_name=node16_name,
                value=top_level_unique_values_dict["fbba38a0-e5cd-4ad6-af91-ad0c5541a6f6"],
                initial_setup=True,
                is_output=False,
            )
        )
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="rules",
                node_name=node16_name,
                value=top_level_unique_values_dict["303283f5-54bb-4d20-9089-20bf65cfea7a"],
                initial_setup=True,
                is_output=False,
            )
        )
