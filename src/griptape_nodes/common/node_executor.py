from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from griptape_nodes.exe_types.core_types import ParameterTypeBuiltin
from griptape_nodes.exe_types.node_types import LOCAL_EXECUTION, EndNode, StartNode
from griptape_nodes.node_library.library_registry import Library, LibraryRegistry
from griptape_nodes.retained_mode.events.flow_events import (
    PackageNodeAsSerializedFlowRequest,
    PackageNodeAsSerializedFlowResultSuccess,
)
from griptape_nodes.retained_mode.events.workflow_events import (
    PublishWorkflowRequest,
    SaveWorkflowFileFromSerializedFlowRequest,
    SaveWorkflowFileFromSerializedFlowResultSuccess,
)
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

if TYPE_CHECKING:
    from griptape_nodes.exe_types.node_types import BaseNode
    from griptape_nodes.node_library.advanced_node_library import AdvancedNodeLibrary
    from griptape_nodes.retained_mode.managers.library_manager import LibraryManager

logger = logging.getLogger("griptape_nodes")


class NodeExecutor:
    """Simple singleton executor that draws methods from libraries and executes them dynamically."""
    advanced_libraries: dict[str, AdvancedNodeLibrary]

    def __init__(self) -> None:
        self._advanced_libraries = {}

    def load_library(self, library: Library) -> None:
        advanced_library = library.get_advanced_library()
        library_name = library.get_library_data().name
        if advanced_library is not None:
            self._advanced_libraries[library_name] = advanced_library

    def unload_library(self, library_name:str) -> None:
        if library_name in self._advanced_libraries:
            del self._advanced_libraries[library_name]

    def get_workflow_handler(self, library_name: str) -> LibraryManager.RegisteredEventHandler | None:
        """Get the PublishWorkflowRequest handler for a library, or None if not available."""
        if library_name in self._advanced_libraries:

            library_manager = GriptapeNodes.LibraryManager()
            registered_handlers = library_manager.get_registered_event_handlers(PublishWorkflowRequest)
            if library_name in registered_handlers:
                return registered_handlers[library_name]
        return None

    async def execute(self, node: BaseNode, library_name: str | None = None) -> None:
        """Execute the given node.

        Args:
            node: The BaseNode to execute
            library_name: The library that the execute method should come from.
        """
        execution_type = node.get_parameter_value(node.execution_environment.name)
        if execution_type != LOCAL_EXECUTION:
            try:
                # Get the node's library name
                library = LibraryRegistry.get_library(name=execution_type)
            except KeyError:
                # Fallback to default node processing
                logger.error("Could not find library for node '%s', defaulting to local execution.", node.name)
                await node.aprocess()
                return
            library_name = library.get_library_data().name
            # Check if the library has a PublishWorkflowRequest handler
            workflow_handler = self.get_workflow_handler(library_name)
            if workflow_handler is not None:
                # Call the library's workflow handler
                start_node_type = library.get_nodes_by_base_type(StartNode)
                if len(start_node_type) > 0:
                    start_node_type = start_node_type[0]
                else:
                    start_node_type = "StartFlow"
                end_node_type = library.get_nodes_by_base_type(EndNode)
                # Uses the libraries start and end node types if they exist.
                if len(end_node_type) > 0:
                    end_node_type = end_node_type[0]
                else:
                    end_node_type = "EndFlow"
                # Get a name for the output parameter prefix - attached to node name because node names are unique.
                # We may have to have multiple prefixes if we end up having multiple nodes attached to one EndFlow.
                sanitized_name = node.name.replace(" ", "_")
                output_parameter_prefix = f"{sanitized_name}_packaged_node_"
                request = PackageNodeAsSerializedFlowRequest(
                    node_name= node.name,
                    start_node_type=start_node_type,
                    end_node_type=end_node_type,
                    start_end_specific_library_name=library_name,
                    # Provide the entry control parameter name if it exists.
                    entry_control_parameter_name=node._entry_control_parameter.name if node._entry_control_parameter is not None else None,
                    output_parameter_prefix=output_parameter_prefix
                )
                # now we package the flow into a serialized flow commands.
                package_result = GriptapeNodes.handle_request(request)
                if not isinstance(package_result, PackageNodeAsSerializedFlowResultSuccess):
                    msg = f"Failed to package node '{node.name}'. Error: {package_result.result_details}"
                    raise ValueError(msg)
                file_name = f"{node.name}_{library_name}_packaged_flow"
                workflow_file_request = SaveWorkflowFileFromSerializedFlowRequest(file_name=file_name,serialized_flow_commands=package_result.serialized_flow_commands)
                workflow_result = GriptapeNodes.handle_request(workflow_file_request)
                if not isinstance(workflow_result, SaveWorkflowFileFromSerializedFlowResultSuccess):
                    msg = f"Failed to Save Workflow File from Serialized Flow for node '{node.name}'. Error: {package_result.result_details}"
                    raise ValueError(msg)
                #TODO: Call Zach's PublishWorkflowRequest executor, running the workflow_rest.file_path in memory!

                #TODO: Call Zach's Subprocess Execute exector, which runs the created workflow file from the PublishWorkflowRequest.

                my_subprocess_result = subprocess_executor.output
                # {end_node_name: parameter_output_values dict}
                # For now, we know we have one end node, I believe.
                parameter_output_values = {k: v for result_dict in my_subprocess_result.values() for k, v in result_dict.items()}
                #TODO: How do we handle pickled values?
                # Remove the output_parameter_prefix and set values on BaseNode
                for param_name, param_value in parameter_output_values.items():
                    if param_name.startswith(output_parameter_prefix):
                        clean_param_name = param_name[len(output_parameter_prefix):]
                        # Set this value for certain hacks
                        parameter = node.get_parameter_by_name(clean_param_name)
                        if parameter is not None:
                            # Don't run set_parameter_value on control parameters
                            if parameter.type != ParameterTypeBuiltin.CONTROL_TYPE:
                                node.set_parameter_value(clean_param_name, param_value)
                            # Set this value for output values. Include if a control parameter has an output value, because it signals the path to take.
                            node.parameter_output_values[clean_param_name] = param_value
                return
        # Fallback to default node processing
        await node.aprocess()
        return

    def clear(self) -> None:
        self._advanced_libraries = {}
