# /// script
# dependencies = []
#
# [tool.griptape-nodes]
# name = "photography_team"
# schema_version = "0.7.0"
# engine_version_created_with = "0.45.0"
# node_libraries_referenced = [["Griptape Nodes Library", "0.41.0"]]
# description = "A team of experts develop a prompt."
# image = "https://raw.githubusercontent.com/griptape-ai/griptape-nodes/refs/heads/main/libraries/griptape_nodes_library/workflows/templates/thumbnail_photography_team.webp"
# is_griptape_provided = true
# is_template = true
# creation_date = 2025-05-01T00:00:00.000000+00:00
# last_modified_date = 2025-07-07T13:38:23.074102-07:00
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
    context_manager.push_workflow(workflow_name="photography_team_new_1")

"""
1. We've collated all of the unique parameter values into a dictionary so that we do not have to duplicate them.
   This minimizes the size of the code, especially for large objects like serialized image files.
2. We're using a prefix so that it's clear which Flow these values are associated with.
3. The values are serialized using pickle, which is a binary format. This makes them harder to read, but makes
   them consistently save and load. It allows us to serialize complex objects like custom classes, which otherwise
   would be difficult to serialize.
"""
top_level_unique_values_dict = {
    "bbcde3ca-6ff5-4c31-958b-c381c71f87de": pickle.loads(
        b'\x80\x04\x95\xbd\x01\x00\x00\x00\x00\x00\x00X\xb6\x01\x00\x00This workflow serves as the lesson material for the tutorial located at:\n\nhttps://docs.griptapenodes.com/en/stable/ftue/04_photography_team/FTUE_04_photography_team/\n\nThe concepts covered are:\n\n- Incorporating key upgrades available to agents:\n    - Rulesets to define and manage agent behaviors\n    - Tools to give agents more abilities\n- Converting agents into tools\n- Creating and orchestrating a team of "experts" with specific roles\n\x94.'
    ),
    "b23686c4-1408-4e76-99e3-fc91d6d00c28": pickle.loads(
        b'\x80\x04\x95F\x00\x00\x00\x00\x00\x00\x00\x8cBGood job. You\'ve completed our "Getting Started" set of tutorials!\x94.'
    ),
    "fd38d38d-3e75-49b7-b395-22e8a3907488": pickle.loads(
        b"\x80\x04\x95\x0b\x00\x00\x00\x00\x00\x00\x00\x8c\x07gpt-4.1\x94."
    ),
    "808292c8-e29b-496a-9dcd-0705577f874f": pickle.loads(b"\x80\x04]\x94."),
    "3f319ec6-06e7-4067-8e79-0edfeb8f1942": pickle.loads(b"\x80\x04\x89."),
    "16434c01-79dd-4c2f-b7e6-51f7fcca7e91": pickle.loads(
        b"\x80\x04\x95\x13\x00\x00\x00\x00\x00\x00\x00\x8c\x0fCinematographer\x94."
    ),
    "e5c95f3d-4c53-4ac8-9ad3-33a73bee0a7f": pickle.loads(
        b"\x80\x04\x95)\x00\x00\x00\x00\x00\x00\x00\x8c%This agent understands cinematography\x94."
    ),
    "6e2c8bfb-aeb9-4a9a-8aba-2cb3c42403ae": pickle.loads(b"\x80\x04]\x94."),
    "ba3f2cb9-1dff-4345-abc4-47ab3ad5708b": pickle.loads(
        b"\x80\x04\x95\x12\x00\x00\x00\x00\x00\x00\x00\x8c\x0eColor_Theorist\x94."
    ),
    "2ba51731-bbf8-4e30-85b4-44763b39f918": pickle.loads(
        b"\x80\x04\x954\x00\x00\x00\x00\x00\x00\x00\x8c0This agent can be used to ensure the best colors\x94."
    ),
    "d6744953-025c-4aaa-9f53-79eb8b98b73c": pickle.loads(b"\x80\x04]\x94."),
    "d850e1e8-c07b-44fd-a8f4-d1bc4f0de969": pickle.loads(
        b"\x80\x04\x95\x15\x00\x00\x00\x00\x00\x00\x00\x8c\x11Detail_Enthusiast\x94."
    ),
    "f0476edb-7828-4eb8-9e9d-dc343122ec3e": pickle.loads(
        b"\x80\x04\x95n\x00\x00\x00\x00\x00\x00\x00\x8cjThis agent is into the fine details of an image. Use it to make sure descriptions are specific and unique.\x94."
    ),
    "2dc8a93d-e3e6-4490-af81-a7b303c52c03": pickle.loads(b"\x80\x04]\x94."),
    "4a6464b1-d6ed-400a-8a6b-049cca6489fc": pickle.loads(
        b"\x80\x04\x95\x1f\x00\x00\x00\x00\x00\x00\x00\x8c\x1bImage_Generation_Specialist\x94."
    ),
    "4d7d52ff-7791-4555-a15b-b60299f63c01": pickle.loads(
        b'\x80\x04\x95\x9a\x00\x00\x00\x00\x00\x00\x00\x8c\x96Use all the tools at your disposal to create a spectacular image generation prompt about "a skateboarding lion", that is no longer than 500 characters\x94.'
    ),
    "82e38800-da6e-4b7f-9823-f5069896f762": pickle.loads(b"\x80\x04\x95\x06\x00\x00\x00\x00\x00\x00\x00]\x94]\x94a."),
    "908f03b8-dd59-445c-ab60-ea8301536bf3": pickle.loads(b"\x80\x04]\x94."),
    "9647fa7c-990b-4569-b327-b9d337b94510": pickle.loads(
        b"\x80\x04\x95\x1d\x00\x00\x00\x00\x00\x00\x00\x8c\x19Detail_Enthusiast Ruleset\x94."
    ),
    "a2b7a70b-19ba-41d6-90e4-f6564adb3d7b": pickle.loads(
        b'\x80\x04\x95\xa3\x01\x00\x00\x00\x00\x00\x00X\x9c\x01\x00\x00You care about the unique details and specific descriptions of items.\nWhen describing things, call out specific details and don\'t be generic. Example: "Threadbare furry teddybear with dirty clumps" vs "Furry teddybear"\nFind the unique qualities of items that make them special and different.\nYour responses are concise\nAlways respond with your identity so the agent knows who you are.\nKeep your responses brief.\n\x94.'
    ),
    "81d60a84-a902-49fd-ad66-1204b10fc791": pickle.loads(
        b"\x80\x04\x95\x1b\x00\x00\x00\x00\x00\x00\x00\x8c\x17Cinematographer Ruleset\x94."
    ),
    "766407fb-b1d1-4f26-b241-7a77d2e8cb9a": pickle.loads(
        b"\x80\x04\x95\xf0\x02\x00\x00\x00\x00\x00\x00X\xe9\x02\x00\x00You identify as a cinematographer\nThe main subject of the image should be well framed\nIf no environment is specified, set the image in a location that will evoke a deep and meaningful connection to the viewer.\nYou care deeply about light, shadow, color, and composition\nWhen coming up with image prompts, you always specify the position of the camera, the lens, and the color\nYou are specific about the technical details of a shot.\nYou like to add atmosphere to your shots, so you include depth of field, haze, dust particles in the air close to and far away from camera, and the way lighting reacts with each item.\nYour responses are brief and concise\nAlways respond with your identity so the agent knows who you are.\nKeep your responses brief.\x94."
    ),
    "bf549e47-ba68-4707-981b-612da03965f2": pickle.loads(
        b"\x80\x04\x95\x1a\x00\x00\x00\x00\x00\x00\x00\x8c\x16Color_Theorist Ruleset\x94."
    ),
    "ac574883-b14b-4b3c-aa65-f0cb22172a64": pickle.loads(
        b"\x80\x04\x95'\x01\x00\x00\x00\x00\x00\x00X \x01\x00\x00You identify as an expert in color theory\nYou have a deep understanding of how color impacts one's psychological outlook\nYou are a fan of non-standard colors\nYour responses are brief and concise\nAlways respond with your identity  so the agent knows who you are.\nKeep your responses brief.\x94."
    ),
    "abfd3d2a-22d8-4e3a-866a-9f81dfda3482": pickle.loads(
        b"\x80\x04\x95'\x00\x00\x00\x00\x00\x00\x00\x8c#Image_Generation_Specialist Ruleset\x94."
    ),
    "cfeafb6c-9bc0-4f81-8e49-b3c685f6e7b6": pickle.loads(
        b"\x80\x04\x95Q\x02\x00\x00\x00\x00\x00\x00XJ\x02\x00\x00You are an expert in creating prompts for image generation engines\nYou use the latest knowledge available to you to generate the best prompts.\nYou create prompts that are direct and succinct and you understand they need to be under 800 characters long\nAlways include the following: subject, attributes of subject, visual characteristics of the image, film grain, camera angle, lighting, art style, color scheme, surrounding environment, camera used (ex: Nikon d850 film stock, polaroid, etc).\nAlways respond with your identity so the agent knows who you are.\nKeep your responses brief.\n\x94."
    ),
    "458b8478-96cc-4b14-a99a-435c53f38006": pickle.loads(
        b"\x80\x04\x95\x0f\x00\x00\x00\x00\x00\x00\x00\x8c\x0bAgent Rules\x94."
    ),
    "b471e489-6e9c-4fe0-a6a3-94c0ca6c5a9a": pickle.loads(
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
                    group=None,
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
                parameter_name="rulesets_ParameterListUniqueParamID_2eadbf6ecaac46a7beb1ad1ae7c4b085",  # ignore
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
                    group=None,
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
                    group=None,
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
                    group=None,
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
                    group=None,
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
                    group=None,
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
                    group=None,
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
                    group=None,
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
                    group=None,
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
                    group="tasks",
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
            node_type="RulesetList",
            specific_library_name="Griptape Nodes Library",
            node_name="Agent_RulesetList",
            metadata={
                "position": {"x": 3500, "y": 1500},
                "library_node_metadata": NodeMetadata(
                    category="agents/rules",
                    description="Combine rulesets to give an agent a more complex set of behaviors",
                    display_name="Ruleset List",
                    tags=None,
                    icon=None,
                    color=None,
                    group=None,
                ),
                "library": "Griptape Nodes Library",
                "node_type": "RulesetList",
            },
            initial_setup=True,
        )
    ).node_name
    node13_name = GriptapeNodes.handle_request(
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
                    group=None,
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
                    group=None,
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
                    group=None,
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
                    group=None,
                ),
                "library": "Griptape Nodes Library",
                "node_type": "Ruleset",
            },
            initial_setup=True,
        )
    ).node_name
    node17_name = GriptapeNodes.handle_request(
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
                    group=None,
                ),
                "library": "Griptape Nodes Library",
                "node_type": "Ruleset",
            },
            initial_setup=True,
        )
    ).node_name
    node18_name = GriptapeNodes.handle_request(
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
                    group=None,
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
            source_node_name=node17_name,
            source_parameter_name="ruleset",
            target_node_name=node12_name,
            target_parameter_name="ruleset_1",
            initial_setup=True,
        )
    )
    GriptapeNodes.handle_request(
        CreateConnectionRequest(
            source_node_name=node12_name,
            source_parameter_name="rulesets",
            target_node_name=node10_name,
            target_parameter_name="rulesets",
            initial_setup=True,
        )
    )
    GriptapeNodes.handle_request(
        CreateConnectionRequest(
            source_node_name=node3_name,
            source_parameter_name="tool",
            target_node_name=node18_name,
            target_parameter_name="tool_1",
            initial_setup=True,
        )
    )
    GriptapeNodes.handle_request(
        CreateConnectionRequest(
            source_node_name=node5_name,
            source_parameter_name="tool",
            target_node_name=node18_name,
            target_parameter_name="tool_2",
            initial_setup=True,
        )
    )
    GriptapeNodes.handle_request(
        CreateConnectionRequest(
            source_node_name=node7_name,
            source_parameter_name="tool",
            target_node_name=node18_name,
            target_parameter_name="tool_3",
            initial_setup=True,
        )
    )
    GriptapeNodes.handle_request(
        CreateConnectionRequest(
            source_node_name=node9_name,
            source_parameter_name="tool",
            target_node_name=node18_name,
            target_parameter_name="tool_4",
            initial_setup=True,
        )
    )
    GriptapeNodes.handle_request(
        CreateConnectionRequest(
            source_node_name=node18_name,
            source_parameter_name="tool_list",
            target_node_name=node10_name,
            target_parameter_name="tools_ParameterListUniqueParamID_b4d4b9d18fd342179cce723c48902d6f",
            initial_setup=True,
        )
    )
    GriptapeNodes.handle_request(
        CreateConnectionRequest(
            source_node_name=node16_name,
            source_parameter_name="ruleset",
            target_node_name=node8_name,
            target_parameter_name="rulesets_ParameterListUniqueParamID_7193b2c58028446c88eb62836380",
            initial_setup=True,
        )
    )
    GriptapeNodes.handle_request(
        CreateConnectionRequest(
            source_node_name=node13_name,
            source_parameter_name="ruleset",
            target_node_name=node6_name,
            target_parameter_name="rulesets_ParameterListUniqueParamID_bbba9d0539324d21bec72679f8034624",
            initial_setup=True,
        )
    )
    GriptapeNodes.handle_request(
        CreateConnectionRequest(
            source_node_name=node15_name,
            source_parameter_name="ruleset",
            target_node_name=node4_name,
            target_parameter_name="rulesets_ParameterListUniqueParamID_bda37a1a564c496da5d47bfbee59d572",
            initial_setup=True,
        )
    )
    GriptapeNodes.handle_request(
        CreateConnectionRequest(
            source_node_name=node14_name,
            source_parameter_name="ruleset",
            target_node_name=node2_name,
            target_parameter_name="rulesets_ParameterListUniqueParamID_2eadbf6ecaac46a7beb1ad1ae7c4b085",
            initial_setup=True,
        )
    )
    with GriptapeNodes.ContextManager().node(node0_name):
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="note",
                node_name=node0_name,
                value=top_level_unique_values_dict["bbcde3ca-6ff5-4c31-958b-c381c71f87de"],
                initial_setup=True,
                is_output=False,
            )
        )
    with GriptapeNodes.ContextManager().node(node1_name):
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="note",
                node_name=node1_name,
                value=top_level_unique_values_dict["b23686c4-1408-4e76-99e3-fc91d6d00c28"],
                initial_setup=True,
                is_output=False,
            )
        )
    with GriptapeNodes.ContextManager().node(node2_name):
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="model",
                node_name=node2_name,
                value=top_level_unique_values_dict["fd38d38d-3e75-49b7-b395-22e8a3907488"],
                initial_setup=True,
                is_output=False,
            )
        )
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="tools",
                node_name=node2_name,
                value=top_level_unique_values_dict["808292c8-e29b-496a-9dcd-0705577f874f"],
                initial_setup=True,
                is_output=False,
            )
        )
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="include_details",
                node_name=node2_name,
                value=top_level_unique_values_dict["3f319ec6-06e7-4067-8e79-0edfeb8f1942"],
                initial_setup=True,
                is_output=False,
            )
        )
    with GriptapeNodes.ContextManager().node(node3_name):
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="name",
                node_name=node3_name,
                value=top_level_unique_values_dict["16434c01-79dd-4c2f-b7e6-51f7fcca7e91"],
                initial_setup=True,
                is_output=False,
            )
        )
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="description",
                node_name=node3_name,
                value=top_level_unique_values_dict["e5c95f3d-4c53-4ac8-9ad3-33a73bee0a7f"],
                initial_setup=True,
                is_output=False,
            )
        )
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="off_prompt",
                node_name=node3_name,
                value=top_level_unique_values_dict["3f319ec6-06e7-4067-8e79-0edfeb8f1942"],
                initial_setup=True,
                is_output=False,
            )
        )
    with GriptapeNodes.ContextManager().node(node4_name):
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="model",
                node_name=node4_name,
                value=top_level_unique_values_dict["fd38d38d-3e75-49b7-b395-22e8a3907488"],
                initial_setup=True,
                is_output=False,
            )
        )
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="tools",
                node_name=node4_name,
                value=top_level_unique_values_dict["6e2c8bfb-aeb9-4a9a-8aba-2cb3c42403ae"],
                initial_setup=True,
                is_output=False,
            )
        )
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="include_details",
                node_name=node4_name,
                value=top_level_unique_values_dict["3f319ec6-06e7-4067-8e79-0edfeb8f1942"],
                initial_setup=True,
                is_output=False,
            )
        )
    with GriptapeNodes.ContextManager().node(node5_name):
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="name",
                node_name=node5_name,
                value=top_level_unique_values_dict["ba3f2cb9-1dff-4345-abc4-47ab3ad5708b"],
                initial_setup=True,
                is_output=False,
            )
        )
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="description",
                node_name=node5_name,
                value=top_level_unique_values_dict["2ba51731-bbf8-4e30-85b4-44763b39f918"],
                initial_setup=True,
                is_output=False,
            )
        )
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="off_prompt",
                node_name=node5_name,
                value=top_level_unique_values_dict["3f319ec6-06e7-4067-8e79-0edfeb8f1942"],
                initial_setup=True,
                is_output=False,
            )
        )
    with GriptapeNodes.ContextManager().node(node6_name):
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="model",
                node_name=node6_name,
                value=top_level_unique_values_dict["fd38d38d-3e75-49b7-b395-22e8a3907488"],
                initial_setup=True,
                is_output=False,
            )
        )
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="tools",
                node_name=node6_name,
                value=top_level_unique_values_dict["d6744953-025c-4aaa-9f53-79eb8b98b73c"],
                initial_setup=True,
                is_output=False,
            )
        )
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="include_details",
                node_name=node6_name,
                value=top_level_unique_values_dict["3f319ec6-06e7-4067-8e79-0edfeb8f1942"],
                initial_setup=True,
                is_output=False,
            )
        )
    with GriptapeNodes.ContextManager().node(node7_name):
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="name",
                node_name=node7_name,
                value=top_level_unique_values_dict["d850e1e8-c07b-44fd-a8f4-d1bc4f0de969"],
                initial_setup=True,
                is_output=False,
            )
        )
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="description",
                node_name=node7_name,
                value=top_level_unique_values_dict["f0476edb-7828-4eb8-9e9d-dc343122ec3e"],
                initial_setup=True,
                is_output=False,
            )
        )
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="off_prompt",
                node_name=node7_name,
                value=top_level_unique_values_dict["3f319ec6-06e7-4067-8e79-0edfeb8f1942"],
                initial_setup=True,
                is_output=False,
            )
        )
    with GriptapeNodes.ContextManager().node(node8_name):
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="model",
                node_name=node8_name,
                value=top_level_unique_values_dict["fd38d38d-3e75-49b7-b395-22e8a3907488"],
                initial_setup=True,
                is_output=False,
            )
        )
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="tools",
                node_name=node8_name,
                value=top_level_unique_values_dict["2dc8a93d-e3e6-4490-af81-a7b303c52c03"],
                initial_setup=True,
                is_output=False,
            )
        )
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="include_details",
                node_name=node8_name,
                value=top_level_unique_values_dict["3f319ec6-06e7-4067-8e79-0edfeb8f1942"],
                initial_setup=True,
                is_output=False,
            )
        )
    with GriptapeNodes.ContextManager().node(node9_name):
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="name",
                node_name=node9_name,
                value=top_level_unique_values_dict["4a6464b1-d6ed-400a-8a6b-049cca6489fc"],
                initial_setup=True,
                is_output=False,
            )
        )
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="description",
                node_name=node9_name,
                value=top_level_unique_values_dict["f0476edb-7828-4eb8-9e9d-dc343122ec3e"],
                initial_setup=True,
                is_output=False,
            )
        )
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="off_prompt",
                node_name=node9_name,
                value=top_level_unique_values_dict["3f319ec6-06e7-4067-8e79-0edfeb8f1942"],
                initial_setup=True,
                is_output=False,
            )
        )
    with GriptapeNodes.ContextManager().node(node10_name):
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="model",
                node_name=node10_name,
                value=top_level_unique_values_dict["fd38d38d-3e75-49b7-b395-22e8a3907488"],
                initial_setup=True,
                is_output=False,
            )
        )
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="prompt",
                node_name=node10_name,
                value=top_level_unique_values_dict["4d7d52ff-7791-4555-a15b-b60299f63c01"],
                initial_setup=True,
                is_output=False,
            )
        )
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="tools",
                node_name=node10_name,
                value=top_level_unique_values_dict["82e38800-da6e-4b7f-9823-f5069896f762"],
                initial_setup=True,
                is_output=False,
            )
        )
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="rulesets",
                node_name=node10_name,
                value=top_level_unique_values_dict["908f03b8-dd59-445c-ab60-ea8301536bf3"],
                initial_setup=True,
                is_output=False,
            )
        )
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="include_details",
                node_name=node10_name,
                value=top_level_unique_values_dict["3f319ec6-06e7-4067-8e79-0edfeb8f1942"],
                initial_setup=True,
                is_output=False,
            )
        )
    with GriptapeNodes.ContextManager().node(node11_name):
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="enhance_prompt",
                node_name=node11_name,
                value=top_level_unique_values_dict["3f319ec6-06e7-4067-8e79-0edfeb8f1942"],
                initial_setup=True,
                is_output=False,
            )
        )
    with GriptapeNodes.ContextManager().node(node13_name):
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="name",
                node_name=node13_name,
                value=top_level_unique_values_dict["9647fa7c-990b-4569-b327-b9d337b94510"],
                initial_setup=True,
                is_output=False,
            )
        )
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="rules",
                node_name=node13_name,
                value=top_level_unique_values_dict["a2b7a70b-19ba-41d6-90e4-f6564adb3d7b"],
                initial_setup=True,
                is_output=False,
            )
        )
    with GriptapeNodes.ContextManager().node(node14_name):
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="name",
                node_name=node14_name,
                value=top_level_unique_values_dict["81d60a84-a902-49fd-ad66-1204b10fc791"],
                initial_setup=True,
                is_output=False,
            )
        )
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="rules",
                node_name=node14_name,
                value=top_level_unique_values_dict["766407fb-b1d1-4f26-b241-7a77d2e8cb9a"],
                initial_setup=True,
                is_output=False,
            )
        )
    with GriptapeNodes.ContextManager().node(node15_name):
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="name",
                node_name=node15_name,
                value=top_level_unique_values_dict["bf549e47-ba68-4707-981b-612da03965f2"],
                initial_setup=True,
                is_output=False,
            )
        )
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="rules",
                node_name=node15_name,
                value=top_level_unique_values_dict["ac574883-b14b-4b3c-aa65-f0cb22172a64"],
                initial_setup=True,
                is_output=False,
            )
        )
    with GriptapeNodes.ContextManager().node(node16_name):
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="name",
                node_name=node16_name,
                value=top_level_unique_values_dict["abfd3d2a-22d8-4e3a-866a-9f81dfda3482"],
                initial_setup=True,
                is_output=False,
            )
        )
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="rules",
                node_name=node16_name,
                value=top_level_unique_values_dict["cfeafb6c-9bc0-4f81-8e49-b3c685f6e7b6"],
                initial_setup=True,
                is_output=False,
            )
        )
    with GriptapeNodes.ContextManager().node(node17_name):
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="name",
                node_name=node17_name,
                value=top_level_unique_values_dict["458b8478-96cc-4b14-a99a-435c53f38006"],
                initial_setup=True,
                is_output=False,
            )
        )
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="rules",
                node_name=node17_name,
                value=top_level_unique_values_dict["b471e489-6e9c-4fe0-a6a3-94c0ca6c5a9a"],
                initial_setup=True,
                is_output=False,
            )
        )
