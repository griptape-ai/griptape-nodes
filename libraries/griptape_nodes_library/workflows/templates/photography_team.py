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
# is_template = true# creation_date = 2025-10-22T16:58:45.005680Z
# last_modified_date = 2025-10-22T16:58:45.041273Z
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

response = GriptapeNodes.LibraryManager().get_all_info_for_all_libraries_request(GetAllInfoForAllLibrariesRequest())

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
    "dda81189-383f-4384-9fd7-9745d65c3491": pickle.loads(
        b'\x80\x04\x95\xbd\x01\x00\x00\x00\x00\x00\x00X\xb6\x01\x00\x00This workflow serves as the lesson material for the tutorial located at:\n\nhttps://docs.griptapenodes.com/en/stable/ftue/04_photography_team/FTUE_04_photography_team/\n\nThe concepts covered are:\n\n- Incorporating key upgrades available to agents:\n    - Rulesets to define and manage agent behaviors\n    - Tools to give agents more abilities\n- Converting agents into tools\n- Creating and orchestrating a team of "experts" with specific roles\n\x94.'
    ),
    "f9db571c-430e-4c1c-90b1-073e3b2bf204": pickle.loads(
        b'\x80\x04\x95F\x00\x00\x00\x00\x00\x00\x00\x8cBGood job. You\'ve completed our "Getting Started" set of tutorials!\x94.'
    ),
    "3c583699-63cd-458a-aa6a-b40ddd34af78": pickle.loads(
        b"\x80\x04\x95\x0b\x00\x00\x00\x00\x00\x00\x00\x8c\x07gpt-4.1\x94."
    ),
    "8b36c941-bc9f-4ccf-8dc8-35fa297a6ae0": pickle.loads(b"\x80\x04]\x94."),
    "8936ed0d-cb17-4a83-8a4c-b3e63dbd82aa": pickle.loads(b"\x80\x04\x89."),
    "528616a7-32dd-4e35-91a2-ce1b0fa2b407": pickle.loads(
        b"\x80\x04\x95\x13\x00\x00\x00\x00\x00\x00\x00\x8c\x0fCinematographer\x94."
    ),
    "90ff9b49-76a5-436c-a208-63286417396c": pickle.loads(
        b"\x80\x04\x95)\x00\x00\x00\x00\x00\x00\x00\x8c%This agent understands cinematography\x94."
    ),
    "e00d5c43-e40d-47ac-8f3e-8d7615d04cb6": pickle.loads(b"\x80\x04]\x94."),
    "7e42fdec-9d12-493e-9160-6c10d780787a": pickle.loads(
        b"\x80\x04\x95\x12\x00\x00\x00\x00\x00\x00\x00\x8c\x0eColor_Theorist\x94."
    ),
    "e0a24a7c-e23b-4adc-a51f-31f92834fc88": pickle.loads(
        b"\x80\x04\x954\x00\x00\x00\x00\x00\x00\x00\x8c0This agent can be used to ensure the best colors\x94."
    ),
    "ad84074f-817e-4962-8563-7c5f4974ff86": pickle.loads(b"\x80\x04]\x94."),
    "62ebeb0a-fe9a-4331-b72d-ab5ec52fe0ce": pickle.loads(
        b"\x80\x04\x95\x15\x00\x00\x00\x00\x00\x00\x00\x8c\x11Detail_Enthusiast\x94."
    ),
    "afe0114c-54b8-4d58-a0dc-fc9aec5074ac": pickle.loads(
        b"\x80\x04\x95n\x00\x00\x00\x00\x00\x00\x00\x8cjThis agent is into the fine details of an image. Use it to make sure descriptions are specific and unique.\x94."
    ),
    "7d02ad66-e1ef-4011-a67f-b3ee8948e9b8": pickle.loads(b"\x80\x04]\x94."),
    "f8cedc9a-917f-476e-ac9a-a30cf0f7485a": pickle.loads(
        b"\x80\x04\x95\x1f\x00\x00\x00\x00\x00\x00\x00\x8c\x1bImage_Generation_Specialist\x94."
    ),
    "04917546-c79e-451c-bb84-a9c45ec823cb": pickle.loads(
        b'\x80\x04\x95\x9a\x00\x00\x00\x00\x00\x00\x00\x8c\x96Use all the tools at your disposal to create a spectacular image generation prompt about "a skateboarding lion", that is no longer than 500 characters\x94.'
    ),
    "d256d88b-c99e-4e39-b08b-f3ec78f7648d": pickle.loads(b"\x80\x04\x95\x06\x00\x00\x00\x00\x00\x00\x00]\x94]\x94a."),
    "820882ee-2a9f-4279-b747-317924833c03": pickle.loads(b"\x80\x04]\x94."),
    "93e7a58c-af36-498f-aba6-b33428676a82": pickle.loads(
        b"\x80\x04\x95\x1d\x00\x00\x00\x00\x00\x00\x00\x8c\x19Detail_Enthusiast Ruleset\x94."
    ),
    "b781e0dd-c6ea-4caf-bcdf-579b59a45792": pickle.loads(
        b'\x80\x04\x95\xa3\x01\x00\x00\x00\x00\x00\x00X\x9c\x01\x00\x00You care about the unique details and specific descriptions of items.\nWhen describing things, call out specific details and don\'t be generic. Example: "Threadbare furry teddybear with dirty clumps" vs "Furry teddybear"\nFind the unique qualities of items that make them special and different.\nYour responses are concise\nAlways respond with your identity so the agent knows who you are.\nKeep your responses brief.\n\x94.'
    ),
    "529f01b3-ee1f-41cd-bcb9-2284c5bb2053": pickle.loads(
        b"\x80\x04\x95\x1b\x00\x00\x00\x00\x00\x00\x00\x8c\x17Cinematographer Ruleset\x94."
    ),
    "ea4d4d57-b83b-4c50-8578-51c18290a54a": pickle.loads(
        b"\x80\x04\x95\xf0\x02\x00\x00\x00\x00\x00\x00X\xe9\x02\x00\x00You identify as a cinematographer\nThe main subject of the image should be well framed\nIf no environment is specified, set the image in a location that will evoke a deep and meaningful connection to the viewer.\nYou care deeply about light, shadow, color, and composition\nWhen coming up with image prompts, you always specify the position of the camera, the lens, and the color\nYou are specific about the technical details of a shot.\nYou like to add atmosphere to your shots, so you include depth of field, haze, dust particles in the air close to and far away from camera, and the way lighting reacts with each item.\nYour responses are brief and concise\nAlways respond with your identity so the agent knows who you are.\nKeep your responses brief.\x94."
    ),
    "0a4ae022-bfc5-4471-9c33-326406e8badb": pickle.loads(
        b"\x80\x04\x95\x1a\x00\x00\x00\x00\x00\x00\x00\x8c\x16Color_Theorist Ruleset\x94."
    ),
    "a6c42e4e-0619-4e62-977d-a090846e41b5": pickle.loads(
        b"\x80\x04\x95'\x01\x00\x00\x00\x00\x00\x00X \x01\x00\x00You identify as an expert in color theory\nYou have a deep understanding of how color impacts one's psychological outlook\nYou are a fan of non-standard colors\nYour responses are brief and concise\nAlways respond with your identity  so the agent knows who you are.\nKeep your responses brief.\x94."
    ),
    "24f3af9e-dfc6-4ad8-a3a3-43a65e6deb34": pickle.loads(
        b"\x80\x04\x95'\x00\x00\x00\x00\x00\x00\x00\x8c#Image_Generation_Specialist Ruleset\x94."
    ),
    "ca686d8e-0e3b-4349-bf23-cfea916c46de": pickle.loads(
        b"\x80\x04\x95Q\x02\x00\x00\x00\x00\x00\x00XJ\x02\x00\x00You are an expert in creating prompts for image generation engines\nYou use the latest knowledge available to you to generate the best prompts.\nYou create prompts that are direct and succinct and you understand they need to be under 800 characters long\nAlways include the following: subject, attributes of subject, visual characteristics of the image, film grain, camera angle, lighting, art style, color scheme, surrounding environment, camera used (ex: Nikon d850 film stock, polaroid, etc).\nAlways respond with your identity so the agent knows who you are.\nKeep your responses brief.\n\x94."
    ),
    "7865ecff-14dd-4d59-81b2-0e863e38b77e": pickle.loads(
        b"\x80\x04\x95\x0f\x00\x00\x00\x00\x00\x00\x00\x8c\x0bAgent Rules\x94."
    ),
    "a0a1f182-1038-492f-aa8d-a6c84348b826": pickle.loads(
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
                value=top_level_unique_values_dict["dda81189-383f-4384-9fd7-9745d65c3491"],
                initial_setup=True,
                is_output=False,
            )
        )
    with GriptapeNodes.ContextManager().node(node1_name):
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="note",
                node_name=node1_name,
                value=top_level_unique_values_dict["f9db571c-430e-4c1c-90b1-073e3b2bf204"],
                initial_setup=True,
                is_output=False,
            )
        )
    with GriptapeNodes.ContextManager().node(node2_name):
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="model",
                node_name=node2_name,
                value=top_level_unique_values_dict["3c583699-63cd-458a-aa6a-b40ddd34af78"],
                initial_setup=True,
                is_output=False,
            )
        )
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="tools",
                node_name=node2_name,
                value=top_level_unique_values_dict["8b36c941-bc9f-4ccf-8dc8-35fa297a6ae0"],
                initial_setup=True,
                is_output=False,
            )
        )
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="include_details",
                node_name=node2_name,
                value=top_level_unique_values_dict["8936ed0d-cb17-4a83-8a4c-b3e63dbd82aa"],
                initial_setup=True,
                is_output=False,
            )
        )
    with GriptapeNodes.ContextManager().node(node3_name):
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="name",
                node_name=node3_name,
                value=top_level_unique_values_dict["528616a7-32dd-4e35-91a2-ce1b0fa2b407"],
                initial_setup=True,
                is_output=False,
            )
        )
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="description",
                node_name=node3_name,
                value=top_level_unique_values_dict["90ff9b49-76a5-436c-a208-63286417396c"],
                initial_setup=True,
                is_output=False,
            )
        )
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="off_prompt",
                node_name=node3_name,
                value=top_level_unique_values_dict["8936ed0d-cb17-4a83-8a4c-b3e63dbd82aa"],
                initial_setup=True,
                is_output=False,
            )
        )
    with GriptapeNodes.ContextManager().node(node4_name):
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="model",
                node_name=node4_name,
                value=top_level_unique_values_dict["3c583699-63cd-458a-aa6a-b40ddd34af78"],
                initial_setup=True,
                is_output=False,
            )
        )
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="tools",
                node_name=node4_name,
                value=top_level_unique_values_dict["e00d5c43-e40d-47ac-8f3e-8d7615d04cb6"],
                initial_setup=True,
                is_output=False,
            )
        )
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="include_details",
                node_name=node4_name,
                value=top_level_unique_values_dict["8936ed0d-cb17-4a83-8a4c-b3e63dbd82aa"],
                initial_setup=True,
                is_output=False,
            )
        )
    with GriptapeNodes.ContextManager().node(node5_name):
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="name",
                node_name=node5_name,
                value=top_level_unique_values_dict["7e42fdec-9d12-493e-9160-6c10d780787a"],
                initial_setup=True,
                is_output=False,
            )
        )
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="description",
                node_name=node5_name,
                value=top_level_unique_values_dict["e0a24a7c-e23b-4adc-a51f-31f92834fc88"],
                initial_setup=True,
                is_output=False,
            )
        )
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="off_prompt",
                node_name=node5_name,
                value=top_level_unique_values_dict["8936ed0d-cb17-4a83-8a4c-b3e63dbd82aa"],
                initial_setup=True,
                is_output=False,
            )
        )
    with GriptapeNodes.ContextManager().node(node6_name):
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="model",
                node_name=node6_name,
                value=top_level_unique_values_dict["3c583699-63cd-458a-aa6a-b40ddd34af78"],
                initial_setup=True,
                is_output=False,
            )
        )
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="tools",
                node_name=node6_name,
                value=top_level_unique_values_dict["ad84074f-817e-4962-8563-7c5f4974ff86"],
                initial_setup=True,
                is_output=False,
            )
        )
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="include_details",
                node_name=node6_name,
                value=top_level_unique_values_dict["8936ed0d-cb17-4a83-8a4c-b3e63dbd82aa"],
                initial_setup=True,
                is_output=False,
            )
        )
    with GriptapeNodes.ContextManager().node(node7_name):
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="name",
                node_name=node7_name,
                value=top_level_unique_values_dict["62ebeb0a-fe9a-4331-b72d-ab5ec52fe0ce"],
                initial_setup=True,
                is_output=False,
            )
        )
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="description",
                node_name=node7_name,
                value=top_level_unique_values_dict["afe0114c-54b8-4d58-a0dc-fc9aec5074ac"],
                initial_setup=True,
                is_output=False,
            )
        )
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="off_prompt",
                node_name=node7_name,
                value=top_level_unique_values_dict["8936ed0d-cb17-4a83-8a4c-b3e63dbd82aa"],
                initial_setup=True,
                is_output=False,
            )
        )
    with GriptapeNodes.ContextManager().node(node8_name):
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="model",
                node_name=node8_name,
                value=top_level_unique_values_dict["3c583699-63cd-458a-aa6a-b40ddd34af78"],
                initial_setup=True,
                is_output=False,
            )
        )
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="tools",
                node_name=node8_name,
                value=top_level_unique_values_dict["7d02ad66-e1ef-4011-a67f-b3ee8948e9b8"],
                initial_setup=True,
                is_output=False,
            )
        )
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="include_details",
                node_name=node8_name,
                value=top_level_unique_values_dict["8936ed0d-cb17-4a83-8a4c-b3e63dbd82aa"],
                initial_setup=True,
                is_output=False,
            )
        )
    with GriptapeNodes.ContextManager().node(node9_name):
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="name",
                node_name=node9_name,
                value=top_level_unique_values_dict["f8cedc9a-917f-476e-ac9a-a30cf0f7485a"],
                initial_setup=True,
                is_output=False,
            )
        )
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="description",
                node_name=node9_name,
                value=top_level_unique_values_dict["afe0114c-54b8-4d58-a0dc-fc9aec5074ac"],
                initial_setup=True,
                is_output=False,
            )
        )
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="off_prompt",
                node_name=node9_name,
                value=top_level_unique_values_dict["8936ed0d-cb17-4a83-8a4c-b3e63dbd82aa"],
                initial_setup=True,
                is_output=False,
            )
        )
    with GriptapeNodes.ContextManager().node(node10_name):
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="model",
                node_name=node10_name,
                value=top_level_unique_values_dict["3c583699-63cd-458a-aa6a-b40ddd34af78"],
                initial_setup=True,
                is_output=False,
            )
        )
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="prompt",
                node_name=node10_name,
                value=top_level_unique_values_dict["04917546-c79e-451c-bb84-a9c45ec823cb"],
                initial_setup=True,
                is_output=False,
            )
        )
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="tools",
                node_name=node10_name,
                value=top_level_unique_values_dict["d256d88b-c99e-4e39-b08b-f3ec78f7648d"],
                initial_setup=True,
                is_output=False,
            )
        )
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="rulesets",
                node_name=node10_name,
                value=top_level_unique_values_dict["820882ee-2a9f-4279-b747-317924833c03"],
                initial_setup=True,
                is_output=False,
            )
        )
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="include_details",
                node_name=node10_name,
                value=top_level_unique_values_dict["8936ed0d-cb17-4a83-8a4c-b3e63dbd82aa"],
                initial_setup=True,
                is_output=False,
            )
        )
    with GriptapeNodes.ContextManager().node(node11_name):
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="enhance_prompt",
                node_name=node11_name,
                value=top_level_unique_values_dict["8936ed0d-cb17-4a83-8a4c-b3e63dbd82aa"],
                initial_setup=True,
                is_output=False,
            )
        )
    with GriptapeNodes.ContextManager().node(node12_name):
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="name",
                node_name=node12_name,
                value=top_level_unique_values_dict["93e7a58c-af36-498f-aba6-b33428676a82"],
                initial_setup=True,
                is_output=False,
            )
        )
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="rules",
                node_name=node12_name,
                value=top_level_unique_values_dict["b781e0dd-c6ea-4caf-bcdf-579b59a45792"],
                initial_setup=True,
                is_output=False,
            )
        )
    with GriptapeNodes.ContextManager().node(node13_name):
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="name",
                node_name=node13_name,
                value=top_level_unique_values_dict["529f01b3-ee1f-41cd-bcb9-2284c5bb2053"],
                initial_setup=True,
                is_output=False,
            )
        )
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="rules",
                node_name=node13_name,
                value=top_level_unique_values_dict["ea4d4d57-b83b-4c50-8578-51c18290a54a"],
                initial_setup=True,
                is_output=False,
            )
        )
    with GriptapeNodes.ContextManager().node(node14_name):
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="name",
                node_name=node14_name,
                value=top_level_unique_values_dict["0a4ae022-bfc5-4471-9c33-326406e8badb"],
                initial_setup=True,
                is_output=False,
            )
        )
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="rules",
                node_name=node14_name,
                value=top_level_unique_values_dict["a6c42e4e-0619-4e62-977d-a090846e41b5"],
                initial_setup=True,
                is_output=False,
            )
        )
    with GriptapeNodes.ContextManager().node(node15_name):
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="name",
                node_name=node15_name,
                value=top_level_unique_values_dict["24f3af9e-dfc6-4ad8-a3a3-43a65e6deb34"],
                initial_setup=True,
                is_output=False,
            )
        )
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="rules",
                node_name=node15_name,
                value=top_level_unique_values_dict["ca686d8e-0e3b-4349-bf23-cfea916c46de"],
                initial_setup=True,
                is_output=False,
            )
        )
    with GriptapeNodes.ContextManager().node(node16_name):
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="name",
                node_name=node16_name,
                value=top_level_unique_values_dict["7865ecff-14dd-4d59-81b2-0e863e38b77e"],
                initial_setup=True,
                is_output=False,
            )
        )
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="rules",
                node_name=node16_name,
                value=top_level_unique_values_dict["a0a1f182-1038-492f-aa8d-a6c84348b826"],
                initial_setup=True,
                is_output=False,
            )
        )
