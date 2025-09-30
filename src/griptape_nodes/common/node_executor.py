from __future__ import annotations

import ast
import logging
import pickle
from pathlib import Path
from typing import TYPE_CHECKING, Any

from griptape_nodes.bootstrap.workflow_publishers.subprocess_workflow_publisher import SubprocessWorkflowPublisher
from griptape_nodes.drivers.storage.storage_backend import StorageBackend
from griptape_nodes.exe_types.core_types import ParameterTypeBuiltin
from griptape_nodes.exe_types.node_types import (
    CONTROL_INPUT_PARAMETER,
    LOCAL_EXECUTION,
    EndNode,
    NodeGroupProxyNode,
    StartNode,
)
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
    from griptape_nodes.retained_mode.managers.library_manager import LibraryManager

logger = logging.getLogger("griptape_nodes")


class NodeExecutor:
    """Simple singleton executor that draws methods from libraries and executes them dynamically."""

    def get_workflow_handler(self, library_name: str) -> LibraryManager.RegisteredEventHandler | None:
        """Get the PublishWorkflowRequest handler for a library, or None if not available."""
        library_manager = GriptapeNodes.LibraryManager()
        registered_handlers = library_manager.get_registered_event_handlers(PublishWorkflowRequest)
        if library_name in registered_handlers:
            return registered_handlers[library_name]
        return None

    async def execute(self, node: BaseNode, library_name: str | None = None) -> None:  # noqa: C901, PLR0912, PLR0915
        """Execute the given node.

        Args:
            node: The BaseNode to execute
            library_name: The library that the execute method should come from.
        """
        execution_type = node.get_parameter_value(node.execution_environment.name)
        if isinstance(node, NodeGroupProxyNode):
            logger.info("Handling Group")
            # TEST CASE: Simulate subprocess execution result for node group
            # Dictionary mapping proxy parameter names to (node_name, parameter_name)
            proxy_param_mapping = {
                "Agent__output": ("Agent", "output"),
                "Agent__prompt": ("Agent", "prompt"),
                "Display_Text__value": ("Text Input", "value"),
            }

            # Simulated subprocess result with random test values
            test_subprocess_result = {
                "workflow_output": {
                    "parameter_output_values": {
                        "Agent__output": "This is a test agent response",
                        "Agent__prompt": "Test prompt for the agent",
                        "Display_Text__value": "Test input value",
                    },
                    "unique_parameter_uuid_to_values": {},
                }
            }

            # Extract parameter values using the existing method
            parameter_output_values = self._extract_parameter_output_values(test_subprocess_result)
            logger.info("Extracted parameter values: %s", parameter_output_values)

            for proxy_param_name, param_value in parameter_output_values.items():
                if proxy_param_name in proxy_param_mapping:
                    target_node_name, target_param_name = proxy_param_mapping[proxy_param_name]
                    # Get the target node from the flow
                    if target_node_name in node.node_group_data.nodes:
                        target_node = node.node_group_data.nodes[target_node_name]
                        target_param = target_node.get_parameter_by_name(target_param_name)

                        if target_param is not None and target_param != target_node.execution_environment:
                            if target_param.type != ParameterTypeBuiltin.CONTROL_TYPE:
                                target_node.set_parameter_value(target_param_name, param_value)
                            target_node.parameter_output_values[target_param_name] = param_value
                            logger.info(
                                "Set parameter '%s' on node '%s' to value: %s",
                                target_param_name,
                                target_node_name,
                                param_value,
                            )
                    else:
                        logger.warning("Target node '%s' not found in flow", target_node_name)
                else:
                    logger.warning("Proxy parameter '%s' not in mapping", proxy_param_name)

            logger.info("Completed test case for NodeGroupProxyNode")
            return

        if execution_type == LOCAL_EXECUTION or execution_type is None:
            await node.aprocess()
            return

        try:
            library = LibraryRegistry.get_library(name=execution_type)
        except KeyError:
            logger.error("Could not find library for node '%s', defaulting to local execution.", node.name)
            await node.aprocess()
            return

        library_name = library.get_library_data().name
        workflow_handler = self.get_workflow_handler(library_name)
        if workflow_handler is None:
            logger.error("Could not find workflow handler for node '%s', defaulting to local execution.", node.name)
            await node.aprocess()
            return
        workflow_result = None
        published_workflow_filename = None

        try:
            (
                workflow_result,
                published_workflow_filename,
                file_name,
                output_parameter_prefix,
            ) = await self._publish_workflow(node, library, library_name)
            my_subprocess_result = await self._execute_subprocess(published_workflow_filename, file_name)
            parameter_output_values = self._extract_parameter_output_values(my_subprocess_result)
            self._apply_parameter_values_to_node(node, parameter_output_values, output_parameter_prefix)

        except Exception as e:
            logger.exception(
                "Failed to execute node '%s' via library executor '%s'. Node type: %s",
                node.name,
                library_name,
                node.__class__.__name__,
            )
            msg = f"Library executor failed for node '{node.name}': {e}"
            raise RuntimeError(msg) from e

        finally:
            GriptapeNodes.ConfigManager().set_config_value("pickle_control_flow_result", False)
            if workflow_result is not None and published_workflow_filename is not None:
                published_filename = Path(published_workflow_filename).stem
                for workflow in [
                    (workflow_result.workflow_metadata.name, Path(workflow_result.file_path)),
                    (published_filename, Path(published_workflow_filename)),
                ]:
                    await self._delete_workflow(workflow_name=workflow[0], workflow_path=workflow[1])

    async def _publish_workflow(
        self, node: BaseNode, library: Library, library_name: str
    ) -> tuple[SaveWorkflowFileFromSerializedFlowResultSuccess, Path, str, str]:
        """Package and publish a workflow for subprocess execution.

        Returns:
            Tuple of (workflow_result, published_workflow_filename, file_name, output_parameter_prefix)
        """
        start_node_type = library.get_nodes_by_base_type(StartNode)
        start_node_type = start_node_type[0] if len(start_node_type) > 0 else "StartFlow"

        end_node_type = library.get_nodes_by_base_type(EndNode)
        end_node_type = end_node_type[0] if len(end_node_type) > 0 else "EndFlow"

        sanitized_node_name = node.name.replace(" ", "_")
        output_parameter_prefix = f"{sanitized_node_name}_packaged_node_"
        sanitized_library_name = library_name.replace(" ", "_")

        request = PackageNodeAsSerializedFlowRequest(
            node_name=node.name,
            start_node_type=start_node_type,
            end_node_type=end_node_type,
            start_end_specific_library_name=library_name,
            entry_control_parameter_name=node._entry_control_parameter.name
            if node._entry_control_parameter is not None
            else None,
            output_parameter_prefix=output_parameter_prefix,
        )

        package_result = GriptapeNodes.handle_request(request)
        if not isinstance(package_result, PackageNodeAsSerializedFlowResultSuccess):
            msg = f"Failed to package node '{node.name}'. Error: {package_result.result_details}"
            raise RuntimeError(msg)  # noqa: TRY004

        file_name = f"{sanitized_node_name}_{sanitized_library_name}_packaged_flow"
        workflow_file_request = SaveWorkflowFileFromSerializedFlowRequest(
            file_name=file_name,
            serialized_flow_commands=package_result.serialized_flow_commands,
            workflow_shape=package_result.workflow_shape,
        )

        workflow_result = GriptapeNodes.handle_request(workflow_file_request)
        if not isinstance(workflow_result, SaveWorkflowFileFromSerializedFlowResultSuccess):
            msg = f"Failed to Save Workflow File from Serialized Flow for node '{node.name}'. Error: {package_result.result_details}"
            raise RuntimeError(msg)  # noqa: TRY004

        subprocess_workflow_publisher = SubprocessWorkflowPublisher()
        published_filename = f"{Path(workflow_result.file_path).stem}_published"
        published_workflow_filename = GriptapeNodes.ConfigManager().workspace_path / (published_filename + ".py")

        await subprocess_workflow_publisher.arun(
            workflow_name=file_name,
            workflow_path=workflow_result.file_path,
            publisher_name=library_name,
            published_workflow_file_name=published_filename,
        )

        if not published_workflow_filename.exists():
            msg = f"Published workflow file does not exist at path: {published_workflow_filename}"
            raise FileNotFoundError(msg)

        return workflow_result, published_workflow_filename, file_name, output_parameter_prefix

    async def _execute_subprocess(
        self,
        published_workflow_filename: Path,
        file_name: str,
    ) -> dict:
        """Execute the published workflow in a subprocess.

        Returns:
            The subprocess execution output dictionary
        """
        from griptape_nodes.bootstrap.workflow_executors.subprocess_workflow_executor import (
            SubprocessWorkflowExecutor,
        )

        GriptapeNodes.ConfigManager().set_config_value("pickle_control_flow_result", True)
        subprocess_executor = SubprocessWorkflowExecutor(workflow_path=str(published_workflow_filename))

        try:
            async with subprocess_executor as executor:
                await executor.arun(
                    workflow_name=file_name, flow_input={}, storage_backend=await self._get_storage_backend()
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

    def _extract_parameter_output_values(self, subprocess_result: dict) -> dict:
        """Extract and deserialize parameter output values from subprocess result.

        Returns:
            Dictionary of parameter names to their deserialized values
        """
        parameter_output_values = {}
        for result_dict in subprocess_result.values():
            # Handle backward compatibility: old flat structure
            if not isinstance(result_dict, dict) or "parameter_output_values" not in result_dict:
                parameter_output_values.update(result_dict)
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

    def _apply_parameter_values_to_node(
        self, node: BaseNode, parameter_output_values: dict, output_parameter_prefix: str
    ) -> None:
        """Apply deserialized parameter values back to the node.

        Sets parameter values on the node and updates parameter_output_values dictionary.
        """
        if "failed" in parameter_output_values and parameter_output_values["failed"] == CONTROL_INPUT_PARAMETER:
            msg = f"Failed to execute node: {node.name}, with exception: {parameter_output_values.get('result_details', 'No result details were returned.')}"
            raise RuntimeError(msg)
        for param_name, param_value in parameter_output_values.items():
            if param_name.startswith(output_parameter_prefix):
                clean_param_name = param_name[len(output_parameter_prefix) :]
                parameter = node.get_parameter_by_name(clean_param_name)

                if parameter is not None and parameter != node.execution_environment:
                    if parameter.type != ParameterTypeBuiltin.CONTROL_TYPE:
                        node.set_parameter_value(clean_param_name, param_value)
                    node.parameter_output_values[clean_param_name] = param_value

    async def _delete_workflow(self, workflow_name: str, workflow_path: Path) -> None:
        from griptape_nodes.node_library.workflow_registry import WorkflowRegistry
        from griptape_nodes.retained_mode.events.workflow_events import (
            DeleteWorkflowRequest,
            DeleteWorkflowResultFailure,
            LoadWorkflowMetadata,
            LoadWorkflowMetadataResultSuccess,
        )

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
