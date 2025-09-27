from __future__ import annotations

import logging
from pathlib import Path
import pickle
from typing import TYPE_CHECKING

from griptape_nodes.bootstrap.workflow_executors.local_workflow_executor import LocalWorkflowExecutor
from griptape_nodes.bootstrap.workflow_publishers.subprocess_workflow_publisher import SubprocessWorkflowPublisher
from griptape_nodes.drivers.storage.storage_backend import StorageBackend
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

    def unload_library(self, library_name: str) -> None:
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
                sanitized_node_name = node.name.replace(" ", "_")
                output_parameter_prefix = f"{sanitized_node_name}_packaged_node_"
                sanitized_library_name = library_name.replace(" ", "_")
                request = PackageNodeAsSerializedFlowRequest(
                    node_name=node.name,
                    start_node_type=start_node_type,
                    end_node_type=end_node_type,
                    start_end_specific_library_name=library_name,
                    # Provide the entry control parameter name if it exists.
                    entry_control_parameter_name=node._entry_control_parameter.name
                    if node._entry_control_parameter is not None
                    else None,
                    output_parameter_prefix=output_parameter_prefix,
                )
                # now we package the flow into a serialized flow commands.
                package_result = GriptapeNodes.handle_request(request)
                if not isinstance(package_result, PackageNodeAsSerializedFlowResultSuccess):
                    msg = f"Failed to package node '{node.name}'. Error: {package_result.result_details}"
                    raise ValueError(msg)
                file_name = f"{sanitized_node_name}_{sanitized_library_name}_packaged_flow"
                workflow_file_request = SaveWorkflowFileFromSerializedFlowRequest(
                    file_name=file_name, serialized_flow_commands=package_result.serialized_flow_commands
                )
                workflow_result = GriptapeNodes.handle_request(workflow_file_request)
                if not isinstance(workflow_result, SaveWorkflowFileFromSerializedFlowResultSuccess):
                    msg = f"Failed to Save Workflow File from Serialized Flow for node '{node.name}'. Error: {package_result.result_details}"
                    raise ValueError(msg)
                local_workflow_publisher = SubprocessWorkflowPublisher()
                # Remove .py extension from the original file path and add _published
                published_filename = f"{Path(workflow_result.file_path).stem}_published"
                published_workflow_filename = GriptapeNodes.ConfigManager().workspace_path / (published_filename + ".py")
                # Get the full path where the published workflow will be saved
                await local_workflow_publisher.arun(
                    workflow_name="TestDeadlineCloud", workflow_path=workflow_result.file_path, publisher_name=library_name, published_workflow_file_name=published_filename
                )
                if not Path(published_workflow_filename).exists():
                    msg = f"Published workflow file does not exist at path: {published_workflow_filename}"
                    raise FileNotFoundError(msg)
                #Run the subprocess.
                from griptape_nodes.bootstrap.workflow_executors.subprocess_workflow_executor import SubprocessWorkflowExecutor
                subprocess_executor = SubprocessWorkflowExecutor(workflow_path=published_workflow_filename)
                #TODO: How do I determine storage backend?
                async with subprocess_executor as executor:
                    await executor.arun(workflow_name="TestDeadlineCloud", flow_input={}, storage_backend=StorageBackend.LOCAL)
                my_subprocess_result = subprocess_executor.output
                # Error handle for this
                if my_subprocess_result is None:
                    msg = "Subprocess result is None."
                    raise ValueError(msg)
                # For now, we know we have one end node, I believe.
                # Extract parameter output values and deserialize pickled values if present
                parameter_output_values = {}
                for end_node_name, result_dict in my_subprocess_result.items():
                    # Handle new structure with pickled values
                    if isinstance(result_dict, dict) and "parameter_output_values" in result_dict:
                        param_output_vals = result_dict["parameter_output_values"]
                        unique_uuid_to_values = result_dict.get("unique_parameter_uuid_to_values")

                        # Deserialize UUID references back to actual values
                        if unique_uuid_to_values:
                            for param_name, param_value in param_output_vals.items():
                                if param_value in unique_uuid_to_values:
                                    # This is a UUID reference, replace with actual pickled value
                                    parameter_output_values[param_name] = pickle.loads(unique_uuid_to_values[param_value])
                                else:
                                    # This is either a direct value or None (for non-serializable values)
                                    parameter_output_values[param_name] = param_value
                        else:
                            # No pickled values, use parameter output values directly
                            parameter_output_values.update(param_output_vals)
                    else:
                        # Backward compatibility: old structure (flat dictionary)
                        parameter_output_values.update(result_dict)
                # Remove the output_parameter_prefix and set values on BaseNode
                for param_name, param_value in parameter_output_values.items():
                    if param_name.startswith(output_parameter_prefix):
                        clean_param_name = param_name[len(output_parameter_prefix) :]
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
