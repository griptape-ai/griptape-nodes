# /// script
# dependencies = []
#
# [tool.griptape-nodes]
# name = "photography_team"
# schema_version = "0.4.0"
# engine_version_created_with = "0.39.0"
# node_libraries_referenced = [["Griptape Nodes Library", "0.39.0"]]
# is_griptape_provided = true
# description = "A team of experts develop a prompt."
# image = "https://raw.githubusercontent.com/griptape-ai/griptape-nodes/refs/heads/main/libraries/griptape_nodes_library/workflows/templates/thumbnail_photography_team.webp"
# is_template = true
# creation_date = 2025-05-01T00:00:00.000000+00:00
# last_modified_date = 2025-05-17T06:40:00.145097+12:00
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
    context_manager.push_workflow(workflow_name="photography_team_new")

"""
1. We've collated all of the unique parameter values into a dictionary so that we do not have to duplicate them.
   This minimizes the size of the code, especially for large objects like serialized image files.
2. We're using a prefix so that it's clear which Flow these values are associated with.
3. The values are serialized using pickle, which is a binary format. This makes them harder to read, but makes
   them consistently save and load. It allows us to serialize complex objects like custom classes, which otherwise
   would be difficult to serialize.
"""
top_level_unique_values_dict = {
    "b20b6f8b-e01c-4f89-96e1-80f9c092b6e4": pickle.loads(
        b'\x80\x04\x95\xbd\x01\x00\x00\x00\x00\x00\x00X\xb6\x01\x00\x00This workflow serves as the lesson material for the tutorial located at:\n\nhttps://docs.griptapenodes.com/en/stable/ftue/04_photography_team/FTUE_04_photography_team/\n\nThe concepts covered are:\n\n- Incorporating key upgrades available to agents:\n    - Rulesets to define and manage agent behaviors\n    - Tools to give agents more abilities\n- Converting agents into tools\n- Creating and orchestrating a team of "experts" with specific roles\n\x94.'
    ),
    "e54613ac-3be5-4dc6-a7c8-9be8181249fe": pickle.loads(
        b'\x80\x04\x95F\x00\x00\x00\x00\x00\x00\x00\x8cBGood job. You\'ve completed our "Getting Started" set of tutorials!\x94.'
    ),
    "acf60b14-6db3-464b-b868-81c2456900cb": pickle.loads(
        b"\x80\x04\x95\x0b\x00\x00\x00\x00\x00\x00\x00\x8c\x07gpt-4.1\x94."
    ),
    "dddbac95-d3d6-4064-ab88-a001a62aea23": pickle.loads(b"\x80\x04]\x94."),
    "21c7f153-13aa-4c0a-976f-1b1e1fed6266": pickle.loads(b"\x80\x04]\x94."),
    "38b74ba3-2993-470e-892c-d466ff0f59ba": pickle.loads(b"\x80\x04\x89."),
    "8dcae506-4127-496d-a024-821221e366c5": pickle.loads(
        b"\x80\x04\x95\x13\x00\x00\x00\x00\x00\x00\x00\x8c\x0fCinematographer\x94."
    ),
    "ff2647c3-a694-416d-b09b-44c52d971194": pickle.loads(
        b"\x80\x04\x95)\x00\x00\x00\x00\x00\x00\x00\x8c%This agent understands cinematography\x94."
    ),
    "03388e53-199a-4b40-a230-18113e567340": pickle.loads(b"\x80\x04]\x94."),
    "35cbc3e6-8433-4084-a4bc-a47d12183e7e": pickle.loads(b"\x80\x04]\x94."),
    "e660cb89-9835-4c2c-bc93-e09f19fc4dbf": pickle.loads(
        b"\x80\x04\x95\x12\x00\x00\x00\x00\x00\x00\x00\x8c\x0eColor_Theorist\x94."
    ),
    "fb5e6d87-5f3a-4be3-8bc1-a84a86c1c4b1": pickle.loads(
        b"\x80\x04\x954\x00\x00\x00\x00\x00\x00\x00\x8c0This agent can be used to ensure the best colors\x94."
    ),
    "bd211a92-eaeb-40a6-b630-dabeff9ee172": pickle.loads(b"\x80\x04]\x94."),
    "ab26282f-f4de-4a92-8eee-825b71360e33": pickle.loads(b"\x80\x04]\x94."),
    "6ace4b72-2824-455d-a5ba-5de61deb0c3e": pickle.loads(
        b"\x80\x04\x95\x15\x00\x00\x00\x00\x00\x00\x00\x8c\x11Detail_Enthusiast\x94."
    ),
    "1992fe77-4bbf-4599-b5f8-1a6c36895c2b": pickle.loads(
        b"\x80\x04\x95n\x00\x00\x00\x00\x00\x00\x00\x8cjThis agent is into the fine details of an image. Use it to make sure descriptions are specific and unique.\x94."
    ),
    "715b8861-eaeb-4bb9-a682-1e71226cc1f8": pickle.loads(b"\x80\x04]\x94."),
    "36c8b764-fb47-4697-947b-2371aad8df8c": pickle.loads(b"\x80\x04]\x94."),
    "2d107f31-7776-4eb7-9e79-2b65930712d0": pickle.loads(
        b"\x80\x04\x95\x1f\x00\x00\x00\x00\x00\x00\x00\x8c\x1bImage_Generation_Specialist\x94."
    ),
    "ecfa18d1-3ae8-451c-add3-1a97db88eb2b": pickle.loads(
        b'\x80\x04\x95\x9a\x00\x00\x00\x00\x00\x00\x00\x8c\x96Use all the tools at your disposal to create a spectacular image generation prompt about "a skateboarding lion", that is no longer than 500 characters\x94.'
    ),
    "66d8e4a3-fe34-4948-8d82-db85586ae21f": pickle.loads(b"\x80\x04]\x94."),
    "a024aea0-0c99-4792-97f1-300867710602": pickle.loads(
        b"\x80\x04\x95\x1d\x00\x00\x00\x00\x00\x00\x00\x8c\x19Detail_Enthusiast Ruleset\x94."
    ),
    "97ba7f16-6044-424b-b402-925ef60c353d": pickle.loads(
        b'\x80\x04\x95\xa3\x01\x00\x00\x00\x00\x00\x00X\x9c\x01\x00\x00You care about the unique details and specific descriptions of items.\nWhen describing things, call out specific details and don\'t be generic. Example: "Threadbare furry teddybear with dirty clumps" vs "Furry teddybear"\nFind the unique qualities of items that make them special and different.\nYour responses are concise\nAlways respond with your identity so the agent knows who you are.\nKeep your responses brief.\n\x94.'
    ),
    "c2ecb3c1-72e8-4a3c-ab22-743bef2f20c4": pickle.loads(
        b"\x80\x04\x95\x1b\x00\x00\x00\x00\x00\x00\x00\x8c\x17Cinematographer Ruleset\x94."
    ),
    "be355baf-f684-412d-9b48-8333e357c55d": pickle.loads(
        b"\x80\x04\x95\xf0\x02\x00\x00\x00\x00\x00\x00X\xe9\x02\x00\x00You identify as a cinematographer\nThe main subject of the image should be well framed\nIf no environment is specified, set the image in a location that will evoke a deep and meaningful connection to the viewer.\nYou care deeply about light, shadow, color, and composition\nWhen coming up with image prompts, you always specify the position of the camera, the lens, and the color\nYou are specific about the technical details of a shot.\nYou like to add atmosphere to your shots, so you include depth of field, haze, dust particles in the air close to and far away from camera, and the way lighting reacts with each item.\nYour responses are brief and concise\nAlways respond with your identity so the agent knows who you are.\nKeep your responses brief.\x94."
    ),
    "8c9a50e2-0d18-47a2-98e2-52cc5dd0e4f3": pickle.loads(
        b"\x80\x04\x95\x1a\x00\x00\x00\x00\x00\x00\x00\x8c\x16Color_Theorist Ruleset\x94."
    ),
    "544b3629-42cd-429e-96aa-9517cf52530d": pickle.loads(
        b"\x80\x04\x95'\x01\x00\x00\x00\x00\x00\x00X \x01\x00\x00You identify as an expert in color theory\nYou have a deep understanding of how color impacts one's psychological outlook\nYou are a fan of non-standard colors\nYour responses are brief and concise\nAlways respond with your identity  so the agent knows who you are.\nKeep your responses brief.\x94."
    ),
    "9ff03863-7757-4f5b-aa15-2acafbbb4515": pickle.loads(
        b"\x80\x04\x95'\x00\x00\x00\x00\x00\x00\x00\x8c#Image_Generation_Specialist Ruleset\x94."
    ),
    "132a6511-3d73-46d8-a61e-7a7f32237089": pickle.loads(
        b"\x80\x04\x95Q\x02\x00\x00\x00\x00\x00\x00XJ\x02\x00\x00You are an expert in creating prompts for image generation engines\nYou use the latest knowledge available to you to generate the best prompts.\nYou create prompts that are direct and succinct and you understand they need to be under 800 characters long\nAlways include the following: subject, attributes of subject, visual characteristics of the image, film grain, camera angle, lighting, art style, color scheme, surrounding environment, camera used (ex: Nikon d850 film stock, polaroid, etc).\nAlways respond with your identity so the agent knows who you are.\nKeep your responses brief.\n\x94."
    ),
    "d5bc0a5d-922a-4722-8c93-50ae5d023193": pickle.loads(
        b"\x80\x04\x95\x0f\x00\x00\x00\x00\x00\x00\x00\x8c\x0bAgent Rules\x94."
    ),
    "bff4d87b-7069-4c44-a39d-3ece298df4b3": pickle.loads(
        b"\x80\x04\x95\xac\x02\x00\x00\x00\x00\x00\x00X\xa5\x02\x00\x00You are creating a prompt for an image generation engine.\nYou have access to topic experts in their respective fields\nWork with the experts to get the results you need\nYou facilitate communication between them.\nIf they ask for feedback, you can provide it.\nAsk the Image_Generation_Specialist for the final prompt.\nOutput only the final image generation prompt. Do not wrap in markdown context.\nKeep your responses brief.\nIMPORTANT: Always ensure image generation prompts are completely free of sexual, violent, hateful, or politically divisive content. When in doubt, err on the side of caution and choose wholesome, neutral themes that would be appropriate for all audiences.\x94."
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
            node_type="RulesetList",
            specific_library_name="Griptape Nodes Library",
            node_name="Cinematographer_RulesetList",
            metadata={
                "position": {"x": 500, "y": 0},
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
    node3_name = GriptapeNodes.handle_request(
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
    with GriptapeNodes.ContextManager().node(node3_name):
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
    node4_name = GriptapeNodes.handle_request(
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
    node5_name = GriptapeNodes.handle_request(
        CreateNodeRequest(
            node_type="RulesetList",
            specific_library_name="Griptape Nodes Library",
            node_name="Color_Theorist_RulesetList",
            metadata={
                "position": {"x": 500, "y": 600},
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
    node6_name = GriptapeNodes.handle_request(
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
    with GriptapeNodes.ContextManager().node(node6_name):
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
    node7_name = GriptapeNodes.handle_request(
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
    node8_name = GriptapeNodes.handle_request(
        CreateNodeRequest(
            node_type="RulesetList",
            specific_library_name="Griptape Nodes Library",
            node_name="Detail_Enthusiast_RulesetList",
            metadata={
                "position": {"x": 500, "y": 1200},
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
    node9_name = GriptapeNodes.handle_request(
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
    with GriptapeNodes.ContextManager().node(node9_name):
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
    node10_name = GriptapeNodes.handle_request(
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
    node11_name = GriptapeNodes.handle_request(
        CreateNodeRequest(
            node_type="RulesetList",
            specific_library_name="Griptape Nodes Library",
            node_name="Image_Generation_Specialist_RulesetList",
            metadata={
                "position": {"x": 500, "y": 1800},
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
    node12_name = GriptapeNodes.handle_request(
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
    with GriptapeNodes.ContextManager().node(node12_name):
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
    node13_name = GriptapeNodes.handle_request(
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
    node14_name = GriptapeNodes.handle_request(
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
    with GriptapeNodes.ContextManager().node(node14_name):
        GriptapeNodes.handle_request(
            AlterParameterDetailsRequest(
                parameter_name="tools",
                default_value=[],
                tooltip="Connect Griptape Tools for the agent to use.\nOr connect individual tools.",
                initial_setup=True,
            )
        )
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
            AlterParameterDetailsRequest(
                parameter_name="rulesets",
                default_value=[],
                tooltip="Rulesets to apply to the agent to control its behavior.",
                initial_setup=True,
            )
        )
    node15_name = GriptapeNodes.handle_request(
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
    with GriptapeNodes.ContextManager().node(node15_name):
        GriptapeNodes.handle_request(
            AlterParameterDetailsRequest(parameter_name="prompt", mode_allowed_property=False, initial_setup=True)
        )
    node16_name = GriptapeNodes.handle_request(
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
    node17_name = GriptapeNodes.handle_request(
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
    node18_name = GriptapeNodes.handle_request(
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
    node19_name = GriptapeNodes.handle_request(
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
    node20_name = GriptapeNodes.handle_request(
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
    node21_name = GriptapeNodes.handle_request(
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
    node22_name = GriptapeNodes.handle_request(
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
        source_node_name=node18_name,
        source_parameter_name="ruleset",
        target_node_name=node2_name,
        target_parameter_name="ruleset_1",
        initial_setup=True,
    )
)

GriptapeNodes.handle_request(
    CreateConnectionRequest(
        source_node_name=node2_name,
        source_parameter_name="rulesets",
        target_node_name=node3_name,
        target_parameter_name="rulesets",
        initial_setup=True,
    )
)

GriptapeNodes.handle_request(
    CreateConnectionRequest(
        source_node_name=node3_name,
        source_parameter_name="agent",
        target_node_name=node4_name,
        target_parameter_name="agent",
        initial_setup=True,
    )
)

GriptapeNodes.handle_request(
    CreateConnectionRequest(
        source_node_name=node19_name,
        source_parameter_name="ruleset",
        target_node_name=node5_name,
        target_parameter_name="ruleset_1",
        initial_setup=True,
    )
)

GriptapeNodes.handle_request(
    CreateConnectionRequest(
        source_node_name=node5_name,
        source_parameter_name="rulesets",
        target_node_name=node6_name,
        target_parameter_name="rulesets",
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
        source_node_name=node17_name,
        source_parameter_name="ruleset",
        target_node_name=node8_name,
        target_parameter_name="ruleset_1",
        initial_setup=True,
    )
)

GriptapeNodes.handle_request(
    CreateConnectionRequest(
        source_node_name=node8_name,
        source_parameter_name="rulesets",
        target_node_name=node9_name,
        target_parameter_name="rulesets",
        initial_setup=True,
    )
)

GriptapeNodes.handle_request(
    CreateConnectionRequest(
        source_node_name=node9_name,
        source_parameter_name="agent",
        target_node_name=node10_name,
        target_parameter_name="agent",
        initial_setup=True,
    )
)

GriptapeNodes.handle_request(
    CreateConnectionRequest(
        source_node_name=node20_name,
        source_parameter_name="ruleset",
        target_node_name=node11_name,
        target_parameter_name="ruleset_1",
        initial_setup=True,
    )
)

GriptapeNodes.handle_request(
    CreateConnectionRequest(
        source_node_name=node11_name,
        source_parameter_name="rulesets",
        target_node_name=node12_name,
        target_parameter_name="rulesets",
        initial_setup=True,
    )
)

GriptapeNodes.handle_request(
    CreateConnectionRequest(
        source_node_name=node12_name,
        source_parameter_name="agent",
        target_node_name=node13_name,
        target_parameter_name="agent",
        initial_setup=True,
    )
)

GriptapeNodes.handle_request(
    CreateConnectionRequest(
        source_node_name=node14_name,
        source_parameter_name="output",
        target_node_name=node15_name,
        target_parameter_name="prompt",
        initial_setup=True,
    )
)

GriptapeNodes.handle_request(
    CreateConnectionRequest(
        source_node_name=node21_name,
        source_parameter_name="ruleset",
        target_node_name=node16_name,
        target_parameter_name="ruleset_1",
        initial_setup=True,
    )
)

GriptapeNodes.handle_request(
    CreateConnectionRequest(
        source_node_name=node16_name,
        source_parameter_name="rulesets",
        target_node_name=node14_name,
        target_parameter_name="rulesets",
        initial_setup=True,
    )
)

GriptapeNodes.handle_request(
    CreateConnectionRequest(
        source_node_name=node4_name,
        source_parameter_name="tool",
        target_node_name=node22_name,
        target_parameter_name="tool_1",
        initial_setup=True,
    )
)

GriptapeNodes.handle_request(
    CreateConnectionRequest(
        source_node_name=node7_name,
        source_parameter_name="tool",
        target_node_name=node22_name,
        target_parameter_name="tool_2",
        initial_setup=True,
    )
)

GriptapeNodes.handle_request(
    CreateConnectionRequest(
        source_node_name=node10_name,
        source_parameter_name="tool",
        target_node_name=node22_name,
        target_parameter_name="tool_3",
        initial_setup=True,
    )
)

GriptapeNodes.handle_request(
    CreateConnectionRequest(
        source_node_name=node13_name,
        source_parameter_name="tool",
        target_node_name=node22_name,
        target_parameter_name="tool_4",
        initial_setup=True,
    )
)

GriptapeNodes.handle_request(
    CreateConnectionRequest(
        source_node_name=node22_name,
        source_parameter_name="tool_list",
        target_node_name=node14_name,
        target_parameter_name="tools_ParameterListUniqueParamID_b4d4b9d18fd342179cce723c48902d6f",
        initial_setup=True,
    )
)

with GriptapeNodes.ContextManager().node(node0_name):
    GriptapeNodes.handle_request(
        SetParameterValueRequest(
            parameter_name="note",
            node_name=node0_name,
            value=top_level_unique_values_dict["b20b6f8b-e01c-4f89-96e1-80f9c092b6e4"],
            initial_setup=True,
            is_output=False,
        )
    )

with GriptapeNodes.ContextManager().node(node1_name):
    GriptapeNodes.handle_request(
        SetParameterValueRequest(
            parameter_name="note",
            node_name=node1_name,
            value=top_level_unique_values_dict["e54613ac-3be5-4dc6-a7c8-9be8181249fe"],
            initial_setup=True,
            is_output=False,
        )
    )

with GriptapeNodes.ContextManager().node(node3_name):
    GriptapeNodes.handle_request(
        SetParameterValueRequest(
            parameter_name="model",
            node_name=node3_name,
            value=top_level_unique_values_dict["acf60b14-6db3-464b-b868-81c2456900cb"],
            initial_setup=True,
            is_output=False,
        )
    )
    GriptapeNodes.handle_request(
        SetParameterValueRequest(
            parameter_name="tools",
            node_name=node3_name,
            value=top_level_unique_values_dict["dddbac95-d3d6-4064-ab88-a001a62aea23"],
            initial_setup=True,
            is_output=False,
        )
    )
    GriptapeNodes.handle_request(
        SetParameterValueRequest(
            parameter_name="rulesets",
            node_name=node3_name,
            value=top_level_unique_values_dict["21c7f153-13aa-4c0a-976f-1b1e1fed6266"],
            initial_setup=True,
            is_output=False,
        )
    )
    GriptapeNodes.handle_request(
        SetParameterValueRequest(
            parameter_name="include_details",
            node_name=node3_name,
            value=top_level_unique_values_dict["38b74ba3-2993-470e-892c-d466ff0f59ba"],
            initial_setup=True,
            is_output=False,
        )
    )

with GriptapeNodes.ContextManager().node(node4_name):
    GriptapeNodes.handle_request(
        SetParameterValueRequest(
            parameter_name="name",
            node_name=node4_name,
            value=top_level_unique_values_dict["8dcae506-4127-496d-a024-821221e366c5"],
            initial_setup=True,
            is_output=False,
        )
    )
    GriptapeNodes.handle_request(
        SetParameterValueRequest(
            parameter_name="description",
            node_name=node4_name,
            value=top_level_unique_values_dict["ff2647c3-a694-416d-b09b-44c52d971194"],
            initial_setup=True,
            is_output=False,
        )
    )
    GriptapeNodes.handle_request(
        SetParameterValueRequest(
            parameter_name="off_prompt",
            node_name=node4_name,
            value=top_level_unique_values_dict["38b74ba3-2993-470e-892c-d466ff0f59ba"],
            initial_setup=True,
            is_output=False,
        )
    )

with GriptapeNodes.ContextManager().node(node6_name):
    GriptapeNodes.handle_request(
        SetParameterValueRequest(
            parameter_name="model",
            node_name=node6_name,
            value=top_level_unique_values_dict["acf60b14-6db3-464b-b868-81c2456900cb"],
            initial_setup=True,
            is_output=False,
        )
    )
    GriptapeNodes.handle_request(
        SetParameterValueRequest(
            parameter_name="tools",
            node_name=node6_name,
            value=top_level_unique_values_dict["03388e53-199a-4b40-a230-18113e567340"],
            initial_setup=True,
            is_output=False,
        )
    )
    GriptapeNodes.handle_request(
        SetParameterValueRequest(
            parameter_name="rulesets",
            node_name=node6_name,
            value=top_level_unique_values_dict["35cbc3e6-8433-4084-a4bc-a47d12183e7e"],
            initial_setup=True,
            is_output=False,
        )
    )
    GriptapeNodes.handle_request(
        SetParameterValueRequest(
            parameter_name="include_details",
            node_name=node6_name,
            value=top_level_unique_values_dict["38b74ba3-2993-470e-892c-d466ff0f59ba"],
            initial_setup=True,
            is_output=False,
        )
    )

with GriptapeNodes.ContextManager().node(node7_name):
    GriptapeNodes.handle_request(
        SetParameterValueRequest(
            parameter_name="name",
            node_name=node7_name,
            value=top_level_unique_values_dict["e660cb89-9835-4c2c-bc93-e09f19fc4dbf"],
            initial_setup=True,
            is_output=False,
        )
    )
    GriptapeNodes.handle_request(
        SetParameterValueRequest(
            parameter_name="description",
            node_name=node7_name,
            value=top_level_unique_values_dict["fb5e6d87-5f3a-4be3-8bc1-a84a86c1c4b1"],
            initial_setup=True,
            is_output=False,
        )
    )
    GriptapeNodes.handle_request(
        SetParameterValueRequest(
            parameter_name="off_prompt",
            node_name=node7_name,
            value=top_level_unique_values_dict["38b74ba3-2993-470e-892c-d466ff0f59ba"],
            initial_setup=True,
            is_output=False,
        )
    )

with GriptapeNodes.ContextManager().node(node9_name):
    GriptapeNodes.handle_request(
        SetParameterValueRequest(
            parameter_name="model",
            node_name=node9_name,
            value=top_level_unique_values_dict["acf60b14-6db3-464b-b868-81c2456900cb"],
            initial_setup=True,
            is_output=False,
        )
    )
    GriptapeNodes.handle_request(
        SetParameterValueRequest(
            parameter_name="tools",
            node_name=node9_name,
            value=top_level_unique_values_dict["bd211a92-eaeb-40a6-b630-dabeff9ee172"],
            initial_setup=True,
            is_output=False,
        )
    )
    GriptapeNodes.handle_request(
        SetParameterValueRequest(
            parameter_name="rulesets",
            node_name=node9_name,
            value=top_level_unique_values_dict["ab26282f-f4de-4a92-8eee-825b71360e33"],
            initial_setup=True,
            is_output=False,
        )
    )
    GriptapeNodes.handle_request(
        SetParameterValueRequest(
            parameter_name="include_details",
            node_name=node9_name,
            value=top_level_unique_values_dict["38b74ba3-2993-470e-892c-d466ff0f59ba"],
            initial_setup=True,
            is_output=False,
        )
    )

with GriptapeNodes.ContextManager().node(node10_name):
    GriptapeNodes.handle_request(
        SetParameterValueRequest(
            parameter_name="name",
            node_name=node10_name,
            value=top_level_unique_values_dict["6ace4b72-2824-455d-a5ba-5de61deb0c3e"],
            initial_setup=True,
            is_output=False,
        )
    )
    GriptapeNodes.handle_request(
        SetParameterValueRequest(
            parameter_name="description",
            node_name=node10_name,
            value=top_level_unique_values_dict["1992fe77-4bbf-4599-b5f8-1a6c36895c2b"],
            initial_setup=True,
            is_output=False,
        )
    )
    GriptapeNodes.handle_request(
        SetParameterValueRequest(
            parameter_name="off_prompt",
            node_name=node10_name,
            value=top_level_unique_values_dict["38b74ba3-2993-470e-892c-d466ff0f59ba"],
            initial_setup=True,
            is_output=False,
        )
    )

with GriptapeNodes.ContextManager().node(node12_name):
    GriptapeNodes.handle_request(
        SetParameterValueRequest(
            parameter_name="model",
            node_name=node12_name,
            value=top_level_unique_values_dict["acf60b14-6db3-464b-b868-81c2456900cb"],
            initial_setup=True,
            is_output=False,
        )
    )
    GriptapeNodes.handle_request(
        SetParameterValueRequest(
            parameter_name="tools",
            node_name=node12_name,
            value=top_level_unique_values_dict["715b8861-eaeb-4bb9-a682-1e71226cc1f8"],
            initial_setup=True,
            is_output=False,
        )
    )
    GriptapeNodes.handle_request(
        SetParameterValueRequest(
            parameter_name="rulesets",
            node_name=node12_name,
            value=top_level_unique_values_dict["36c8b764-fb47-4697-947b-2371aad8df8c"],
            initial_setup=True,
            is_output=False,
        )
    )
    GriptapeNodes.handle_request(
        SetParameterValueRequest(
            parameter_name="include_details",
            node_name=node12_name,
            value=top_level_unique_values_dict["38b74ba3-2993-470e-892c-d466ff0f59ba"],
            initial_setup=True,
            is_output=False,
        )
    )

with GriptapeNodes.ContextManager().node(node13_name):
    GriptapeNodes.handle_request(
        SetParameterValueRequest(
            parameter_name="name",
            node_name=node13_name,
            value=top_level_unique_values_dict["2d107f31-7776-4eb7-9e79-2b65930712d0"],
            initial_setup=True,
            is_output=False,
        )
    )
    GriptapeNodes.handle_request(
        SetParameterValueRequest(
            parameter_name="description",
            node_name=node13_name,
            value=top_level_unique_values_dict["1992fe77-4bbf-4599-b5f8-1a6c36895c2b"],
            initial_setup=True,
            is_output=False,
        )
    )
    GriptapeNodes.handle_request(
        SetParameterValueRequest(
            parameter_name="off_prompt",
            node_name=node13_name,
            value=top_level_unique_values_dict["38b74ba3-2993-470e-892c-d466ff0f59ba"],
            initial_setup=True,
            is_output=False,
        )
    )

with GriptapeNodes.ContextManager().node(node14_name):
    GriptapeNodes.handle_request(
        SetParameterValueRequest(
            parameter_name="model",
            node_name=node14_name,
            value=top_level_unique_values_dict["acf60b14-6db3-464b-b868-81c2456900cb"],
            initial_setup=True,
            is_output=False,
        )
    )
    GriptapeNodes.handle_request(
        SetParameterValueRequest(
            parameter_name="prompt",
            node_name=node14_name,
            value=top_level_unique_values_dict["ecfa18d1-3ae8-451c-add3-1a97db88eb2b"],
            initial_setup=True,
            is_output=False,
        )
    )
    GriptapeNodes.handle_request(
        SetParameterValueRequest(
            parameter_name="rulesets",
            node_name=node14_name,
            value=top_level_unique_values_dict["66d8e4a3-fe34-4948-8d82-db85586ae21f"],
            initial_setup=True,
            is_output=False,
        )
    )
    GriptapeNodes.handle_request(
        SetParameterValueRequest(
            parameter_name="include_details",
            node_name=node14_name,
            value=top_level_unique_values_dict["38b74ba3-2993-470e-892c-d466ff0f59ba"],
            initial_setup=True,
            is_output=False,
        )
    )

with GriptapeNodes.ContextManager().node(node15_name):
    GriptapeNodes.handle_request(
        SetParameterValueRequest(
            parameter_name="enhance_prompt",
            node_name=node15_name,
            value=top_level_unique_values_dict["38b74ba3-2993-470e-892c-d466ff0f59ba"],
            initial_setup=True,
            is_output=False,
        )
    )

with GriptapeNodes.ContextManager().node(node17_name):
    GriptapeNodes.handle_request(
        SetParameterValueRequest(
            parameter_name="name",
            node_name=node17_name,
            value=top_level_unique_values_dict["a024aea0-0c99-4792-97f1-300867710602"],
            initial_setup=True,
            is_output=False,
        )
    )
    GriptapeNodes.handle_request(
        SetParameterValueRequest(
            parameter_name="rules",
            node_name=node17_name,
            value=top_level_unique_values_dict["97ba7f16-6044-424b-b402-925ef60c353d"],
            initial_setup=True,
            is_output=False,
        )
    )

with GriptapeNodes.ContextManager().node(node18_name):
    GriptapeNodes.handle_request(
        SetParameterValueRequest(
            parameter_name="name",
            node_name=node18_name,
            value=top_level_unique_values_dict["c2ecb3c1-72e8-4a3c-ab22-743bef2f20c4"],
            initial_setup=True,
            is_output=False,
        )
    )
    GriptapeNodes.handle_request(
        SetParameterValueRequest(
            parameter_name="rules",
            node_name=node18_name,
            value=top_level_unique_values_dict["be355baf-f684-412d-9b48-8333e357c55d"],
            initial_setup=True,
            is_output=False,
        )
    )

with GriptapeNodes.ContextManager().node(node19_name):
    GriptapeNodes.handle_request(
        SetParameterValueRequest(
            parameter_name="name",
            node_name=node19_name,
            value=top_level_unique_values_dict["8c9a50e2-0d18-47a2-98e2-52cc5dd0e4f3"],
            initial_setup=True,
            is_output=False,
        )
    )
    GriptapeNodes.handle_request(
        SetParameterValueRequest(
            parameter_name="rules",
            node_name=node19_name,
            value=top_level_unique_values_dict["544b3629-42cd-429e-96aa-9517cf52530d"],
            initial_setup=True,
            is_output=False,
        )
    )

with GriptapeNodes.ContextManager().node(node20_name):
    GriptapeNodes.handle_request(
        SetParameterValueRequest(
            parameter_name="name",
            node_name=node20_name,
            value=top_level_unique_values_dict["9ff03863-7757-4f5b-aa15-2acafbbb4515"],
            initial_setup=True,
            is_output=False,
        )
    )
    GriptapeNodes.handle_request(
        SetParameterValueRequest(
            parameter_name="rules",
            node_name=node20_name,
            value=top_level_unique_values_dict["132a6511-3d73-46d8-a61e-7a7f32237089"],
            initial_setup=True,
            is_output=False,
        )
    )

with GriptapeNodes.ContextManager().node(node21_name):
    GriptapeNodes.handle_request(
        SetParameterValueRequest(
            parameter_name="name",
            node_name=node21_name,
            value=top_level_unique_values_dict["d5bc0a5d-922a-4722-8c93-50ae5d023193"],
            initial_setup=True,
            is_output=False,
        )
    )
    GriptapeNodes.handle_request(
        SetParameterValueRequest(
            parameter_name="rules",
            node_name=node21_name,
            value=top_level_unique_values_dict["bff4d87b-7069-4c44-a39d-3ece298df4b3"],
            initial_setup=True,
            is_output=False,
        )
    )
