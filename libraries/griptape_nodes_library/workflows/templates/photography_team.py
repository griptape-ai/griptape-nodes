# /// script
# dependencies = []
#
# [tool.griptape-nodes]
# name = "photography_team"
# schema_version = "0.3.0"
# description = "A team of experts develop a prompt."
# image = "https://raw.githubusercontent.com/griptape-ai/griptape-nodes/refs/heads/main/libraries/griptape_nodes_library/workflows/templates/thumbnail_photography_team.webp"
# engine_version_created_with = "0.33.1"
# node_libraries_referenced = [["Griptape Nodes Library", "0.34.0"]]
# is_griptape_provided = true
# is_template = true
# creation_date = 2025-05-01T00:00:00.000000+00:00
# last_modified_date = 2025-05-17T06:40:00.145097+12:00
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
    "85506ace-a561-40ad-8907-fb6ea68b81bd": pickle.loads(
        b'\x80\x04\x95\xbd\x01\x00\x00\x00\x00\x00\x00X\xb6\x01\x00\x00This workflow serves as the lesson material for the tutorial located at:\n\nhttps://docs.griptapenodes.com/en/stable/ftue/04_photography_team/FTUE_04_photography_team/\n\nThe concepts covered are:\n\n- Incorporating key upgrades available to agents:\n    - Rulesets to define and manage agent behaviors\n    - Tools to give agents more abilities\n- Converting agents into tools\n- Creating and orchestrating a team of "experts" with specific roles\n\x94.'
    ),
    "ea84a998-d22b-4701-bc3f-a6b253ba73b5": pickle.loads(
        b'\x80\x04\x95F\x00\x00\x00\x00\x00\x00\x00\x8cBGood job. You\'ve completed our "Getting Started" set of tutorials!\x94.'
    ),
    "321bb927-4e93-4ebe-8ed8-457056ee517b": pickle.loads(
        b"\x80\x04\x95\x0b\x00\x00\x00\x00\x00\x00\x00\x8c\x07gpt-4.1\x94."
    ),
    "0ddbb521-abbe-429f-aa04-c6632f296625": pickle.loads(b"\x80\x04\x89."),
    "5781b53b-b6e8-4eac-9b6b-0952efdaf11e": pickle.loads(
        b"\x80\x04\x95\x13\x00\x00\x00\x00\x00\x00\x00\x8c\x0fCinematographer\x94."
    ),
    "e4246496-f430-47a6-997d-5e09aff4b5ee": pickle.loads(
        b"\x80\x04\x95)\x00\x00\x00\x00\x00\x00\x00\x8c%This agent understands cinematography\x94."
    ),
    "3fe15b30-6a18-498b-a6c8-fe56a9180fb4": pickle.loads(
        b"\x80\x04\x95\x12\x00\x00\x00\x00\x00\x00\x00\x8c\x0eColor_Theorist\x94."
    ),
    "53a1d2ac-49e0-4e53-8189-985510a820d4": pickle.loads(
        b"\x80\x04\x954\x00\x00\x00\x00\x00\x00\x00\x8c0This agent can be used to ensure the best colors\x94."
    ),
    "807e9435-e4be-4b88-bcb6-4cfc8fcdb50a": pickle.loads(
        b"\x80\x04\x95\x15\x00\x00\x00\x00\x00\x00\x00\x8c\x11Detail_Enthusiast\x94."
    ),
    "d86f5502-f2c0-41b5-a34d-f0543d8b5b04": pickle.loads(
        b"\x80\x04\x95n\x00\x00\x00\x00\x00\x00\x00\x8cjThis agent is into the fine details of an image. Use it to make sure descriptions are specific and unique.\x94."
    ),
    "5130a1c1-f610-4baa-9664-f5180459c41a": pickle.loads(
        b"\x80\x04\x95\x1f\x00\x00\x00\x00\x00\x00\x00\x8c\x1bImage_Generation_Specialist\x94."
    ),
    "dd2715d5-6a64-4223-a441-a0f85f604de7": pickle.loads(
        b'\x80\x04\x95\x9a\x00\x00\x00\x00\x00\x00\x00\x8c\x96Use all the tools at your disposal to create a spectacular image generation prompt about "a skateboarding lion", that is no longer than 500 characters\x94.'
    ),
    "d0a1c36c-6b07-4be2-a0ce-720110a42a03": pickle.loads(
        b"\x80\x04\x95\x1d\x00\x00\x00\x00\x00\x00\x00\x8c\x19Detail_Enthusiast Ruleset\x94."
    ),
    "0eb78488-8b6f-4a59-9232-b9b1f27c1c48": pickle.loads(
        b'\x80\x04\x95\xa3\x01\x00\x00\x00\x00\x00\x00X\x9c\x01\x00\x00You care about the unique details and specific descriptions of items.\nWhen describing things, call out specific details and don\'t be generic. Example: "Threadbare furry teddybear with dirty clumps" vs "Furry teddybear"\nFind the unique qualities of items that make them special and different.\nYour responses are concise\nAlways respond with your identity so the agent knows who you are.\nKeep your responses brief.\n\x94.'
    ),
    "2de88611-5009-4b8b-a7d4-9ad1bad64711": pickle.loads(
        b"\x80\x04\x95\x1b\x00\x00\x00\x00\x00\x00\x00\x8c\x17Cinematographer Ruleset\x94."
    ),
    "f7cee877-e115-402c-b51b-a1044b770c85": pickle.loads(
        b"\x80\x04\x95\xf0\x02\x00\x00\x00\x00\x00\x00X\xe9\x02\x00\x00You identify as a cinematographer\nThe main subject of the image should be well framed\nIf no environment is specified, set the image in a location that will evoke a deep and meaningful connection to the viewer.\nYou care deeply about light, shadow, color, and composition\nWhen coming up with image prompts, you always specify the position of the camera, the lens, and the color\nYou are specific about the technical details of a shot.\nYou like to add atmosphere to your shots, so you include depth of field, haze, dust particles in the air close to and far away from camera, and the way lighting reacts with each item.\nYour responses are brief and concise\nAlways respond with your identity so the agent knows who you are.\nKeep your responses brief.\x94."
    ),
    "72c9854b-d9d5-4d41-8900-1cd1103c5040": pickle.loads(
        b"\x80\x04\x95\x1a\x00\x00\x00\x00\x00\x00\x00\x8c\x16Color_Theorist Ruleset\x94."
    ),
    "a519ea6e-b7e0-4f9b-83ad-225c77cfed67": pickle.loads(
        b"\x80\x04\x95'\x01\x00\x00\x00\x00\x00\x00X \x01\x00\x00You identify as an expert in color theory\nYou have a deep understanding of how color impacts one's psychological outlook\nYou are a fan of non-standard colors\nYour responses are brief and concise\nAlways respond with your identity  so the agent knows who you are.\nKeep your responses brief.\x94."
    ),
    "8d5a0f2e-169c-47b4-8de4-c3baeaa16f96": pickle.loads(
        b"\x80\x04\x95'\x00\x00\x00\x00\x00\x00\x00\x8c#Image_Generation_Specialist Ruleset\x94."
    ),
    "a6cfc39d-b4e4-43a0-a5ef-64b0b16d6359": pickle.loads(
        b"\x80\x04\x95Q\x02\x00\x00\x00\x00\x00\x00XJ\x02\x00\x00You are an expert in creating prompts for image generation engines\nYou use the latest knowledge available to you to generate the best prompts.\nYou create prompts that are direct and succinct and you understand they need to be under 800 characters long\nAlways include the following: subject, attributes of subject, visual characteristics of the image, film grain, camera angle, lighting, art style, color scheme, surrounding environment, camera used (ex: Nikon d850 film stock, polaroid, etc).\nAlways respond with your identity so the agent knows who you are.\nKeep your responses brief.\n\x94."
    ),
    "d4204c6b-5bb0-46ce-a6cf-c39f636199bd": pickle.loads(
        b"\x80\x04\x95\x0f\x00\x00\x00\x00\x00\x00\x00\x8c\x0bAgent Rules\x94."
    ),
    "804b1fbd-45c2-43ef-99b7-4dc14745b9f5": pickle.loads(
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
            node_name="Congratulations",
            metadata={
                "position": {"x": 5100, "y": 1500},
                "size": {"width": 650, "height": 150},
                "library_node_metadata": NodeMetadata(
                    category="Base", description="Note node", display_name="Note", tags=None
                ),
                "library": "Griptape Nodes Library",
                "node_type": "Note",
            },
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
                    category="rules",
                    description="Combine rulesets to give an agent a more complex set of behaviors",
                    display_name="Ruleset List",
                    tags=None,
                ),
                "library": "Griptape Nodes Library",
                "node_type": "RulesetList",
            },
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
                    category="agents", description="Agent node", display_name="Agent", tags=None
                ),
                "library": "Griptape Nodes Library",
                "node_type": "Agent",
            },
        )
    ).node_name
    with GriptapeNodes.ContextManager().node(node3_name):
        GriptapeNodes.handle_request(
            AlterParameterDetailsRequest(
                parameter_name="tools",
                node_name="Cinematographer",
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
                node_name="Cinematographer",
                default_value=[],
                tooltip="Rulesets to apply to the agent to control its behavior.",
                mode_allowed_input=True,
                mode_allowed_property=False,
                mode_allowed_output=False,
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
                    category="convert", description="AgentToTool node", display_name="Agent To Tool", tags=None
                ),
                "library": "Griptape Nodes Library",
                "node_type": "AgentToTool",
            },
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
                    category="rules",
                    description="Combine rulesets to give an agent a more complex set of behaviors",
                    display_name="Ruleset List",
                    tags=None,
                ),
                "library": "Griptape Nodes Library",
                "node_type": "RulesetList",
            },
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
                    category="agents", description="Agent node", display_name="Agent", tags=None
                ),
                "library": "Griptape Nodes Library",
                "node_type": "Agent",
            },
        )
    ).node_name
    with GriptapeNodes.ContextManager().node(node6_name):
        GriptapeNodes.handle_request(
            AlterParameterDetailsRequest(
                parameter_name="tools",
                node_name="Color_Theorist",
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
                node_name="Color_Theorist",
                default_value=[],
                tooltip="Rulesets to apply to the agent to control its behavior.",
                mode_allowed_input=True,
                mode_allowed_property=False,
                mode_allowed_output=False,
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
                    category="convert", description="AgentToTool node", display_name="Agent To Tool", tags=None
                ),
                "library": "Griptape Nodes Library",
                "node_type": "AgentToTool",
            },
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
                    category="rules",
                    description="Combine rulesets to give an agent a more complex set of behaviors",
                    display_name="Ruleset List",
                    tags=None,
                ),
                "library": "Griptape Nodes Library",
                "node_type": "RulesetList",
            },
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
                    category="agents", description="Agent node", display_name="Agent", tags=None
                ),
                "library": "Griptape Nodes Library",
                "node_type": "Agent",
            },
        )
    ).node_name
    with GriptapeNodes.ContextManager().node(node9_name):
        GriptapeNodes.handle_request(
            AlterParameterDetailsRequest(
                parameter_name="tools",
                node_name="Detail_Enthusiast",
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
                node_name="Detail_Enthusiast",
                default_value=[],
                tooltip="Rulesets to apply to the agent to control its behavior.",
                mode_allowed_input=True,
                mode_allowed_property=False,
                mode_allowed_output=False,
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
                    category="convert", description="AgentToTool node", display_name="Agent To Tool", tags=None
                ),
                "library": "Griptape Nodes Library",
                "node_type": "AgentToTool",
            },
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
                    category="rules",
                    description="Combine rulesets to give an agent a more complex set of behaviors",
                    display_name="Ruleset List",
                    tags=None,
                ),
                "library": "Griptape Nodes Library",
                "node_type": "RulesetList",
            },
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
                    category="agents", description="Agent node", display_name="Agent", tags=None
                ),
                "library": "Griptape Nodes Library",
                "node_type": "Agent",
            },
        )
    ).node_name
    with GriptapeNodes.ContextManager().node(node12_name):
        GriptapeNodes.handle_request(
            AlterParameterDetailsRequest(
                parameter_name="tools",
                node_name="Image_Generation_Specialist",
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
                node_name="Image_Generation_Specialist",
                default_value=[],
                tooltip="Rulesets to apply to the agent to control its behavior.",
                mode_allowed_input=True,
                mode_allowed_property=False,
                mode_allowed_output=False,
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
                    category="convert", description="AgentToTool node", display_name="Agent To Tool", tags=None
                ),
                "library": "Griptape Nodes Library",
                "node_type": "AgentToTool",
            },
        )
    ).node_name
    node14_name = GriptapeNodes.handle_request(
        CreateNodeRequest(
            node_type="ToolList",
            specific_library_name="Griptape Nodes Library",
            node_name="ToolList_1",
            metadata={
                "position": {"x": 2500, "y": 1000},
                "library_node_metadata": NodeMetadata(
                    category="tools",
                    description="Combine tools to give an agent a more complex set of tools",
                    display_name="Tool List",
                    tags=None,
                ),
                "library": "Griptape Nodes Library",
                "node_type": "ToolList",
            },
        )
    ).node_name
    node15_name = GriptapeNodes.handle_request(
        CreateNodeRequest(
            node_type="Agent",
            specific_library_name="Griptape Nodes Library",
            node_name="Orchestrator",
            metadata={
                "position": {"x": 4000, "y": 800},
                "library_node_metadata": NodeMetadata(
                    category="agents", description="Agent node", display_name="Agent", tags=None
                ),
                "library": "Griptape Nodes Library",
                "node_type": "Agent",
            },
        )
    ).node_name
    with GriptapeNodes.ContextManager().node(node15_name):
        GriptapeNodes.handle_request(
            AlterParameterDetailsRequest(
                parameter_name="tools",
                node_name="Orchestrator",
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
                node_name="Orchestrator",
                default_value=[],
                tooltip="Rulesets to apply to the agent to control its behavior.",
                mode_allowed_input=True,
                mode_allowed_property=False,
                mode_allowed_output=False,
                initial_setup=True,
            )
        )
    node16_name = GriptapeNodes.handle_request(
        CreateNodeRequest(
            node_type="GenerateImage",
            specific_library_name="Griptape Nodes Library",
            node_name="GenerateImage_1",
            metadata={
                "position": {"x": 4600, "y": 1050},
                "library_node_metadata": {"category": "image", "description": "GenerateImage node"},
                "library": "Griptape Nodes Library",
                "node_type": "GenerateImage",
                "size": {"width": 427, "height": 609},
            },
        )
    ).node_name
    with GriptapeNodes.ContextManager().node(node16_name):
        GriptapeNodes.handle_request(
            AlterParameterDetailsRequest(
                parameter_name="prompt", node_name="GenerateImage_1", mode_allowed_property=False, initial_setup=True
            )
        )
    node17_name = GriptapeNodes.handle_request(
        CreateNodeRequest(
            node_type="RulesetList",
            specific_library_name="Griptape Nodes Library",
            node_name="Agent_RulesetList",
            metadata={
                "position": {"x": 3500, "y": 1500},
                "library_node_metadata": NodeMetadata(
                    category="rules",
                    description="Combine rulesets to give an agent a more complex set of behaviors",
                    display_name="Ruleset List",
                    tags=None,
                ),
                "library": "Griptape Nodes Library",
                "node_type": "RulesetList",
            },
        )
    ).node_name
    node18_name = GriptapeNodes.handle_request(
        CreateNodeRequest(
            node_type="Ruleset",
            specific_library_name="Griptape Nodes Library",
            node_name="Detail_Enthusiast_Ruleset",
            metadata={
                "position": {"x": -500, "y": 1200},
                "size": {"width": 900, "height": 450},
                "library_node_metadata": NodeMetadata(
                    category="rules", description="Ruleset node", display_name="Ruleset", tags=None
                ),
                "library": "Griptape Nodes Library",
                "node_type": "Ruleset",
            },
        )
    ).node_name
    node19_name = GriptapeNodes.handle_request(
        CreateNodeRequest(
            node_type="Ruleset",
            specific_library_name="Griptape Nodes Library",
            node_name="Cinematographer_Ruleset",
            metadata={
                "position": {"x": -500, "y": 0},
                "size": {"width": 900, "height": 450},
                "library_node_metadata": NodeMetadata(
                    category="rules", description="Ruleset node", display_name="Ruleset", tags=None
                ),
                "library": "Griptape Nodes Library",
                "node_type": "Ruleset",
            },
        )
    ).node_name
    node20_name = GriptapeNodes.handle_request(
        CreateNodeRequest(
            node_type="Ruleset",
            specific_library_name="Griptape Nodes Library",
            node_name="Color_Theorist_Ruleset",
            metadata={
                "position": {"x": -500, "y": 600},
                "size": {"width": 900, "height": 450},
                "library_node_metadata": NodeMetadata(
                    category="rules", description="Ruleset node", display_name="Ruleset", tags=None
                ),
                "library": "Griptape Nodes Library",
                "node_type": "Ruleset",
            },
        )
    ).node_name
    node21_name = GriptapeNodes.handle_request(
        CreateNodeRequest(
            node_type="Ruleset",
            specific_library_name="Griptape Nodes Library",
            node_name="Image_Generation_Specialist_Ruleset",
            metadata={
                "position": {"x": -500, "y": 1800},
                "size": {"width": 900, "height": 450},
                "library_node_metadata": NodeMetadata(
                    category="rules", description="Ruleset node", display_name="Ruleset", tags=None
                ),
                "library": "Griptape Nodes Library",
                "node_type": "Ruleset",
            },
        )
    ).node_name
    node22_name = GriptapeNodes.handle_request(
        CreateNodeRequest(
            node_type="Ruleset",
            specific_library_name="Griptape Nodes Library",
            node_name="Agent_Ruleset",
            metadata={
                "position": {"x": 2500, "y": 1500},
                "size": {"width": 900, "height": 450},
                "library_node_metadata": NodeMetadata(
                    category="rules", description="Ruleset node", display_name="Ruleset", tags=None
                ),
                "library": "Griptape Nodes Library",
                "node_type": "Ruleset",
            },
        )
    ).node_name

GriptapeNodes.handle_request(
    CreateConnectionRequest(
        source_node_name=node19_name,
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
        source_node_name=node4_name,
        source_parameter_name="tool",
        target_node_name=node14_name,
        target_parameter_name="tool_1",
        initial_setup=True,
    )
)

GriptapeNodes.handle_request(
    CreateConnectionRequest(
        source_node_name=node20_name,
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
        source_node_name=node7_name,
        source_parameter_name="tool",
        target_node_name=node14_name,
        target_parameter_name="tool_2",
        initial_setup=True,
    )
)

GriptapeNodes.handle_request(
    CreateConnectionRequest(
        source_node_name=node18_name,
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
        source_node_name=node10_name,
        source_parameter_name="tool",
        target_node_name=node14_name,
        target_parameter_name="tool_3",
        initial_setup=True,
    )
)

GriptapeNodes.handle_request(
    CreateConnectionRequest(
        source_node_name=node21_name,
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
        source_node_name=node13_name,
        source_parameter_name="tool",
        target_node_name=node14_name,
        target_parameter_name="tool_4",
        initial_setup=True,
    )
)

GriptapeNodes.handle_request(
    CreateConnectionRequest(
        source_node_name=node14_name,
        source_parameter_name="tool_list",
        target_node_name=node15_name,
        target_parameter_name="tools",
        initial_setup=True,
    )
)

GriptapeNodes.handle_request(
    CreateConnectionRequest(
        source_node_name=node15_name,
        source_parameter_name="output",
        target_node_name=node16_name,
        target_parameter_name="prompt",
        initial_setup=True,
    )
)

GriptapeNodes.handle_request(
    CreateConnectionRequest(
        source_node_name=node22_name,
        source_parameter_name="ruleset",
        target_node_name=node17_name,
        target_parameter_name="ruleset_1",
        initial_setup=True,
    )
)

GriptapeNodes.handle_request(
    CreateConnectionRequest(
        source_node_name=node17_name,
        source_parameter_name="rulesets",
        target_node_name=node15_name,
        target_parameter_name="rulesets",
        initial_setup=True,
    )
)

with GriptapeNodes.ContextManager().node(node0_name):
    GriptapeNodes.handle_request(
        SetParameterValueRequest(
            parameter_name="note",
            node_name=node0_name,
            value=top_level_unique_values_dict["85506ace-a561-40ad-8907-fb6ea68b81bd"],
            initial_setup=True,
            is_output=False,
        )
    )

with GriptapeNodes.ContextManager().node(node1_name):
    GriptapeNodes.handle_request(
        SetParameterValueRequest(
            parameter_name="note",
            node_name=node1_name,
            value=top_level_unique_values_dict["ea84a998-d22b-4701-bc3f-a6b253ba73b5"],
            initial_setup=True,
            is_output=False,
        )
    )

with GriptapeNodes.ContextManager().node(node3_name):
    GriptapeNodes.handle_request(
        SetParameterValueRequest(
            parameter_name="model",
            node_name=node3_name,
            value=top_level_unique_values_dict["321bb927-4e93-4ebe-8ed8-457056ee517b"],
            initial_setup=True,
            is_output=False,
        )
    )
    GriptapeNodes.handle_request(
        SetParameterValueRequest(
            parameter_name="include_details",
            node_name=node3_name,
            value=top_level_unique_values_dict["0ddbb521-abbe-429f-aa04-c6632f296625"],
            initial_setup=True,
            is_output=False,
        )
    )

with GriptapeNodes.ContextManager().node(node4_name):
    GriptapeNodes.handle_request(
        SetParameterValueRequest(
            parameter_name="name",
            node_name=node4_name,
            value=top_level_unique_values_dict["5781b53b-b6e8-4eac-9b6b-0952efdaf11e"],
            initial_setup=True,
            is_output=False,
        )
    )
    GriptapeNodes.handle_request(
        SetParameterValueRequest(
            parameter_name="description",
            node_name=node4_name,
            value=top_level_unique_values_dict["e4246496-f430-47a6-997d-5e09aff4b5ee"],
            initial_setup=True,
            is_output=False,
        )
    )
    GriptapeNodes.handle_request(
        SetParameterValueRequest(
            parameter_name="off_prompt",
            node_name=node4_name,
            value=top_level_unique_values_dict["0ddbb521-abbe-429f-aa04-c6632f296625"],
            initial_setup=True,
            is_output=False,
        )
    )

with GriptapeNodes.ContextManager().node(node6_name):
    GriptapeNodes.handle_request(
        SetParameterValueRequest(
            parameter_name="model",
            node_name=node6_name,
            value=top_level_unique_values_dict["321bb927-4e93-4ebe-8ed8-457056ee517b"],
            initial_setup=True,
            is_output=False,
        )
    )
    GriptapeNodes.handle_request(
        SetParameterValueRequest(
            parameter_name="include_details",
            node_name=node6_name,
            value=top_level_unique_values_dict["0ddbb521-abbe-429f-aa04-c6632f296625"],
            initial_setup=True,
            is_output=False,
        )
    )

with GriptapeNodes.ContextManager().node(node7_name):
    GriptapeNodes.handle_request(
        SetParameterValueRequest(
            parameter_name="name",
            node_name=node7_name,
            value=top_level_unique_values_dict["3fe15b30-6a18-498b-a6c8-fe56a9180fb4"],
            initial_setup=True,
            is_output=False,
        )
    )
    GriptapeNodes.handle_request(
        SetParameterValueRequest(
            parameter_name="description",
            node_name=node7_name,
            value=top_level_unique_values_dict["53a1d2ac-49e0-4e53-8189-985510a820d4"],
            initial_setup=True,
            is_output=False,
        )
    )
    GriptapeNodes.handle_request(
        SetParameterValueRequest(
            parameter_name="off_prompt",
            node_name=node7_name,
            value=top_level_unique_values_dict["0ddbb521-abbe-429f-aa04-c6632f296625"],
            initial_setup=True,
            is_output=False,
        )
    )

with GriptapeNodes.ContextManager().node(node9_name):
    GriptapeNodes.handle_request(
        SetParameterValueRequest(
            parameter_name="model",
            node_name=node9_name,
            value=top_level_unique_values_dict["321bb927-4e93-4ebe-8ed8-457056ee517b"],
            initial_setup=True,
            is_output=False,
        )
    )
    GriptapeNodes.handle_request(
        SetParameterValueRequest(
            parameter_name="include_details",
            node_name=node9_name,
            value=top_level_unique_values_dict["0ddbb521-abbe-429f-aa04-c6632f296625"],
            initial_setup=True,
            is_output=False,
        )
    )

with GriptapeNodes.ContextManager().node(node10_name):
    GriptapeNodes.handle_request(
        SetParameterValueRequest(
            parameter_name="name",
            node_name=node10_name,
            value=top_level_unique_values_dict["807e9435-e4be-4b88-bcb6-4cfc8fcdb50a"],
            initial_setup=True,
            is_output=False,
        )
    )
    GriptapeNodes.handle_request(
        SetParameterValueRequest(
            parameter_name="description",
            node_name=node10_name,
            value=top_level_unique_values_dict["d86f5502-f2c0-41b5-a34d-f0543d8b5b04"],
            initial_setup=True,
            is_output=False,
        )
    )
    GriptapeNodes.handle_request(
        SetParameterValueRequest(
            parameter_name="off_prompt",
            node_name=node10_name,
            value=top_level_unique_values_dict["0ddbb521-abbe-429f-aa04-c6632f296625"],
            initial_setup=True,
            is_output=False,
        )
    )

with GriptapeNodes.ContextManager().node(node12_name):
    GriptapeNodes.handle_request(
        SetParameterValueRequest(
            parameter_name="model",
            node_name=node12_name,
            value=top_level_unique_values_dict["321bb927-4e93-4ebe-8ed8-457056ee517b"],
            initial_setup=True,
            is_output=False,
        )
    )
    GriptapeNodes.handle_request(
        SetParameterValueRequest(
            parameter_name="include_details",
            node_name=node12_name,
            value=top_level_unique_values_dict["0ddbb521-abbe-429f-aa04-c6632f296625"],
            initial_setup=True,
            is_output=False,
        )
    )

with GriptapeNodes.ContextManager().node(node13_name):
    GriptapeNodes.handle_request(
        SetParameterValueRequest(
            parameter_name="name",
            node_name=node13_name,
            value=top_level_unique_values_dict["5130a1c1-f610-4baa-9664-f5180459c41a"],
            initial_setup=True,
            is_output=False,
        )
    )
    GriptapeNodes.handle_request(
        SetParameterValueRequest(
            parameter_name="description",
            node_name=node13_name,
            value=top_level_unique_values_dict["d86f5502-f2c0-41b5-a34d-f0543d8b5b04"],
            initial_setup=True,
            is_output=False,
        )
    )
    GriptapeNodes.handle_request(
        SetParameterValueRequest(
            parameter_name="off_prompt",
            node_name=node13_name,
            value=top_level_unique_values_dict["0ddbb521-abbe-429f-aa04-c6632f296625"],
            initial_setup=True,
            is_output=False,
        )
    )

with GriptapeNodes.ContextManager().node(node15_name):
    GriptapeNodes.handle_request(
        SetParameterValueRequest(
            parameter_name="model",
            node_name=node15_name,
            value=top_level_unique_values_dict["321bb927-4e93-4ebe-8ed8-457056ee517b"],
            initial_setup=True,
            is_output=False,
        )
    )
    GriptapeNodes.handle_request(
        SetParameterValueRequest(
            parameter_name="prompt",
            node_name=node15_name,
            value=top_level_unique_values_dict["dd2715d5-6a64-4223-a441-a0f85f604de7"],
            initial_setup=True,
            is_output=False,
        )
    )
    GriptapeNodes.handle_request(
        SetParameterValueRequest(
            parameter_name="include_details",
            node_name=node15_name,
            value=top_level_unique_values_dict["0ddbb521-abbe-429f-aa04-c6632f296625"],
            initial_setup=True,
            is_output=False,
        )
    )

with GriptapeNodes.ContextManager().node(node16_name):
    GriptapeNodes.handle_request(
        SetParameterValueRequest(
            parameter_name="enhance_prompt",
            node_name=node16_name,
            value=top_level_unique_values_dict["0ddbb521-abbe-429f-aa04-c6632f296625"],
            initial_setup=True,
            is_output=False,
        )
    )

with GriptapeNodes.ContextManager().node(node18_name):
    GriptapeNodes.handle_request(
        SetParameterValueRequest(
            parameter_name="name",
            node_name=node18_name,
            value=top_level_unique_values_dict["d0a1c36c-6b07-4be2-a0ce-720110a42a03"],
            initial_setup=True,
            is_output=False,
        )
    )
    GriptapeNodes.handle_request(
        SetParameterValueRequest(
            parameter_name="rules",
            node_name=node18_name,
            value=top_level_unique_values_dict["0eb78488-8b6f-4a59-9232-b9b1f27c1c48"],
            initial_setup=True,
            is_output=False,
        )
    )

with GriptapeNodes.ContextManager().node(node19_name):
    GriptapeNodes.handle_request(
        SetParameterValueRequest(
            parameter_name="name",
            node_name=node19_name,
            value=top_level_unique_values_dict["2de88611-5009-4b8b-a7d4-9ad1bad64711"],
            initial_setup=True,
            is_output=False,
        )
    )
    GriptapeNodes.handle_request(
        SetParameterValueRequest(
            parameter_name="rules",
            node_name=node19_name,
            value=top_level_unique_values_dict["f7cee877-e115-402c-b51b-a1044b770c85"],
            initial_setup=True,
            is_output=False,
        )
    )

with GriptapeNodes.ContextManager().node(node20_name):
    GriptapeNodes.handle_request(
        SetParameterValueRequest(
            parameter_name="name",
            node_name=node20_name,
            value=top_level_unique_values_dict["72c9854b-d9d5-4d41-8900-1cd1103c5040"],
            initial_setup=True,
            is_output=False,
        )
    )
    GriptapeNodes.handle_request(
        SetParameterValueRequest(
            parameter_name="rules",
            node_name=node20_name,
            value=top_level_unique_values_dict["a519ea6e-b7e0-4f9b-83ad-225c77cfed67"],
            initial_setup=True,
            is_output=False,
        )
    )

with GriptapeNodes.ContextManager().node(node21_name):
    GriptapeNodes.handle_request(
        SetParameterValueRequest(
            parameter_name="name",
            node_name=node21_name,
            value=top_level_unique_values_dict["8d5a0f2e-169c-47b4-8de4-c3baeaa16f96"],
            initial_setup=True,
            is_output=False,
        )
    )
    GriptapeNodes.handle_request(
        SetParameterValueRequest(
            parameter_name="rules",
            node_name=node21_name,
            value=top_level_unique_values_dict["a6cfc39d-b4e4-43a0-a5ef-64b0b16d6359"],
            initial_setup=True,
            is_output=False,
        )
    )

with GriptapeNodes.ContextManager().node(node22_name):
    GriptapeNodes.handle_request(
        SetParameterValueRequest(
            parameter_name="name",
            node_name=node22_name,
            value=top_level_unique_values_dict["d4204c6b-5bb0-46ce-a6cf-c39f636199bd"],
            initial_setup=True,
            is_output=False,
        )
    )
    GriptapeNodes.handle_request(
        SetParameterValueRequest(
            parameter_name="rules",
            node_name=node22_name,
            value=top_level_unique_values_dict["804b1fbd-45c2-43ef-99b7-4dc14745b9f5"],
            initial_setup=True,
            is_output=False,
        )
    )
