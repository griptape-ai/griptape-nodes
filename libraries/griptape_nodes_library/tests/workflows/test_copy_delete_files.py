# /// script
# dependencies = []
#
# [tool.griptape-nodes]
# name = "test_copy_delete_files"
# schema_version = "0.14.0"
# engine_version_created_with = "0.65.4"
# node_libraries_referenced = [["Griptape Nodes Library", "0.52.3"]]
# node_types_used = [["Griptape Nodes Library", "CopyFiles"], ["Griptape Nodes Library", "DeleteFile"], ["Griptape Nodes Library", "DisplayList"], ["Griptape Nodes Library", "EndFlow"], ["Griptape Nodes Library", "SaveText"], ["Griptape Nodes Library", "StartFlow"], ["Griptape Nodes Library", "TempDirectory"], ["Griptape Nodes Library", "TempFilename"]]
# is_griptape_provided = false
# creation_date = 2025-12-16T20:18:48.735663Z
# last_modified_date = 2025-12-16T21:15:15.140489Z
# workflow_shape = "{\"inputs\":{\"Start Flow\":{\"exec_out\":{\"name\":\"exec_out\",\"tooltip\":\"Connection to the next node in the execution chain\",\"type\":\"parametercontroltype\",\"input_types\":[\"parametercontroltype\"],\"output_type\":\"parametercontroltype\",\"default_value\":null,\"tooltip_as_input\":null,\"tooltip_as_property\":null,\"tooltip_as_output\":null,\"ui_options\":{\"display_name\":\"Flow Out\"},\"settable\":true,\"is_user_defined\":true,\"parent_container_name\":null,\"parent_element_name\":null},\"name\":{\"name\":\"name\",\"tooltip\":\"New parameter\",\"type\":\"str\",\"input_types\":[\"any\"],\"output_type\":\"str\",\"default_value\":\"\",\"tooltip_as_input\":null,\"tooltip_as_property\":null,\"tooltip_as_output\":null,\"ui_options\":{\"placeholder_text\":\"Example: myfile or document\",\"hide_label\":false,\"hide_property\":false,\"is_custom\":true,\"is_user_added\":true},\"settable\":true,\"is_user_defined\":true,\"parent_container_name\":\"\",\"parent_element_name\":null}}},\"outputs\":{\"End Flow\":{\"exec_in\":{\"name\":\"exec_in\",\"tooltip\":\"Control path when the flow completed successfully\",\"type\":\"parametercontroltype\",\"input_types\":[\"parametercontroltype\"],\"output_type\":\"parametercontroltype\",\"default_value\":null,\"tooltip_as_input\":null,\"tooltip_as_property\":null,\"tooltip_as_output\":null,\"ui_options\":{\"display_name\":\"Succeeded\"},\"settable\":true,\"is_user_defined\":true,\"parent_container_name\":null,\"parent_element_name\":null},\"failed\":{\"name\":\"failed\",\"tooltip\":\"Control path when the flow failed\",\"type\":\"parametercontroltype\",\"input_types\":[\"parametercontroltype\"],\"output_type\":\"parametercontroltype\",\"default_value\":null,\"tooltip_as_input\":null,\"tooltip_as_property\":null,\"tooltip_as_output\":null,\"ui_options\":{\"display_name\":\"Failed\"},\"settable\":true,\"is_user_defined\":true,\"parent_container_name\":null,\"parent_element_name\":null},\"was_successful\":{\"name\":\"was_successful\",\"tooltip\":\"Indicates whether it completed without errors.\",\"type\":\"bool\",\"input_types\":[\"bool\"],\"output_type\":\"bool\",\"default_value\":false,\"tooltip_as_input\":null,\"tooltip_as_property\":null,\"tooltip_as_output\":null,\"ui_options\":{},\"settable\":false,\"is_user_defined\":true,\"parent_container_name\":null,\"parent_element_name\":null},\"result_details\":{\"name\":\"result_details\",\"tooltip\":\"Details about the operation result\",\"type\":\"str\",\"input_types\":[\"str\"],\"output_type\":\"str\",\"default_value\":null,\"tooltip_as_input\":null,\"tooltip_as_property\":null,\"tooltip_as_output\":null,\"ui_options\":{\"multiline\":true,\"placeholder_text\":\"Details about the completion or failure will be shown here.\"},\"settable\":false,\"is_user_defined\":true,\"parent_container_name\":null,\"parent_element_name\":null}}}}"
#
# ///

import argparse
import asyncio
import json
import pickle
from griptape_nodes.bootstrap.workflow_executors.local_workflow_executor import LocalWorkflowExecutor
from griptape_nodes.bootstrap.workflow_executors.workflow_executor import WorkflowExecutor
from griptape_nodes.drivers.storage.storage_backend import StorageBackend
from griptape_nodes.node_library.library_registry import IconVariant, NodeDeprecationMetadata, NodeMetadata
from griptape_nodes.retained_mode.events.connection_events import CreateConnectionRequest
from griptape_nodes.retained_mode.events.flow_events import (
    CreateFlowRequest,
    GetTopLevelFlowRequest,
    GetTopLevelFlowResultSuccess,
)
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
    context_manager.push_workflow(workflow_name="test_copy_delete_files")

"""
1. We've collated all of the unique parameter values into a dictionary so that we do not have to duplicate them.
   This minimizes the size of the code, especially for large objects like serialized image files.
2. We're using a prefix so that it's clear which Flow these values are associated with.
3. The values are serialized using pickle, which is a binary format. This makes them harder to read, but makes
   them consistently save and load. It allows us to serialize complex objects like custom classes, which otherwise
   would be difficult to serialize.
"""
top_level_unique_values_dict = {
    "969942c9-3db3-4a64-8024-84f8cec13b14": pickle.loads(
        b"\x80\x04\x954\x00\x00\x00\x00\x00\x00\x00\x8c0/var/folders/b4/13z163m95qb1kg2m0x12_0mw0000gn/T\x94."
    ),
    "75bd64b2-d9f0-41a3-9e95-8cd309df75f4": pickle.loads(
        b"\x80\x04\x95\x06\x00\x00\x00\x00\x00\x00\x00\x8c\x02my\x94."
    ),
    "e8ce4f96-a0df-400b-8a0a-562341a3c6bf": pickle.loads(
        b"\x80\x04\x95\x13\x00\x00\x00\x00\x00\x00\x00\x8c\x0ftest_file_nodes\x94."
    ),
    "c73c4663-7d95-44f7-a65e-97804ede33a7": pickle.loads(b"\x80\x04\x95\x05\x00\x00\x00\x00\x00\x00\x00\x8c\x01_\x94."),
    "915bb38a-5613-4b18-92e4-9a9668b2672f": pickle.loads(
        b"\x80\x04\x95\x08\x00\x00\x00\x00\x00\x00\x00\x8c\x04test\x94."
    ),
    "283fe656-e079-4339-a5e2-251e1984d3d7": pickle.loads(
        b"\x80\x04\x95\x07\x00\x00\x00\x00\x00\x00\x00\x8c\x03txt\x94."
    ),
    "c393cb99-3a44-47ec-a95d-0dbdd6a80e29": pickle.loads(b"\x80\x04\x88."),
    "01428e67-1ea9-4b87-9650-472886a4f19e": pickle.loads(
        b"\x80\x04\x95`\x00\x00\x00\x00\x00\x00\x00\x8c\\/private/var/folders/b4/13z163m95qb1kg2m0x12_0mw0000gn/T/my_test_file_nodes_jptg1hi1test.txt\x94."
    ),
    "80636c21-3c85-4b1e-8e38-af4ea7c17085": pickle.loads(
        b"\x80\x04\x95\x17\x00\x00\x00\x00\x00\x00\x00\x8c\x13This is a test file\x94."
    ),
    "2d31db0d-ef0e-4ec4-a56b-ecda413faa1a": pickle.loads(
        b"\x80\x04\x95c\x00\x00\x00\x00\x00\x00\x00]\x94\x8c\\/private/var/folders/b4/13z163m95qb1kg2m0x12_0mw0000gn/T/my_test_file_nodes_jptg1hi1test.txt\x94a."
    ),
    "2111570c-c172-43f7-84f2-aeb996773ed4": pickle.loads(
        b"\x80\x04\x95U\x00\x00\x00\x00\x00\x00\x00\x8cQ/private/var/folders/b4/13z163m95qb1kg2m0x12_0mw0000gn/T/my_file_r9zld_88test.txt\x94."
    ),
    "81c2c58f-a640-44ea-8474-ba2c2d4c95d9": pickle.loads(
        b"\x80\x04\x95X\x00\x00\x00\x00\x00\x00\x00]\x94\x8cQ/private/var/folders/b4/13z163m95qb1kg2m0x12_0mw0000gn/T/my_file_r9zld_88test.txt\x94a."
    ),
    "355f7651-e1e0-4be6-ba39-94ec3c8ad6fd": pickle.loads(
        b"\x80\x04\x95\n\x00\x00\x00\x00\x00\x00\x00G?\xf0\x00\x00\x00\x00\x00\x00."
    ),
    "fbbe07cb-6305-40b7-8ec9-d467e905f0ae": pickle.loads(
        b"\x80\x04\x95\xee\x00\x00\x00\x00\x00\x00\x00\x8c\xeaCopied 1/1 valid items\n\nSuccessfully copied (1):\n  \xf0\x9f\x93\x84 /private/var/folders/b4/13z163m95qb1kg2m0x12_0mw0000gn/T/my_test_file_nodes_jptg1hi1test.txt \xe2\x86\x92 /private/var/folders/b4/13z163m95qb1kg2m0x12_0mw0000gn/T/my_file_r9zld_88test.txt\x94."
    ),
    "870358da-c991-4f91-9e08-78f9e393145e": pickle.loads(
        b"\x80\x04\x95\x08\x00\x00\x00\x00\x00\x00\x00\x8c\x04file\x94."
    ),
    "8dbc85e2-1d91-4aae-a2bd-540cb8c2ee5e": pickle.loads(
        b"\x80\x04\x95c\x00\x00\x00\x00\x00\x00\x00]\x94\x8c\\/private/var/folders/b4/13z163m95qb1kg2m0x12_0mw0000gn/T/my_test_file_nodes_jptg1hi1test.txt\x94a."
    ),
    "5b0dfb96-82d0-4983-84af-1d411c3e0430": pickle.loads(
        b"\x80\x04\x95c\x00\x00\x00\x00\x00\x00\x00]\x94\x8c\\/private/var/folders/b4/13z163m95qb1kg2m0x12_0mw0000gn/T/my_test_file_nodes_jptg1hi1test.txt\x94a."
    ),
    "3875ba80-b199-46f9-a86b-646afcaf53fb": pickle.loads(
        b"\x80\x04\x95\x94\x00\x00\x00\x00\x00\x00\x00\x8c\x90Deleted 1/1 items\n\nSuccessfully deleted (1):\n  \xf0\x9f\x93\x84 /private/var/folders/b4/13z163m95qb1kg2m0x12_0mw0000gn/T/my_test_file_nodes_jptg1hi1test.txt\x94."
    ),
    "163d2ee3-7aef-4522-a80a-4fc29df28c33": pickle.loads(
        b"\x80\x04\x95X\x00\x00\x00\x00\x00\x00\x00]\x94\x8cQ/private/var/folders/b4/13z163m95qb1kg2m0x12_0mw0000gn/T/my_file_r9zld_88test.txt\x94a."
    ),
    "9782dde2-168d-4826-b3e0-0015a9bafde2": pickle.loads(
        b"\x80\x04\x95\x1b\x00\x00\x00\x00\x00\x00\x00\x8c\x17Control Input Selection\x94."
    ),
    "fcb91394-0ffd-4730-8c5d-df1a167a7173": pickle.loads(
        b"\x80\x04\x95\xa0\x00\x00\x00\x00\x00\x00\x00\x8c\x9c[SUCCEEDED]\nDeleted 1/1 items\n\nSuccessfully deleted (1):\n  \xf0\x9f\x93\x84 /private/var/folders/b4/13z163m95qb1kg2m0x12_0mw0000gn/T/my_test_file_nodes_jptg1hi1test.txt\x94."
    ),
}

"# Create the Flow, then do work within it as context."

flow0_name = GriptapeNodes.handle_request(
    CreateFlowRequest(parent_flow_name=None, flow_name="ControlFlow_1", set_as_new_context=False, metadata={})
).flow_name

with GriptapeNodes.ContextManager().flow(flow0_name):
    node0_name = GriptapeNodes.handle_request(
        CreateNodeRequest(
            node_type="TempDirectory",
            specific_library_name="Griptape Nodes Library",
            node_name="Temp Directory",
            metadata={
                "position": {"x": -1394.8735643584932, "y": 947.7234921906015},
                "tempId": "placing-1765918203589-cacb1g",
                "library_node_metadata": NodeMetadata(
                    category="files",
                    description="Get the system temporary directory path. Works cross-platform (Windows, macOS, Linux).",
                    display_name="Temp Directory",
                    tags=None,
                    icon="Folder",
                    color=None,
                    group=None,
                    deprecation=None,
                    is_node_group=None,
                ),
                "library": "Griptape Nodes Library",
                "node_type": "TempDirectory",
                "showaddparameter": False,
                "size": {"width": 600, "height": 196},
                "category": "files",
            },
            resolution="resolved",
            initial_setup=True,
        )
    ).node_name
    node1_name = GriptapeNodes.handle_request(
        CreateNodeRequest(
            node_type="TempFilename",
            specific_library_name="Griptape Nodes Library",
            node_name="Temp Filename",
            metadata={
                "position": {"x": -569.1870251305756, "y": 921.3091580630366},
                "tempId": "placing-1765918259715-h6yy66",
                "library_node_metadata": NodeMetadata(
                    category="files",
                    description="Generate a unique temporary filename using Python's tempfile module. Supports optional directory, suffix, prefix, and can return absolute path or just filename.",
                    display_name="Temp Filename",
                    tags=None,
                    icon="FileText",
                    color=None,
                    group=None,
                    deprecation=None,
                    is_node_group=None,
                ),
                "library": "Griptape Nodes Library",
                "node_type": "TempFilename",
                "showaddparameter": False,
                "size": {"width": 669, "height": 512},
                "category": "files",
            },
            resolution="resolved",
            initial_setup=True,
        )
    ).node_name
    node2_name = GriptapeNodes.handle_request(
        CreateNodeRequest(
            node_type="SaveText",
            specific_library_name="Griptape Nodes Library",
            node_name="Save Text",
            metadata={
                "position": {"x": 416.60269999614064, "y": 863.7234921906014},
                "tempId": "placing-1765919090373-pybnr8",
                "library_node_metadata": NodeMetadata(
                    category="text",
                    description="Save text to a file",
                    display_name="Save Text",
                    tags=None,
                    icon="file-down",
                    color=None,
                    group="Input/Output",
                    deprecation=None,
                    is_node_group=None,
                ),
                "library": "Griptape Nodes Library",
                "node_type": "SaveText",
                "showaddparameter": False,
                "size": {"width": 600, "height": 280},
                "category": "text",
            },
            resolution="resolved",
            initial_setup=True,
        )
    ).node_name
    node3_name = GriptapeNodes.handle_request(
        CreateNodeRequest(
            node_type="CopyFiles",
            specific_library_name="Griptape Nodes Library",
            node_name="Copy Files",
            metadata={
                "position": {"x": 2003.3255036082787, "y": 1103.0104570707665},
                "tempId": "placing-1765919126082-ri7a1j",
                "library_node_metadata": NodeMetadata(
                    category="files",
                    description="Copy files and/or directories from source to destination. Supports glob patterns and multiple sources.",
                    display_name="Copy Files",
                    tags=None,
                    icon="Copy",
                    color=None,
                    group=None,
                    deprecation=None,
                    is_node_group=None,
                ),
                "library": "Griptape Nodes Library",
                "node_type": "CopyFiles",
                "showaddparameter": False,
                "size": {"width": 600, "height": 714},
                "category": "files",
            },
            resolution="resolved",
            initial_setup=True,
        )
    ).node_name
    with GriptapeNodes.ContextManager().node(node3_name):
        GriptapeNodes.handle_request(
            AddParameterToNodeRequest(
                parameter_name="source_paths_ParameterListUniqueParamID_31f3035837864ff1ae31fe4089332086",
                default_value=[],
                tooltip="Path(s) to file(s) or directory(ies) to copy. Supports glob patterns (e.g., '/path/*.txt').",
                type="str",
                input_types=["str", "list", "any"],
                output_type="str",
                ui_options={},
                mode_allowed_input=True,
                mode_allowed_property=True,
                mode_allowed_output=False,
                is_user_defined=True,
                settable=True,
                parent_container_name="source_paths",
                initial_setup=True,
            )
        )
    node4_name = GriptapeNodes.handle_request(
        CreateNodeRequest(
            node_type="TempFilename",
            specific_library_name="Griptape Nodes Library",
            node_name="Temp Filename_1",
            metadata={
                "position": {"x": 1158.2148105724013, "y": 1723.939534623123},
                "tempId": "placing-1765918259715-h6yy66",
                "library_node_metadata": NodeMetadata(
                    category="files",
                    description="Generate a unique temporary filename using Python's tempfile module. Supports optional directory, suffix, prefix, and can return absolute path or just filename.",
                    display_name="Temp Filename",
                    tags=None,
                    icon="FileText",
                    color=None,
                    group=None,
                    deprecation=None,
                    is_node_group=None,
                ),
                "library": "Griptape Nodes Library",
                "node_type": "TempFilename",
                "showaddparameter": False,
                "size": {"width": 669, "height": 512},
                "category": "files",
            },
            resolution="resolved",
            initial_setup=True,
        )
    ).node_name
    node5_name = GriptapeNodes.handle_request(
        CreateNodeRequest(
            node_type="DeleteFile",
            specific_library_name="Griptape Nodes Library",
            node_name="Delete File",
            metadata={
                "position": {"x": 3520.668440640511, "y": 1655.1208358764438},
                "tempId": "placing-1765919312706-7aktsj",
                "library_node_metadata": NodeMetadata(
                    category="files",
                    description="Delete a file or directory from the file system. Directories are deleted with all their contents.",
                    display_name="Delete File",
                    tags=None,
                    icon="Trash",
                    color=None,
                    group=None,
                    deprecation=None,
                    is_node_group=None,
                ),
                "library": "Griptape Nodes Library",
                "node_type": "DeleteFile",
                "showaddparameter": False,
                "size": {"width": 773, "height": 832},
                "category": "files",
            },
            resolution="resolved",
            initial_setup=True,
        )
    ).node_name
    with GriptapeNodes.ContextManager().node(node5_name):
        GriptapeNodes.handle_request(
            AddParameterToNodeRequest(
                parameter_name="file_paths_ParameterListUniqueParamID_bf35a91dffe249c594860d5d87f1f23b",
                tooltip="Paths to files or directories to delete. Supports glob patterns (e.g., '/path/*.txt').",
                type="str",
                input_types=["str", "list"],
                output_type="str",
                ui_options={},
                mode_allowed_input=True,
                mode_allowed_property=True,
                mode_allowed_output=False,
                is_user_defined=True,
                settable=True,
                parent_container_name="file_paths",
                initial_setup=True,
            )
        )
        GriptapeNodes.handle_request(
            AddParameterToNodeRequest(
                parameter_name="file_paths_ParameterListUniqueParamID_9db4fb593cf94ff6a096373d9f6d4a31",
                tooltip="Paths to files or directories to delete. Supports glob patterns (e.g., '/path/*.txt').",
                type="str",
                input_types=["str", "list"],
                output_type="str",
                ui_options={},
                mode_allowed_input=True,
                mode_allowed_property=True,
                mode_allowed_output=False,
                is_user_defined=True,
                settable=True,
                parent_container_name="file_paths",
                initial_setup=True,
            )
        )
    node6_name = GriptapeNodes.handle_request(
        CreateNodeRequest(
            node_type="DisplayList",
            specific_library_name="Griptape Nodes Library",
            node_name="Display List",
            metadata={
                "position": {"x": 2682.089515012948, "y": 1655.1208358764438},
                "tempId": "placing-1765919344881-s3639o",
                "library_node_metadata": NodeMetadata(
                    category="lists",
                    description="Takes a list input and creates output parameters for each item in the list",
                    display_name="Display List",
                    tags=None,
                    icon=None,
                    color=None,
                    group="display",
                    deprecation=None,
                    is_node_group=None,
                ),
                "library": "Griptape Nodes Library",
                "node_type": "DisplayList",
                "showaddparameter": False,
                "size": {"width": 774, "height": 229},
                "category": "lists",
            },
            resolution="resolved",
            initial_setup=True,
        )
    ).node_name
    with GriptapeNodes.ContextManager().node(node6_name):
        GriptapeNodes.handle_request(
            AlterParameterDetailsRequest(
                parameter_name="display_list",
                type="list[str]",
                input_types=["list[str]"],
                output_type="list[str]",
                ui_options={"hide_property": False, "hide": False},
                initial_setup=True,
            )
        )
        GriptapeNodes.handle_request(
            AddParameterToNodeRequest(
                parameter_name="display_list_ParameterListUniqueParamID_494e9271a7784c01a1ca1f2dfb330dcd",
                tooltip="Output list. Your values will propagate in these inputs here.",
                type="str",
                input_types=["str"],
                output_type="str",
                ui_options={"hide_property": False, "hide": False},
                mode_allowed_input=False,
                mode_allowed_property=True,
                mode_allowed_output=True,
                is_user_defined=True,
                settable=True,
                parent_container_name="display_list",
                initial_setup=True,
            )
        )
    node7_name = GriptapeNodes.handle_request(
        CreateNodeRequest(
            node_type="StartFlow",
            specific_library_name="Griptape Nodes Library",
            node_name="Start Flow",
            metadata={
                "position": {"x": -2073.849695830111, "y": 943.0104570707665},
                "tempId": "placing-1765919427996-lqyf7kg",
                "library_node_metadata": NodeMetadata(
                    category="workflows",
                    description="Define the start of a workflow and pass parameters into the flow",
                    display_name="Start Flow",
                    tags=None,
                    icon=None,
                    color=None,
                    group="create",
                    deprecation=None,
                    is_node_group=None,
                ),
                "library": "Griptape Nodes Library",
                "node_type": "StartFlow",
                "showaddparameter": True,
                "size": {"width": 606, "height": 277},
                "category": "workflows",
            },
            resolution="resolved",
            initial_setup=True,
        )
    ).node_name
    with GriptapeNodes.ContextManager().node(node7_name):
        GriptapeNodes.handle_request(
            AddParameterToNodeRequest(
                parameter_name="name",
                default_value="",
                tooltip="New parameter",
                type="str",
                input_types=["any"],
                output_type="str",
                ui_options={
                    "placeholder_text": "Example: myfile or document",
                    "hide_label": False,
                    "hide_property": False,
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
    node8_name = GriptapeNodes.handle_request(
        CreateNodeRequest(
            node_type="EndFlow",
            specific_library_name="Griptape Nodes Library",
            node_name="End Flow",
            metadata={
                "position": {"x": 5119.6962420791715, "y": 1456.2639255759202},
                "tempId": "placing-1765919445139-b460ju",
                "library_node_metadata": NodeMetadata(
                    category="workflows",
                    description="Define the end of a workflow and return parameters from the flow",
                    display_name="End Flow",
                    tags=None,
                    icon=None,
                    color=None,
                    group="create",
                    deprecation=None,
                    is_node_group=None,
                ),
                "library": "Griptape Nodes Library",
                "node_type": "EndFlow",
                "showaddparameter": True,
                "size": {"width": 647, "height": 430},
                "category": "workflows",
            },
            resolution="resolved",
            initial_setup=True,
        )
    ).node_name
    GriptapeNodes.handle_request(
        CreateConnectionRequest(
            source_node_name=node0_name,
            source_parameter_name="path",
            target_node_name=node1_name,
            target_parameter_name="directory",
            initial_setup=True,
        )
    )
    GriptapeNodes.handle_request(
        CreateConnectionRequest(
            source_node_name=node1_name,
            source_parameter_name="filename",
            target_node_name=node2_name,
            target_parameter_name="output_path",
            initial_setup=True,
        )
    )
    GriptapeNodes.handle_request(
        CreateConnectionRequest(
            source_node_name=node1_name,
            source_parameter_name="filename",
            target_node_name=node3_name,
            target_parameter_name="source_paths_ParameterListUniqueParamID_31f3035837864ff1ae31fe4089332086",
            initial_setup=True,
        )
    )
    GriptapeNodes.handle_request(
        CreateConnectionRequest(
            source_node_name=node0_name,
            source_parameter_name="path",
            target_node_name=node4_name,
            target_parameter_name="directory",
            initial_setup=True,
        )
    )
    GriptapeNodes.handle_request(
        CreateConnectionRequest(
            source_node_name=node4_name,
            source_parameter_name="filename",
            target_node_name=node3_name,
            target_parameter_name="destination_path",
            initial_setup=True,
        )
    )
    GriptapeNodes.handle_request(
        CreateConnectionRequest(
            source_node_name=node0_name,
            source_parameter_name="exec_out",
            target_node_name=node1_name,
            target_parameter_name="exec_in",
            initial_setup=True,
        )
    )
    GriptapeNodes.handle_request(
        CreateConnectionRequest(
            source_node_name=node1_name,
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
            target_node_name=node4_name,
            target_parameter_name="exec_in",
            initial_setup=True,
        )
    )
    GriptapeNodes.handle_request(
        CreateConnectionRequest(
            source_node_name=node4_name,
            source_parameter_name="exec_out",
            target_node_name=node3_name,
            target_parameter_name="exec_in",
            initial_setup=True,
        )
    )
    GriptapeNodes.handle_request(
        CreateConnectionRequest(
            source_node_name=node3_name,
            source_parameter_name="copied_paths",
            target_node_name=node6_name,
            target_parameter_name="items",
            initial_setup=True,
        )
    )
    GriptapeNodes.handle_request(
        CreateConnectionRequest(
            source_node_name=node6_name,
            source_parameter_name="display_list_ParameterListUniqueParamID_a3e2daa1bc69469d8bcf7e179c9d6bc7",
            target_node_name=node5_name,
            target_parameter_name="file_paths_ParameterListUniqueParamID_bf35a91dffe249c594860d5d87f1f23b",
            initial_setup=True,
        )
    )
    GriptapeNodes.handle_request(
        CreateConnectionRequest(
            source_node_name=node1_name,
            source_parameter_name="filename",
            target_node_name=node5_name,
            target_parameter_name="file_paths_ParameterListUniqueParamID_9db4fb593cf94ff6a096373d9f6d4a31",
            initial_setup=True,
        )
    )
    GriptapeNodes.handle_request(
        CreateConnectionRequest(
            source_node_name=node3_name,
            source_parameter_name="exec_out",
            target_node_name=node6_name,
            target_parameter_name="exec_in",
            initial_setup=True,
        )
    )
    GriptapeNodes.handle_request(
        CreateConnectionRequest(
            source_node_name=node6_name,
            source_parameter_name="exec_out",
            target_node_name=node5_name,
            target_parameter_name="exec_in",
            initial_setup=True,
        )
    )
    GriptapeNodes.handle_request(
        CreateConnectionRequest(
            source_node_name=node7_name,
            source_parameter_name="name",
            target_node_name=node1_name,
            target_parameter_name="name",
            initial_setup=True,
        )
    )
    GriptapeNodes.handle_request(
        CreateConnectionRequest(
            source_node_name=node5_name,
            source_parameter_name="exec_out",
            target_node_name=node8_name,
            target_parameter_name="exec_in",
            initial_setup=True,
        )
    )
    GriptapeNodes.handle_request(
        CreateConnectionRequest(
            source_node_name=node5_name,
            source_parameter_name="result_details",
            target_node_name=node8_name,
            target_parameter_name="result_details",
            initial_setup=True,
        )
    )
    with GriptapeNodes.ContextManager().node(node0_name):
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="path",
                node_name=node0_name,
                value=top_level_unique_values_dict["969942c9-3db3-4a64-8024-84f8cec13b14"],
                initial_setup=True,
                is_output=False,
            )
        )
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="path",
                node_name=node0_name,
                value=top_level_unique_values_dict["969942c9-3db3-4a64-8024-84f8cec13b14"],
                initial_setup=True,
                is_output=True,
            )
        )
    with GriptapeNodes.ContextManager().node(node1_name):
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="directory",
                node_name=node1_name,
                value=top_level_unique_values_dict["969942c9-3db3-4a64-8024-84f8cec13b14"],
                initial_setup=True,
                is_output=False,
            )
        )
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="prefix",
                node_name=node1_name,
                value=top_level_unique_values_dict["75bd64b2-d9f0-41a3-9e95-8cd309df75f4"],
                initial_setup=True,
                is_output=False,
            )
        )
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="name",
                node_name=node1_name,
                value=top_level_unique_values_dict["e8ce4f96-a0df-400b-8a0a-562341a3c6bf"],
                initial_setup=True,
                is_output=False,
            )
        )
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="separator",
                node_name=node1_name,
                value=top_level_unique_values_dict["c73c4663-7d95-44f7-a65e-97804ede33a7"],
                initial_setup=True,
                is_output=False,
            )
        )
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="suffix",
                node_name=node1_name,
                value=top_level_unique_values_dict["915bb38a-5613-4b18-92e4-9a9668b2672f"],
                initial_setup=True,
                is_output=False,
            )
        )
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="extension",
                node_name=node1_name,
                value=top_level_unique_values_dict["283fe656-e079-4339-a5e2-251e1984d3d7"],
                initial_setup=True,
                is_output=False,
            )
        )
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="return_absolute_path",
                node_name=node1_name,
                value=top_level_unique_values_dict["c393cb99-3a44-47ec-a95d-0dbdd6a80e29"],
                initial_setup=True,
                is_output=False,
            )
        )
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="filename",
                node_name=node1_name,
                value=top_level_unique_values_dict["01428e67-1ea9-4b87-9650-472886a4f19e"],
                initial_setup=True,
                is_output=False,
            )
        )
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="filename",
                node_name=node1_name,
                value=top_level_unique_values_dict["01428e67-1ea9-4b87-9650-472886a4f19e"],
                initial_setup=True,
                is_output=True,
            )
        )
    with GriptapeNodes.ContextManager().node(node2_name):
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="text",
                node_name=node2_name,
                value=top_level_unique_values_dict["80636c21-3c85-4b1e-8e38-af4ea7c17085"],
                initial_setup=True,
                is_output=False,
            )
        )
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="output_path",
                node_name=node2_name,
                value=top_level_unique_values_dict["01428e67-1ea9-4b87-9650-472886a4f19e"],
                initial_setup=True,
                is_output=False,
            )
        )
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="output_path",
                node_name=node2_name,
                value=top_level_unique_values_dict["01428e67-1ea9-4b87-9650-472886a4f19e"],
                initial_setup=True,
                is_output=True,
            )
        )
    with GriptapeNodes.ContextManager().node(node3_name):
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="source_paths",
                node_name=node3_name,
                value=top_level_unique_values_dict["2d31db0d-ef0e-4ec4-a56b-ecda413faa1a"],
                initial_setup=True,
                is_output=False,
            )
        )
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="source_paths_ParameterListUniqueParamID_31f3035837864ff1ae31fe4089332086",
                node_name=node3_name,
                value=top_level_unique_values_dict["01428e67-1ea9-4b87-9650-472886a4f19e"],
                initial_setup=True,
                is_output=False,
            )
        )
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="destination_path",
                node_name=node3_name,
                value=top_level_unique_values_dict["2111570c-c172-43f7-84f2-aeb996773ed4"],
                initial_setup=True,
                is_output=False,
            )
        )
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="overwrite",
                node_name=node3_name,
                value=top_level_unique_values_dict["c393cb99-3a44-47ec-a95d-0dbdd6a80e29"],
                initial_setup=True,
                is_output=False,
            )
        )
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="copied_paths",
                node_name=node3_name,
                value=top_level_unique_values_dict["81c2c58f-a640-44ea-8474-ba2c2d4c95d9"],
                initial_setup=True,
                is_output=False,
            )
        )
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="copied_paths",
                node_name=node3_name,
                value=top_level_unique_values_dict["81c2c58f-a640-44ea-8474-ba2c2d4c95d9"],
                initial_setup=True,
                is_output=True,
            )
        )
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="progress",
                node_name=node3_name,
                value=top_level_unique_values_dict["355f7651-e1e0-4be6-ba39-94ec3c8ad6fd"],
                initial_setup=True,
                is_output=True,
            )
        )
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="was_successful",
                node_name=node3_name,
                value=top_level_unique_values_dict["c393cb99-3a44-47ec-a95d-0dbdd6a80e29"],
                initial_setup=True,
                is_output=False,
            )
        )
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="was_successful",
                node_name=node3_name,
                value=top_level_unique_values_dict["c393cb99-3a44-47ec-a95d-0dbdd6a80e29"],
                initial_setup=True,
                is_output=True,
            )
        )
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="result_details",
                node_name=node3_name,
                value=top_level_unique_values_dict["fbbe07cb-6305-40b7-8ec9-d467e905f0ae"],
                initial_setup=True,
                is_output=False,
            )
        )
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="result_details",
                node_name=node3_name,
                value=top_level_unique_values_dict["fbbe07cb-6305-40b7-8ec9-d467e905f0ae"],
                initial_setup=True,
                is_output=True,
            )
        )
    with GriptapeNodes.ContextManager().node(node4_name):
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="directory",
                node_name=node4_name,
                value=top_level_unique_values_dict["969942c9-3db3-4a64-8024-84f8cec13b14"],
                initial_setup=True,
                is_output=False,
            )
        )
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="prefix",
                node_name=node4_name,
                value=top_level_unique_values_dict["75bd64b2-d9f0-41a3-9e95-8cd309df75f4"],
                initial_setup=True,
                is_output=False,
            )
        )
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="name",
                node_name=node4_name,
                value=top_level_unique_values_dict["870358da-c991-4f91-9e08-78f9e393145e"],
                initial_setup=True,
                is_output=False,
            )
        )
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="separator",
                node_name=node4_name,
                value=top_level_unique_values_dict["c73c4663-7d95-44f7-a65e-97804ede33a7"],
                initial_setup=True,
                is_output=False,
            )
        )
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="suffix",
                node_name=node4_name,
                value=top_level_unique_values_dict["915bb38a-5613-4b18-92e4-9a9668b2672f"],
                initial_setup=True,
                is_output=False,
            )
        )
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="extension",
                node_name=node4_name,
                value=top_level_unique_values_dict["283fe656-e079-4339-a5e2-251e1984d3d7"],
                initial_setup=True,
                is_output=False,
            )
        )
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="return_absolute_path",
                node_name=node4_name,
                value=top_level_unique_values_dict["c393cb99-3a44-47ec-a95d-0dbdd6a80e29"],
                initial_setup=True,
                is_output=False,
            )
        )
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="filename",
                node_name=node4_name,
                value=top_level_unique_values_dict["2111570c-c172-43f7-84f2-aeb996773ed4"],
                initial_setup=True,
                is_output=False,
            )
        )
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="filename",
                node_name=node4_name,
                value=top_level_unique_values_dict["2111570c-c172-43f7-84f2-aeb996773ed4"],
                initial_setup=True,
                is_output=True,
            )
        )
    with GriptapeNodes.ContextManager().node(node5_name):
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="file_paths",
                node_name=node5_name,
                value=top_level_unique_values_dict["8dbc85e2-1d91-4aae-a2bd-540cb8c2ee5e"],
                initial_setup=True,
                is_output=False,
            )
        )
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="file_paths_ParameterListUniqueParamID_9db4fb593cf94ff6a096373d9f6d4a31",
                node_name=node5_name,
                value=top_level_unique_values_dict["01428e67-1ea9-4b87-9650-472886a4f19e"],
                initial_setup=True,
                is_output=False,
            )
        )
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="deleted_paths",
                node_name=node5_name,
                value=top_level_unique_values_dict["5b0dfb96-82d0-4983-84af-1d411c3e0430"],
                initial_setup=True,
                is_output=False,
            )
        )
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="deleted_paths",
                node_name=node5_name,
                value=top_level_unique_values_dict["5b0dfb96-82d0-4983-84af-1d411c3e0430"],
                initial_setup=True,
                is_output=True,
            )
        )
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="was_successful",
                node_name=node5_name,
                value=top_level_unique_values_dict["c393cb99-3a44-47ec-a95d-0dbdd6a80e29"],
                initial_setup=True,
                is_output=False,
            )
        )
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="was_successful",
                node_name=node5_name,
                value=top_level_unique_values_dict["c393cb99-3a44-47ec-a95d-0dbdd6a80e29"],
                initial_setup=True,
                is_output=True,
            )
        )
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="result_details",
                node_name=node5_name,
                value=top_level_unique_values_dict["3875ba80-b199-46f9-a86b-646afcaf53fb"],
                initial_setup=True,
                is_output=False,
            )
        )
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="result_details",
                node_name=node5_name,
                value=top_level_unique_values_dict["3875ba80-b199-46f9-a86b-646afcaf53fb"],
                initial_setup=True,
                is_output=True,
            )
        )
    with GriptapeNodes.ContextManager().node(node6_name):
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="items",
                node_name=node6_name,
                value=top_level_unique_values_dict["81c2c58f-a640-44ea-8474-ba2c2d4c95d9"],
                initial_setup=True,
                is_output=False,
            )
        )
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="display_list",
                node_name=node6_name,
                value=top_level_unique_values_dict["163d2ee3-7aef-4522-a80a-4fc29df28c33"],
                initial_setup=True,
                is_output=False,
            )
        )
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="display_list_ParameterListUniqueParamID_494e9271a7784c01a1ca1f2dfb330dcd",
                node_name=node6_name,
                value=top_level_unique_values_dict["2111570c-c172-43f7-84f2-aeb996773ed4"],
                initial_setup=True,
                is_output=False,
            )
        )
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="display_list_ParameterListUniqueParamID_494e9271a7784c01a1ca1f2dfb330dcd",
                node_name=node6_name,
                value=top_level_unique_values_dict["2111570c-c172-43f7-84f2-aeb996773ed4"],
                initial_setup=True,
                is_output=True,
            )
        )
    with GriptapeNodes.ContextManager().node(node7_name):
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="name",
                node_name=node7_name,
                value=top_level_unique_values_dict["e8ce4f96-a0df-400b-8a0a-562341a3c6bf"],
                initial_setup=True,
                is_output=False,
            )
        )
    with GriptapeNodes.ContextManager().node(node8_name):
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="exec_in",
                node_name=node8_name,
                value=top_level_unique_values_dict["9782dde2-168d-4826-b3e0-0015a9bafde2"],
                initial_setup=True,
                is_output=True,
            )
        )
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="was_successful",
                node_name=node8_name,
                value=top_level_unique_values_dict["c393cb99-3a44-47ec-a95d-0dbdd6a80e29"],
                initial_setup=True,
                is_output=False,
            )
        )
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="was_successful",
                node_name=node8_name,
                value=top_level_unique_values_dict["c393cb99-3a44-47ec-a95d-0dbdd6a80e29"],
                initial_setup=True,
                is_output=True,
            )
        )
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="result_details",
                node_name=node8_name,
                value=top_level_unique_values_dict["fcb91394-0ffd-4730-8c5d-df1a167a7173"],
                initial_setup=True,
                is_output=False,
            )
        )
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="result_details",
                node_name=node8_name,
                value=top_level_unique_values_dict["fcb91394-0ffd-4730-8c5d-df1a167a7173"],
                initial_setup=True,
                is_output=True,
            )
        )


def _ensure_workflow_context():
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
    input: dict,
    storage_backend: str = "local",
    workflow_executor: WorkflowExecutor | None = None,
    pickle_control_flow_result: bool = False,
) -> dict | None:
    return asyncio.run(
        aexecute_workflow(
            input=input,
            storage_backend=storage_backend,
            workflow_executor=workflow_executor,
            pickle_control_flow_result=pickle_control_flow_result,
        )
    )


async def aexecute_workflow(
    input: dict,
    storage_backend: str = "local",
    workflow_executor: WorkflowExecutor | None = None,
    pickle_control_flow_result: bool = False,
) -> dict | None:
    _ensure_workflow_context()
    storage_backend_enum = StorageBackend(storage_backend)
    workflow_executor = workflow_executor or LocalWorkflowExecutor(storage_backend=storage_backend_enum)
    async with workflow_executor as executor:
        await executor.arun(flow_input=input, pickle_control_flow_result=pickle_control_flow_result)
    return executor.output


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
    parser.add_argument("--exec_out", default=None, help="Connection to the next node in the execution chain")
    parser.add_argument("--name", default=None, help="New parameter")
    args = parser.parse_args()
    flow_input = {}
    if args.json_input is not None:
        flow_input = json.loads(args.json_input)
    if args.json_input is None:
        if "Start Flow" not in flow_input:
            flow_input["Start Flow"] = {}
        if args.exec_out is not None:
            flow_input["Start Flow"]["exec_out"] = args.exec_out
        if args.name is not None:
            flow_input["Start Flow"]["name"] = args.name
    workflow_output = execute_workflow(input=flow_input, storage_backend=args.storage_backend)
    print(workflow_output)
