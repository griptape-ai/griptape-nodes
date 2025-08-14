# /// script
# dependencies = []
#
# [tool.griptape-nodes]
# name = "control_flow_test"
# schema_version = "0.7.0"
# engine_version_created_with = "0.47.0"
# node_libraries_referenced = [["Griptape Nodes Library", "0.41.0"]]
# image = "workflow_28-thumbnail-2025-08-14.png"
# is_griptape_provided = false
# is_template = false
# creation_date = 2025-08-14T00:56:12.333293Z
# last_modified_date = 2025-08-14T00:56:12.361513Z
#
# ///

import argparse
import json
import pickle

from griptape_nodes.bootstrap.workflow_executors.local_workflow_executor import LocalWorkflowExecutor
from griptape_nodes.bootstrap.workflow_executors.workflow_executor import WorkflowExecutor
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
    context_manager.push_workflow(workflow_name="control_flow_test")

"""
1. We've collated all of the unique parameter values into a dictionary so that we do not have to duplicate them.
   This minimizes the size of the code, especially for large objects like serialized image files.
2. We're using a prefix so that it's clear which Flow these values are associated with.
3. The values are serialized using pickle, which is a binary format. This makes them harder to read, but makes
   them consistently save and load. It allows us to serialize complex objects like custom classes, which otherwise
   would be difficult to serialize.
"""
top_level_unique_values_dict = {
    "9d2b2774-862a-4526-8666-ea832d16f2e0": pickle.loads(b"\x80\x04\x95\x04\x00\x00\x00\x00\x00\x00\x00\x8c\x00\x94.")
}

"# Create the Flow, then do work within it as context."

flow0_name = GriptapeNodes.handle_request(
    CreateFlowRequest(parent_flow_name=None, set_as_new_context=False, metadata={})
).flow_name

with GriptapeNodes.ContextManager().flow(flow0_name):
    node0_name = GriptapeNodes.handle_request(
        CreateNodeRequest(
            node_type="StartFlow",
            specific_library_name="Griptape Nodes Library",
            node_name="Start Flow",
            metadata={
                "position": {"x": 802.5599206823966, "y": 354.9315060803245},
                "tempId": "placing-1755132865920-alv1gi",
                "library_node_metadata": {
                    "category": "workflows",
                    "description": "Define the start of a workflow and pass parameters into the flow",
                    "display_name": "Start Flow",
                    "tags": None,
                    "icon": None,
                    "color": None,
                    "group": None,
                },
                "library": "Griptape Nodes Library",
                "node_type": "StartFlow",
                "showaddparameter": True,
                "min_size": {"width": 299, "height": 128},
            },
            initial_setup=True,
        )
    ).node_name
    with GriptapeNodes.ContextManager().node(node0_name):
        GriptapeNodes.handle_request(
            AddParameterToNodeRequest(
                parameter_name="prompt",
                default_value="",
                tooltip="New parameter",
                type="str",
                input_types=["str"],
                output_type="str",
                ui_options={
                    "multiline": True,
                    "placeholder_text": "Talk with the Agent.",
                    "is_custom": True,
                    "is_user_added": True,
                },
                mode_allowed_input=True,
                mode_allowed_property=True,
                mode_allowed_output=True,
                parent_container_name="",
                initial_setup=True,
            )
        )
    node1_name = GriptapeNodes.handle_request(
        CreateNodeRequest(
            node_type="EndFlow",
            specific_library_name="Griptape Nodes Library",
            node_name="End Flow",
            metadata={
                "position": {"x": 1695.322398085316, "y": 344.7706221979213},
                "tempId": "placing-1755132870797-ex293xd",
                "library_node_metadata": {
                    "category": "workflows",
                    "description": "Define the end of a workflow and return parameters from the flow",
                },
                "library": "Griptape Nodes Library",
                "node_type": "EndFlow",
                "showaddparameter": True,
                "min_size": {"width": 284, "height": 128},
                "category": "workflows",
            },
            initial_setup=True,
        )
    ).node_name
    with GriptapeNodes.ContextManager().node(node1_name):
        GriptapeNodes.handle_request(
            AddParameterToNodeRequest(
                parameter_name="output",
                default_value="",
                tooltip="New parameter",
                type="str",
                input_types=["str"],
                output_type="str",
                ui_options={
                    "multiline": True,
                    "placeholder_text": "Agent response",
                    "markdown": False,
                    "is_custom": True,
                    "is_user_added": True,
                },
                mode_allowed_input=True,
                mode_allowed_property=True,
                mode_allowed_output=True,
                parent_container_name="",
                initial_setup=True,
            )
        )
    node2_name = GriptapeNodes.handle_request(
        CreateNodeRequest(
            node_type="Agent",
            specific_library_name="Griptape Nodes Library",
            node_name="Agent",
            metadata={
                "position": {"x": 1188.7497327905344, "y": 344.7706221979213},
                "tempId": "placing-1755132881246-bf8ofo",
                "library_node_metadata": {
                    "category": "agents",
                    "description": "Creates an AI agent with conversation memory and the ability to use tools",
                },
                "library": "Griptape Nodes Library",
                "node_type": "Agent",
                "showaddparameter": False,
                "min_size": {"width": 402, "height": 544},
                "category": "agents",
            },
            initial_setup=True,
        )
    ).node_name
    GriptapeNodes.handle_request(
        CreateConnectionRequest(
            source_node_name=node0_name,
            source_parameter_name="exec_out",
            target_node_name=node2_name,
            target_parameter_name="exec_in",
            initial_setup=True,
        )
    )
    GriptapeNodes.handle_request(
        CreateConnectionRequest(
            source_node_name=node2_name,
            source_parameter_name="exec_out",
            target_node_name=node1_name,
            target_parameter_name="exec_in",
            initial_setup=True,
        )
    )
    GriptapeNodes.handle_request(
        CreateConnectionRequest(
            source_node_name=node0_name,
            source_parameter_name="prompt",
            target_node_name=node2_name,
            target_parameter_name="prompt",
            initial_setup=True,
        )
    )
    GriptapeNodes.handle_request(
        CreateConnectionRequest(
            source_node_name=node2_name,
            source_parameter_name="output",
            target_node_name=node1_name,
            target_parameter_name="output",
            initial_setup=True,
        )
    )
    with GriptapeNodes.ContextManager().node(node0_name):
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="prompt",
                node_name=node0_name,
                value=top_level_unique_values_dict["9d2b2774-862a-4526-8666-ea832d16f2e0"],
                initial_setup=True,
                is_output=False,
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
    parser.add_argument(
        "--json-input",
        default=None,
        help="JSON string containing parameter values. Takes precedence over individual parameter arguments if provided.",
    )
    parser.add_argument("--prompt", default=None, help="New parameter")
    args = parser.parse_args()
    flow_input = {}
    if args.json_input is not None:
        flow_input = json.loads(args.json_input)
    if args.json_input is None:
        if "Start Flow" not in flow_input:
            flow_input["Start Flow"] = {}
        if args.prompt is not None:
            flow_input["Start Flow"]["prompt"] = args.prompt
    workflow_output = execute_workflow(input=flow_input, storage_backend=args.storage_backend)
