# /// script
# dependencies = []
#
# [tool.griptape-nodes]
# name = "coordinating_agents"
# schema_version = "0.4.0"
# engine_version_created_with = "0.41.0"
# node_libraries_referenced = [["Griptape Nodes Library", "0.41.0"]]
# description = "Multiple agents with different jobs."
# image = "https://raw.githubusercontent.com/griptape-ai/griptape-nodes/refs/heads/main/libraries/griptape_nodes_library/workflows/templates/thumbnail_coordinating_agents.webp"
# is_griptape_provided = true
# is_template = true
# creation_date = 2025-05-01T02:00:00.000000+00:00
# last_modified_date = 2025-07-07T13:37:59.421997-07:00
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
    context_manager.push_workflow(workflow_name="coordinating_agents_1")

"""
1. We've collated all of the unique parameter values into a dictionary so that we do not have to duplicate them.
   This minimizes the size of the code, especially for large objects like serialized image files.
2. We're using a prefix so that it's clear which Flow these values are associated with.
3. The values are serialized using pickle, which is a binary format. This makes them harder to read, but makes
   them consistently save and load. It allows us to serialize complex objects like custom classes, which otherwise
   would be difficult to serialize.
"""
top_level_unique_values_dict = {
    "add20ee2-713f-4e9f-9393-439f6de5b670": pickle.loads(
        b'\x80\x04\x95\x98\x01\x00\x00\x00\x00\x00\x00X\x91\x01\x00\x00This workflow serves as the lesson material for the tutorial located at:\n\nhttps://docs.griptapenodes.com/en/stable/ftue/02_coordinating_agents/FTUE_02_coordinating_agents/\n\nThe concepts covered are:\n\n- Multi-agent workflows where agents have different "jobs"\n- How to use Merge Text nodes to better pass information between agents\n- Understanding execution chains to control the order things happen in\x94.'
    ),
    "d0faef6c-390e-4e75-b75c-a289d70fbcbb": pickle.loads(
        b"\x80\x04\x95\xf6\x00\x00\x00\x00\x00\x00\x00\x8c\xf2If you're following along with our Getting Started tutorials, check out the next suggested template: Compare_Prompts.\n\nLoad the next tutorial page here:\nhttps://docs.griptapenodes.com/en/stable/ftue/03_compare_prompts/FTUE_03_compare_prompts/\x94."
    ),
    "699d7e27-b40d-49be-b406-7ab396449881": pickle.loads(
        b'\x80\x04\x95\xf2\x03\x00\x00\x00\x00\x00\x00}\x94(\x8c\x04type\x94\x8c\x05Agent\x94\x8c\x08rulesets\x94]\x94\x8c\x05rules\x94]\x94\x8c\x02id\x94\x8c 3610082a55f048f6a70755fc5ad5a791\x94\x8c\x13conversation_memory\x94}\x94(h\x01\x8c\x12ConversationMemory\x94\x8c\x04runs\x94]\x94}\x94(h\x01\x8c\x03Run\x94h\x07\x8c 8151c6b54c184f4fb06a244b8f2614a3\x94\x8c\x04meta\x94N\x8c\x05input\x94}\x94(h\x01\x8c\x0cTextArtifact\x94h\x07\x8c e98fb473558c465b8eaf202db77884bf\x94\x8c\treference\x94Nh\x11}\x94\x8c\x04name\x94h\x15\x8c\x05value\x94\x8c"Write me a 4-line story in Spanish\x94u\x8c\x06output\x94}\x94(h\x01h\x14h\x07\x8c 4e8eaa1eeed14a818a13389b181c34fb\x94h\x16Nh\x11}\x94\x8c\x0fis_react_prompt\x94\x89sh\x18h\x1dh\x19\x8c\xadBeneath the old oak, a buried key lay,  \nUnlocking a chest from a forgotten day.  \nInside, a note: "The treasure is you,"  \nAnd the seeker smiled, for they knew it was true.\x94uuah\x11}\x94\x8c\x08max_runs\x94Nu\x8c\x1cconversation_memory_strategy\x94\x8c\rper_structure\x94\x8c\x05tasks\x94]\x94}\x94(h\x01\x8c\nPromptTask\x94h\x03]\x94h\x05]\x94h\x07\x8c 0085d4e037264bcb8eefd7c1ce1d6d87\x94\x8c\x05state\x94\x8c\x0eState.FINISHED\x94\x8c\nparent_ids\x94]\x94\x8c\tchild_ids\x94]\x94\x8c\x17max_meta_memory_entries\x94K\x14\x8c\x07context\x94}\x94\x8c\rprompt_driver\x94}\x94(h\x01\x8c\x19GriptapeCloudPromptDriver\x94\x8c\x0btemperature\x94G?\xb9\x99\x99\x99\x99\x99\x9a\x8c\nmax_tokens\x94N\x8c\x06stream\x94\x88\x8c\x0cextra_params\x94}\x94\x8c\x1astructured_output_strategy\x94\x8c\x06native\x94u\x8c\x05tools\x94]\x94\x8c\x0cmax_subtasks\x94K\x14uau.'
    ),
    "aead598a-274a-45ee-a943-155af83993bf": pickle.loads(
        b'\x80\x04\x95&\x00\x00\x00\x00\x00\x00\x00\x8c"Write me a 4-line story in Spanish\x94.'
    ),
    "a4a2a557-2a35-4927-8a8c-6b6651589b45": pickle.loads(b"\x80\x04]\x94."),
    "d58b0dd2-21fa-44ab-a4c6-ce060e753cba": pickle.loads(b"\x80\x04]\x94."),
    "aca687c0-630d-4a8f-b823-397ec0dc18df": pickle.loads(
        b"\x80\x04\x95\x9e\x00\x00\x00\x00\x00\x00\x00\x8c\x9aBajo la luna, el r\xc3\xado cant\xc3\xb3,  \nUn secreto antiguo en su agua dej\xc3\xb3.  \nLa ni\xc3\xb1a lo escuch\xc3\xb3 y empez\xc3\xb3 a so\xc3\xb1ar,  \nQue el mundo era suyo, listo para amar.\n\x94."
    ),
    "58b249e3-7aac-48eb-9011-0674b36e4925": pickle.loads(
        b'\x80\x04\x95\xa4\x04\x00\x00\x00\x00\x00\x00}\x94(\x8c\x04type\x94\x8c\x05Agent\x94\x8c\x08rulesets\x94]\x94\x8c\x05rules\x94]\x94\x8c\x02id\x94\x8c e954ec3c2831431abfbd789bd278b1c0\x94\x8c\x13conversation_memory\x94}\x94(h\x01\x8c\x12ConversationMemory\x94\x8c\x04runs\x94]\x94}\x94(h\x01\x8c\x03Run\x94h\x07\x8c 6ea17a0c803a4bacb90c1c07521a1131\x94\x8c\x04meta\x94N\x8c\x05input\x94}\x94(h\x01\x8c\x0cTextArtifact\x94h\x07\x8c f31d526077e94062a84ae01655b2b6c9\x94\x8c\treference\x94Nh\x11}\x94\x8c\x04name\x94h\x15\x8c\x05value\x94\x8c\xc6rewrite this in english\n\nBeneath the old oak, a buried key lay,  \nUnlocking a chest from a forgotten day.  \nInside, a note: "The treasure is you,"  \nAnd the seeker smiled, for they knew it was true.\x94u\x8c\x06output\x94}\x94(h\x01h\x14h\x07\x8c 2762bd49ac7b4d9790a9cbac1b8ecb58\x94h\x16Nh\x11}\x94\x8c\x0fis_react_prompt\x94\x89sh\x18h\x1dh\x19\x8c\xbbBajo el viejo roble, una llave enterrada yac\xc3\xada,  \nAbriendo un cofre de una \xc3\xa9poca olvidada.  \nDentro, una nota: "El tesoro eres t\xc3\xba,"  \nY el buscador sonri\xc3\xb3, pues sab\xc3\xada que era verdad.\x94uuah\x11}\x94\x8c\x08max_runs\x94Nu\x8c\x1cconversation_memory_strategy\x94\x8c\rper_structure\x94\x8c\x05tasks\x94]\x94}\x94(h\x01\x8c\nPromptTask\x94h\x03]\x94h\x05]\x94h\x07\x8c e6cb8ec1dd6848239afd5d0b1a7abff9\x94\x8c\x05state\x94\x8c\x0eState.FINISHED\x94\x8c\nparent_ids\x94]\x94\x8c\tchild_ids\x94]\x94\x8c\x17max_meta_memory_entries\x94K\x14\x8c\x07context\x94}\x94\x8c\rprompt_driver\x94}\x94(h\x01\x8c\x19GriptapeCloudPromptDriver\x94\x8c\x0btemperature\x94G?\xb9\x99\x99\x99\x99\x99\x9a\x8c\nmax_tokens\x94N\x8c\x06stream\x94\x88\x8c\x0cextra_params\x94}\x94\x8c\x1astructured_output_strategy\x94\x8c\x06native\x94u\x8c\x05tools\x94]\x94\x8c\x0cmax_subtasks\x94K\x14uau.'
    ),
    "7dfbcb97-3adc-4ac8-942d-bea1eebc967e": pickle.loads(
        b"\x80\x04\x95\xb6\x00\x00\x00\x00\x00\x00\x00\x8c\xb2rewrite this in english\n\nBajo la luna, el r\xc3\xado cant\xc3\xb3,  \nUn secreto antiguo en su agua dej\xc3\xb3.  \nLa ni\xc3\xb1a lo escuch\xc3\xb3 y empez\xc3\xb3 a so\xc3\xb1ar,  \nQue el mundo era suyo, listo para amar.\x94."
    ),
    "27b1a674-ee54-417f-8658-2ed8bed2824c": pickle.loads(b"\x80\x04]\x94."),
    "ca6c4074-d38e-41cf-964e-881e4f251923": pickle.loads(b"\x80\x04]\x94."),
    "78d6973d-5bd4-446c-a603-dbf57b58fdfb": pickle.loads(
        b"\x80\x04\x95\xa4\x00\x00\x00\x00\x00\x00\x00\x8c\xa0Beneath the moon, the river sang,  \nAn ancient secret in its waters it rang.  \nThe girl heard it and began to dream,  \nThat the world was hers, ready to gleam.\n\x94."
    ),
    "0d7be787-e82a-4afa-aae1-70552b9c610d": pickle.loads(
        b"\x80\x04\x95\x1b\x00\x00\x00\x00\x00\x00\x00\x8c\x17rewrite this in english\x94."
    ),
    "63d5f571-387c-41c2-9513-95decc5b2001": pickle.loads(
        b"\x80\x04\x95\x06\x00\x00\x00\x00\x00\x00\x00\x8c\x02\n\n\x94."
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
                "position": {"x": -550, "y": -400},
                "size": {"width": 1000, "height": 350},
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
                "position": {"x": 1700, "y": 500},
                "size": {"width": 1100, "height": 232},
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
            node_name="spanish_story",
            metadata={
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
                "category": "Agent",
                "position": {"x": -535, "y": 0},
            },
            initial_setup=True,
        )
    ).node_name
    with GriptapeNodes.ContextManager().node(node2_name):
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
                    group=None,
                ),
                "library": "Griptape Nodes Library",
                "node_type": "Agent",
                "category": "Agent",
                "position": {"x": 635, "y": 0},
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
                    group="edit",
                ),
                "library": "Griptape Nodes Library",
                "node_type": "MergeTexts",
                "category": "Text",
                "position": {"x": 40, "y": 200},
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
                    group="general",
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
            value=top_level_unique_values_dict["add20ee2-713f-4e9f-9393-439f6de5b670"],
            initial_setup=True,
            is_output=False,
        )
    )

with GriptapeNodes.ContextManager().node(node1_name):
    GriptapeNodes.handle_request(
        SetParameterValueRequest(
            parameter_name="note",
            node_name=node1_name,
            value=top_level_unique_values_dict["d0faef6c-390e-4e75-b75c-a289d70fbcbb"],
            initial_setup=True,
            is_output=False,
        )
    )

with GriptapeNodes.ContextManager().node(node2_name):
    GriptapeNodes.handle_request(
        SetParameterValueRequest(
            parameter_name="agent",
            node_name=node2_name,
            value=top_level_unique_values_dict["699d7e27-b40d-49be-b406-7ab396449881"],
            initial_setup=True,
            is_output=False,
        )
    )
    GriptapeNodes.handle_request(
        SetParameterValueRequest(
            parameter_name="prompt",
            node_name=node2_name,
            value=top_level_unique_values_dict["aead598a-274a-45ee-a943-155af83993bf"],
            initial_setup=True,
            is_output=False,
        )
    )
    GriptapeNodes.handle_request(
        SetParameterValueRequest(
            parameter_name="tools",
            node_name=node2_name,
            value=top_level_unique_values_dict["a4a2a557-2a35-4927-8a8c-6b6651589b45"],
            initial_setup=True,
            is_output=False,
        )
    )
    GriptapeNodes.handle_request(
        SetParameterValueRequest(
            parameter_name="rulesets",
            node_name=node2_name,
            value=top_level_unique_values_dict["d58b0dd2-21fa-44ab-a4c6-ce060e753cba"],
            initial_setup=True,
            is_output=False,
        )
    )
    GriptapeNodes.handle_request(
        SetParameterValueRequest(
            parameter_name="output",
            node_name=node2_name,
            value=top_level_unique_values_dict["aca687c0-630d-4a8f-b823-397ec0dc18df"],
            initial_setup=True,
            is_output=False,
        )
    )

with GriptapeNodes.ContextManager().node(node3_name):
    GriptapeNodes.handle_request(
        SetParameterValueRequest(
            parameter_name="agent",
            node_name=node3_name,
            value=top_level_unique_values_dict["58b249e3-7aac-48eb-9011-0674b36e4925"],
            initial_setup=True,
            is_output=False,
        )
    )
    GriptapeNodes.handle_request(
        SetParameterValueRequest(
            parameter_name="prompt",
            node_name=node3_name,
            value=top_level_unique_values_dict["7dfbcb97-3adc-4ac8-942d-bea1eebc967e"],
            initial_setup=True,
            is_output=False,
        )
    )
    GriptapeNodes.handle_request(
        SetParameterValueRequest(
            parameter_name="tools",
            node_name=node3_name,
            value=top_level_unique_values_dict["27b1a674-ee54-417f-8658-2ed8bed2824c"],
            initial_setup=True,
            is_output=False,
        )
    )
    GriptapeNodes.handle_request(
        SetParameterValueRequest(
            parameter_name="rulesets",
            node_name=node3_name,
            value=top_level_unique_values_dict["ca6c4074-d38e-41cf-964e-881e4f251923"],
            initial_setup=True,
            is_output=False,
        )
    )
    GriptapeNodes.handle_request(
        SetParameterValueRequest(
            parameter_name="output",
            node_name=node3_name,
            value=top_level_unique_values_dict["78d6973d-5bd4-446c-a603-dbf57b58fdfb"],
            initial_setup=True,
            is_output=False,
        )
    )

with GriptapeNodes.ContextManager().node(node4_name):
    GriptapeNodes.handle_request(
        SetParameterValueRequest(
            parameter_name="input_1",
            node_name=node4_name,
            value=top_level_unique_values_dict["0d7be787-e82a-4afa-aae1-70552b9c610d"],
            initial_setup=True,
            is_output=False,
        )
    )
    GriptapeNodes.handle_request(
        SetParameterValueRequest(
            parameter_name="input_2",
            node_name=node4_name,
            value=top_level_unique_values_dict["aca687c0-630d-4a8f-b823-397ec0dc18df"],
            initial_setup=True,
            is_output=False,
        )
    )
    GriptapeNodes.handle_request(
        SetParameterValueRequest(
            parameter_name="merge_string",
            node_name=node4_name,
            value=top_level_unique_values_dict["63d5f571-387c-41c2-9513-95decc5b2001"],
            initial_setup=True,
            is_output=False,
        )
    )
    GriptapeNodes.handle_request(
        SetParameterValueRequest(
            parameter_name="output",
            node_name=node4_name,
            value=top_level_unique_values_dict["7dfbcb97-3adc-4ac8-942d-bea1eebc967e"],
            initial_setup=True,
            is_output=False,
        )
    )

with GriptapeNodes.ContextManager().node(node5_name):
    GriptapeNodes.handle_request(
        SetParameterValueRequest(
            parameter_name="text",
            node_name=node5_name,
            value=top_level_unique_values_dict["78d6973d-5bd4-446c-a603-dbf57b58fdfb"],
            initial_setup=True,
            is_output=False,
        )
    )
