from __future__ import annotations

import ast
import asyncio
import logging
import pickle
from pathlib import Path
from typing import TYPE_CHECKING, Any, NamedTuple

from griptape_nodes.bootstrap.workflow_publishers.subprocess_workflow_publisher import SubprocessWorkflowPublisher
from griptape_nodes.drivers.storage.storage_backend import StorageBackend
from griptape_nodes.exe_types.base_iterative_nodes import (
    BaseIterativeEndNode,
    BaseIterativeStartNode,
)
from griptape_nodes.exe_types.core_types import ParameterTypeBuiltin
from griptape_nodes.exe_types.node_types import (
    CONTROL_INPUT_PARAMETER,
    LOCAL_EXECUTION,
    PRIVATE_EXECUTION,
    BaseNode,
    EndNode,
    NodeGroup,
    NodeGroupProxyNode,
    NodeResolutionState,
    StartNode,
)
from griptape_nodes.machines.dag_builder import DagBuilder
from griptape_nodes.node_library.library_registry import Library, LibraryRegistry
from griptape_nodes.node_library.workflow_registry import WorkflowRegistry
from griptape_nodes.retained_mode.events.connection_events import (
    ListConnectionsForNodeRequest,
    ListConnectionsForNodeResultSuccess,
)
from griptape_nodes.retained_mode.events.execution_events import (
    StartLocalSubflowRequest,
    StartLocalSubflowResultSuccess,
)
from griptape_nodes.retained_mode.events.flow_events import (
    DeleteFlowRequest,
    DeleteFlowResultSuccess,
    DeserializeFlowFromCommandsRequest,
    DeserializeFlowFromCommandsResultSuccess,
    PackageNodesAsSerializedFlowRequest,
    PackageNodesAsSerializedFlowResultSuccess,
)
from griptape_nodes.retained_mode.events.parameter_events import (
    SetParameterValueRequest,
    SetParameterValueResultSuccess,
)
from griptape_nodes.retained_mode.events.workflow_events import (
    DeleteWorkflowRequest,
    DeleteWorkflowResultFailure,
    LoadWorkflowMetadata,
    LoadWorkflowMetadataResultSuccess,
    PublishWorkflowRequest,
    SaveWorkflowFileFromSerializedFlowRequest,
    SaveWorkflowFileFromSerializedFlowResultSuccess,
)
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
from griptape_nodes.retained_mode.managers.event_manager import EventSuppressionContext

if TYPE_CHECKING:
    from griptape_nodes.exe_types.connections import Connections
    from griptape_nodes.retained_mode.events.node_events import SerializedNodeCommands
    from griptape_nodes.retained_mode.managers.library_manager import LibraryManager

logger = logging.getLogger("griptape_nodes")

LOOP_EVENTS_TO_SUPPRESS = [
    "CreateFlowResultSuccess",
    "CreateFlowResultFailure",
    "ImportWorkflowAsReferencedSubFlowResultSuccess",
    "ImportWorkflowAsReferencedSubFlowResultFailure",
    "DeserializeNodeFromCommandsResultSuccess",
    "DeserializeNodeFromCommandsResultFailure",
    "CreateConnectionResultSuccess",
    "CreateConnectionResultFailure",
    "SetParameterValueResultSuccess",
    "SetParameterValueResultFailure",
    "SetLockNodeStateResultSuccess",
    "SetLockNodeStateResultFailure",
    "DeserializeFlowFromCommandsResultSuccess",
    "DeserializeFlowFromCommandsResultFailure",
]

EXECUTION_EVENTS_TO_SUPPRESS = [
    "CurrentControlNodeEvent",
    "CurrentDataNodeEvent",
    "SelectedControlOutputEvent",
    "ParameterSpotlightEvent",
    "ControlFlowResolvedEvent",
    "ControlFlowCancelledEvent",
    "NodeResolvedEvent",
    "ParameterValueUpdateEvent",
    "NodeUnresolvedEvent",
    "NodeStartProcessEvent",
    "NodeFinishProcessEvent",
    "InvolvedNodesEvent",
    "GriptapeEvent",
    "PublishWorkflowProgressEvent",
    "AgentStreamEvent",
    "AlterElementEvent",
    "RemoveElementEvent",
    "ProgressEvent",
    "StartLocalSubflowResultSuccess",
    "StartLocalSubflowResultFailure",
]


class PublishLocalWorkflowResult(NamedTuple):
    """Result from publishing a local workflow."""

    workflow_result: SaveWorkflowFileFromSerializedFlowResultSuccess
    file_name: str
    output_parameter_prefix: str
    package_result: PackageNodesAsSerializedFlowResultSuccess


class NodeExecutor:
    """Singleton executor that executes nodes dynamically."""

    def get_workflow_handler(self, library_name: str) -> LibraryManager.RegisteredEventHandler:
        """Get the PublishWorkflowRequest handler for a library, or None if not available."""
        library_manager = GriptapeNodes.LibraryManager()
        registered_handlers = library_manager.get_registered_event_handlers(PublishWorkflowRequest)
        if library_name in registered_handlers:
            return registered_handlers[library_name]
        msg = f"Could not find PublishWorkflowRequest handler for library {library_name}"
        raise ValueError(msg)

    async def execute(self, node: BaseNode) -> None:
        """Execute the given node.

        Args:
            node: The BaseNode to execute
            library_name: The library that the execute method should come from.
        """
        execution_type = node.get_parameter_value(node.execution_environment.name)

        # If this is a loop node, we need to handle it totally differently.
        # if False:
        if isinstance(node, BaseIterativeEndNode):
            await self.handle_loop_execution(node, execution_type)
            return

        if execution_type == LOCAL_EXECUTION:
            await node.aprocess()
        elif execution_type == PRIVATE_EXECUTION:
            await self._execute_private_workflow(node)
        else:
            await self._execute_library_workflow(node, execution_type)

    async def _execute_and_apply_workflow(
        self,
        node: BaseNode,
        workflow_path: Path,
        file_name: str,
        package_result: PackageNodesAsSerializedFlowResultSuccess,
    ) -> None:
        """Execute workflow in subprocess and apply results to node.

        Args:
            node: The node to apply results to
            workflow_path: Path to workflow file to execute
            file_name: Name of workflow for logging
            package_result: The packaging result containing parameter mappings
        """
        my_subprocess_result = await self._execute_subprocess(workflow_path, file_name)
        parameter_output_values = self._extract_parameter_output_values(my_subprocess_result)
        self._apply_parameter_values_to_node(node, parameter_output_values, package_result)

    async def _execute_private_workflow(self, node: BaseNode) -> None:
        """Execute node in private subprocess environment.

        Args:
            node: The node to execute
        """
        workflow_result = None
        try:
            result = await self._publish_local_workflow(node)
            workflow_result = result.workflow_result
        except Exception as e:
            logger.exception(
                "Failed to publish local workflow for node '%s'. Node type: %s",
                node.name,
                node.__class__.__name__,
            )
            msg = f"Failed to publish workflow for node '{node.name}': {e}"
            raise RuntimeError(msg) from e

        try:
            await self._execute_and_apply_workflow(
                node=node,
                workflow_path=Path(workflow_result.file_path),
                file_name=result.file_name,
                package_result=result.package_result,
            )
        except RuntimeError:
            raise
        except Exception as e:
            logger.exception(
                "Subprocess execution failed for node '%s'. Node type: %s",
                node.name,
                node.__class__.__name__,
            )
            msg = f"Failed to execute node '{node.name}' in local subprocess: {e}"
            raise RuntimeError(msg) from e
        finally:
            if workflow_result is not None:
                await self._delete_workflow(
                    workflow_result.workflow_metadata.name, workflow_path=Path(workflow_result.file_path)
                )

    async def _execute_library_workflow(self, node: BaseNode, execution_type: str) -> None:
        """Execute node via library handler.

        Args:
            node: The node to execute
            execution_type: Library name for execution
        """
        try:
            library = LibraryRegistry.get_library(name=execution_type)
        except KeyError:
            msg = f"Could not find library for execution environment {execution_type} for node {node.name}."
            raise RuntimeError(msg)  # noqa: B904

        library_name = library.get_library_data().name

        try:
            self.get_workflow_handler(library_name)
        except ValueError as e:
            logger.error("Library execution failed for node '%s' via library '%s': %s", node.name, library_name, e)
            msg = f"Failed to execute node '{node.name}' via library '{library_name}': {e}"
            raise RuntimeError(msg) from e

        workflow_result = None
        published_workflow_filename = None

        try:
            result = await self._publish_local_workflow(node, library=library)
            workflow_result = result.workflow_result
        except Exception as e:
            logger.exception(
                "Failed to publish local workflow for node '%s' via library '%s'. Node type: %s",
                node.name,
                library_name,
                node.__class__.__name__,
            )
            msg = f"Failed to publish workflow for node '{node.name}' via library '{library_name}': {e}"
            raise RuntimeError(msg) from e

        try:
            published_workflow_filename = await self._publish_library_workflow(
                workflow_result, library_name, result.file_name
            )
        except Exception as e:
            logger.exception(
                "Failed to publish library workflow for node '%s' via library '%s'. Node type: %s",
                node.name,
                library_name,
                node.__class__.__name__,
            )
            msg = f"Failed to publish library workflow for node '{node.name}' via library '{library_name}': {e}"
            raise RuntimeError(msg) from e

        try:
            await self._execute_and_apply_workflow(
                node,
                published_workflow_filename,
                result.file_name,
                result.package_result,
            )
        except RuntimeError:
            raise
        except Exception as e:
            logger.exception(
                "Subprocess execution failed for node '%s' via library '%s'. Node type: %s",
                node.name,
                library_name,
                node.__class__.__name__,
            )
            msg = f"Failed to execute node '{node.name}' via library '{library_name}': {e}"
            raise RuntimeError(msg) from e
        finally:
            if workflow_result is not None:
                await self._delete_workflow(
                    workflow_name=workflow_result.workflow_metadata.name, workflow_path=Path(workflow_result.file_path)
                )
            if published_workflow_filename is not None:
                published_filename = published_workflow_filename.stem
                await self._delete_workflow(workflow_name=published_filename, workflow_path=published_workflow_filename)

    async def _publish_local_workflow(
        self, node: BaseNode, library: Library | None = None
    ) -> PublishLocalWorkflowResult:
        """Package and publish a workflow for subprocess execution.

        Returns:
            PublishLocalWorkflowResult containing workflow_result, file_name, and output_parameter_prefix
        """
        sanitized_node_name = node.name.replace(" ", "_")
        output_parameter_prefix = f"{sanitized_node_name}_packaged_node_"
        # We have to make our defaults strings because the PackageNodesAsSerializedFlowRequest doesn't accept None types.
        library_name = "Griptape Nodes Library"
        start_node_type = "StartFlow"
        end_node_type = "EndFlow"
        if library is not None:
            start_nodes = library.get_nodes_by_base_type(StartNode)
            end_nodes = library.get_nodes_by_base_type(EndNode)
            if len(start_nodes) > 0 and len(end_nodes) > 0:
                start_node_type = start_nodes[0]
                end_node_type = end_nodes[0]
                library_name = library.get_library_data().name
        sanitized_library_name = library_name.replace(" ", "_")
        # If we are packaging a NodeGroupProxyNode, that means that we are packaging multiple nodes together, so we have to get the list of nodes from the proxy node.
        if isinstance(node, NodeGroupProxyNode):
            node_names = list(node.node_group_data.nodes.keys())
        else:
            # Otherwise, it's a list of one node!
            node_names = [node.name]

        # Pass the proxy node if this is a NodeGroupProxyNode so serialization can use stored connections
        proxy_node_for_packaging = node if isinstance(node, NodeGroupProxyNode) else None

        request = PackageNodesAsSerializedFlowRequest(
            node_names=node_names,
            start_node_type=start_node_type,
            end_node_type=end_node_type,
            start_end_specific_library_name=library_name,
            output_parameter_prefix=output_parameter_prefix,
            entry_control_node_name=None,
            entry_control_parameter_name=None,
            proxy_node=proxy_node_for_packaging,
        )
        package_result = GriptapeNodes.handle_request(request)
        if not isinstance(package_result, PackageNodesAsSerializedFlowResultSuccess):
            msg = f"Failed to package node '{node.name}'. Error: {package_result.result_details}"
            raise RuntimeError(msg)  # noqa: TRY004

        file_name = f"{sanitized_node_name}_{sanitized_library_name}_packaged_flow"
        workflow_file_request = SaveWorkflowFileFromSerializedFlowRequest(
            file_name=file_name,
            serialized_flow_commands=package_result.serialized_flow_commands,
            workflow_shape=package_result.workflow_shape,
            pickle_control_flow_result=True,
        )

        workflow_result = await GriptapeNodes.ahandle_request(workflow_file_request)
        if not isinstance(workflow_result, SaveWorkflowFileFromSerializedFlowResultSuccess):
            msg = f"Failed to Save Workflow File from Serialized Flow for node '{node.name}'. Error: {workflow_result.result_details}"
            raise RuntimeError(msg)  # noqa: TRY004

        return PublishLocalWorkflowResult(
            workflow_result=workflow_result,
            file_name=file_name,
            output_parameter_prefix=output_parameter_prefix,
            package_result=package_result,
        )

    async def _publish_library_workflow(
        self, workflow_result: SaveWorkflowFileFromSerializedFlowResultSuccess, library_name: str, file_name: str
    ) -> Path:
        subprocess_workflow_publisher = SubprocessWorkflowPublisher()
        published_filename = f"{Path(workflow_result.file_path).stem}_published"
        published_workflow_filename = GriptapeNodes.ConfigManager().workspace_path / (published_filename + ".py")

        await subprocess_workflow_publisher.arun(
            workflow_name=file_name,
            workflow_path=workflow_result.file_path,
            publisher_name=library_name,
            published_workflow_file_name=published_filename,
            pickle_control_flow_result=True,
        )

        if not published_workflow_filename.exists():
            msg = f"Published workflow file does not exist at path: {published_workflow_filename}"
            raise FileNotFoundError(msg)

        return published_workflow_filename

    async def _execute_subprocess(
        self,
        published_workflow_filename: Path,
        file_name: str,
        pickle_control_flow_result: bool = True,  # noqa: FBT001, FBT002
        flow_input: dict[str, Any] | None = None,
    ) -> dict[str, dict[str | SerializedNodeCommands.UniqueParameterValueUUID, Any] | None]:
        """Execute the published workflow in a subprocess.

        Args:
            published_workflow_filename: Path to the workflow file to execute
            file_name: Name of the workflow for logging
            pickle_control_flow_result: Whether to pickle control flow results (defaults to True)
            flow_input: Optional dictionary of parameter values to pass to the workflow's StartFlow node

        Returns:
            The subprocess execution output dictionary
        """
        from griptape_nodes.bootstrap.workflow_executors.subprocess_workflow_executor import (
            SubprocessWorkflowExecutor,
        )

        subprocess_executor = SubprocessWorkflowExecutor(workflow_path=str(published_workflow_filename))

        try:
            async with subprocess_executor as executor:
                await executor.arun(
                    flow_input=flow_input or {},
                    storage_backend=await self._get_storage_backend(),
                    pickle_control_flow_result=pickle_control_flow_result,
                )
        except RuntimeError as e:
            # Subprocess returned non-zero exit code
            logger.error(
                "Subprocess execution failed for workflow '%s' at path '%s'. Error: %s",
                file_name,
                published_workflow_filename,
                e,
            )
            raise

        my_subprocess_result = subprocess_executor.output
        if my_subprocess_result is None:
            msg = f"Subprocess completed but returned no output for workflow '{file_name}'"
            logger.error(msg)
            raise ValueError(msg)
        return my_subprocess_result

    async def handle_loop_execution(self, node: BaseIterativeEndNode, execution_type: str) -> None:  # noqa: C901, PLR0912, PLR0915
        """Handle execution of a loop by packaging nodes from start to end and running them.

        Args:
            node: The BaseIterativeEndNode marking the end of the loop
            execution_type: The execution environment type
        """
        # Validate start node exists
        if node.start_node is None:
            msg = f"BaseIterativeEndNode '{node.name}' has no start_node reference"
            raise ValueError(msg)

        start_node = node.start_node

        # Initialize iteration data to determine total iterations
        if hasattr(start_node, "_initialize_iteration_data"):
            start_node._initialize_iteration_data()  # pyright: ignore[reportAttributeAccessIssue]

        total_iterations = start_node._get_total_iterations()
        if total_iterations == 0:
            logger.info("No iterations for empty loop from '%s' to '%s'", start_node.name, node.name)
            return
        flow_manager = GriptapeNodes.FlowManager()
        connections = flow_manager.get_connections()

        # Step 1: Collect all nodes in the forward control path from start to end
        nodes_in_control_flow = DagBuilder.collect_nodes_in_forward_control_path(start_node, node, connections)

        # Step 2: Filter out nodes that have already been added to the current DAG
        # and collect data dependencies for each remaining node
        dag_builder = flow_manager.global_dag_builder
        all_nodes: set[str] = set()
        visited_deps: set[str] = set()

        node_manager = GriptapeNodes.NodeManager()
        for node_name in nodes_in_control_flow:
            # Skip nodes that have already been added to the current DAG
            # This prevents re-packaging nodes that have already been processed in this flow execution
            if node_name not in dag_builder.node_to_reference:
                all_nodes.add(node_name)
                # Collect dependencies (DagBuilder.collect_data_dependencies_for_node already filters out
                # resolved nodes, so we don't need to check that here)
                node_obj = node_manager.get_node_by_name(node_name)
                deps = DagBuilder.collect_data_dependencies_for_node(
                    node_obj, connections, nodes_in_control_flow, visited_deps
                )
                all_nodes.update(deps)

        # Exclude the start and end loop nodes from packaging
        # They will be managed separately and their state will be updated based on results
        all_nodes.discard(start_node.name)
        all_nodes.discard(node.name)

        # Handle empty loop body (no nodes between start and end)
        if not all_nodes:
            logger.info(
                "No nodes found between ForEach Start '%s' and End '%s'. Processing empty loop body.",
                start_node.name,
                node.name,
            )

            # Check if there are direct data connections from start to end
            # Could be: current_item (ForEach), index (ForLoop or ForEach), or other output parameters
            list_connections_request = ListConnectionsForNodeRequest(node_name=start_node.name)
            list_connections_result = GriptapeNodes.handle_request(list_connections_request)

            connected_source_param = None
            if isinstance(list_connections_result, ListConnectionsForNodeResultSuccess):
                for conn in list_connections_result.outgoing_connections:
                    if conn.target_node_name == node.name and conn.target_parameter_name == "new_item_to_add":
                        connected_source_param = conn.source_parameter_name
                        break

            logger.info(
                "Processing %d iterations for empty loop from '%s' to '%s' (connected param: %s)",
                total_iterations,
                start_node.name,
                node.name,
                connected_source_param,
            )

            # Process iterations to collect results from direct connections
            node._results_list = []
            if connected_source_param:
                for iteration_index in range(total_iterations):
                    # Set the current iteration count
                    start_node._current_iteration_count = iteration_index

                    # Get the value based on which parameter is connected
                    if connected_source_param == "current_item":
                        # ForEach: get current item value
                        value = start_node._get_current_item_value()
                    elif connected_source_param == "index":
                        # ForLoop or ForEach: get index value
                        value = start_node.get_current_index()
                    else:
                        # Other parameters: get from parameter_output_values
                        start_node._get_current_item_value()  # Ensure values are set
                        value = start_node.parameter_output_values.get(connected_source_param)

                    if value is not None:
                        node._results_list.append(value)

            node._output_results_list()
            return

        # Find the first node in the loop body (where start_node.exec_out connects to)
        entry_control_node_name = None
        entry_control_parameter_name = None

        # Look up the outgoing connections from start_node.exec_out
        exec_out_param_name = start_node.exec_out.name
        if start_node.name in connections.outgoing_index:
            exec_out_connections = connections.outgoing_index[start_node.name].get(exec_out_param_name, [])
            if exec_out_connections:
                # Get the first connection (there should typically only be one control flow out)
                first_conn_id = exec_out_connections[0]
                first_conn = connections.connections[first_conn_id]
                entry_control_node_name = first_conn.target_node.name
                entry_control_parameter_name = first_conn.target_parameter.name

        # Step 3: Package into PackageNodesAsSerializedFlowRequest
        # Determine library based on execution_type (similar to _publish_local_workflow)
        library_name = "Griptape Nodes Library"
        start_node_type = None
        end_node_type = None

        if execution_type not in (LOCAL_EXECUTION, PRIVATE_EXECUTION):
            try:
                library = LibraryRegistry.get_library(name=execution_type)
                start_nodes = library.get_nodes_by_base_type(StartNode)
                end_nodes = library.get_nodes_by_base_type(EndNode)
                if len(start_nodes) > 0 and len(end_nodes) > 0:
                    start_node_type = start_nodes[0]
                    if len(start_nodes) > 1:
                        logger.warning(
                            "Multiple StartNodes found in library '%s' for loop execution, using first StartNode '%s'",
                            execution_type,
                            start_node_type
                        )
                    end_node_type = end_nodes[0]
                    if len(end_nodes) > 1:
                        logger.warning(
                            "Multiple EndNodes found in library '%s' for loop execution, using first EndNode '%s'",
                            execution_type,
                            end_node_type
                        )
                    library_name = library.get_library_data().name
            except KeyError:
                logger.warning("Could not find library '%s' for loop execution, using default library", execution_type)

        # Create the packaging request with the entry node being the first node after start
        request = PackageNodesAsSerializedFlowRequest(
            node_names=list(all_nodes),
            start_node_type=start_node_type,
            end_node_type=end_node_type,
            start_end_specific_library_name=library_name,
            entry_control_node_name=entry_control_node_name,
            entry_control_parameter_name=entry_control_parameter_name,
            output_parameter_prefix=f"{node.name.replace(' ', '_')}_loop_",
            proxy_node=None,
        )

        package_result = GriptapeNodes.handle_request(request)
        if not isinstance(package_result, PackageNodesAsSerializedFlowResultSuccess):
            msg = f"Failed to package loop nodes for '{node.name}'. Error: {package_result.result_details}"
            raise TypeError(msg)

        logger.info(
            "Successfully packaged %d nodes for loop execution from '%s' to '%s'",
            len(all_nodes),
            start_node.name,
            node.name,
        )

        # Step 4a: Get parameter values from start node (vary per iteration)
        parameter_values_to_set_before_run = self.get_parameter_values_per_iteration(
            start_node, package_result.parameter_name_mappings
        )

        # Step 4b: Get resolved upstream values (constant across all iterations)
        resolved_upstream_values = self.get_resolved_upstream_values(
            packaged_node_names=list(all_nodes), parameter_name_mappings=package_result.parameter_name_mappings
        )

        # Step 4c: Merge upstream values into each iteration
        # Resolved upstream values are the same for all iterations
        if resolved_upstream_values:
            for iteration_index in parameter_values_to_set_before_run:
                parameter_values_to_set_before_run[iteration_index].update(resolved_upstream_values)
            logger.info(
                "Added %d resolved upstream values to %d iterations",
                len(resolved_upstream_values),
                len(parameter_values_to_set_before_run),
            )

        # Step 5: Execute all iterations based on execution environment
        if execution_type == LOCAL_EXECUTION:
            iteration_results, successful_iterations, last_iteration_values = await self._execute_loop_iterations_locally(
                package_result=package_result,
                total_iterations=total_iterations,
                parameter_values_per_iteration=parameter_values_to_set_before_run,
                end_loop_node=node,
            )
        elif execution_type == PRIVATE_EXECUTION:
            iteration_results, successful_iterations, last_iteration_values = (
                await self._execute_loop_iterations_privately(
                    package_result=package_result,
                    total_iterations=total_iterations,
                    parameter_values_per_iteration=parameter_values_to_set_before_run,
                    end_loop_node=node,
                )
            )
        else:
            # Cloud publisher execution (Deadline Cloud, etc.)
            iteration_results, successful_iterations, last_iteration_values = (
                await self._execute_loop_iterations_via_publisher(
                    package_result=package_result,
                    total_iterations=total_iterations,
                    parameter_values_per_iteration=parameter_values_to_set_before_run,
                    end_loop_node=node,
                    execution_type=execution_type,
                )
            )

        if len(successful_iterations) != total_iterations:
            failed_count = total_iterations - len(successful_iterations)
            msg = f"Loop execution failed: {failed_count} of {total_iterations} iterations failed"
            raise RuntimeError(msg)

        logger.info(
            "Successfully completed parallel execution of %d iterations for loop '%s'",
            total_iterations,
            start_node.name,
        )

        # Step 6: Build results list in iteration order
        node._results_list = []
        for iteration_index in sorted(iteration_results.keys()):
            value = iteration_results[iteration_index]
            node._results_list.append(value)

        # Step 7: Output final results to the results parameter
        node._output_results_list()

        # Step 8: Apply last iteration values to the original packaged nodes in main flow
        self._apply_last_iteration_to_packaged_nodes(
            last_iteration_values=last_iteration_values,
            package_result=package_result,
        )

        logger.info(
            "Successfully aggregated %d results for loop '%s' to '%s'",
            len(iteration_results),
            start_node.name,
            node.name,
        )

    def _get_iteration_value_for_parameter(
        self,
        source_param_name: str,
        iteration_index: int,
        index_values: list[int],
        current_item_values: list[Any],
    ) -> Any:
        """Get the value for a specific parameter at a given iteration.

        Args:
            source_param_name: Name of the source parameter (e.g., "index" or "current_item")
            iteration_index: 0-based iteration index
            index_values: List of actual loop values for ForLoop nodes
            current_item_values: List of items for ForEach nodes

        Returns:
            The value to set for this parameter at this iteration
        """
        if source_param_name == "index":
            # For ForLoop nodes, use actual loop value; otherwise use iteration_index
            if index_values and iteration_index < len(index_values):
                return index_values[iteration_index]
            return iteration_index
        if source_param_name == "current_item" and iteration_index < len(current_item_values):
            return current_item_values[iteration_index]
        return None

    def get_parameter_values_per_iteration(
        self,
        start_node: BaseIterativeStartNode,
        parameter_name_mappings: list,
    ) -> dict[int, dict[str, Any]]:
        """Get parameter values for each iteration of the loop.

        This maps iteration index to parameter values that should be set on the packaged flow's StartFlow node.
        Useful for: setting local values, sending as input for cloud publishing, or private workflow execution.

        Args:
            start_node: The start loop node (ForEach or ForLoop)
            parameter_name_mappings: List of PackagedNodeParameterMapping from
                                    PackageNodesAsSerializedFlowResultSuccess.parameter_name_mappings

        Returns:
            Dict mapping iteration_index -> {startflow_param_name: value}
        """
        total_iterations = start_node._get_total_iterations()

        # Calculate current_item values for ForEach nodes
        current_item_values = []
        if hasattr(start_node, "current_item"):
            iteration_items = start_node._get_iteration_items()
            current_item_values = list(iteration_items)

        # Calculate index values for ForLoop nodes
        # For ForLoop, we need actual loop values (start, start+step, start+2*step, ...)
        # not just 0-based iteration indices
        index_values = []
        if hasattr(start_node, "get_all_iteration_values"):
            index_values = start_node.get_all_iteration_values()

        list_connections_request = ListConnectionsForNodeRequest(node_name=start_node.name)
        list_connections_result = GriptapeNodes.handle_request(list_connections_request)
        if not isinstance(list_connections_result, ListConnectionsForNodeResultSuccess):
            msg = f"Failed to list connections for node {start_node.name}: {list_connections_result.result_details}"
            raise RuntimeError(msg)  # noqa: TRY004 This should be a runtime error because it happens during execution.
        # Build parameter values for each iteration
        outgoing_connections = list_connections_result.outgoing_connections

        # Get Start node's parameter mappings (index 0 in the list)
        start_node_mapping = parameter_name_mappings[0]
        start_node_param_mappings = start_node_mapping.parameter_mappings

        # For each outgoing connection from start_node, find the corresponding StartFlow parameter
        # The start_node_param_mappings tells us: startflow_param_name -> OriginalNodeParameter(target_node, target_param)
        # We need to match the target of each connection to find the right startflow parameter
        parameter_val_mappings = {}
        for iteration_index in range(total_iterations):
            iteration_values = {}
            # iteration_values is going to be startflow parameter name -> value to set

            # For each outgoing data connection from start_node
            for conn in outgoing_connections:
                source_param_name = conn.source_parameter_name
                target_node_name = conn.target_node_name
                target_param_name = conn.target_parameter_name

                # Find the target parameter that corresponds to this target
                for startflow_param_name, original_node_param in start_node_param_mappings.items():
                    if (
                        original_node_param.node_name == target_node_name
                        and original_node_param.parameter_name == target_param_name
                    ):
                        # This StartFlow parameter feeds the target - set the appropriate value
                        value = self._get_iteration_value_for_parameter(
                            source_param_name, iteration_index, index_values, current_item_values
                        )
                        if value is not None:
                            iteration_values[startflow_param_name] = value
                        break

            parameter_val_mappings[iteration_index] = iteration_values

        return parameter_val_mappings

    def get_resolved_upstream_values(
        self,
        packaged_node_names: list[str],
        parameter_name_mappings: list,
    ) -> dict[str, Any]:
        """Collect parameter values from resolved upstream nodes outside the loop.

        When nodes inside the loop have connections to nodes outside that have already
        executed (RESOLVED state), we need to pass those values into the packaged flow
        via the StartFlow node parameters.

        Args:
            packaged_node_names: List of node names being packaged in the loop
            parameter_name_mappings: List of PackagedNodeParameterMapping from
                                    PackageNodesAsSerializedFlowResultSuccess.parameter_name_mappings

        Returns:
            Dict mapping startflow_param_name -> value from resolved upstream node
        """
        flow_manager = GriptapeNodes.FlowManager()
        connections = flow_manager.get_connections()
        node_manager = GriptapeNodes.NodeManager()

        # Get Start node's parameter mappings (index 0 in the list)
        start_node_mapping = parameter_name_mappings[0]
        start_node_param_mappings = start_node_mapping.parameter_mappings

        resolved_upstream_values = {}

        # For each packaged node, check its incoming data connections
        for packaged_node_name in packaged_node_names:
            try:
                packaged_node = node_manager.get_node_by_name(packaged_node_name)
            except Exception:
                logger.warning("Could not find packaged node '%s' to check upstream connections", packaged_node_name)
                continue

            # Check each parameter for incoming connections
            for param in packaged_node.parameters:
                # Skip control parameters
                if param.type == ParameterTypeBuiltin.CONTROL_TYPE:
                    continue

                # Get upstream connection
                upstream_connection = connections.get_connected_node(packaged_node, param)
                if not upstream_connection:
                    continue

                upstream_node, upstream_param = upstream_connection

                # Only process if upstream node is RESOLVED (already executed outside loop)
                if upstream_node.state != NodeResolutionState.RESOLVED:
                    continue

                # Skip if upstream node is also in the packaged nodes (internal connection)
                if upstream_node.name in packaged_node_names:
                    continue

                # Get the value from the resolved upstream node
                if upstream_param.name in upstream_node.parameter_output_values:
                    upstream_value = upstream_node.parameter_output_values[upstream_param.name]
                else:
                    upstream_value = upstream_node.get_parameter_value(upstream_param.name)

                # Find the corresponding StartFlow parameter name
                # start_node_param_mappings maps: startflow_param_name -> OriginalNodeParameter(target_node, target_param)
                for startflow_param_name, original_node_param in start_node_param_mappings.items():
                    if (
                        original_node_param.node_name == packaged_node_name
                        and original_node_param.parameter_name == param.name
                    ):
                        # Found the StartFlow parameter that feeds this packaged node parameter
                        resolved_upstream_values[startflow_param_name] = upstream_value
                        logger.debug(
                            "Collected resolved upstream value: %s.%s -> StartFlow.%s = %s",
                            upstream_node.name,
                            upstream_param.name,
                            startflow_param_name,
                            upstream_value,
                        )
                        break

        logger.info("Collected %d resolved upstream values for loop execution", len(resolved_upstream_values))
        return resolved_upstream_values

    def _find_endflow_param_for_end_loop_node(
        self,
        incoming_connections: list,
        end_node_param_mappings: dict,
    ) -> str | None:
        """Find the EndFlow parameter name that corresponds to BaseIterativeEndNode's new_item_to_add.

        Args:
            incoming_connections: List of incoming connections to end_loop_node
            end_node_param_mappings: Parameter mappings from EndFlow node

        Returns:
            Sanitized parameter name on EndFlow node, or None if not found
        """
        for conn in incoming_connections:
            if conn.target_parameter_name != "new_item_to_add":
                continue

            source_node_name = conn.source_node_name
            source_param_name = conn.source_parameter_name

            # Find the EndFlow parameter that corresponds to this source
            for sanitized_param_name, original_node_param in end_node_param_mappings.items():
                if (
                    original_node_param.node_name == source_node_name
                    and original_node_param.parameter_name == source_param_name
                ):
                    return sanitized_param_name

        return None

    def get_parameter_values_from_iterations(
        self,
        end_loop_node: BaseIterativeEndNode,
        deserialized_flows: list[tuple[int, str, dict[str, str]]],
        parameter_name_mappings: list,
    ) -> dict[int, Any]:
        """Extract parameter values from each iteration's EndFlow node.

        The BaseIterativeEndNode is NOT packaged. Instead, we find what connects TO it,
        then extract those values from the packaged EndFlow node.

        Mirrors get_parameter_values_per_iteration pattern but works in reverse.

        Args:
            end_loop_node: The End Loop Node (NOT packaged, just used for reference)
            deserialized_flows: List of (iteration_index, flow_name, node_name_mappings)
            parameter_name_mappings: List from PackageNodesAsSerializedFlowResultSuccess.parameter_name_mappings

        Returns:
            Dict mapping iteration_index -> value for that iteration
        """
        # Step 1: Get incoming connections TO the end_loop_node
        list_connections_request = ListConnectionsForNodeRequest(node_name=end_loop_node.name)
        list_connections_result = GriptapeNodes.handle_request(list_connections_request)
        if not isinstance(list_connections_result, ListConnectionsForNodeResultSuccess):
            msg = f"Failed to list connections for node {end_loop_node.name}: {list_connections_result.result_details}"
            raise RuntimeError(msg)  # noqa: TRY004

        incoming_connections = list_connections_result.incoming_connections

        # Step 2: Get End node's parameter mappings (index 1 = EndFlow node)
        end_node_mapping = parameter_name_mappings[1]
        end_node_param_mappings = end_node_mapping.parameter_mappings

        # Step 3: Find the EndFlow parameter that corresponds to new_item_to_add
        endflow_param_name = self._find_endflow_param_for_end_loop_node(incoming_connections, end_node_param_mappings)

        if endflow_param_name is None:
            logger.warning(
                "No connections found to BaseIterativeEndNode '%s' new_item_to_add parameter. No results will be collected.",
                end_loop_node.name,
            )
            return {}

        # Step 4: Extract values from each iteration's EndFlow node
        packaged_end_node_name = end_node_mapping.node_name
        iteration_results = {}
        node_manager = GriptapeNodes.NodeManager()

        for iteration_index, flow_name, node_name_mappings in deserialized_flows:
            deserialized_end_node_name = node_name_mappings.get(packaged_end_node_name)
            if deserialized_end_node_name is None:
                logger.warning(
                    "Could not find deserialized End node for iteration %d in flow '%s'",
                    iteration_index,
                    flow_name,
                )
                continue

            try:
                deserialized_end_node = node_manager.get_node_by_name(deserialized_end_node_name)
                if endflow_param_name in deserialized_end_node.parameter_output_values:
                    iteration_results[iteration_index] = deserialized_end_node.parameter_output_values[
                        endflow_param_name
                    ]
            except Exception as e:
                logger.warning(
                    "Failed to extract result from End node for iteration %d: %s",
                    iteration_index,
                    e,
                )

        return iteration_results

    def get_last_iteration_values_for_packaged_nodes(
        self,
        deserialized_flows: list[tuple[int, str, dict[str, str]]],
        package_result: PackageNodesAsSerializedFlowResultSuccess,
        total_iterations: int,
    ) -> dict[str, Any]:
        """Extract parameter values from the LAST iteration's End Flow node for all output parameters.

        Returns values in same format as _extract_parameter_output_values(), ready to pass to
        _apply_parameter_values_to_node(). This sets the final state of packaged nodes after loop completes.

        Args:
            deserialized_flows: List of (iteration_index, flow_name, node_name_mappings)
            package_result: PackageNodesAsSerializedFlowResultSuccess containing parameter mappings
            total_iterations: Total number of iterations that were executed

        Returns:
            Dict mapping sanitized parameter names -> values from last iteration's End node
        """
        if total_iterations == 0:
            return {}

        last_iteration_index = total_iterations - 1

        # Find the last iteration in deserialized_flows
        last_iteration_flow = None
        for iteration_index, flow_name, node_name_mappings in deserialized_flows:
            if iteration_index == last_iteration_index:
                last_iteration_flow = (iteration_index, flow_name, node_name_mappings)
                break

        if last_iteration_flow is None:
            logger.warning(
                "Could not find last iteration (index %d) in deserialized flows. Cannot extract final values.",
                last_iteration_index,
            )
            return {}

        # Get End node's parameter mappings (index 1 = EndFlow node)
        end_node_mapping = package_result.parameter_name_mappings[1]
        packaged_end_node_name = end_node_mapping.node_name

        # Get the deserialized End node name for last iteration
        _, _, node_name_mappings = last_iteration_flow
        deserialized_end_node_name = node_name_mappings.get(packaged_end_node_name)

        if deserialized_end_node_name is None:
            logger.warning(
                "Could not find deserialized End node (packaged name: '%s') in last iteration",
                packaged_end_node_name,
            )
            return {}

        # Get the End node instance
        node_manager = GriptapeNodes.NodeManager()
        try:
            deserialized_end_node = node_manager.get_node_by_name(deserialized_end_node_name)
        except Exception as e:
            logger.warning("Failed to get End node '%s' for last iteration: %s", deserialized_end_node_name, e)
            return {}

        # Extract ALL parameter output values from the End node
        # Return them with sanitized names (as they appear on End node)
        last_iteration_values = {}
        for sanitized_param_name in end_node_mapping.parameter_mappings:
            if sanitized_param_name in deserialized_end_node.parameter_output_values:
                last_iteration_values[sanitized_param_name] = deserialized_end_node.parameter_output_values[
                    sanitized_param_name
                ]

        logger.debug(
            "Extracted %d parameter values from last iteration's End node '%s'",
            len(last_iteration_values),
            deserialized_end_node_name,
        )

        return last_iteration_values

    async def _execute_loop_iterations_locally(  # noqa: C901, PLR0912, PLR0915
        self,
        package_result: PackageNodesAsSerializedFlowResultSuccess,
        total_iterations: int,
        parameter_values_per_iteration: dict[int, dict[str, Any]],
        end_loop_node: BaseIterativeEndNode,
    ) -> tuple[dict[int, Any], list[int], dict[str, Any]]:
        """Execute loop iterations locally by deserializing and running flows.

        This method handles LOCAL execution of loop iterations. Other libraries
        can implement their own execution strategies (cloud, remote, etc.) by
        creating similar methods with the same signature.

        Args:
            package_result: The packaged flow with parameter mappings
            total_iterations: Number of iterations to run
            parameter_values_per_iteration: Dict mapping iteration_index -> parameter values
            end_loop_node: The End Loop Node to extract results for

        Returns:
            Tuple of:
            - iteration_results: Dict mapping iteration_index -> result value
            - successful_iterations: List of iteration indices that succeeded
            - last_iteration_values: Dict mapping parameter names -> values from last iteration
        """

        # Step 1: Deserialize N flow instances from the serialized flow
        # Save the current context and restore it after each deserialization to prevent
        # iteration flows from becoming children of each other
        deserialized_flows = []
        context_manager = GriptapeNodes.ContextManager()
        saved_context_flow = context_manager.get_current_flow() if context_manager.has_current_flow() else None

        # Suppress events during deserialization to prevent sending them to websockets

        event_manager = GriptapeNodes.EventManager()
        with EventSuppressionContext(event_manager, LOOP_EVENTS_TO_SUPPRESS):
            for iteration_index in range(total_iterations):
                # Restore context before each deserialization to ensure all iteration flows
                # are created at the same level (not as children of each other)
                if saved_context_flow is not None:
                    # Pop any flows that were pushed during previous iteration
                    while (
                        context_manager.has_current_flow() and context_manager.get_current_flow() != saved_context_flow
                    ):
                        context_manager.pop_flow()

                deserialize_request = DeserializeFlowFromCommandsRequest(
                    serialized_flow_commands=package_result.serialized_flow_commands
                )
                deserialize_result = GriptapeNodes.handle_request(deserialize_request)
                if not isinstance(deserialize_result, DeserializeFlowFromCommandsResultSuccess):
                    msg = f"Failed to deserialize flow for iteration {iteration_index}. Error: {deserialize_result.result_details}"
                    raise TypeError(msg)

                deserialized_flows.append(
                    (iteration_index, deserialize_result.flow_name, deserialize_result.node_name_mappings)
                )

                # Pop the deserialized flow from the context stack to prevent it from staying there
                # Deserialization pushes the flow onto the stack, but we don't want iteration flows
                # to remain on the stack after deserialization
                if (
                    context_manager.has_current_flow()
                    and context_manager.get_current_flow().name == deserialize_result.flow_name
                ):
                    context_manager.pop_flow()

        logger.info("Successfully deserialized %d flow instances for parallel execution", total_iterations)

        # Step 2: Set input values on start nodes for each iteration
        for iteration_index, _, node_name_mappings in deserialized_flows:
            parameter_values = parameter_values_per_iteration[iteration_index]

            # Get Start node mapping (index 0 in the list)
            start_node_mapping = package_result.parameter_name_mappings[0]
            start_node_name = start_node_mapping.node_name
            start_params = start_node_mapping.parameter_mappings

            # Find the deserialized name for the Start node
            deserialized_start_node_name = node_name_mappings.get(start_node_name)
            if deserialized_start_node_name is None:
                logger.warning(
                    "Could not find deserialized Start node (original: '%s') for iteration %d",
                    start_node_name,
                    iteration_index,
                )
                continue

            # Set all parameter values on the deserialized Start node
            for startflow_param_name in start_params:
                if startflow_param_name not in parameter_values:
                    continue

                value_to_set = parameter_values[startflow_param_name]

                set_value_request = SetParameterValueRequest(
                    node_name=deserialized_start_node_name,
                    parameter_name=startflow_param_name,
                    value=value_to_set,
                )
                set_value_result = await GriptapeNodes.ahandle_request(set_value_request)
                if not isinstance(set_value_result, SetParameterValueResultSuccess):
                    logger.warning(
                        "Failed to set parameter '%s' on Start node '%s' for iteration %d: %s",
                        startflow_param_name,
                        deserialized_start_node_name,
                        iteration_index,
                        set_value_result.result_details,
                    )

        logger.info("Successfully set input values for %d iterations", total_iterations)

        # Step 3: Run all flows concurrently
        packaged_start_node_name = package_result.parameter_name_mappings[0].node_name

        async def run_single_iteration(flow_name: str, iteration_index: int, start_node_name: str) -> tuple[int, bool]:
            """Run a single iteration flow and return success status."""
            # Suppress execution events during parallel iteration to prevent flooding websockets
            with EventSuppressionContext(event_manager, EXECUTION_EVENTS_TO_SUPPRESS):
                start_subflow_request = StartLocalSubflowRequest(
                    flow_name=flow_name,
                    start_node=start_node_name,
                    pickle_control_flow_result=False,
                )
                start_subflow_result = await GriptapeNodes.ahandle_request(start_subflow_request)
                success = isinstance(start_subflow_result, StartLocalSubflowResultSuccess)
                return iteration_index, success

        try:
            # Run all iterations concurrently
            iteration_tasks = [
                run_single_iteration(
                    flow_name,
                    iteration_index,
                    node_name_mappings.get(packaged_start_node_name),
                )
                for iteration_index, flow_name, node_name_mappings in deserialized_flows
            ]
            iteration_results = await asyncio.gather(*iteration_tasks, return_exceptions=True)

            # Step 4: Collect successful and failed iterations
            successful_iterations = []
            failed_iterations = []

            for result in iteration_results:
                if isinstance(result, Exception):
                    failed_iterations.append(result)
                    continue
                if isinstance(result, tuple):
                    iteration_index, success = result
                    if success:
                        successful_iterations.append(iteration_index)
                    else:
                        failed_iterations.append(iteration_index)

            if failed_iterations:
                msg = f"Loop execution failed: {len(failed_iterations)} of {total_iterations} iterations failed"
                raise RuntimeError(msg)

            # Step 4: Extract parameter values from iterations BEFORE cleanup
            iteration_results = self.get_parameter_values_from_iterations(
                end_loop_node=end_loop_node,
                deserialized_flows=deserialized_flows,
                parameter_name_mappings=package_result.parameter_name_mappings,
            )

            # Step 5: Extract last iteration values BEFORE cleanup (flows deleted in finally block)
            last_iteration_values = self.get_last_iteration_values_for_packaged_nodes(
                deserialized_flows=deserialized_flows,
                package_result=package_result,
                total_iterations=total_iterations,
            )

            return iteration_results, successful_iterations, last_iteration_values

        finally:
            # Step 5: Cleanup - delete all iteration flows
            # Suppress events during deletion to prevent sending them to websockets
            with EventSuppressionContext(event_manager, ["DeleteFlowResultSuccess", "DeleteFlowResultFailure"]):
                for iteration_index, flow_name, _ in deserialized_flows:
                    delete_request = DeleteFlowRequest(flow_name=flow_name)
                    delete_result = await GriptapeNodes.ahandle_request(delete_request)
                    if not isinstance(delete_result, DeleteFlowResultSuccess):
                        logger.warning(
                            "Failed to delete iteration flow '%s' (iteration %d): %s",
                            flow_name,
                            iteration_index,
                            delete_result.result_details,
                        )

    async def _execute_loop_iterations_privately(
        self,
        package_result: PackageNodesAsSerializedFlowResultSuccess,
        total_iterations: int,
        parameter_values_per_iteration: dict[int, dict[str, Any]],
        end_loop_node: BaseIterativeEndNode,
    ) -> tuple[dict[int, Any], list[int], dict[str, Any]]:
        """Execute loop iterations in private subprocess (no cloud publishing).

        This method publishes the workflow to a local file and executes it N times
        as subprocesses with different parameter values.

        Args:
            package_result: The packaged flow with parameter mappings
            total_iterations: Number of iterations to run
            parameter_values_per_iteration: Dict mapping iteration_index -> parameter values
            end_loop_node: The End Loop Node to extract results for

        Returns:
            Tuple of:
            - iteration_results: Dict mapping iteration_index -> result value
            - successful_iterations: List of iteration indices that succeeded
            - last_iteration_values: Dict mapping parameter names -> values from last iteration
        """
        # Step 1: Save workflow file
        sanitized_loop_name = end_loop_node.name.replace(" ", "_")
        file_name = f"{sanitized_loop_name}_private_loop_flow"

        workflow_file_request = SaveWorkflowFileFromSerializedFlowRequest(
            file_name=file_name,
            serialized_flow_commands=package_result.serialized_flow_commands,
            workflow_shape=package_result.workflow_shape,
            pickle_control_flow_result=True,
        )

        workflow_result = await GriptapeNodes.ahandle_request(workflow_file_request)
        if not isinstance(workflow_result, SaveWorkflowFileFromSerializedFlowResultSuccess):
            msg = f"Failed to save workflow file for private loop execution: {workflow_result.result_details}"
            raise TypeError(msg)

        workflow_path = Path(workflow_result.file_path)

        logger.info(
            "Saved workflow to '%s'. Executing %d iterations in private subprocesses...",
            workflow_path,
            total_iterations,
        )

        # Get the StartFlow node name from package_result
        start_node_mapping = package_result.parameter_name_mappings[0]
        start_node_name = start_node_mapping.node_name

        # Step 2: Execute N times with different flow_input values
        async def run_single_iteration(iteration_index: int) -> tuple[int, bool, dict[str, Any] | None]:
            """Run a single iteration and return success status and output."""
            try:
                # Wrap parameter values with StartFlow node name
                # flow_input structure: {"StartFlowNodeName": {"param1": value1, "param2": value2}}
                flow_input_for_iteration = {start_node_name: parameter_values_per_iteration[iteration_index]}

                logger.info(
                    "Executing private iteration %d/%d for loop '%s'",
                    iteration_index + 1,
                    total_iterations,
                    end_loop_node.name,
                )

                subprocess_result = await self._execute_subprocess(
                    published_workflow_filename=workflow_path,
                    file_name=f"{file_name}_iteration_{iteration_index}",
                    pickle_control_flow_result=True,
                    flow_input=flow_input_for_iteration,
                )

                return iteration_index, True, subprocess_result
            except Exception:
                logger.exception(
                    "Private iteration %d failed for loop '%s'",
                    iteration_index,
                    end_loop_node.name,
                )
                return iteration_index, False, None

        try:
            # Run all iterations concurrently
            iteration_tasks = [run_single_iteration(i) for i in range(total_iterations)]
            iteration_outputs = await asyncio.gather(*iteration_tasks)

            # Step 3: Extract results from each iteration's output
            successful_iterations = []
            iteration_results = {}
            iteration_subprocess_outputs = {}

            for iteration_index, success, subprocess_result in iteration_outputs:
                if success and subprocess_result is not None:
                    successful_iterations.append(iteration_index)
                    iteration_subprocess_outputs[iteration_index] = subprocess_result

            # Extract the actual result values from subprocess outputs
            end_node_mapping = package_result.parameter_name_mappings[1]
            end_node_param_mappings = end_node_mapping.parameter_mappings

            # Find which EndFlow parameter corresponds to new_item_to_add
            list_connections_request = ListConnectionsForNodeRequest(node_name=end_loop_node.name)
            list_connections_result = GriptapeNodes.handle_request(list_connections_request)

            endflow_param_name = None
            if isinstance(list_connections_result, ListConnectionsForNodeResultSuccess):
                endflow_param_name = self._find_endflow_param_for_end_loop_node(
                    list_connections_result.incoming_connections, end_node_param_mappings
                )

            # Extract iteration results from subprocess outputs
            for iteration_index in successful_iterations:
                subprocess_result = iteration_subprocess_outputs[iteration_index]
                parameter_output_values = self._extract_parameter_output_values(subprocess_result)

                if endflow_param_name and endflow_param_name in parameter_output_values:
                    iteration_results[iteration_index] = parameter_output_values[endflow_param_name]

            # Step 4: Get last iteration values from the last successful iteration
            last_iteration_values = {}
            if successful_iterations:
                last_iteration_index = max(successful_iterations)
                last_subprocess_result = iteration_subprocess_outputs[last_iteration_index]
                last_iteration_values = self._extract_parameter_output_values(last_subprocess_result)

            logger.info(
                "Successfully completed %d/%d private iterations for loop '%s'",
                len(successful_iterations),
                total_iterations,
                end_loop_node.name,
            )

            return iteration_results, successful_iterations, last_iteration_values

        finally:
            # Cleanup: delete the workflow file
            try:
                await self._delete_workflow(
                    workflow_name=workflow_result.workflow_metadata.name, workflow_path=workflow_path
                )
            except Exception as e:
                logger.warning("Failed to cleanup workflow file: %s", e)

    async def _execute_loop_iterations_via_publisher(
        self,
        package_result: PackageNodesAsSerializedFlowResultSuccess,
        total_iterations: int,
        parameter_values_per_iteration: dict[int, dict[str, Any]],
        end_loop_node: BaseIterativeEndNode,
        execution_type: str,
    ) -> tuple[dict[int, Any], list[int], dict[str, Any]]:
        """Execute loop iterations via cloud publisher (Deadline Cloud, etc.).

        This method publishes the packaged workflow once, then executes it N times
        with different parameter values passed via flow_input.

        Args:
            package_result: The packaged flow with parameter mappings
            total_iterations: Number of iterations to run
            parameter_values_per_iteration: Dict mapping iteration_index -> parameter values
            end_loop_node: The End Loop Node to extract results for
            execution_type: The execution environment (library name)

        Returns:
            Tuple of:
            - iteration_results: Dict mapping iteration_index -> result value
            - successful_iterations: List of iteration indices that succeeded
            - last_iteration_values: Dict mapping parameter names -> values from last iteration
        """
        try:
            library = LibraryRegistry.get_library(name=execution_type)
        except KeyError:
            msg = f"Could not find library for execution environment {execution_type}"
            raise RuntimeError(msg)  # noqa: B904

        library_name = library.get_library_data().name

        # Step 1: Publish the base workflow ONCE
        logger.info("Publishing workflow for loop execution via library '%s'", library_name)

        # Create a temporary node-like object to use with _publish_local_workflow
        # We can't use the actual loop nodes, so we'll create the workflow directly
        sanitized_loop_name = end_loop_node.name.replace(" ", "_")
        file_name = f"{sanitized_loop_name}_{library_name.replace(' ', '_')}_loop_flow"

        workflow_file_request = SaveWorkflowFileFromSerializedFlowRequest(
            file_name=file_name,
            serialized_flow_commands=package_result.serialized_flow_commands,
            workflow_shape=package_result.workflow_shape,
            pickle_control_flow_result=True,
        )

        workflow_result = await GriptapeNodes.ahandle_request(workflow_file_request)
        if not isinstance(workflow_result, SaveWorkflowFileFromSerializedFlowResultSuccess):
            msg = f"Failed to save workflow file for loop: {workflow_result.result_details}"
            raise RuntimeError(msg)

        # Publish to the library
        published_workflow_filename = await self._publish_library_workflow(
            workflow_result, library_name, file_name
        )

        logger.info(
            "Successfully published workflow to '%s'. Executing %d iterations...",
            published_workflow_filename,
            total_iterations,
        )

        # Get the StartFlow node name from package_result
        start_node_mapping = package_result.parameter_name_mappings[0]
        start_node_name = start_node_mapping.node_name

        # Step 2: Execute N times with different flow_input values
        async def run_single_iteration(iteration_index: int) -> tuple[int, bool, dict[str, Any] | None]:
            """Run a single iteration and return success status and output."""
            try:
                # Wrap parameter values with StartFlow node name
                # flow_input structure: {"StartFlowNodeName": {"param1": value1, "param2": value2}}
                flow_input_for_iteration = {start_node_name: parameter_values_per_iteration[iteration_index]}

                logger.info(
                    "Executing iteration %d/%d for loop '%s'",
                    iteration_index + 1,
                    total_iterations,
                    end_loop_node.name,
                )

                subprocess_result = await self._execute_subprocess(
                    published_workflow_filename=published_workflow_filename,
                    file_name=f"{file_name}_iteration_{iteration_index}",
                    pickle_control_flow_result=True,
                    flow_input=flow_input_for_iteration,
                )

                return iteration_index, True, subprocess_result
            except Exception as e:
                logger.exception(
                    "Iteration %d failed for loop '%s': %s",
                    iteration_index,
                    end_loop_node.name,
                    e,
                )
                return iteration_index, False, None

        try:
            # Run all iterations concurrently
            iteration_tasks = [run_single_iteration(i) for i in range(total_iterations)]
            iteration_outputs = await asyncio.gather(*iteration_tasks)

            # Step 3: Extract results from each iteration's output
            successful_iterations = []
            iteration_results = {}
            iteration_subprocess_outputs = {}

            for iteration_index, success, subprocess_result in iteration_outputs:
                if success and subprocess_result is not None:
                    successful_iterations.append(iteration_index)
                    iteration_subprocess_outputs[iteration_index] = subprocess_result

            # Extract the actual result values from subprocess outputs
            # The result is in the EndFlow node's output parameters
            end_node_mapping = package_result.parameter_name_mappings[1]
            end_node_param_mappings = end_node_mapping.parameter_mappings

            # Find which EndFlow parameter corresponds to new_item_to_add
            list_connections_request = ListConnectionsForNodeRequest(node_name=end_loop_node.name)
            list_connections_result = GriptapeNodes.handle_request(list_connections_request)

            endflow_param_name = None
            if isinstance(list_connections_result, ListConnectionsForNodeResultSuccess):
                endflow_param_name = self._find_endflow_param_for_end_loop_node(
                    list_connections_result.incoming_connections, end_node_param_mappings
                )

            # Extract iteration results from subprocess outputs
            for iteration_index in successful_iterations:
                subprocess_result = iteration_subprocess_outputs[iteration_index]
                parameter_output_values = self._extract_parameter_output_values(subprocess_result)

                if endflow_param_name and endflow_param_name in parameter_output_values:
                    iteration_results[iteration_index] = parameter_output_values[endflow_param_name]

            # Step 4: Get last iteration values from the last successful iteration
            last_iteration_values = {}
            if successful_iterations:
                last_iteration_index = max(successful_iterations)
                last_subprocess_result = iteration_subprocess_outputs[last_iteration_index]
                last_iteration_values = self._extract_parameter_output_values(last_subprocess_result)

            logger.info(
                "Successfully completed %d/%d iterations via publisher for loop '%s'",
                len(successful_iterations),
                total_iterations,
                end_loop_node.name,
            )

            return iteration_results, successful_iterations, last_iteration_values

        finally:
            # Cleanup: delete the published workflow file and original workflow
            try:
                await self._delete_workflow(
                    workflow_name=workflow_result.workflow_metadata.name,
                    workflow_path=Path(workflow_result.file_path),
                )
                published_filename = published_workflow_filename.stem
                await self._delete_workflow(
                    workflow_name=published_filename, workflow_path=published_workflow_filename
                )
            except Exception as e:
                logger.warning("Failed to cleanup workflow files: %s", e)

    def set_parameter_output_values_for_loops(
        self, subprocess_result: dict[str, dict[str | SerializedNodeCommands.UniqueParameterValueUUID, Any] | None]
    ) -> None:
        pass

    def _extract_parameter_output_values(
        self, subprocess_result: dict[str, dict[str | SerializedNodeCommands.UniqueParameterValueUUID, Any] | None]
    ) -> dict[str, Any]:
        """Extract and deserialize parameter output values from subprocess result.

        Returns:
            Dictionary of parameter names to their deserialized values
        """
        parameter_output_values = {}
        for result_dict in subprocess_result.values():
            # Handle backward compatibility: old flat structure
            if not isinstance(result_dict, dict) or "parameter_output_values" not in result_dict:
                parameter_output_values.update(result_dict)  # type: ignore[arg-type]
                continue

            param_output_vals = result_dict["parameter_output_values"]
            unique_uuid_to_values = result_dict.get("unique_parameter_uuid_to_values")

            # No UUID mapping - use values directly
            if not unique_uuid_to_values:
                parameter_output_values.update(param_output_vals)
                continue

            # Deserialize UUID-referenced values
            for param_name, param_value in param_output_vals.items():
                parameter_output_values[param_name] = self._deserialize_parameter_value(
                    param_name, param_value, unique_uuid_to_values
                )
        return parameter_output_values

    def _deserialize_parameter_value(self, param_name: str, param_value: Any, unique_uuid_to_values: dict) -> Any:
        """Deserialize a single parameter value, handling UUID references and pickling.

        Args:
            param_name: Parameter name for logging
            param_value: Either a direct value or UUID reference
            unique_uuid_to_values: Mapping of UUIDs to pickled values

        Returns:
            Deserialized parameter value
        """
        # Direct value (not a UUID reference)
        if param_value not in unique_uuid_to_values:
            return param_value

        stored_value = unique_uuid_to_values[param_value]

        # Non-string stored values are used directly
        if not isinstance(stored_value, str):
            return stored_value

        # Attempt to unpickle string-represented bytes
        try:
            actual_bytes = ast.literal_eval(stored_value)
            if isinstance(actual_bytes, bytes):
                return pickle.loads(actual_bytes)  # noqa: S301
        except (ValueError, SyntaxError, pickle.UnpicklingError) as e:
            logger.warning(
                "Failed to unpickle string-represented bytes for parameter '%s': %s",
                param_name,
                e,
            )
            return stored_value
        return stored_value

    def _apply_parameter_values_to_node(  # noqa: C901
        self,
        node: BaseNode,
        parameter_output_values: dict[str, Any],
        package_result: PackageNodesAsSerializedFlowResultSuccess,
    ) -> None:
        """Apply deserialized parameter values back to the node.

        Sets parameter values on the node and updates parameter_output_values dictionary.
        Uses parameter_name_mappings from package_result to map packaged parameters back to original nodes.
        Works for both single-node and multi-node packages.
        """
        # If the packaged flow fails, the End Flow Node in the library published workflow will have entered from 'failed'
        if "failed" in parameter_output_values and parameter_output_values["failed"] == CONTROL_INPUT_PARAMETER:
            msg = f"Failed to execute node: {node.name}, with exception: {parameter_output_values.get('result_details', 'No result details were returned.')}"
            raise RuntimeError(msg)

        # Use parameter mappings to apply values back to original nodes
        # Output values come from the End node (index 1 in the list)
        end_node_mapping = package_result.parameter_name_mappings[1]
        end_node_param_mappings = end_node_mapping.parameter_mappings

        for param_name, param_value in parameter_output_values.items():
            # Check if this parameter has a mapping in the End node
            if param_name not in end_node_param_mappings:
                continue

            original_node_param = end_node_param_mappings[param_name]
            target_node_name = original_node_param.node_name
            target_param_name = original_node_param.parameter_name

            # For multi-node packages, get the target node from the group
            # For single-node packages, use the node itself
            if isinstance(node, NodeGroupProxyNode):
                if target_node_name not in node.node_group_data.nodes:
                    msg = f"Target node '{target_node_name}' not found in node group for proxy node '{node.name}'. Available nodes: {list(node.node_group_data.nodes.keys())}"
                    raise RuntimeError(msg)
                target_node = node.node_group_data.nodes[target_node_name]
            else:
                target_node = node

            # Get the parameter from the target node
            target_param = target_node.get_parameter_by_name(target_param_name)

            # Skip if parameter not found or is special parameter (execution_environment, node_group)
            if target_param is None or target_param in (
                target_node.execution_environment,
                target_node.node_group,
            ):
                logger.debug(
                    "Skipping special or missing parameter '%s' on node '%s'", target_param_name, target_node_name
                )
                continue

            # Set the value on the target node
            if target_param.type != ParameterTypeBuiltin.CONTROL_TYPE:
                target_node.set_parameter_value(target_param_name, param_value)
            target_node.parameter_output_values[target_param_name] = param_value

            # For multi-node packages, also set the value on the proxy node's corresponding output parameter
            if isinstance(node, NodeGroupProxyNode):
                sanitized_node_name = target_node_name.replace(" ", "_")
                proxy_param_name = f"{sanitized_node_name}__{target_param_name}"
                proxy_param = node.get_parameter_by_name(proxy_param_name)
                if proxy_param is not None:
                    if target_param.type != ParameterTypeBuiltin.CONTROL_TYPE:
                        node.set_parameter_value(proxy_param_name, param_value)
                    node.parameter_output_values[proxy_param_name] = param_value

            logger.debug(
                "Set parameter '%s' on node '%s' to value: %s",
                target_param_name,
                target_node_name,
                param_value,
            )

    def _apply_last_iteration_to_packaged_nodes(
        self,
        last_iteration_values: dict[str, Any],
        package_result: PackageNodesAsSerializedFlowResultSuccess,
    ) -> None:
        """Apply last iteration values to the original packaged nodes in main flow.

        After parallel loop execution, this sets the final state of each packaged node
        to match the last iteration's execution results. This is important for nodes that
        output values or produce artifacts during loop execution.

        Args:
            last_iteration_values: Dict mapping sanitized End node parameter names to values
            package_result: PackageNodesAsSerializedFlowResultSuccess containing parameter mappings and node names
        """
        if not last_iteration_values:
            logger.debug("No last iteration values to apply to packaged nodes")
            return

        # Get End node parameter mappings (index 1 in the list)
        end_node_mapping = package_result.parameter_name_mappings[1]
        end_node_param_mappings = end_node_mapping.parameter_mappings

        node_manager = GriptapeNodes.NodeManager()

        # For each parameter in the End node, map it back to the original node and set the value
        for sanitized_param_name, param_value in last_iteration_values.items():
            # Check if this parameter has a mapping in the End node
            if sanitized_param_name not in end_node_param_mappings:
                continue

            original_node_param = end_node_param_mappings[sanitized_param_name]
            target_node_name = original_node_param.node_name
            target_param_name = original_node_param.parameter_name

            # Get the original packaged node in the main flow
            try:
                target_node = node_manager.get_node_by_name(target_node_name)
            except Exception:
                logger.warning(
                    "Could not find packaged node '%s' in main flow to apply last iteration values", target_node_name
                )
                continue

            # Get the parameter from the target node
            target_param = target_node.get_parameter_by_name(target_param_name)

            # Skip if parameter not found or is special parameter
            if target_param is None or target_param in (
                target_node.execution_environment,
                getattr(target_node, "node_group", None),
            ):
                logger.debug(
                    "Skipping special or missing parameter '%s' on node '%s'", target_param_name, target_node_name
                )
                continue

            # Skip control parameters
            if target_param.type == ParameterTypeBuiltin.CONTROL_TYPE:
                logger.debug("Skipping control parameter '%s' on node '%s'", target_param_name, target_node_name)
                continue

            # Set the value on the target node
            target_node.set_parameter_value(target_param_name, param_value)
            target_node.parameter_output_values[target_param_name] = param_value

            logger.debug(
                "Applied last iteration value to packaged node '%s' parameter '%s'",
                target_node_name,
                target_param_name,
            )

        logger.info(
            "Successfully applied %d parameter values from last iteration to packaged nodes",
            len(last_iteration_values),
        )

    async def _delete_workflow(self, workflow_name: str, workflow_path: Path) -> None:
        try:
            WorkflowRegistry.get_workflow_by_name(workflow_name)
        except KeyError:
            # Register the workflow if not already registered since a subprocess may have created it
            load_workflow_metadata_request = LoadWorkflowMetadata(file_name=workflow_path.name)
            result = GriptapeNodes.handle_request(load_workflow_metadata_request)
            if isinstance(result, LoadWorkflowMetadataResultSuccess):
                WorkflowRegistry.generate_new_workflow(str(workflow_path), result.metadata)

        delete_request = DeleteWorkflowRequest(name=workflow_name)
        delete_result = GriptapeNodes.handle_request(delete_request)
        if isinstance(delete_result, DeleteWorkflowResultFailure):
            logger.error(
                "Failed to delete workflow '%s'. Error: %s",
                workflow_name,
                delete_result.result_details,
            )
        else:
            logger.info(
                "Cleanup result for workflow '%s': %s",
                workflow_name,
                delete_result.result_details,
            )

    async def _get_storage_backend(self) -> StorageBackend:
        storage_backend_str = GriptapeNodes.ConfigManager().get_config_value("storage_backend")
        # Convert string to StorageBackend enum
        try:
            storage_backend = StorageBackend(storage_backend_str)
        except ValueError:
            storage_backend = StorageBackend.LOCAL
        return storage_backend

    def _toggle_directional_control_connections(
        self,
        proxy_node: BaseNode,
        node_group: NodeGroup,
        connections: Connections,
        *,
        restore_to_original: bool,
        is_incoming: bool,
    ) -> None:
        """Toggle control connections between proxy and original nodes for a specific direction.

        When a NodeGroupProxyNode is created, control connections from/to the original nodes are
        redirected to/from the proxy node. Before packaging the flow for execution, we need to
        temporarily restore these connections back to the original nodes so the packaged flow
        has the correct control flow structure. After packaging, we toggle them back to the proxy.

        Args:
            proxy_node: The proxy node containing the node group
            node_group: The node group data containing original nodes and connection mappings
            connections: The connections manager that tracks all connections via indexes
            restore_to_original: If True, restore connections to original nodes (for packaging);
                               if False, remap connections to proxy (after packaging)
            is_incoming: If True, handle incoming connections (target_node/target_parameter);
                        if False, handle outgoing connections (source_node/source_parameter)
        """
        # Select the appropriate connection list, mapping, and index based on direction
        if is_incoming:
            # Incoming: connections pointing TO nodes in this group
            connection_list = node_group.external_incoming_connections
            original_nodes_map = node_group.original_incoming_targets
            index = connections.incoming_index
        else:
            # Outgoing: connections originating FROM nodes in this group
            connection_list = node_group.external_outgoing_connections
            original_nodes_map = node_group.original_outgoing_sources
            index = connections.outgoing_index

        for conn in connection_list:
            # Get the parameter based on connection direction (target for incoming, source for outgoing)
            parameter = conn.target_parameter if is_incoming else conn.source_parameter

            # Only toggle control flow connections, skip data connections
            if parameter.type != ParameterTypeBuiltin.CONTROL_TYPE:
                continue

            conn_id = id(conn)
            original_node = original_nodes_map.get(conn_id)

            # Validate we have the original node mapping
            # Incoming connections must have originals (error if missing)
            # Outgoing connections may not have originals in some cases (skip if missing)
            if original_node is None:
                if is_incoming:
                    msg = f"No original target found for connection {conn_id} in node group '{node_group.group_id}'"
                    raise RuntimeError(msg)
                continue

            # Build the proxy parameter name: {sanitized_node_name}__{parameter_name}
            # Example: "My Node" with param "enter" -> "My_Node__enter"
            sanitized_node_name = original_node.name.replace(" ", "_")
            proxy_param_name = f"{sanitized_node_name}__{parameter.name}"

            # Determine the direction of the toggle
            if restore_to_original:
                # Restore: proxy -> original (for packaging)
                # Before: External -> Proxy -> (internal nodes)
                # After:  External -> Original node in group
                from_node = proxy_node
                from_param = proxy_param_name
                to_node = original_node
                to_param = parameter.name
            else:
                # Remap: original -> proxy (after packaging)
                # Before: External -> Original node in group
                # After:  External -> Proxy -> (internal nodes)
                from_node = original_node
                from_param = parameter.name
                to_node = proxy_node
                to_param = proxy_param_name

            # Step 1: Remove connection reference from the old node's index
            if from_node.name in index and from_param in index[from_node.name]:
                index[from_node.name][from_param].remove(conn_id)

            # Step 2: Update the connection object to point to the new node
            if is_incoming:
                conn.target_node = to_node
            else:
                conn.source_node = to_node

            # Step 3: Add connection reference to the new node's index
            index.setdefault(to_node.name, {}).setdefault(to_param, []).append(conn_id)

    def _toggle_control_connections(self, proxy_node: BaseNode, *, restore_to_original: bool) -> None:
        """Toggle control connections between proxy node and original nodes.

        Args:
            proxy_node: The proxy node containing the node group
            restore_to_original: If True, restore connections from proxy to original nodes.
                               If False, remap connections from original nodes back to proxy.
        """
        if not isinstance(proxy_node, NodeGroupProxyNode):
            return
        node_group = proxy_node.node_group_data
        connections = GriptapeNodes.FlowManager().get_connections()

        # Toggle both incoming and outgoing connections
        self._toggle_directional_control_connections(
            proxy_node, node_group, connections, restore_to_original=restore_to_original, is_incoming=True
        )
        self._toggle_directional_control_connections(
            proxy_node, node_group, connections, restore_to_original=restore_to_original, is_incoming=False
        )
