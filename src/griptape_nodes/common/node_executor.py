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
    EndNode,
    StartNode,
)
from griptape_nodes.node_library.library_registry import Library, LibraryRegistry
from griptape_nodes.node_library.workflow_registry import WorkflowRegistry
from griptape_nodes.retained_mode.events.flow_events import (
    PackageNodeAsSerializedFlowRequest,
    PackageNodeAsSerializedFlowResultSuccess,
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
    from griptape_nodes.exe_types.node_types import BaseNode
    from griptape_nodes.retained_mode.events.node_events import SerializedNodeCommands
    from griptape_nodes.retained_mode.managers.library_manager import LibraryManager

logger = logging.getLogger("griptape_nodes")


class PublishLocalWorkflowResult(NamedTuple):
    """Result from publishing a local workflow."""

    workflow_result: SaveWorkflowFileFromSerializedFlowResultSuccess
    file_name: str
    output_parameter_prefix: str


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
        output_parameter_prefix: str,
    ) -> None:
        """Execute workflow in subprocess and apply results to node.

        Args:
            node: The node to apply results to
            workflow_path: Path to workflow file to execute
            file_name: Name of workflow for logging
            output_parameter_prefix: Prefix for output parameters
        """
        my_subprocess_result = await self._execute_subprocess(workflow_path, file_name)
        parameter_output_values = self._extract_parameter_output_values(my_subprocess_result)
        self._apply_parameter_values_to_node(node, parameter_output_values, output_parameter_prefix)

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
                node, Path(workflow_result.file_path), result.file_name, result.output_parameter_prefix
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
                node, published_workflow_filename, result.file_name, result.output_parameter_prefix
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
        # We have to make our defaults strings because the PackageNodeAsSerializedFlowRequest doesn't accept None types.
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
            pickle_control_flow_result=True,
        )

        workflow_result = GriptapeNodes.handle_request(workflow_file_request)
        if not isinstance(workflow_result, SaveWorkflowFileFromSerializedFlowResultSuccess):
            msg = f"Failed to Save Workflow File from Serialized Flow for node '{node.name}'. Error: {package_result.result_details}"
            raise RuntimeError(msg)  # noqa: TRY004

        return PublishLocalWorkflowResult(
            workflow_result=workflow_result, file_name=file_name, output_parameter_prefix=output_parameter_prefix
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
                    workflow_name=file_name,
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

    def _apply_parameter_values_to_node(
        self, node: BaseNode, parameter_output_values: dict[str, Any], output_parameter_prefix: str
    ) -> None:
        """Apply deserialized parameter values back to the node.

        Sets parameter values on the node and updates parameter_output_values dictionary.
        """
        # If the packaged flow fails, the End Flow Node in the library published workflow will have entered from 'failed'. That means that running the node failed, but was caught by the published flow.
        # In this case, we should fail the node, since it didn't complete properly.
        if "failed" in parameter_output_values and parameter_output_values["failed"] == CONTROL_INPUT_PARAMETER:
            msg = f"Failed to execute node: {node.name}, with exception: {parameter_output_values.get('result_details', 'No result details were returned.')}"
            raise RuntimeError(msg)
        for param_name, param_value in parameter_output_values.items():
            # We are grabbing all of the parameters on our end nodes that align with the node being published.
            if param_name.startswith(output_parameter_prefix):
                clean_param_name = param_name[len(output_parameter_prefix) :]
                # If the parameter exists on the node, then we need to set those values on the node.
                parameter = node.get_parameter_by_name(clean_param_name)
                # Don't set execution_environment, since that will be set to Local Execution on any published flow.
                if parameter is None:
                    msg = (
                        "Parameter '%s' from parameter output values not found on node '%s'",
                        clean_param_name,
                        node.name,
                    )
                    logger.error(msg)
                    raise RuntimeError(msg)
                if parameter != node.execution_environment:
                    if parameter.type != ParameterTypeBuiltin.CONTROL_TYPE:
                        # If the node is control type, only set its value in parameter_output_values.
                        node.set_parameter_value(clean_param_name, param_value)
                    node.parameter_output_values[clean_param_name] = param_value

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
