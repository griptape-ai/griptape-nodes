# /// script
# dependencies = []
#
# [tool.griptape-nodes]
# name = "coordinating_agents"
# schema_version = "0.11.0"
# engine_version_created_with = "0.60.0"
# node_libraries_referenced = [["Griptape Nodes Library", "0.50.0"]]
# node_types_used = [["Griptape Nodes Library", "Agent"], ["Griptape Nodes Library", "DisplayText"], ["Griptape Nodes Library", "MergeTexts"], ["Griptape Nodes Library", "Note"]]
# description = "Multiple agents with different jobs."
# image = "https://raw.githubusercontent.com/griptape-ai/griptape-nodes/refs/heads/main/libraries/griptape_nodes_library/workflows/templates/thumbnail_coordinating_agents.webp"
# is_griptape_provided = true
# is_template = true
# creation_date = 2025-10-22T19:03:54.190207Z
# last_modified_date = 2025-10-22T19:03:54.208049Z
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
    context_manager.push_workflow(workflow_name="coordinating_agents")

"""
1. We've collated all of the unique parameter values into a dictionary so that we do not have to duplicate them.
   This minimizes the size of the code, especially for large objects like serialized image files.
2. We're using a prefix so that it's clear which Flow these values are associated with.
3. The values are serialized using pickle, which is a binary format. This makes them harder to read, but makes
   them consistently save and load. It allows us to serialize complex objects like custom classes, which otherwise
   would be difficult to serialize.
"""
top_level_unique_values_dict = {
    "efc9d5ce-6ae5-4795-bcad-4864333c010c": pickle.loads(
        b'\x80\x04\x95\x98\x01\x00\x00\x00\x00\x00\x00X\x91\x01\x00\x00This workflow serves as the lesson material for the tutorial located at:\n\nhttps://docs.griptapenodes.com/en/stable/ftue/02_coordinating_agents/FTUE_02_coordinating_agents/\n\nThe concepts covered are:\n\n- Multi-agent workflows where agents have different "jobs"\n- How to use Merge Text nodes to better pass information between agents\n- Understanding execution chains to control the order things happen in\x94.'
    ),
    "ce2b1405-a2c5-4be8-9162-85ac5575904c": pickle.loads(
        b"\x80\x04\x95\xf6\x00\x00\x00\x00\x00\x00\x00\x8c\xf2If you're following along with our Getting Started tutorials, check out the next suggested template: Compare_Prompts.\n\nLoad the next tutorial page here:\nhttps://docs.griptapenodes.com/en/stable/ftue/03_compare_prompts/FTUE_03_compare_prompts/\x94."
    ),
    "cabf603c-6f08-458a-8212-87c004c9d0ea": pickle.loads(
        b'\x80\x04\x95\xf2\x03\x00\x00\x00\x00\x00\x00}\x94(\x8c\x04type\x94\x8c\x05Agent\x94\x8c\x08rulesets\x94]\x94\x8c\x05rules\x94]\x94\x8c\x02id\x94\x8c 3610082a55f048f6a70755fc5ad5a791\x94\x8c\x13conversation_memory\x94}\x94(h\x01\x8c\x12ConversationMemory\x94\x8c\x04runs\x94]\x94}\x94(h\x01\x8c\x03Run\x94h\x07\x8c 8151c6b54c184f4fb06a244b8f2614a3\x94\x8c\x04meta\x94N\x8c\x05input\x94}\x94(h\x01\x8c\x0cTextArtifact\x94h\x07\x8c e98fb473558c465b8eaf202db77884bf\x94\x8c\treference\x94Nh\x11}\x94\x8c\x04name\x94h\x15\x8c\x05value\x94\x8c"Write me a 4-line story in Spanish\x94u\x8c\x06output\x94}\x94(h\x01h\x14h\x07\x8c 4e8eaa1eeed14a818a13389b181c34fb\x94h\x16Nh\x11}\x94\x8c\x0fis_react_prompt\x94\x89sh\x18h\x1dh\x19\x8c\xadBeneath the old oak, a buried key lay,  \nUnlocking a chest from a forgotten day.  \nInside, a note: "The treasure is you,"  \nAnd the seeker smiled, for they knew it was true.\x94uuah\x11}\x94\x8c\x08max_runs\x94Nu\x8c\x1cconversation_memory_strategy\x94\x8c\rper_structure\x94\x8c\x05tasks\x94]\x94}\x94(h\x01\x8c\nPromptTask\x94h\x03]\x94h\x05]\x94h\x07\x8c 0085d4e037264bcb8eefd7c1ce1d6d87\x94\x8c\x05state\x94\x8c\x0eState.FINISHED\x94\x8c\nparent_ids\x94]\x94\x8c\tchild_ids\x94]\x94\x8c\x17max_meta_memory_entries\x94K\x14\x8c\x07context\x94}\x94\x8c\rprompt_driver\x94}\x94(h\x01\x8c\x19GriptapeCloudPromptDriver\x94\x8c\x0btemperature\x94G?\xb9\x99\x99\x99\x99\x99\x9a\x8c\nmax_tokens\x94N\x8c\x06stream\x94\x88\x8c\x0cextra_params\x94}\x94\x8c\x1astructured_output_strategy\x94\x8c\x06native\x94u\x8c\x05tools\x94]\x94\x8c\x0cmax_subtasks\x94K\x14uau.'
    ),
    "f376f5b1-fccd-42f3-83f4-fca94aa5c14e": pickle.loads(
        b'\x80\x04\x95&\x00\x00\x00\x00\x00\x00\x00\x8c"Write me a 4-line story in Spanish\x94.'
    ),
    "27b9bebd-3025-4515-9119-f2f3e456bed0": pickle.loads(b"\x80\x04]\x94."),
    "d75d1527-fd5c-479f-8d72-43086ea4aa64": pickle.loads(b"\x80\x04]\x94."),
    "ad8461fd-7d8e-4ab9-8ff9-c9ce218acfe5": pickle.loads(
        b"\x80\x04\x95\x9e\x00\x00\x00\x00\x00\x00\x00\x8c\x9aBajo la luna, el r\xc3\xado cant\xc3\xb3,  \nUn secreto antiguo en su agua dej\xc3\xb3.  \nLa ni\xc3\xb1a lo escuch\xc3\xb3 y empez\xc3\xb3 a so\xc3\xb1ar,  \nQue el mundo era suyo, listo para amar.\n\x94."
    ),
    "05eec6dd-9f24-499e-8639-a0bbabbe2a97": pickle.loads(
        b'\x80\x04\x95\xa4\x04\x00\x00\x00\x00\x00\x00}\x94(\x8c\x04type\x94\x8c\x05Agent\x94\x8c\x08rulesets\x94]\x94\x8c\x05rules\x94]\x94\x8c\x02id\x94\x8c e954ec3c2831431abfbd789bd278b1c0\x94\x8c\x13conversation_memory\x94}\x94(h\x01\x8c\x12ConversationMemory\x94\x8c\x04runs\x94]\x94}\x94(h\x01\x8c\x03Run\x94h\x07\x8c 6ea17a0c803a4bacb90c1c07521a1131\x94\x8c\x04meta\x94N\x8c\x05input\x94}\x94(h\x01\x8c\x0cTextArtifact\x94h\x07\x8c f31d526077e94062a84ae01655b2b6c9\x94\x8c\treference\x94Nh\x11}\x94\x8c\x04name\x94h\x15\x8c\x05value\x94\x8c\xc6rewrite this in english\n\nBeneath the old oak, a buried key lay,  \nUnlocking a chest from a forgotten day.  \nInside, a note: "The treasure is you,"  \nAnd the seeker smiled, for they knew it was true.\x94u\x8c\x06output\x94}\x94(h\x01h\x14h\x07\x8c 2762bd49ac7b4d9790a9cbac1b8ecb58\x94h\x16Nh\x11}\x94\x8c\x0fis_react_prompt\x94\x89sh\x18h\x1dh\x19\x8c\xbbBajo el viejo roble, una llave enterrada yac\xc3\xada,  \nAbriendo un cofre de una \xc3\xa9poca olvidada.  \nDentro, una nota: "El tesoro eres t\xc3\xba,"  \nY el buscador sonri\xc3\xb3, pues sab\xc3\xada que era verdad.\x94uuah\x11}\x94\x8c\x08max_runs\x94Nu\x8c\x1cconversation_memory_strategy\x94\x8c\rper_structure\x94\x8c\x05tasks\x94]\x94}\x94(h\x01\x8c\nPromptTask\x94h\x03]\x94h\x05]\x94h\x07\x8c e6cb8ec1dd6848239afd5d0b1a7abff9\x94\x8c\x05state\x94\x8c\x0eState.FINISHED\x94\x8c\nparent_ids\x94]\x94\x8c\tchild_ids\x94]\x94\x8c\x17max_meta_memory_entries\x94K\x14\x8c\x07context\x94}\x94\x8c\rprompt_driver\x94}\x94(h\x01\x8c\x19GriptapeCloudPromptDriver\x94\x8c\x0btemperature\x94G?\xb9\x99\x99\x99\x99\x99\x9a\x8c\nmax_tokens\x94N\x8c\x06stream\x94\x88\x8c\x0cextra_params\x94}\x94\x8c\x1astructured_output_strategy\x94\x8c\x06native\x94u\x8c\x05tools\x94]\x94\x8c\x0cmax_subtasks\x94K\x14uau.'
    ),
    "3d67ebcd-a1be-4ff2-83e2-af0935cfccb4": pickle.loads(
        b"\x80\x04\x95\xb6\x00\x00\x00\x00\x00\x00\x00\x8c\xb2rewrite this in english\n\nBajo la luna, el r\xc3\xado cant\xc3\xb3,  \nUn secreto antiguo en su agua dej\xc3\xb3.  \nLa ni\xc3\xb1a lo escuch\xc3\xb3 y empez\xc3\xb3 a so\xc3\xb1ar,  \nQue el mundo era suyo, listo para amar.\x94."
    ),
    "76546260-a95c-47df-8d18-9940d8a9a009": pickle.loads(b"\x80\x04]\x94."),
    "b146ffd2-8111-4c79-b6d3-1028082a8f08": pickle.loads(b"\x80\x04]\x94."),
    "d16cc368-50da-4a64-a2a0-3ec910d0ade5": pickle.loads(
        b"\x80\x04\x95\xa4\x00\x00\x00\x00\x00\x00\x00\x8c\xa0Beneath the moon, the river sang,  \nAn ancient secret in its waters it rang.  \nThe girl heard it and began to dream,  \nThat the world was hers, ready to gleam.\n\x94."
    ),
    "454ffd60-d892-4d63-87ca-9811de7eae08": pickle.loads(
        b"\x80\x04\x95\x1b\x00\x00\x00\x00\x00\x00\x00\x8c\x17rewrite this in english\x94."
    ),
    "cec8f8a6-557e-45e5-8484-429b5c8a9dea": pickle.loads(
        b"\x80\x04\x95\x06\x00\x00\x00\x00\x00\x00\x00\x8c\x02\n\n\x94."
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
                "position": {"x": -550, "y": -400},
                "size": {"width": 1000, "height": 350},
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
                "position": {"x": 1700, "y": 500},
                "size": {"width": 1100, "height": 232},
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
            node_name="spanish_story",
            metadata={
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
                "category": "Agent",
                "position": {"x": -535, "y": 0},
            },
            initial_setup=True,
        )
    ).node_name
    node3_name = GriptapeNodes.handle_request(
        CreateNodeRequest(
            node_type="Agent",
            specific_library_name="Griptape Nodes Library",
            node_name="to_english",
            metadata={
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
                "category": "Agent",
                "position": {"x": 635, "y": 0},
                "showaddparameter": False,
                "size": {"width": 400, "height": 703},
            },
            initial_setup=True,
        )
    ).node_name
    node4_name = GriptapeNodes.handle_request(
        CreateNodeRequest(
            node_type="MergeTexts",
            specific_library_name="Griptape Nodes Library",
            node_name="prompt_header",
            metadata={
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
                "category": "Text",
                "position": {"x": 40, "y": 200},
                "showaddparameter": False,
                "size": {"width": 400, "height": 568},
            },
            initial_setup=True,
        )
    ).node_name
    node5_name = GriptapeNodes.handle_request(
        CreateNodeRequest(
            node_type="DisplayText",
            specific_library_name="Griptape Nodes Library",
            node_name="english_story",
            metadata={
                "library_node_metadata": NodeMetadata(
                    category="text",
                    description="DisplayText node",
                    display_name="Display Text",
                    tags=None,
                    icon=None,
                    color=None,
                    group="display",
                    deprecation=None,
                ),
                "library": "Griptape Nodes Library",
                "node_type": "DisplayText",
                "category": "Text",
                "position": {"x": 1200, "y": 200},
                "size": {"width": 475, "height": 265},
            },
            initial_setup=True,
        )
    ).node_name
    GriptapeNodes.handle_request(
        CreateConnectionRequest(
            source_node_name=node2_name,
            source_parameter_name="exec_out",
            target_node_name=node3_name,
            target_parameter_name="exec_in",
            initial_setup=True,
        )
    )
    GriptapeNodes.handle_request(
        CreateConnectionRequest(
            source_node_name=node2_name,
            source_parameter_name="output",
            target_node_name=node4_name,
            target_parameter_name="input_2",
            initial_setup=True,
        )
    )
    GriptapeNodes.handle_request(
        CreateConnectionRequest(
            source_node_name=node3_name,
            source_parameter_name="output",
            target_node_name=node5_name,
            target_parameter_name="text",
            initial_setup=True,
        )
    )
    GriptapeNodes.handle_request(
        CreateConnectionRequest(
            source_node_name=node4_name,
            source_parameter_name="output",
            target_node_name=node3_name,
            target_parameter_name="prompt",
            initial_setup=True,
        )
    )
    with GriptapeNodes.ContextManager().node(node0_name):
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="note",
                node_name=node0_name,
                value=top_level_unique_values_dict["efc9d5ce-6ae5-4795-bcad-4864333c010c"],
                initial_setup=True,
                is_output=False,
            )
        )
    with GriptapeNodes.ContextManager().node(node1_name):
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="note",
                node_name=node1_name,
                value=top_level_unique_values_dict["ce2b1405-a2c5-4be8-9162-85ac5575904c"],
                initial_setup=True,
                is_output=False,
            )
        )
    with GriptapeNodes.ContextManager().node(node2_name):
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="agent",
                node_name=node2_name,
                value=top_level_unique_values_dict["cabf603c-6f08-458a-8212-87c004c9d0ea"],
                initial_setup=True,
                is_output=False,
            )
        )
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="prompt",
                node_name=node2_name,
                value=top_level_unique_values_dict["f376f5b1-fccd-42f3-83f4-fca94aa5c14e"],
                initial_setup=True,
                is_output=False,
            )
        )
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="tools",
                node_name=node2_name,
                value=top_level_unique_values_dict["27b9bebd-3025-4515-9119-f2f3e456bed0"],
                initial_setup=True,
                is_output=False,
            )
        )
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="rulesets",
                node_name=node2_name,
                value=top_level_unique_values_dict["d75d1527-fd5c-479f-8d72-43086ea4aa64"],
                initial_setup=True,
                is_output=False,
            )
        )
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="output",
                node_name=node2_name,
                value=top_level_unique_values_dict["ad8461fd-7d8e-4ab9-8ff9-c9ce218acfe5"],
                initial_setup=True,
                is_output=False,
            )
        )
    with GriptapeNodes.ContextManager().node(node3_name):
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="agent",
                node_name=node3_name,
                value=top_level_unique_values_dict["05eec6dd-9f24-499e-8639-a0bbabbe2a97"],
                initial_setup=True,
                is_output=False,
            )
        )
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="prompt",
                node_name=node3_name,
                value=top_level_unique_values_dict["3d67ebcd-a1be-4ff2-83e2-af0935cfccb4"],
                initial_setup=True,
                is_output=False,
            )
        )
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="tools",
                node_name=node3_name,
                value=top_level_unique_values_dict["76546260-a95c-47df-8d18-9940d8a9a009"],
                initial_setup=True,
                is_output=False,
            )
        )
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="rulesets",
                node_name=node3_name,
                value=top_level_unique_values_dict["b146ffd2-8111-4c79-b6d3-1028082a8f08"],
                initial_setup=True,
                is_output=False,
            )
        )
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="output",
                node_name=node3_name,
                value=top_level_unique_values_dict["d16cc368-50da-4a64-a2a0-3ec910d0ade5"],
                initial_setup=True,
                is_output=False,
            )
        )
    with GriptapeNodes.ContextManager().node(node4_name):
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="input_1",
                node_name=node4_name,
                value=top_level_unique_values_dict["454ffd60-d892-4d63-87ca-9811de7eae08"],
                initial_setup=True,
                is_output=False,
            )
        )
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="input_2",
                node_name=node4_name,
                value=top_level_unique_values_dict["ad8461fd-7d8e-4ab9-8ff9-c9ce218acfe5"],
                initial_setup=True,
                is_output=False,
            )
        )
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="merge_string",
                node_name=node4_name,
                value=top_level_unique_values_dict["cec8f8a6-557e-45e5-8484-429b5c8a9dea"],
                initial_setup=True,
                is_output=False,
            )
        )
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="output",
                node_name=node4_name,
                value=top_level_unique_values_dict["3d67ebcd-a1be-4ff2-83e2-af0935cfccb4"],
                initial_setup=True,
                is_output=False,
            )
        )
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="output",
                node_name=node4_name,
                value=top_level_unique_values_dict["3d67ebcd-a1be-4ff2-83e2-af0935cfccb4"],
                initial_setup=True,
                is_output=True,
            )
        )
    with GriptapeNodes.ContextManager().node(node5_name):
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="text",
                node_name=node5_name,
                value=top_level_unique_values_dict["d16cc368-50da-4a64-a2a0-3ec910d0ade5"],
                initial_setup=True,
                is_output=False,
            )
        )
