import logging
from collections.abc import Callable
from functools import wraps
from typing import Any

from griptape_nodes.retained_mode.events.arbitrary_python_events import RunArbitraryPythonStringRequest
from griptape_nodes.retained_mode.events.base_events import (
    ResultPayload,
)
from griptape_nodes.retained_mode.events.config_events import (
    GetConfigCategoryRequest,
    GetConfigValueRequest,
    SetConfigCategoryRequest,
    SetConfigValueRequest,
)
from griptape_nodes.retained_mode.events.connection_events import (
    CreateConnectionRequest,
    DeleteConnectionRequest,
    ListConnectionsForNodeRequest,
)
from griptape_nodes.retained_mode.events.execution_events import (
    CancelFlowRequest,
    ContinueExecutionStepRequest,
    GetFlowStateRequest,
    ResolveNodeRequest,
    SingleExecutionStepRequest,
    SingleNodeStepRequest,
    StartFlowRequest,
    UnresolveFlowRequest,
)
from griptape_nodes.retained_mode.events.flow_events import (
    CreateFlowRequest,
    DeleteFlowRequest,
    ListFlowsInFlowRequest,
    ListNodesInFlowRequest,
)
from griptape_nodes.retained_mode.events.library_events import (
    GetNodeMetadataFromLibraryRequest,
    ListNodeTypesInLibraryRequest,
    ListRegisteredLibrariesRequest,
)
from griptape_nodes.retained_mode.events.node_events import (
    CreateNodeRequest,
    DeleteNodeRequest,
    GetNodeMetadataRequest,
    GetNodeResolutionStateRequest,
    ListParametersOnNodeRequest,
    SetNodeMetadataRequest,
)
from griptape_nodes.retained_mode.events.object_events import (
    RenameObjectRequest,
)
from griptape_nodes.retained_mode.events.parameter_events import (
    AddParameterToNodeRequest,
    AlterParameterDetailsRequest,
    GetParameterDetailsRequest,
    GetParameterValueRequest,
    GetParameterValueResultFailure,
    RemoveParameterFromNodeRequest,
    SetParameterValueRequest,
)
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

MIN_NODES = 2

logger = logging.getLogger("griptpae_nodes_engine")


def node_param_split(node_and_param: str) -> tuple[str, str]:
    """Split a string in format 'node.param' into node and param."""
    if "." not in node_and_param:
        msg = f"Expected format 'node.param', got '{node_and_param}'"
        raise ValueError(msg)
    parts = node_and_param.split(".", 1)
    return parts[0], parts[1]  # Explicitly return two values


def command_arg_handler(node_param_split_func: Callable) -> Callable:
    """Decorator to handle different argument patterns for commands.

    Allows either a positional string argument in format "node.param"
    or explicit keyword arguments (node, param).
    """

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            # Skip first arg if it's the class (for @classmethod)
            instance_or_cls = args[0] if args else None
            args_to_process = args[1:] if args else []

            # Extract node and param information
            node = kwargs.get("node")
            param = kwargs.get("param")

            # Case 1: Direct string format as positional arg ("node.param")
            if args_to_process and isinstance(args_to_process[0], str):
                node_and_param = args_to_process[0]
                node_result, param_result = node_param_split_func(node_and_param)
                node = node_result  # Set the node
                param = param_result  # Set the param
                # Remove the processed arg
                args_to_process = args_to_process[1:]
            # Case 2: Explicit keyword args (already extracted)
            elif node is not None and param is not None:
                # We already have node and param from kwargs
                pass
            else:
                msg = (
                    "Either provide a string in format 'node.param' as the first argument "
                    "or both 'node' and 'param' as keyword arguments"
                )
                raise ValueError(msg)

            # Clean up kwargs by removing already processed arguments
            cleaned_kwargs = {k: v for k, v in kwargs.items() if k not in {"node", "param"}}

            # Call the original function with processed arguments
            if instance_or_cls is not None:
                return func(
                    instance_or_cls,
                    node=node,
                    param=param,
                    *args_to_process,
                    **cleaned_kwargs,
                )
            return func(node=node, param=param, *args_to_process, **cleaned_kwargs)

        return wrapper

    return decorator


class RetainedMode:
    # FLOW OPERATIONS
    @classmethod
    def create_flow(
        cls,
        flow_name: str | None = None,
        parent_flow_name: str | None = None,
    ) -> ResultPayload:
        request = CreateFlowRequest(parent_flow_name=parent_flow_name, flow_name=flow_name)
        result = GriptapeNodes().handle_request(request)
        return result

    @classmethod
    def delete_flow(cls, flow_name: str) -> ResultPayload:
        request = DeleteFlowRequest(flow_name=flow_name)
        result = GriptapeNodes().handle_request(request)
        return result

    @classmethod
    def get_flows(cls, parent_flow_name: str | None = None) -> ResultPayload:
        request = ListFlowsInFlowRequest(parent_flow_name=parent_flow_name)
        result = GriptapeNodes().handle_request(request)
        return result

    @classmethod
    def get_nodes_in_flow(cls, flow_name: str) -> ResultPayload:
        request = ListNodesInFlowRequest(flow_name=flow_name)
        result = GriptapeNodes().handle_request(request)
        return result

    # NODE OPERATIONS
    @classmethod
    def create_node(
        cls,
        node_type: str,
        specific_library_name: str | None = None,
        node_name: str | None = None,
        parent_flow_name: str | None = None,
        metadata: dict[Any, Any] | None = None,
    ) -> ResultPayload:
        request = CreateNodeRequest(
            node_name=node_name,
            node_type=node_type,
            specific_library_name=specific_library_name,
            override_parent_flow_name=parent_flow_name,
            metadata=metadata,
        )
        result = GriptapeNodes().handle_request(request)
        # Check if result is successful before accessing node_name
        if hasattr(result, "node_name"):
            return result.node_name
        # You could return the result object for debugging
        logger.error("Failed to create node: %s", result)
        return result

    @classmethod
    def delete_node(
        cls,
        node_name: str,
    ) -> ResultPayload:
        request = DeleteNodeRequest(node_name=node_name)
        result = GriptapeNodes().handle_request(request)
        return result

    @classmethod
    def get_resolution_state_for_node(cls, node_name: str) -> ResultPayload:
        request = GetNodeResolutionStateRequest(node_name=node_name)
        result = GriptapeNodes().handle_request(request)
        return result

    @classmethod
    def get_metadata_for_node(cls, node_name: str) -> ResultPayload:
        request = GetNodeMetadataRequest(node_name=node_name)
        result = GriptapeNodes().handle_request(request)
        return result

    @classmethod
    def set_metadata_for_node(cls, node_name: str, metadata: dict[Any, Any]) -> ResultPayload:
        request = SetNodeMetadataRequest(node_name=node_name, metadata=metadata)
        result = GriptapeNodes().handle_request(request)
        return result

    @classmethod
    def get_connections_for_node(cls, node_name: str) -> ResultPayload:
        request = ListConnectionsForNodeRequest(node_name=node_name)
        result = GriptapeNodes().handle_request(request)
        return result

    @classmethod
    def list_params(cls, node: str) -> ResultPayload:
        request = ListParametersOnNodeRequest(node_name=node)
        result = GriptapeNodes().handle_request(request)
        return result.parameter_names

    @classmethod
    def add_param(  # noqa: PLR0913
        cls,
        node_name: str,
        parameter_name: str,
        default_value: Any | None,
        tooltip: str | list[dict],
        type: str | None = None,  # noqa: A002
        input_types: list[str] | None = None,
        output_type: str | None = None,
        edit: bool = False,  # noqa: FBT001, FBT002
        tooltip_as_input: str | list[dict] | None = None,
        tooltip_as_property: str | list[dict] | None = None,
        tooltip_as_output: str | list[dict] | None = None,
        ui_options: dict | None = None,
        mode_allowed_input: bool = True,  # noqa: FBT001, FBT002
        mode_allowed_property: bool = True,  # noqa: FBT001, FBT002
        mode_allowed_output: bool = True,  # noqa: FBT001, FBT002
        **kwargs,  # noqa: ARG003
    ) -> ResultPayload:
        if edit:
            request = AlterParameterDetailsRequest(
                parameter_name=parameter_name,
                node_name=node_name,
                default_value=default_value,
                tooltip=tooltip,
                type=type,
                input_types=input_types,
                output_type=output_type,
                tooltip_as_input=tooltip_as_input,
                tooltip_as_property=tooltip_as_property,
                tooltip_as_output=tooltip_as_output,
                mode_allowed_input=mode_allowed_input,
                mode_allowed_property=mode_allowed_property,
                mode_allowed_output=mode_allowed_output,
                ui_options=ui_options,
            )
        else:
            request = AddParameterToNodeRequest(
                parameter_name=parameter_name,
                node_name=node_name,
                default_value=default_value,
                tooltip=tooltip,
                type=type,
                input_types=input_types,
                output_type=output_type,
                tooltip_as_input=tooltip_as_input,
                tooltip_as_property=tooltip_as_property,
                tooltip_as_output=tooltip_as_output,
                mode_allowed_input=mode_allowed_input,
                mode_allowed_property=mode_allowed_property,
                mode_allowed_output=mode_allowed_output,
                ui_options=ui_options,
            )
        result = GriptapeNodes().handle_request(request)
        return result

    # remove_parameter_from_node
    @classmethod
    def del_param(cls, node_name: str, parameter_name: str) -> ResultPayload:
        request = RemoveParameterFromNodeRequest(parameter_name=parameter_name, node_name=node_name)
        result = GriptapeNodes().handle_request(request)
        return result

    """
    @classmethod
    def get_parameter_details(cls, node_name: str, parameter_name: str) -> ResultPayload:
        event = GetParameterDetailsRequest(
            parameter_name=parameter_name, node_name=node_name
        )
        result = GriptapeNodes().handle_request(request)
        return result
    """

    @classmethod
    @command_arg_handler(node_param_split_func=node_param_split)
    def param_info(cls, *, node: str, param: str, **kwargs) -> Any:  # noqa: ARG003
        """Get parameter info for a node.

        Args:
            node: Name of the node
            param: Name of the parameter
            **kwargs: Additional arguments
        """
        request = GetParameterDetailsRequest(parameter_name=param, node_name=node)
        result = GriptapeNodes().handle_request(request)
        return result

    @classmethod
    def exists(cls, node: str) -> bool:
        rsl = GriptapeNodes.ObjectManager()
        return node in rsl.get_filtered_subset()

    @classmethod
    def get_list_index_from_param_str(cls, param_name: str) -> tuple[str, int | None]:
        index = None
        final_param_name = param_name
        # Check if we're trying to get a list index using syntax like "param[0]"
        if "[" in param_name and param_name.endswith("]"):
            try:
                # Extract the base parameter name and the index
                base_param_name, index_str = param_name.split("[", 1)
                index = int(index_str[:-1])  # Remove the closing ']' and convert to int
                final_param_name = base_param_name
            except Exception as e:
                details = f"Invalid list index format in parameter name: '{param_name}'. Error: {e}."
                logger.exception(details)
        return (final_param_name, index)

    @classmethod
    def parse_indexed_variable(cls, expr_str: str) -> tuple[str, list[str]]:
        """Parse an indexed variable expression and return the variable name and a list of index operations.

        Args:
            expr_str (str): The expression to parse (e.g., "my_value[2][3]" or "123_var['key']")

        Returns:
            tuple: (variable_name, list_of_indices)

        Examples:
            parse_indexed_variable("my_value[2][3]")
            # Returns: ("my_value", ["2", "3"])

            parse_indexed_variable("123var['key'][0]")
            # Returns: ("123var", ["'key'", "0"])
        """
        import re

        # Find the first opening bracket to separate the variable name from indexing operations
        bracket_match = re.search(r"[\[\{]", expr_str)

        if bracket_match:
            # There are indexing operations
            first_bracket_pos = bracket_match.start()
            var_name = expr_str[:first_bracket_pos]
            remaining = expr_str[first_bracket_pos:]
        else:
            # No indexing operations
            var_name = expr_str
            remaining = ""

        # Extract all index operations
        index_pattern = r"\[(.*?)\]"
        indices = re.findall(index_pattern, remaining)

        return var_name, indices

    @classmethod
    def _get_indexed_value(cls, node_name: str, base_param_name: str, indices: list) -> Any:
        """Get a value at specified indices from a container parameter.

        Args:
            node_name: Name of the node containing the parameter
            base_param_name: Base name of the parameter (without indices)
            indices: List of indices to navigate through

        Returns:
            tuple: (success, value_or_error) where success is a boolean and
                value_or_error is either the retrieved value or an error result
        """
        # Get the container value
        request = GetParameterValueRequest(
            parameter_name=base_param_name,
            node_name=node_name,
        )
        result = GriptapeNodes().handle_request(request)

        if not result.succeeded():
            return False, result

        # Navigate through indices
        curr_value = result.value
        for idx_or_key in indices:
            if isinstance(curr_value, list):
                # Convert index to int if needed
                try:
                    idx = int(idx_or_key) if not isinstance(idx_or_key, int) else idx_or_key
                except ValueError:
                    error_msg = f"Failed on key/index '{idx_or_key}'. Int required."
                    return False, error_msg

                # Check if index is in range
                if idx < 0 or idx >= len(curr_value):
                    error_msg = f"Failed on key/index '{idx_or_key}' because it was out of range. Object had {len(curr_value)} elements."
                    return False, error_msg

                curr_value = curr_value[idx]
            else:
                error_msg = f"Failed on key/index '{idx_or_key}' because container was a type that was not expected."
                return False, error_msg

        return True, curr_value

    @classmethod
    def _set_indexed_value(cls, node_name: str, base_param_name: str, indices: list, value: Any) -> ResultPayload:
        """Set a value at specified indices in a container parameter.

        Args:
            node_name: Name of the node containing the parameter
            base_param_name: Base name of the parameter (without indices)
            indices: List of indices to navigate through
            value: Value to set at the specified location

        Returns:
            ResultPayload: Result of the operation
        """
        # If no indices, set directly
        if not indices:
            request = SetParameterValueRequest(
                parameter_name=base_param_name,
                node_name=node_name,
                value=value,
            )
            return GriptapeNodes().handle_request(request)

        # Get the container value
        request = GetParameterValueRequest(
            parameter_name=base_param_name,
            node_name=node_name,
        )
        result = GriptapeNodes().handle_request(request)

        if not result.succeeded():
            return result

        # Navigate to the proper location and set the value
        container = result.value
        curr = container

        for index_ctr, idx_or_key in enumerate(indices):
            if isinstance(curr, list):
                # Convert index to int
                try:
                    idx = int(idx_or_key)
                except ValueError:
                    error_msg = f"Failed on key/index '{idx_or_key}' because it wasn't an int as expected."
                    logger.error(error_msg)
                    return GetParameterValueResultFailure()

                # Handle negative indices
                if idx < 0:
                    error_msg = f"Failed on key/index '{idx_or_key}' because it was less than zero."
                    logger.error(error_msg)
                    return GetParameterValueResultFailure()

                # Extend the list if needed
                while len(curr) <= idx:
                    curr.append(None)

                # If at the final index, set the value
                if index_ctr == len(indices) - 1:
                    curr[idx] = value
                else:
                    # Move to the next level
                    curr = curr[idx]
            else:
                error_msg = f"Failed on key/index '{idx_or_key}' because it was a type that was not expected."
                logger.error(error_msg)
                return GetParameterValueResultFailure()

        # Update the container
        set_request = SetParameterValueRequest(
            parameter_name=base_param_name,
            node_name=node_name,
            value=container,
        )
        return GriptapeNodes().handle_request(set_request)

    @classmethod
    def get_value(cls, *args, **kwargs) -> Any:
        node = kwargs.pop("node", None)
        param = kwargs.pop("param", None)
        lrg = len(args)
        if lrg > 0:
            node, param = node_param_split(args[0])

        # Chop up the param name to see if there are any indices/keys in there.
        base_param_name, indices = cls.parse_indexed_variable(param)

        request = GetParameterValueRequest(
            parameter_name=base_param_name,
            node_name=node,
        )
        result = GriptapeNodes().handle_request(request)

        if result.succeeded():
            # Now see if there were any indices specified.
            curr_pos_value = result.value
            for idx_or_key in indices:
                # What is the type of the current object in the chain?
                if isinstance(curr_pos_value, list):
                    # Index better be an int.
                    if not isinstance(idx_or_key, int):
                        logger.error(
                            "get_value failed for %s.%s on key/index %s only ints allowed.",
                            node,
                            param,
                            idx_or_key,
                        )
                        return GetParameterValueResultFailure()
                    # Is the index in range?
                    if (idx_or_key < 0) or (idx_or_key >= len(curr_pos_value)):
                        logger.error(
                            "get_value failed for %s.%s on key/index %s out of range.",
                            node,
                            param,
                            idx_or_key,
                        )
                        return GetParameterValueResultFailure()
                    curr_pos_value = curr_pos_value[idx_or_key]
                else:
                    logger.error(
                        "get_value failed for %s.%s on key/index %s because it was a type that was not expected.",
                        node,
                        param,
                        idx_or_key,
                    )
                    return GetParameterValueResultFailure()
            # All done
            return curr_pos_value
        return result

    @classmethod
    def set_value(cls, *args, **kwargs) -> Any:  # noqa: C901, PLR0912
        node = kwargs.pop("node", None)
        param = kwargs.pop("param", None)
        value = kwargs.pop("value", None)

        lrg = len(args)
        if lrg > 0:
            node, param = node_param_split(args[0])
        if lrg > 1 and value is None:
            value = args[1]

        if not node or not param or value is None:
            msg = (
                "Missing required parameters. Use one of these formats:\n"
                '  set_value("node.param", value)\n'
                '  set_value("node.param", value=value)\n'
                '  set_value(node="node", param="param", value=value)'
            )
            raise ValueError(msg)

        # Chop up the param name to see if there are any indices/keys in there.
        base_param_name, indices = cls.parse_indexed_variable(param)

        # If we have no indices, set the value directly.
        if len(indices) == 0:
            request = SetParameterValueRequest(
                parameter_name=base_param_name,
                node_name=node,
                value=value,
            )
            result = GriptapeNodes().handle_request(request)
            logger.info("\nD:%s", f"{result=}")
        else:
            # We have indices. Get the value of the container first, then attempt to move all the way up to the end.
            request = GetParameterValueRequest(
                parameter_name=base_param_name,
                node_name=node,
            )
            result = GriptapeNodes().handle_request(request)

            if not result.succeeded():
                logger.error(
                    'set_value failed for "%s.%s", failed to get value for container "%s".',
                    node,
                    param,
                    base_param_name,
                )
                return result

            base_container = result.value
            # Start progress at the base
            curr_pos_value = base_container
            for index_ctr, idx_or_key in enumerate(indices):
                # What is the type of the current object in the chain?
                if isinstance(curr_pos_value, list):
                    # Index better be an int.
                    try:
                        idx_or_key_as_int = int(idx_or_key)
                    except ValueError:
                        logger.exception(
                            'set_value for "%s.%s", failed on key/index "%s". Requires an int.',
                            node,
                            param,
                            idx_or_key,
                        )
                        return GetParameterValueResultFailure()
                    # Is the index in range?
                    if idx_or_key_as_int < 0:
                        logger.error(
                            'set_value for "%s.%s", failed on key/index "%s" because it was less than zero.',
                            node,
                            param,
                            idx_or_key,
                        )
                        return GetParameterValueResultFailure()
                    # Extend the list if needed to accommodate the index.
                    while len(curr_pos_value) <= idx_or_key_as_int:
                        curr_pos_value.append(None)

                    # If we're at the end, assign the value.
                    if index_ctr == len(indices) - 1:
                        curr_pos_value[idx_or_key_as_int] = value

                        # Actually attempt to set the value, which should do type validation, etc.
                        request = SetParameterValueRequest(
                            parameter_name=base_param_name,
                            node_name=node,
                            value=base_container,  # Re-assign the entire updated container.
                        )
                        result = GriptapeNodes().handle_request(request)
                        return result
                    # Advance.
                    curr_pos_value = curr_pos_value[idx_or_key_as_int]
                else:
                    logger.error(
                        'set_value on "%s.%s" failed on key/index "%s" because it was a type that was not expected.',
                        node,
                        param,
                        idx_or_key,
                    )
                    return GetParameterValueResultFailure()
            # All done
        return result

    @classmethod
    def connect(cls, source: str, destination: str) -> ResultPayload:
        src_node, src_param = node_param_split(source)
        dst_node, dst_param = node_param_split(destination)

        request = CreateConnectionRequest(
            source_node_name=src_node,
            source_parameter_name=src_param,
            target_node_name=dst_node,
            target_parameter_name=dst_param,
        )
        return GriptapeNodes().handle_request(request)

    @classmethod
    def exec_chain(cls, *node_names) -> dict:
        """Creates exec_out -> exec_in connections between a sequence of nodes.

        Args:
            *node_names: Variable number of node names to chain together

        Returns:
            Dictionary with results of each connection attempt
        """
        results = {}
        failures = []

        # Need at least 2 nodes to make a connection
        if len(node_names) < MIN_NODES:
            return {"error": "Need at least 2 nodes to create a chain"}

        # Create connections between consecutive nodes
        for i in range(len(node_names) - 1):
            source_node = node_names[i]
            target_node = node_names[i + 1]

            request = CreateConnectionRequest(
                source_node_name=source_node,
                source_parameter_name="exec_out",
                target_node_name=target_node,
                target_parameter_name="exec_in",
            )

            result = GriptapeNodes().handle_request(request)
            results[f"{source_node} -> {target_node}"] = result

            # Track failures without halting execution
            if not hasattr(result, "success") or not result.success:
                failures.append(f"{source_node} -> {target_node}")

        # Add summary of failures to the results
        if failures:
            results["failures"] = failures

        return results

    @classmethod
    def delete_connection(
        cls,
        source_node_name: str,
        source_param_name: str,
        target_node_name: str,
        target_param_name: str,
    ) -> ResultPayload:
        request = DeleteConnectionRequest(
            source_node_name=source_node_name,
            source_parameter_name=source_param_name,
            target_node_name=target_node_name,
            target_parameter_name=target_param_name,
        )
        result = GriptapeNodes().handle_request(request)
        return result

    # LIBRARY OPERATIONS
    @classmethod
    def get_available_libraries(cls) -> ResultPayload:
        request = ListRegisteredLibrariesRequest()
        result = GriptapeNodes().handle_request(request)
        return result

    @classmethod
    def get_node_types_in_library(cls, library_name: str) -> ResultPayload:
        request = ListNodeTypesInLibraryRequest(library=library_name)
        result = GriptapeNodes().handle_request(request)
        return result

    @classmethod
    def get_node_metadata_from_library(cls, library_name: str, node_type_name: str) -> ResultPayload:
        request = GetNodeMetadataFromLibraryRequest(library=library_name, node_type=node_type_name)
        result = GriptapeNodes().handle_request(request)
        return result

    # FLOW OPERATIONS
    @classmethod
    def run_flow(cls, flow_name: str) -> ResultPayload:
        request = StartFlowRequest(flow_name=flow_name, debug_mode=False)
        result = GriptapeNodes().handle_request(request)
        return result

    @classmethod
    def run_node(cls, node_name: str) -> ResultPayload:
        request = ResolveNodeRequest(node_name=node_name)
        result = GriptapeNodes().handle_request(request)
        return result

    @classmethod
    def single_step(cls, flow_name: str) -> ResultPayload:
        request = SingleNodeStepRequest(flow_name=flow_name)
        return GriptapeNodes().handle_request(request)

    @classmethod
    def single_execution_step(cls, flow_name: str) -> ResultPayload:
        request = SingleExecutionStepRequest(flow_name=flow_name)
        return GriptapeNodes().handle_request(request)

    @classmethod
    def continue_flow(cls, flow_name: str) -> ResultPayload:
        request = ContinueExecutionStepRequest(flow_name=flow_name)
        return GriptapeNodes().handle_request(request)

    @classmethod
    def reset_flow(cls, flow_name: str) -> ResultPayload:
        request = UnresolveFlowRequest(flow_name=flow_name)
        return GriptapeNodes().handle_request(request)

    @classmethod
    def cancel_flow(cls, flow_name: str) -> ResultPayload:
        request = CancelFlowRequest(flow_name=flow_name)
        return GriptapeNodes().handle_request(request)

    @classmethod
    def get_flow_state(cls, flow_name: str) -> ResultPayload:
        request = GetFlowStateRequest(flow_name=flow_name)
        return GriptapeNodes().handle_request(request)

    # ARBITRARY PYTHON EXECUTION
    @classmethod
    def run_arbitrary_python(cls, python_str: str) -> ResultPayload:
        request = RunArbitraryPythonStringRequest(python_string=python_str)
        result = GriptapeNodes().handle_request(request)
        return result

    # CONFIG MANAGER
    @classmethod
    def get_config_value(cls, category_and_key: str) -> ResultPayload:
        request = GetConfigValueRequest(category_and_key=category_and_key)
        result = GriptapeNodes().handle_request(request)
        return result

    @classmethod
    def set_config_value(cls, category_and_key: str, value: Any) -> ResultPayload:
        request = SetConfigValueRequest(category_and_key=category_and_key, value=value)
        result = GriptapeNodes().handle_request(request)
        return result

    @classmethod
    def get_config_category(cls, category: str | None) -> ResultPayload:
        request = GetConfigCategoryRequest(category=category)
        result = GriptapeNodes().handle_request(request)
        return result

    @classmethod
    def set_config_category(cls, category: str | None, contents: dict[str, Any]) -> ResultPayload:
        request = SetConfigCategoryRequest(category=category, contents=contents)
        result = GriptapeNodes().handle_request(request)
        return result

    @classmethod
    def rename(cls, object_name: str, requested_name: str) -> ResultPayload:
        request = RenameObjectRequest(
            object_name=object_name,
            requested_name=requested_name,
            allow_next_closest_name_available=True,
        )
        result = GriptapeNodes().handle_request(request)
        return result

    @classmethod
    def ls(cls, **kwargs) -> list:
        rsl = GriptapeNodes.ObjectManager()
        as_dict = rsl.get_filtered_subset(**kwargs)
        return list(as_dict.keys())
