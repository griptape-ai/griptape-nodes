# /// script
# dependencies = []
#
# [tool.griptape-nodes]
# name = "two_agent_workflow"
# schema_version = "0.6.1"
# engine_version_created_with = "0.43.1"
# node_libraries_referenced = [["Griptape Nodes Library", "0.41.0"]]
# image = "two_agent_workflow-thumbnail-2025-08-01.png"
# is_griptape_provided = false
# is_template = false
# creation_date = 2025-08-01T11:26:02.872136-07:00
# last_modified_date = 2025-08-01T11:32:09.088159-07:00
#
# ///

import argparse
import pickle

from griptape_nodes.bootstrap.workflow_executors.local_workflow_executor import LocalWorkflowExecutor
from griptape_nodes.bootstrap.workflow_executors.workflow_executor import WorkflowExecutor
from griptape_nodes.node_library.library_registry import NodeMetadata
from griptape_nodes.retained_mode.events.connection_events import CreateConnectionRequest
from griptape_nodes.retained_mode.events.flow_events import (
    CreateFlowRequest,
    GetTopLevelFlowRequest,
    GetTopLevelFlowResultSuccess,
)
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
    context_manager.push_workflow(workflow_name="two_agent_workflow")

"""
1. We've collated all of the unique parameter values into a dictionary so that we do not have to duplicate them.
   This minimizes the size of the code, especially for large objects like serialized image files.
2. We're using a prefix so that it's clear which Flow these values are associated with.
3. The values are serialized using pickle, which is a binary format. This makes them harder to read, but makes
   them consistently save and load. It allows us to serialize complex objects like custom classes, which otherwise
   would be difficult to serialize.
"""
top_level_unique_values_dict = {
    "464b3a39-8a3a-4628-a8de-136c0fba17b3": pickle.loads(
        b'\x80\x04\x95~\x05\x00\x00\x00\x00\x00\x00}\x94(\x8c\x04type\x94\x8c\x12GriptapeNodesAgent\x94\x8c\x08rulesets\x94]\x94\x8c\x05rules\x94]\x94\x8c\x02id\x94\x8c e1a5a9be42f14a8e8c2abb18775c5686\x94\x8c\x13conversation_memory\x94}\x94(h\x01\x8c\x12ConversationMemory\x94\x8c\x04runs\x94]\x94}\x94(h\x01\x8c\x03Run\x94h\x07\x8c edb2edcf87824faeb2d1fc95a6ec49e9\x94\x8c\x04meta\x94N\x8c\x05input\x94}\x94(h\x01\x8c\x0cTextArtifact\x94h\x07\x8c c33e7b4b8b1c46b4840cdf2c8462de03\x94\x8c\treference\x94Nh\x11}\x94\x8c\x04name\x94h\x15\x8c\x05value\x94\x8c\tsmall cat\x94u\x8c\x06output\x94}\x94(h\x01h\x14h\x07\x8c 308876b371f24d878684779356ac9e7b\x94h\x16Nh\x11}\x94\x8c\x0fis_react_prompt\x94\x89sh\x18h\x1dh\x19XB\x02\x00\x00A **small cat** can refer to either:\n\n1. **A young or petite domestic cat** (Felis catus), such as a kitten or a naturally small breed like the Singapura or Munchkin.\n2. **A member of the "small cats" group** in the wild, which includes species in the Felinae subfamily (as opposed to the "big cats" like lions and tigers). Examples of wild small cats are:\n   - **Serval**\n   - **Caracal**\n   - **Ocelot**\n   - **Margay**\n   - **Sand cat**\n   - **Black-footed cat**\n\nIf you meant a specific type of small cat, let me know! I can provide more information, pictures, or care tips.\x94uuah\x11}\x94\x8c\x08max_runs\x94Nu\x8c\x1cconversation_memory_strategy\x94\x8c\rper_structure\x94\x8c\x05tasks\x94]\x94}\x94(h\x01\x8c\nPromptTask\x94h\x03]\x94h\x05]\x94h\x07\x8c 2b33563effd04f8e98636521b2019e89\x94\x8c\x05state\x94\x8c\x0eState.FINISHED\x94\x8c\nparent_ids\x94]\x94\x8c\tchild_ids\x94]\x94\x8c\x17max_meta_memory_entries\x94K\x14\x8c\x07context\x94}\x94\x8c\rprompt_driver\x94}\x94(h\x01\x8c\x19GriptapeCloudPromptDriver\x94\x8c\x0btemperature\x94G?\xb9\x99\x99\x99\x99\x99\x9a\x8c\nmax_tokens\x94N\x8c\x06stream\x94\x88\x8c\x0cextra_params\x94}\x94\x8c\x1astructured_output_strategy\x94\x8c\x06native\x94u\x8c\x05tools\x94]\x94\x8c\x0cmax_subtasks\x94K\x14uau.'
    ),
    "eabb3e33-7e36-424c-9c59-5a313513590a": pickle.loads(
        b"\x80\x04\x95\x0b\x00\x00\x00\x00\x00\x00\x00\x8c\x07gpt-4.1\x94."
    ),
    "f158d043-e61d-4e20-bcc9-93d5bea558e3": pickle.loads(
        b"\x80\x04\x95\r\x00\x00\x00\x00\x00\x00\x00\x8c\tsmall cat\x94."
    ),
    "1f6b7d04-8bdf-49b8-813e-c5f350f8d3af": pickle.loads(b"\x80\x04\x95\x04\x00\x00\x00\x00\x00\x00\x00\x8c\x00\x94."),
    "33200932-be76-43ae-8c08-991a4fc01cca": pickle.loads(b"\x80\x04]\x94."),
    "5f804ae4-510a-4673-807b-5178c084117e": pickle.loads(b"\x80\x04\x95\x06\x00\x00\x00\x00\x00\x00\x00]\x94]\x94a."),
    "72e3fce1-90dc-48c2-b567-9120365c7350": pickle.loads(b"\x80\x04]\x94."),
    "af3c4100-4ada-4a60-ba0b-77a95e26b24b": pickle.loads(
        b'\x80\x04\x95I\x02\x00\x00\x00\x00\x00\x00XB\x02\x00\x00A **small cat** can refer to either:\n\n1. **A young or petite domestic cat** (Felis catus), such as a kitten or a naturally small breed like the Singapura or Munchkin.\n2. **A member of the "small cats" group** in the wild, which includes species in the Felinae subfamily (as opposed to the "big cats" like lions and tigers). Examples of wild small cats are:\n   - **Serval**\n   - **Caracal**\n   - **Ocelot**\n   - **Margay**\n   - **Sand cat**\n   - **Black-footed cat**\n\nIf you meant a specific type of small cat, let me know! I can provide more information, pictures, or care tips.\x94.'
    ),
    "b4d677bf-f5b6-4362-aa18-a565db6d418e": pickle.loads(b"\x80\x04\x89."),
    "c72ab3e6-e6fa-419b-84de-7879843fe597": pickle.loads(
        b"\x80\x04\x95N\x00\x00\x00\x00\x00\x00\x00\x8cJ[Processing..]\n[Started processing agent..]\n\n[Finished processing agent.]\n\x94."
    ),
    "50deaa4a-c2d2-473b-9999-23037ec4840a": pickle.loads(
        b"\x80\x04\x958\x01\x00\x00\x00\x00\x00\x00\x8c%griptape.artifacts.image_url_artifact\x94\x8c\x10ImageUrlArtifact\x94\x93\x94)\x81\x94}\x94(\x8c\x04type\x94h\x01\x8c\x0bmodule_name\x94h\x00\x8c\x02id\x94\x8c ce10018191704ab9ab026e2226d2a17b\x94\x8c\treference\x94N\x8c\x04meta\x94}\x94\x8c\x04name\x94h\x08\x8c\x16encoding_error_handler\x94\x8c\x06strict\x94\x8c\x08encoding\x94\x8c\x05utf-8\x94\x8c\x05value\x94\x8cRhttp://localhost:8124/static/e6a052b5-e3c3-4ffa-8046-86de5c2e4c0b.png?t=1754073116\x94ub."
    ),
    "0974929e-c290-45f7-8174-9c8be9a5f3dd": pickle.loads(
        b'\x80\x04\x95\x97\x03\x00\x00\x00\x00\x00\x00}\x94(\x8c\x04type\x94\x8c\x12GriptapeNodesAgent\x94\x8c\x08rulesets\x94]\x94\x8c\x05rules\x94]\x94\x8c\x02id\x94\x8c 84780200d38c4db98b186c125db36507\x94\x8c\x13conversation_memory\x94}\x94(h\x01\x8c\x12ConversationMemory\x94\x8c\x04runs\x94]\x94}\x94(h\x01\x8c\x03Run\x94h\x07\x8c 0edfdb2f3e1e4f048caba182a40f3c4c\x94\x8c\x04meta\x94N\x8c\x05input\x94}\x94(h\x01\x8c\x0cTextArtifact\x94h\x07\x8c c86faf5e07384a79b156df4869bc495a\x94\x8c\treference\x94Nh\x11}\x94\x8c\x04name\x94h\x15\x8c\x05value\x94\x8c\tsmall cat\x94u\x8c\x06output\x94}\x94(h\x01h\x14h\x07\x8c d105c2e16a5548728b9f087477e42a35\x94h\x16Nh\x11}\x94h\x18h\x1dh\x19\x8csI created an image based on your prompt.\n<THOUGHT>\nmeta={"used_tool": True, "tool": "GenerateImageTool"}\n</THOUGHT>\x94uuah\x11}\x94\x8c\x08max_runs\x94Nu\x8c\x1cconversation_memory_strategy\x94\x8c\rper_structure\x94\x8c\x05tasks\x94]\x94}\x94(h\x01\x8c\nPromptTask\x94h\x03]\x94h\x05]\x94h\x07\x8c 112b7d0b9e334dd5b8bf6ee9e1378dd5\x94\x8c\x05state\x94\x8c\rState.PENDING\x94\x8c\nparent_ids\x94]\x94\x8c\tchild_ids\x94]\x94\x8c\x17max_meta_memory_entries\x94K\x14\x8c\x07context\x94}\x94\x8c\rprompt_driver\x94}\x94(h\x01\x8c\x19GriptapeCloudPromptDriver\x94\x8c\x0btemperature\x94G?\xb9\x99\x99\x99\x99\x99\x9a\x8c\nmax_tokens\x94N\x8c\x06stream\x94\x88\x8c\x0cextra_params\x94}\x94\x8c\x1astructured_output_strategy\x94\x8c\x06native\x94u\x8c\x05tools\x94]\x94\x8c\x0cmax_subtasks\x94K\x14uau.'
    ),
    "28b1a99e-ecc2-457c-9938-2498ec0993e9": pickle.loads(
        b"\x80\x04\x95\x0c\x00\x00\x00\x00\x00\x00\x00\x8c\x08dall-e-3\x94."
    ),
    "3e44c785-d08e-4ea8-839d-ca95c95711ca": pickle.loads(
        b"\x80\x04\x95\r\x00\x00\x00\x00\x00\x00\x00\x8c\t1024x1024\x94."
    ),
    "0e27c570-2b1d-4edd-8884-618ae21cec0b": pickle.loads(
        b"\x80\x04\x95X\x00\x00\x00\x00\x00\x00\x00\x8cTPrompt enhancement disabled.\nStarting processing image..\nFinished processing image.\n\x94."
    ),
}

"# Create the Flow, then do work within it as context."

flow0_name = GriptapeNodes.handle_request(
    CreateFlowRequest(parent_flow_name=None, set_as_new_context=False, metadata={})
).flow_name

with GriptapeNodes.ContextManager().flow(flow0_name):
    node0_name = GriptapeNodes.handle_request(
        CreateNodeRequest(
            node_type="Agent",
            specific_library_name="Griptape Nodes Library",
            node_name="Agent",
            metadata={
                "position": {"x": 1323.0753493574516, "y": 392.0101624623191},
                "tempId": "placing-1750971886413-ptd8jic",
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
                "category": "agents",
                "size": {"width": 411, "height": 584},
                "showaddparameter": False,
            },
            initial_setup=True,
        )
    ).node_name
    with GriptapeNodes.ContextManager().node(node0_name):
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
        GriptapeNodes.handle_request(
            AddParameterToNodeRequest(
                parameter_name="rulesets_ParameterListUniqueParamID_e44b36b171844a2cbbdb41847f88b353",
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
    node1_name = GriptapeNodes.handle_request(
        CreateNodeRequest(
            node_type="StartFlow",
            specific_library_name="Griptape Nodes Library",
            node_name="Start Flow",
            metadata={
                "position": {"x": 289.11136256156453, "y": 757.3296709243662},
                "tempId": "placing-1752870907697-veq7m",
                "library_node_metadata": NodeMetadata(
                    category="workflows",
                    description="Define the start of a workflow and pass parameters into the flow",
                    display_name="Start Flow",
                    tags=None,
                    icon=None,
                    color=None,
                    group=None,
                ),
                "library": "Griptape Nodes Library",
                "node_type": "StartFlow",
                "showaddparameter": True,
                "category": "workflows",
                "size": {"width": 614, "height": 662},
            },
            initial_setup=True,
        )
    ).node_name
    with GriptapeNodes.ContextManager().node(node1_name):
        GriptapeNodes.handle_request(
            AddParameterToNodeRequest(
                parameter_name="prompt",
                tooltip="",
                type="str",
                input_types=["str"],
                output_type="str",
                ui_options={"is_custom": True, "is_user_added": True},
                mode_allowed_input=False,
                mode_allowed_property=True,
                mode_allowed_output=True,
                initial_setup=True,
            )
        )
    node2_name = GriptapeNodes.handle_request(
        CreateNodeRequest(
            node_type="EndFlow",
            specific_library_name="Griptape Nodes Library",
            node_name="End Flow",
            metadata={
                "position": {"x": 2106.216458963463, "y": 881.1816547410375},
                "tempId": "placing-1753823961680-e6rt2o",
                "library_node_metadata": {
                    "category": "workflows",
                    "description": "Define the end of a workflow and return parameters from the flow",
                },
                "library": "Griptape Nodes Library",
                "node_type": "EndFlow",
                "showaddparameter": True,
                "category": "workflows",
                "size": {"width": 478, "height": 462},
            },
            initial_setup=True,
        )
    ).node_name
    with GriptapeNodes.ContextManager().node(node2_name):
        GriptapeNodes.handle_request(
            AddParameterToNodeRequest(
                parameter_name="response",
                tooltip="",
                type="str",
                input_types=["str"],
                output_type="str",
                ui_options={"is_custom": True, "is_user_added": True},
                mode_allowed_input=True,
                mode_allowed_property=True,
                mode_allowed_output=False,
                initial_setup=True,
            )
        )
        GriptapeNodes.handle_request(
            AddParameterToNodeRequest(
                parameter_name="image",
                tooltip="",
                type="ImageArtifact",
                input_types=["ImageArtifact", "ImageUrlArtifact"],
                output_type="ImageArtifact",
                ui_options={"is_custom": True, "is_user_added": True},
                mode_allowed_input=True,
                mode_allowed_property=True,
                mode_allowed_output=False,
                initial_setup=True,
            )
        )
    node3_name = GriptapeNodes.handle_request(
        CreateNodeRequest(
            node_type="GenerateImage",
            specific_library_name="Griptape Nodes Library",
            node_name="Generate Image",
            metadata={
                "position": {"x": 1334.9159981077585, "y": 1081.4339873246902},
                "tempId": "placing-1753988868095-27huh3",
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
                "showaddparameter": False,
                "category": "image",
            },
            initial_setup=True,
        )
    ).node_name
    with GriptapeNodes.ContextManager().node(node3_name):
        GriptapeNodes.handle_request(
            AlterParameterDetailsRequest(parameter_name="prompt", mode_allowed_property=False, initial_setup=True)
        )
    GriptapeNodes.handle_request(
        CreateConnectionRequest(
            source_node_name=node0_name,
            source_parameter_name="output",
            target_node_name=node2_name,
            target_parameter_name="response",
            initial_setup=True,
        )
    )
    GriptapeNodes.handle_request(
        CreateConnectionRequest(
            source_node_name=node1_name,
            source_parameter_name="prompt",
            target_node_name=node0_name,
            target_parameter_name="prompt",
            initial_setup=True,
        )
    )
    GriptapeNodes.handle_request(
        CreateConnectionRequest(
            source_node_name=node1_name,
            source_parameter_name="prompt",
            target_node_name=node3_name,
            target_parameter_name="prompt",
            initial_setup=True,
        )
    )
    GriptapeNodes.handle_request(
        CreateConnectionRequest(
            source_node_name=node3_name,
            source_parameter_name="output",
            target_node_name=node2_name,
            target_parameter_name="image",
            initial_setup=True,
        )
    )
    with GriptapeNodes.ContextManager().node(node0_name):
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="agent",
                node_name=node0_name,
                value=top_level_unique_values_dict["464b3a39-8a3a-4628-a8de-136c0fba17b3"],
                initial_setup=True,
                is_output=True,
            )
        )
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="model",
                node_name=node0_name,
                value=top_level_unique_values_dict["eabb3e33-7e36-424c-9c59-5a313513590a"],
                initial_setup=True,
                is_output=False,
            )
        )
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="prompt",
                node_name=node0_name,
                value=top_level_unique_values_dict["f158d043-e61d-4e20-bcc9-93d5bea558e3"],
                initial_setup=True,
                is_output=False,
            )
        )
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="additional_context",
                node_name=node0_name,
                value=top_level_unique_values_dict["1f6b7d04-8bdf-49b8-813e-c5f350f8d3af"],
                initial_setup=True,
                is_output=False,
            )
        )
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="tools",
                node_name=node0_name,
                value=top_level_unique_values_dict["33200932-be76-43ae-8c08-991a4fc01cca"],
                initial_setup=True,
                is_output=False,
            )
        )
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="rulesets",
                node_name=node0_name,
                value=top_level_unique_values_dict["5f804ae4-510a-4673-807b-5178c084117e"],
                initial_setup=True,
                is_output=False,
            )
        )
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="rulesets_ParameterListUniqueParamID_e44b36b171844a2cbbdb41847f88b353",
                node_name=node0_name,
                value=top_level_unique_values_dict["72e3fce1-90dc-48c2-b567-9120365c7350"],
                initial_setup=True,
                is_output=False,
            )
        )
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="output",
                node_name=node0_name,
                value=top_level_unique_values_dict["1f6b7d04-8bdf-49b8-813e-c5f350f8d3af"],
                initial_setup=True,
                is_output=False,
            )
        )
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="output",
                node_name=node0_name,
                value=top_level_unique_values_dict["af3c4100-4ada-4a60-ba0b-77a95e26b24b"],
                initial_setup=True,
                is_output=True,
            )
        )
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="include_details",
                node_name=node0_name,
                value=top_level_unique_values_dict["b4d677bf-f5b6-4362-aa18-a565db6d418e"],
                initial_setup=True,
                is_output=False,
            )
        )
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="logs",
                node_name=node0_name,
                value=top_level_unique_values_dict["c72ab3e6-e6fa-419b-84de-7879843fe597"],
                initial_setup=True,
                is_output=True,
            )
        )
    with GriptapeNodes.ContextManager().node(node1_name):
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="prompt",
                node_name=node1_name,
                value=top_level_unique_values_dict["f158d043-e61d-4e20-bcc9-93d5bea558e3"],
                initial_setup=True,
                is_output=False,
            )
        )
    with GriptapeNodes.ContextManager().node(node2_name):
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="response",
                node_name=node2_name,
                value=top_level_unique_values_dict["af3c4100-4ada-4a60-ba0b-77a95e26b24b"],
                initial_setup=True,
                is_output=False,
            )
        )
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="response",
                node_name=node2_name,
                value=top_level_unique_values_dict["af3c4100-4ada-4a60-ba0b-77a95e26b24b"],
                initial_setup=True,
                is_output=True,
            )
        )
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="image",
                node_name=node2_name,
                value=top_level_unique_values_dict["50deaa4a-c2d2-473b-9999-23037ec4840a"],
                initial_setup=True,
                is_output=False,
            )
        )
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="image",
                node_name=node2_name,
                value=top_level_unique_values_dict["50deaa4a-c2d2-473b-9999-23037ec4840a"],
                initial_setup=True,
                is_output=True,
            )
        )
    with GriptapeNodes.ContextManager().node(node3_name):
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="agent",
                node_name=node3_name,
                value=top_level_unique_values_dict["0974929e-c290-45f7-8174-9c8be9a5f3dd"],
                initial_setup=True,
                is_output=True,
            )
        )
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="model",
                node_name=node3_name,
                value=top_level_unique_values_dict["28b1a99e-ecc2-457c-9938-2498ec0993e9"],
                initial_setup=True,
                is_output=False,
            )
        )
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="prompt",
                node_name=node3_name,
                value=top_level_unique_values_dict["f158d043-e61d-4e20-bcc9-93d5bea558e3"],
                initial_setup=True,
                is_output=False,
            )
        )
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="image_size",
                node_name=node3_name,
                value=top_level_unique_values_dict["3e44c785-d08e-4ea8-839d-ca95c95711ca"],
                initial_setup=True,
                is_output=False,
            )
        )
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="enhance_prompt",
                node_name=node3_name,
                value=top_level_unique_values_dict["b4d677bf-f5b6-4362-aa18-a565db6d418e"],
                initial_setup=True,
                is_output=False,
            )
        )
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="output",
                node_name=node3_name,
                value=top_level_unique_values_dict["50deaa4a-c2d2-473b-9999-23037ec4840a"],
                initial_setup=True,
                is_output=True,
            )
        )
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="include_details",
                node_name=node3_name,
                value=top_level_unique_values_dict["b4d677bf-f5b6-4362-aa18-a565db6d418e"],
                initial_setup=True,
                is_output=False,
            )
        )
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="logs",
                node_name=node3_name,
                value=top_level_unique_values_dict["0e27c570-2b1d-4edd-8884-618ae21cec0b"],
                initial_setup=True,
                is_output=True,
            )
        )


def _ensure_workflow_context() -> None:
    context_manager = GriptapeNodes.ContextManager()
    if not context_manager.has_current_flow():
        top_level_flow_request = GetTopLevelFlowRequest()
        top_level_flow_result = GriptapeNodes.handle_request(top_level_flow_request)
        if (
            isinstance(top_level_flow_result, GetTopLevelFlowResultSuccess)
            and top_level_flow_result.flow_name is not None
        ):
            flow_manager = GriptapeNodes.FlowManager()
            flow_obj = flow_manager.get_flow_by_name(top_level_flow_result.flow_name)
            context_manager.push_flow(flow_obj)


def execute_workflow(
    input: dict, storage_backend: str = "local", workflow_executor: WorkflowExecutor | None = None
) -> dict | None:

    _ensure_workflow_context()

    # # Clean up ThreadPoolExecutor to prevent interference between runs
    # from griptape_nodes.machines.node_resolution import ExecuteNodeState
    # ExecuteNodeState.executor.shutdown(wait=True)
    # ExecuteNodeState.executor = ThreadPoolExecutor()

    # Reset the flow state before each execution
    from griptape_nodes.retained_mode.events.execution_events import UnresolveFlowRequest

    flow_name = GriptapeNodes.ContextManager().get_current_flow().name
    GriptapeNodes.handle_request(UnresolveFlowRequest(flow_name=flow_name))

    # # Also reset the flow manager's resolution machine state
    # flow_manager = GriptapeNodes.FlowManager()
    # if flow_manager._global_control_flow_machine:
    #     flow_manager._global_control_flow_machine._context.resolution_machine.reset_machine()

    workflow_executor = workflow_executor or LocalWorkflowExecutor()
    workflow_executor.run(workflow_name="ControlFlow_1", flow_input=input, storage_backend=storage_backend)
    return workflow_executor.output


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--storage-backend",
        choices=["local", "gtc"],
        default="local",
        help="Storage backend to use: 'local' for local filesystem or 'gtc' for Griptape Cloud",
    )
    parser.add_argument("--prompt", default=None, help="")
    args = parser.parse_args()
    flow_input = {}
    if "Start Flow" not in flow_input:
        flow_input["Start Flow"] = {}
    if args.prompt is not None:
        flow_input["Start Flow"]["prompt"] = args.prompt
    workflow_output = execute_workflow(input=flow_input, storage_backend=args.storage_backend)
