# /// script
# dependencies = []
#
# [tool.griptape-nodes]
# name = "/Users/cjkindel/nodes/griptape-nodes/GriptapeNodes2/workflow"
# schema_version = "0.16.0"
# engine_version_created_with = "0.80.0"
# node_libraries_referenced = [["numpy-collision-test-v0", "0.1.0"]]
# node_types_used = [["numpy-collision-test-v0", "NumpyVersion0"]]
# is_griptape_provided = false
# is_template = false
# creation_date = 2026-04-14T22:01:32.218735Z
# last_modified_date = 2026-04-15T17:39:13.668578Z
#
# ///

import pickle

from griptape_nodes.node_library.library_registry import NodeMetadata
from griptape_nodes.retained_mode.events.flow_events import CreateFlowRequest
from griptape_nodes.retained_mode.events.library_events import RegisterLibraryFromFileRequest
from griptape_nodes.retained_mode.events.node_events import CreateNodeRequest
from griptape_nodes.retained_mode.events.parameter_events import (
    SetParameterValueRequest,
)
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

GriptapeNodes.handle_request(
    RegisterLibraryFromFileRequest(library_name="numpy-collision-test-v0", perform_discovery_if_not_found=True)
)

context_manager = GriptapeNodes.ContextManager()

if not context_manager.has_current_workflow():
    context_manager.push_workflow(file_path=__file__)

"""
1. We've collated all of the unique parameter values into a dictionary so that we do not have to duplicate them.
   This minimizes the size of the code, especially for large objects like serialized image files.
2. We're using a prefix so that it's clear which Flow these values are associated with.
3. The values are serialized using pickle, which is a binary format. This makes them harder to read, but makes
   them consistently save and load. It allows us to serialize complex objects like custom classes, which otherwise
   would be difficult to serialize.
"""
top_level_unique_values_dict = {
    "cb90896d-1c7c-4b90-8438-dbfc8415e816": pickle.loads(
        b"\x80\x04\x95\t\x00\x00\x00\x00\x00\x00\x00\x8c\x052.4.3\x94."
    )
}

"# Create the Flow, then do work within it as context."

flow0_name = GriptapeNodes.handle_request(
    CreateFlowRequest(parent_flow_name=None, flow_name="ControlFlow_1", set_as_new_context=False, metadata={})
).flow_name

with GriptapeNodes.ContextManager().flow(flow0_name):
    node0_name = GriptapeNodes.handle_request(
        CreateNodeRequest(
            node_type="NumpyVersion0",
            specific_library_name="numpy-collision-test-v0",
            node_name="Numpy Version (v0)",
            metadata={
                "position": {"x": 1138.3333333333335, "y": 611.6666666666667},
                "tempId": "placing-1776196198105-tw3bvxv",
                "library_node_metadata": NodeMetadata(
                    category="NumpyCollisionTest",
                    description="Returns the numpy version visible to this library's worker subprocess. Expected output: '2.4.3'.",
                    display_name="Numpy Version (v0)",
                    tags=["test"],
                    icon="Flask",
                    color=None,
                    group=None,
                    deprecation=None,
                    is_node_group=None,
                ),
                "library": "numpy-collision-test-v0",
                "node_type": "NumpyVersion0",
                "showaddparameter": False,
                "size": {"width": 600, "height": 196},
            },
            resolution="resolved",
            initial_setup=True,
        )
    ).node_name
    with GriptapeNodes.ContextManager().node(node0_name):
        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name="version",
                node_name=node0_name,
                value=top_level_unique_values_dict["cb90896d-1c7c-4b90-8438-dbfc8415e816"],
                initial_setup=True,
                is_output=True,
            )
        )
