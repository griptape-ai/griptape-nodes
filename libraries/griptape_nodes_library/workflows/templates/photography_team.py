# /// script
# dependencies = []
#
# [tool.griptape-nodes]
# name = "photography_team"
# schema_version = "0.11.0"
# engine_version_created_with = "0.59.3"
# node_libraries_referenced = [["Griptape Nodes Library", "0.50.0"]]
# node_types_used = [["Griptape Nodes Library", "Agent"], ["Griptape Nodes Library", "AgentToTool"], ["Griptape Nodes Library", "GenerateImage"], ["Griptape Nodes Library", "Note"], ["Griptape Nodes Library", "Ruleset"], ["Griptape Nodes Library", "ToolList"]]
# description = "A team of experts develop a prompt."
# image = "https://raw.githubusercontent.com/griptape-ai/griptape-nodes/refs/heads/main/libraries/griptape_nodes_library/workflows/templates/thumbnail_photography_team.webp"
# is_griptape_provided = true
# is_template = true
# creation_date = 2025-10-22T05:10:04.426894Z
# last_modified_date = 2025-10-22T05:10:04.461569Z
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

response = GriptapeNodes.handle_request(GetAllInfoForAllLibrariesRequest())

if (
    isinstance(response, GetAllInfoForAllLibrariesResultSuccess)
    and len(response.library_name_to_library_info.keys()) < 1
):
    GriptapeNodes.handle_request(ReloadAllLibrariesRequest())

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
    "6575854b-a05e-41de-a9b0-f2c1ead257bb": pickle.loads(
        b'\x80\x04\x95\xbd\x01\x00\x00\x00\x00\x00\x00X\xb6\x01\x00\x00This workflow serves as the lesson material for the tutorial located at:\n\nhttps://docs.griptapenodes.com/en/stable/ftue/04_photography_team/FTUE_04_photography_team/\n\nThe concepts covered are:\n\n- Incorporating key upgrades available to agents:\n    - Rulesets to define and manage agent behaviors\n    - Tools to give agents more abilities\n- Converting agents into tools\n- Creating and orchestrating a team of "experts" with specific roles\n\x94.'
    ),
    "c3f6731d-3c23-46ee-9e94-35975b385e98": pickle.loads(
        b'\x80\x04\x95F\x00\x00\x00\x00\x00\x00\x00\x8cBGood job. You\'ve completed our "Getting Started" set of tutorials!\x94.'
    ),
    "edde47b5-8332-4ea5-b60c-4b41f5ffe5f7": pickle.loads(
        b"\x80\x04\x95\x0b\x00\x00\x00\x00\x00\x00\x00\x8c\x07gpt-4.1\x94."
    ),
    "51cfe40f-c04e-4513-a956-353bd5acf9c7": pickle.loads(b"\x80\x04]\x94."),
    "f98e9c6d-4045-4680-8111-fb017897e116": pickle.loads(b"\x80\x04\x89."),
    "c6928fcd-edcc-463b-a91a-1f6b33df700a": pickle.loads(
        b"\x80\x04\x95\x13\x00\x00\x00\x00\x00\x00\x00\x8c\x0fCinematographer\x94."
    ),
    "a8e7d7eb-fcbf-4d2a-ba64-37dac8d5d7ad": pickle.loads(
        b"\x80\x04\x95)\x00\x00\x00\x00\x00\x00\x00\x8c%This agent understands cinematography\x94."
    ),
    "bfa5fc32-937f-408d-aefa-54e94d71f100": pickle.loads(b"\x80\x04]\x94."),
    "9280e54a-608e-4320-8630-9a3c30df62eb": pickle.loads(
        b"\x80\x04\x95\x12\x00\x00\x00\x00\x00\x00\x00\x8c\x0eColor_Theorist\x94."
    ),
    "4c32b4cf-0787-4a33-95cc-d645eb901eeb": pickle.loads(
        b"\x80\x04\x954\x00\x00\x00\x00\x00\x00\x00\x8c0This agent can be used to ensure the best colors\x94."
    ),
    "5df6c49e-3580-4825-96dc-f2ce2c82808c": pickle.loads(b"\x80\x04\x95\x04\x00\x00\x00\x00\x00\x00\x00\x8c\x00\x94."),
    "9bf35242-514e-4134-8536-8f2cb8238d53": pickle.loads(b"\x80\x04]\x94."),
    "aff896b5-7058-4623-b32a-cace02d6113f": pickle.loads(
        b"\x80\x04\x95\x15\x00\x00\x00\x00\x00\x00\x00\x8c\x11Detail_Enthusiast\x94."
    ),
    "2525ebbc-31af-45bb-a97b-a2932f70e783": pickle.loads(
        b"\x80\x04\x95n\x00\x00\x00\x00\x00\x00\x00\x8cjThis agent is into the fine details of an image. Use it to make sure descriptions are specific and unique.\x94."
    ),
    "d3a04efd-81e9-4dab-8b0e-07678603e4d0": pickle.loads(b"\x80\x04]\x94."),
    "aa89b8eb-2d13-4e72-8d3e-3bc8ee9c2130": pickle.loads(
        b"\x80\x04\x95\x1f\x00\x00\x00\x00\x00\x00\x00\x8c\x1bImage_Generation_Specialist\x94."
    ),
    "3ef076f9-37e5-4c30-9d48-28dc6752f279": pickle.loads(
        b'\x80\x04\x95\x9a\x00\x00\x00\x00\x00\x00\x00\x8c\x96Use all the tools at your disposal to create a spectacular image generation prompt about "a skateboarding lion", that is no longer than 500 characters\x94.'
    ),
    "1391d4bd-4ecf-4890-944e-c46b8c733d0a": pickle.loads(b"\x80\x04\x95\x06\x00\x00\x00\x00\x00\x00\x00]\x94]\x94a."),
    "d866a663-902e-4a55-9c3f-0a44145f0e1c": pickle.loads(b"\x80\x04]\x94."),
    "729a08f0-afb1-409a-8860-1b629312c472": pickle.loads(
        b"\x80\x04\x95\x1d\x00\x00\x00\x00\x00\x00\x00\x8c\x19Detail_Enthusiast Ruleset\x94."
    ),
    "99048259-93c1-4ed0-beec-21e6710dc0f2": pickle.loads(
        b'\x80\x04\x95\xa3\x01\x00\x00\x00\x00\x00\x00X\x9c\x01\x00\x00You care about the unique details and specific descriptions of items.\nWhen describing things, call out specific details and don\'t be generic. Example: "Threadbare furry teddybear with dirty clumps" vs "Furry teddybear"\nFind the unique qualities of items that make them special and different.\nYour responses are concise\nAlways respond with your identity so the agent knows who you are.\nKeep your responses brief.\n\x94.'
    ),
    "d839cb9f-a7e5-43fe-b2ee-81ea8da7b5fd": pickle.loads(
        b"\x80\x04\x95\x1b\x00\x00\x00\x00\x00\x00\x00\x8c\x17Cinematographer Ruleset\x94."
    ),
    "6083f82d-ce76-43be-80d3-a9d5b9df0635": pickle.loads(
        b"\x80\x04\x95\xf0\x02\x00\x00\x00\x00\x00\x00X\xe9\x02\x00\x00You identify as a cinematographer\nThe main subject of the image should be well framed\nIf no environment is specified, set the image in a location that will evoke a deep and meaningful connection to the viewer.\nYou care deeply about light, shadow, color, and composition\nWhen coming up with image prompts, you always specify the position of the camera, the lens, and the color\nYou are specific about the technical details of a shot.\nYou like to add atmosphere to your shots, so you include depth of field, haze, dust particles in the air close to and far away from camera, and the way lighting reacts with each item.\nYour responses are brief and concise\nAlways respond with your identity so the agent knows who you are.\nKeep your responses brief.\x94."
    ),
    "fbfd4ec0-d5c1-43b0-bb3a-0518c34b4b9f": pickle.loads(
        b"\x80\x04\x95\x1a\x00\x00\x00\x00\x00\x00\x00\x8c\x16Color_Theorist Ruleset\x94."
    ),
    "0eba143c-5b5c-44a7-9e59-1d55777fbbe3": pickle.loads(
        b"\x80\x04\x95'\x01\x00\x00\x00\x00\x00\x00X \x01\x00\x00You identify as an expert in color theory\nYou have a deep understanding of how color impacts one's psychological outlook\nYou are a fan of non-standard colors\nYour responses are brief and concise\nAlways respond with your identity  so the agent knows who you are.\nKeep your responses brief.\x94."
    ),
    "6ab794e8-701c-47ef-96ba-d86b4bc0b42f": pickle.loads(
        b"\x80\x04\x95'\x00\x00\x00\x00\x00\x00\x00\x8c#Image_Generation_Specialist Ruleset\x94."
    ),
    "4a442902-b01b-4cc0-92d4-ec024077cfcf": pickle.loads(
        b"\x80\x04\x95Q\x02\x00\x00\x00\x00\x00\x00XJ\x02\x00\x00You are an expert in creating prompts for image generation engines\nYou use the latest knowledge available to you to generate the best prompts.\nYou create prompts that are direct and succinct and you understand they need to be under 800 characters long\nAlways include the following: subject, attributes of subject, visual characteristics of the image, film grain, camera angle, lighting, art style, color scheme, surrounding environment, camera used (ex: Nikon d850 film stock, polaroid, etc).\nAlways respond with your identity so the agent knows who you are.\nKeep your responses brief.\n\x94."
    ),
    "65fd286b-d662-461a-b7e4-a77fd97544a1": pickle.loads(
        b"\x80\x04\x95\x0f\x00\x00\x00\x00\x00\x00\x00\x8c\x0bAgent Rules\x94."
    ),
    "28ca9ba7-31d6-4072-8b12-000201ee15bb": pickle.loads(
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
                "position": {"x": 1000, "y": -66.97221903069686},
                "library_node_metadata": {
                    "category": "agents",
                    "description": "Creates an AI agent with conversation memory and the ability to use tools",
                },
                "library": "Griptape Nodes Library",
                "node_type": "Agent",
                "showaddparameter": False,
                "category": "agents",
                "size": {"width": 400, "height": 620},
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
                "position": {"x": 1500, "y": -66.97221903069686},
                "library_node_metadata": {
                    "category": "convert",
                    "description": "Convert an agent into a tool that another agent can use",
                },
                "library": "Griptape Nodes Library",
                "node_type": "AgentToTool",
                "showaddparameter": False,
                "category": "convert",
                "size": {"width": 400, "height": 412},
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
                "position": {"x": 1000, "y": 620},
                "library_node_metadata": {
                    "category": "agents",
                    "description": "Creates an AI agent with conversation memory and the ability to use tools",
                },
                "library": "Griptape Nodes Library",
                "node_type": "Agent",
                "showaddparameter": False,
                "category": "agents",
                "size": {"width": 400, "height": 620},
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
                "position": {"x": 1500, "y": 619},
                "library_node_metadata": {
                    "category": "convert",
                    "description": "Convert an agent into a tool that another agent can use",
                },
                "library": "Griptape Nodes Library",
                "node_type": "AgentToTool",
                "showaddparameter": False,
                "category": "convert",
                "size": {"width": 400, "height": 412},
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
                "position": {"x": 1000, "y": 1283.8291653090869},
                "library_node_metadata": {
                    "category": "agents",
                    "description": "Creates an AI agent with conversation memory and the ability to use tools",
                },
                "library": "Griptape Nodes Library",
                "node_type": "Agent",
                "showaddparameter": False,
                "category": "agents",
                "size": {"width": 400, "height": 620},
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
                "position": {"x": 1500, "y": 1283.8291653090869},
                "library_node_metadata": {
                    "category": "convert",
                    "description": "Convert an agent into a tool that another agent can use",
                },
                "library": "Griptape Nodes Library",
                "node_type": "AgentToTool",
                "showaddparameter": False,
                "category": "convert",
                "size": {"width": 400, "height": 412},
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
                "position": {"x": 1000, "y": 1964.1475956634727},
                "library_node_metadata": {
                    "category": "agents",
                    "description": "Creates an AI agent with conversation memory and the ability to use tools",
                },
                "library": "Griptape Nodes Library",
                "node_type": "Agent",
                "showaddparameter": False,
                "category": "agents",
                "size": {"width": 400, "height": 620},
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
                "position": {"x": 1500, "y": 1964.1475956634727},
                "library_node_metadata": {
                    "category": "convert",
                    "description": "Convert an agent into a tool that another agent can use",
                },
                "library": "Griptape Nodes Library",
                "node_type": "AgentToTool",
                "showaddparameter": False,
                "category": "convert",
                "size": {"width": 400, "height": 412},
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
                parameter_name="rulesets_ParameterListUniqueParamID_8d4976828685496e843becdee1ac7c77",
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
            target_parameter_name="rulesets_ParameterListUniqueParamID_8d4976828685496e843becdee1ac7c77",
            initial_setup=True,
        )
    )
    with GriptapeNodes.ContextManager().node(node0_name):
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="note",
                node_name=node0_name,
                value=top_level_unique_values_dict["6575854b-a05e-41de-a9b0-f2c1ead257bb"],
                initial_setup=True,
                is_output=False,
            )
        )
    with GriptapeNodes.ContextManager().node(node1_name):
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="note",
                node_name=node1_name,
                value=top_level_unique_values_dict["c3f6731d-3c23-46ee-9e94-35975b385e98"],
                initial_setup=True,
                is_output=False,
            )
        )
    with GriptapeNodes.ContextManager().node(node2_name):
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="model",
                node_name=node2_name,
                value=top_level_unique_values_dict["edde47b5-8332-4ea5-b60c-4b41f5ffe5f7"],
                initial_setup=True,
                is_output=False,
            )
        )
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="tools",
                node_name=node2_name,
                value=top_level_unique_values_dict["51cfe40f-c04e-4513-a956-353bd5acf9c7"],
                initial_setup=True,
                is_output=False,
            )
        )
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="include_details",
                node_name=node2_name,
                value=top_level_unique_values_dict["f98e9c6d-4045-4680-8111-fb017897e116"],
                initial_setup=True,
                is_output=False,
            )
        )
    with GriptapeNodes.ContextManager().node(node3_name):
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="name",
                node_name=node3_name,
                value=top_level_unique_values_dict["c6928fcd-edcc-463b-a91a-1f6b33df700a"],
                initial_setup=True,
                is_output=False,
            )
        )
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="description",
                node_name=node3_name,
                value=top_level_unique_values_dict["a8e7d7eb-fcbf-4d2a-ba64-37dac8d5d7ad"],
                initial_setup=True,
                is_output=False,
            )
        )
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="off_prompt",
                node_name=node3_name,
                value=top_level_unique_values_dict["f98e9c6d-4045-4680-8111-fb017897e116"],
                initial_setup=True,
                is_output=False,
            )
        )
    with GriptapeNodes.ContextManager().node(node4_name):
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="model",
                node_name=node4_name,
                value=top_level_unique_values_dict["edde47b5-8332-4ea5-b60c-4b41f5ffe5f7"],
                initial_setup=True,
                is_output=False,
            )
        )
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="tools",
                node_name=node4_name,
                value=top_level_unique_values_dict["bfa5fc32-937f-408d-aefa-54e94d71f100"],
                initial_setup=True,
                is_output=False,
            )
        )
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="include_details",
                node_name=node4_name,
                value=top_level_unique_values_dict["f98e9c6d-4045-4680-8111-fb017897e116"],
                initial_setup=True,
                is_output=False,
            )
        )
    with GriptapeNodes.ContextManager().node(node5_name):
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="name",
                node_name=node5_name,
                value=top_level_unique_values_dict["9280e54a-608e-4320-8630-9a3c30df62eb"],
                initial_setup=True,
                is_output=False,
            )
        )
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="description",
                node_name=node5_name,
                value=top_level_unique_values_dict["4c32b4cf-0787-4a33-95cc-d645eb901eeb"],
                initial_setup=True,
                is_output=False,
            )
        )
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="off_prompt",
                node_name=node5_name,
                value=top_level_unique_values_dict["f98e9c6d-4045-4680-8111-fb017897e116"],
                initial_setup=True,
                is_output=False,
            )
        )
    with GriptapeNodes.ContextManager().node(node6_name):
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="model",
                node_name=node6_name,
                value=top_level_unique_values_dict["edde47b5-8332-4ea5-b60c-4b41f5ffe5f7"],
                initial_setup=True,
                is_output=False,
            )
        )
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="additional_context",
                node_name=node6_name,
                value=top_level_unique_values_dict["5df6c49e-3580-4825-96dc-f2ce2c82808c"],
                initial_setup=True,
                is_output=False,
            )
        )
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="tools",
                node_name=node6_name,
                value=top_level_unique_values_dict["9bf35242-514e-4134-8536-8f2cb8238d53"],
                initial_setup=True,
                is_output=False,
            )
        )
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="include_details",
                node_name=node6_name,
                value=top_level_unique_values_dict["f98e9c6d-4045-4680-8111-fb017897e116"],
                initial_setup=True,
                is_output=False,
            )
        )
    with GriptapeNodes.ContextManager().node(node7_name):
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="name",
                node_name=node7_name,
                value=top_level_unique_values_dict["aff896b5-7058-4623-b32a-cace02d6113f"],
                initial_setup=True,
                is_output=False,
            )
        )
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="description",
                node_name=node7_name,
                value=top_level_unique_values_dict["2525ebbc-31af-45bb-a97b-a2932f70e783"],
                initial_setup=True,
                is_output=False,
            )
        )
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="off_prompt",
                node_name=node7_name,
                value=top_level_unique_values_dict["f98e9c6d-4045-4680-8111-fb017897e116"],
                initial_setup=True,
                is_output=False,
            )
        )
    with GriptapeNodes.ContextManager().node(node8_name):
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="model",
                node_name=node8_name,
                value=top_level_unique_values_dict["edde47b5-8332-4ea5-b60c-4b41f5ffe5f7"],
                initial_setup=True,
                is_output=False,
            )
        )
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="tools",
                node_name=node8_name,
                value=top_level_unique_values_dict["d3a04efd-81e9-4dab-8b0e-07678603e4d0"],
                initial_setup=True,
                is_output=False,
            )
        )
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="include_details",
                node_name=node8_name,
                value=top_level_unique_values_dict["f98e9c6d-4045-4680-8111-fb017897e116"],
                initial_setup=True,
                is_output=False,
            )
        )
    with GriptapeNodes.ContextManager().node(node9_name):
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="name",
                node_name=node9_name,
                value=top_level_unique_values_dict["aa89b8eb-2d13-4e72-8d3e-3bc8ee9c2130"],
                initial_setup=True,
                is_output=False,
            )
        )
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="description",
                node_name=node9_name,
                value=top_level_unique_values_dict["2525ebbc-31af-45bb-a97b-a2932f70e783"],
                initial_setup=True,
                is_output=False,
            )
        )
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="off_prompt",
                node_name=node9_name,
                value=top_level_unique_values_dict["f98e9c6d-4045-4680-8111-fb017897e116"],
                initial_setup=True,
                is_output=False,
            )
        )
    with GriptapeNodes.ContextManager().node(node10_name):
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="model",
                node_name=node10_name,
                value=top_level_unique_values_dict["edde47b5-8332-4ea5-b60c-4b41f5ffe5f7"],
                initial_setup=True,
                is_output=False,
            )
        )
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="prompt",
                node_name=node10_name,
                value=top_level_unique_values_dict["3ef076f9-37e5-4c30-9d48-28dc6752f279"],
                initial_setup=True,
                is_output=False,
            )
        )
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="tools",
                node_name=node10_name,
                value=top_level_unique_values_dict["1391d4bd-4ecf-4890-944e-c46b8c733d0a"],
                initial_setup=True,
                is_output=False,
            )
        )
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="rulesets",
                node_name=node10_name,
                value=top_level_unique_values_dict["d866a663-902e-4a55-9c3f-0a44145f0e1c"],
                initial_setup=True,
                is_output=False,
            )
        )
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="include_details",
                node_name=node10_name,
                value=top_level_unique_values_dict["f98e9c6d-4045-4680-8111-fb017897e116"],
                initial_setup=True,
                is_output=False,
            )
        )
    with GriptapeNodes.ContextManager().node(node11_name):
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="enhance_prompt",
                node_name=node11_name,
                value=top_level_unique_values_dict["f98e9c6d-4045-4680-8111-fb017897e116"],
                initial_setup=True,
                is_output=False,
            )
        )
    with GriptapeNodes.ContextManager().node(node12_name):
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="name",
                node_name=node12_name,
                value=top_level_unique_values_dict["729a08f0-afb1-409a-8860-1b629312c472"],
                initial_setup=True,
                is_output=False,
            )
        )
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="rules",
                node_name=node12_name,
                value=top_level_unique_values_dict["99048259-93c1-4ed0-beec-21e6710dc0f2"],
                initial_setup=True,
                is_output=False,
            )
        )
    with GriptapeNodes.ContextManager().node(node13_name):
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="name",
                node_name=node13_name,
                value=top_level_unique_values_dict["d839cb9f-a7e5-43fe-b2ee-81ea8da7b5fd"],
                initial_setup=True,
                is_output=False,
            )
        )
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="rules",
                node_name=node13_name,
                value=top_level_unique_values_dict["6083f82d-ce76-43be-80d3-a9d5b9df0635"],
                initial_setup=True,
                is_output=False,
            )
        )
    with GriptapeNodes.ContextManager().node(node14_name):
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="name",
                node_name=node14_name,
                value=top_level_unique_values_dict["fbfd4ec0-d5c1-43b0-bb3a-0518c34b4b9f"],
                initial_setup=True,
                is_output=False,
            )
        )
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="rules",
                node_name=node14_name,
                value=top_level_unique_values_dict["0eba143c-5b5c-44a7-9e59-1d55777fbbe3"],
                initial_setup=True,
                is_output=False,
            )
        )
    with GriptapeNodes.ContextManager().node(node15_name):
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="name",
                node_name=node15_name,
                value=top_level_unique_values_dict["6ab794e8-701c-47ef-96ba-d86b4bc0b42f"],
                initial_setup=True,
                is_output=False,
            )
        )
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="rules",
                node_name=node15_name,
                value=top_level_unique_values_dict["4a442902-b01b-4cc0-92d4-ec024077cfcf"],
                initial_setup=True,
                is_output=False,
            )
        )
    with GriptapeNodes.ContextManager().node(node16_name):
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="name",
                node_name=node16_name,
                value=top_level_unique_values_dict["65fd286b-d662-461a-b7e4-a77fd97544a1"],
                initial_setup=True,
                is_output=False,
            )
        )
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="rules",
                node_name=node16_name,
                value=top_level_unique_values_dict["28ca9ba7-31d6-4072-8b12-000201ee15bb"],
                initial_setup=True,
                is_output=False,
            )
        )
