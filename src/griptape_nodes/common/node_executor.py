from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any

from griptape_nodes.exe_types.node_types import StartNode, EndNode, LOCAL_EXECUTION
from griptape_nodes.node_library.library_registry import Library, LibraryRegistry
from griptape_nodes.retained_mode.events.flow_events import PackageNodeAsSerializedFlowRequest, PackageNodeAsSerializedFlowResultSuccess
from griptape_nodes.retained_mode.managers.library_manager import LibraryManager
from griptape_nodes.retained_mode.events.workflow_events import PublishWorkflowRequest, SaveWorkflowFileFromSerializedFlowRequest, SaveWorkflowFileFromSerializedFlowResultSuccess
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

if TYPE_CHECKING:
    from griptape_nodes.exe_types.node_types import BaseNode
    from griptape_nodes.node_library.advanced_node_library import AdvancedNodeLibrary

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

    async def execute_method(self, method_name: str, library_name: str | None = None, *args: Any, **kwargs: Any) -> Any:
        """Execute a method by name with given arguments."""
        if library_name and library_name in self._advanced_libraries:
            advanced_library = self._advanced_libraries[library_name]
            if hasattr(advanced_library, method_name):
                method = getattr(advanced_library, method_name)
                if callable(method):
                    logger.debug("Executing method '%s' from library '%s'", method_name, library_name)
                    if asyncio.iscoroutinefunction(method):
                        return await method(*args, **kwargs)
                    return method(*args, **kwargs)
            msg = f"Method '{method_name}' not found in library '{library_name}'"
            raise KeyError(msg)

        msg = f"No library specified or library '{library_name}' not found"
        raise KeyError(msg)

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
        #TODO: Use some type of config base to determine if a node should use a handler here, and grouping.
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
                # TODO: Call the publishworkflow handler with the workflow file given.
                start_node_type = library.get_nodes_by_base_type(StartNode)[0]
                end_node_type = library.get_nodes_by_base_type(EndNode)[0]
                request = PackageNodeAsSerializedFlowRequest(
                    node_name= node.name,
                    start_node_type=start_node_type,
                    end_node_type=end_node_type,
                    start_end_specific_library_name=library_name,
                    # TODO: How are we going to set this?
                    entry_control_parameter_name=None
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
                # TODO: What is the workflow metadata for?
                publish_request = PublishWorkflowRequest(workflow_name=workflow_result.file_path, publisher_name=library_name, execute_on_publish=True, published_workflow_file_name=workflow_result.file_path)
                publish_result = await workflow_handler.handler(publish_request)
                #TODO: handle the result shape - maybe this should be defined in library too.

                return
        # Fallback to default node processing
        await node.aprocess()

    def clear(self) -> None:
        self._advanced_libraries = {}
