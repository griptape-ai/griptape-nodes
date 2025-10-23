from __future__ import annotations

import ast
import logging
import pickle
from pathlib import Path
from typing import TYPE_CHECKING, Any, NamedTuple

from griptape_nodes.bootstrap.workflow_publishers.subprocess_workflow_publisher import SubprocessWorkflowPublisher
from griptape_nodes.drivers.storage.storage_backend import StorageBackend
from griptape_nodes.exe_types.core_types import ParameterTypeBuiltin
from griptape_nodes.exe_types.node_types import (
    CONTROL_INPUT_PARAMETER,
    LOCAL_EXECUTION,
    PRIVATE_EXECUTION,
    BaseNode,
    EndNode,
    NodeGroup,
    NodeGroupProxyNode,
    StartNode,
)
from griptape_nodes.node_library.library_registry import Library, LibraryRegistry
from griptape_nodes.node_library.workflow_registry import WorkflowRegistry
from griptape_nodes.retained_mode.events.flow_events import (
    PackageNodesAsSerializedFlowRequest,
    PackageNodesAsSerializedFlowResultSuccess,
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

if TYPE_CHECKING:
    from griptape_nodes.exe_types.connections import Connections
    from griptape_nodes.retained_mode.events.node_events import SerializedNodeCommands
    from griptape_nodes.retained_mode.managers.library_manager import LibraryManager

logger = logging.getLogger("griptape_nodes")


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
    ) -> dict[str, dict[str | SerializedNodeCommands.UniqueParameterValueUUID, Any] | None]:
        """Execute the published workflow in a subprocess.

        Args:
            published_workflow_filename: Path to the workflow file to execute
            file_name: Name of the workflow for logging
            pickle_control_flow_result: Whether to pickle control flow results (defaults to True)

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
                    flow_input={},
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
        parameter_name_mappings = package_result.parameter_name_mappings
        for param_name, param_value in parameter_output_values.items():
            # Check if this parameter has a mapping back to an original node parameter
            if param_name not in parameter_name_mappings:
                continue

            original_node_param = parameter_name_mappings[param_name]
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
