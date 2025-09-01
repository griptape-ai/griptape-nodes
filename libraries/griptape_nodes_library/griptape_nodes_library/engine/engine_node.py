import dataclasses
import inspect
import logging
import types
from typing import Any, ClassVar, NamedTuple, Union, get_origin, get_type_hints

from griptape_nodes.exe_types.core_types import (
    ControlParameterOutput,
    Parameter,
    ParameterMessage,
    ParameterMode,
    ParameterType,
    ParameterTypeBuiltin,
)
from griptape_nodes.exe_types.node_types import ControlNode
from griptape_nodes.retained_mode.events.base_events import (
    RequestPayload,
    ResultPayloadFailure,
    ResultPayloadSuccess,
)
from griptape_nodes.retained_mode.events.payload_registry import PayloadRegistry
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
from griptape_nodes.traits.options import Options

logger = logging.getLogger(__name__)


class ResultClasses(NamedTuple):
    """Result classes for a RequestPayload."""

    success_class: type | None
    failure_class: type | None


@dataclasses.dataclass
class RequestInfo:
    """Information about a RequestPayload and its associated result classes."""

    request_class: type
    success_class: type | None
    failure_class: type | None
    has_results: bool


class EngineNode(ControlNode):
    # Fields to skip when creating output parameters from result classes
    _SKIP_RESULT_FIELDS: ClassVar[set[str]] = {"result_details", "altered_workflow_state", "exception"}

    # Parameter name prefixes
    _INPUT_PARAMETER_NAME_PREFIX = "input_"
    _OUTPUT_SUCCESS_PARAMETER_NAME_PREFIX = "output_success_"
    _OUTPUT_FAILURE_PARAMETER_NAME_PREFIX = "output_failure_"

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)

        # Store discovered request types and their result mappings
        self._request_types = self._discover_request_types()

        # Create request type selector dropdown
        self.request_options = []
        for request_name, info in sorted(self._request_types.items()):
            display_name = request_name
            if not info.has_results:
                display_name += " *"
            self.request_options.append(display_name)

        # Ensure we have at least one option for the Parameter
        default_options = self.request_options if self.request_options else ["No requests available"]

        self.request_selector = Parameter(
            name="request_type",
            tooltip="Select the RequestPayload type to execute",
            type="str",
            default_value=default_options[0],
            traits={Options(choices=default_options)},
        )
        self.add_parameter(self.request_selector)

        # Documentation message
        self.info_message = ParameterMessage(
            variant="info",
            value="Select a request type to see its documentation and parameters.",
            name="documentation",
        )
        self.add_node_element(self.info_message)

        # Control outputs for success/failure routing
        self.success_output = ControlParameterOutput(
            name="success",
            tooltip="Executes when the request succeeds",
            display_name="Succeeded",
        )
        self.add_parameter(self.success_output)

        self.failure_output = ControlParameterOutput(
            name="failure",
            tooltip="Executes when the request fails",
            display_name="Failed",
        )
        self.add_parameter(self.failure_output)

        # Initialize with first valid request type if available
        if self.request_options:
            self._update_parameters_for_request_type(self.request_options[0])

        # Track execution state for control flow routing
        self._execution_succeeded: bool | None = None

    # Public Methods
    def process(self) -> None:
        """Execute the selected request and handle the result."""
        # Step 1: Reset execution state at the start of each run
        self._execution_succeeded = None

        # Step 2: Get the selected request type from the dropdown
        selected_type = self.get_parameter_value(self.request_selector.name)
        if not selected_type:
            logger.error("No request type selected")
            msg = "No request type selected. Please choose a RequestPayload type from the dropdown."
            raise ValueError(msg)

        # Step 3: Clean up the request type name (remove asterisk if present)
        clean_type = selected_type.rstrip(" *")
        if clean_type not in self._request_types:
            logger.error("Unknown request type: %s", clean_type)
            msg = f"Unknown request type '{clean_type}'. Please select a valid type from the dropdown."  # noqa: S608
            raise ValueError(msg)

        # Step 4: Get request information and validate it has result classes
        request_info = self._request_types[clean_type]
        if not request_info.has_results:
            logger.warning(
                "Could not find corresponding ResultPayload classes for request type '%s' - execution skipped",
                clean_type,
            )
            msg = (
                f"Cannot execute '{clean_type}': corresponding Success/Failure result classes not found in the system."
            )
            raise ValueError(msg)

        # Step 5: Build the request arguments from input parameters
        request_kwargs = self._build_request_kwargs(request_info.request_class)

        # Step 6: Execute the request and handle success/failure routing
        self._execute_request(request_info.request_class, request_kwargs)

    def get_next_control_output(self) -> Parameter | None:
        """Determine which control output to follow based on execution result."""
        if self._execution_succeeded is None:
            # Execution hasn't completed yet
            self.stop_flow = True
            return None

        if self._execution_succeeded:
            return self.success_output
        return self.failure_output

    def validate_before_workflow_run(self) -> list[Exception] | None:
        """Engine nodes have side effects and need to execute every workflow run."""
        from griptape_nodes.exe_types.node_types import NodeResolutionState

        self.make_node_unresolved(
            current_states_to_trigger_change_event={NodeResolutionState.RESOLVED, NodeResolutionState.RESOLVING}
        )
        return None

    def validate_before_node_run(self) -> list[Exception] | None:
        """Engine nodes have side effects and need to execute every time they run."""
        from griptape_nodes.exe_types.node_types import NodeResolutionState

        self.make_node_unresolved(
            current_states_to_trigger_change_event={NodeResolutionState.RESOLVED, NodeResolutionState.RESOLVING}
        )
        return None

    def set_parameter_value(
        self,
        param_name: str,
        value: Any,
        *,
        initial_setup: bool = False,
        emit_change: bool = True,
        skip_before_value_set: bool = False,
    ) -> None:
        """Override to handle request_type parameter changes."""
        # Handle request type changes with connection cleanup
        if param_name == self.request_selector.name and not initial_setup:
            current_value = self.get_parameter_value(self.request_selector.name)
            if current_value != value:
                # Request type is changing - clean up dynamic parameter connections first
                logger.info("Request type changing from %s to %s", current_value, value)
                self._cleanup_dynamic_parameter_connections()

        super().set_parameter_value(
            param_name,
            value,
            initial_setup=initial_setup,
            emit_change=emit_change,
            skip_before_value_set=skip_before_value_set,
        )

        if param_name == self.request_selector.name:
            self._update_parameters_for_request_type(value)

    def _cleanup_dynamic_parameter_connections(self) -> None:
        """Remove all connections to/from dynamic parameters when request type changes."""
        from griptape_nodes.retained_mode.events.connection_events import (
            DeleteConnectionRequest,
            DeleteConnectionResultSuccess,
            ListConnectionsForNodeRequest,
            ListConnectionsForNodeResultSuccess,
        )
        from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

        connections_request = ListConnectionsForNodeRequest(node_name=self.name)
        connections_result = GriptapeNodes.handle_request(connections_request)

        if not isinstance(connections_result, ListConnectionsForNodeResultSuccess):
            logger.error("Failed to list connections for node '%s': %s", self.name, connections_result.result_details)
            return

        # Delete incoming connections to dynamic parameters
        for connection in connections_result.incoming_connections:
            if self._is_dynamic_parameter(connection.target_parameter_name):
                logger.debug(
                    "Deleting dynamic incoming connection: %s.%s -> %s.%s",
                    connection.source_node_name,
                    connection.source_parameter_name,
                    self.name,
                    connection.target_parameter_name,
                )
                delete_request = DeleteConnectionRequest(
                    source_node_name=connection.source_node_name,
                    source_parameter_name=connection.source_parameter_name,
                    target_node_name=self.name,
                    target_parameter_name=connection.target_parameter_name,
                )
                delete_result = GriptapeNodes.handle_request(delete_request)
                if not isinstance(delete_result, DeleteConnectionResultSuccess):
                    logger.error("Failed to delete dynamic incoming connection: %s", delete_result.result_details)

        # Delete outgoing connections from dynamic parameters
        for connection in connections_result.outgoing_connections:
            if self._is_dynamic_parameter(connection.source_parameter_name):
                logger.debug(
                    "Deleting dynamic outgoing connection: %s.%s -> %s.%s",
                    self.name,
                    connection.source_parameter_name,
                    connection.target_node_name,
                    connection.target_parameter_name,
                )
                delete_request = DeleteConnectionRequest(
                    source_node_name=self.name,
                    source_parameter_name=connection.source_parameter_name,
                    target_node_name=connection.target_node_name,
                    target_parameter_name=connection.target_parameter_name,
                )
                delete_result = GriptapeNodes.handle_request(delete_request)
                if not isinstance(delete_result, DeleteConnectionResultSuccess):
                    logger.error("Failed to delete dynamic outgoing connection: %s", delete_result.result_details)

    def _is_dynamic_parameter(self, parameter_name: str) -> bool:
        """Check if a parameter is dynamically created (vs static control parameters)."""
        # Dynamic parameters follow these patterns:
        # - Input parameters: input_{field_name}
        # - Output parameters: output_success_{field_name}, output_failure_{field_name}
        return parameter_name.startswith(
            (
                self._INPUT_PARAMETER_NAME_PREFIX,
                self._OUTPUT_SUCCESS_PARAMETER_NAME_PREFIX,
                self._OUTPUT_FAILURE_PARAMETER_NAME_PREFIX,
            )
        )

    # Private Methods
    def _discover_request_types(self) -> dict[str, RequestInfo]:
        """Discover all RequestPayload types and their corresponding Result types."""
        registry = PayloadRegistry.get_registry()
        request_types = {}

        for name, cls in registry.items():
            if inspect.isclass(cls) and issubclass(cls, RequestPayload) and cls != RequestPayload:
                # Find corresponding result classes using heuristics
                result_classes = self._find_result_classes(name, registry)

                request_types[name] = RequestInfo(
                    request_class=cls,
                    success_class=result_classes.success_class,
                    failure_class=result_classes.failure_class,
                    has_results=result_classes.success_class is not None or result_classes.failure_class is not None,
                )

        return request_types

    def _find_result_classes(self, request_name: str, registry: dict) -> ResultClasses:
        """Find corresponding Success and Failure result classes for a request."""
        # Determine the base name for pattern matching
        request_suffix = "Request"
        if request_name.endswith(request_suffix):
            base_name = request_name[: -len(request_suffix)]  # Remove "Request"
        else:
            # For classes like LoadWorkflowMetadata, use the full name
            base_name = request_name

        # Try different patterns for success/failure class names
        success_patterns = [
            f"{base_name}ResultSuccess",  # Pattern: {Base}ResultSuccess
            f"{base_name}Success",  # Pattern: {Base}Success
            f"{base_name}_ResultSuccess",  # Snake_case variants
            f"{base_name}Result_Success",
            f"{base_name}_Success",
        ]

        failure_patterns = [
            f"{base_name}ResultFailure",  # Standard pattern
            f"{base_name}Failure",  # Pattern: {Base}Failure
            f"{base_name}_ResultFailure",  # Snake_case variants
            f"{base_name}Result_Failure",
            f"{base_name}_Failure",
        ]

        success_class = None
        failure_class = None

        # Look for success class
        for pattern in success_patterns:
            if pattern in registry:
                cls = registry[pattern]
                if inspect.isclass(cls) and issubclass(cls, ResultPayloadSuccess):
                    success_class = cls
                    break

        # Look for failure class
        for pattern in failure_patterns:
            if pattern in registry:
                cls = registry[pattern]
                if inspect.isclass(cls) and issubclass(cls, ResultPayloadFailure):
                    failure_class = cls
                    break

        return ResultClasses(success_class, failure_class)

    def _update_parameters_for_request_type(self, selected_type: str) -> None:
        """Update node parameters based on selected request type."""
        # Remove asterisk if present
        clean_type = selected_type.rstrip(" *")

        if clean_type not in self._request_types:
            return

        request_info = self._request_types[clean_type]
        request_class = request_info.request_class

        # Clear existing dynamic parameters (keep core ones)
        core_params = {self.request_selector.name, "documentation", "success", "failure"}

        # Remove dynamic parameters and messages
        elements_to_remove = [elem for elem in self.root_ui_element._children if elem.name not in core_params]
        for elem in elements_to_remove:
            self.remove_parameter_element(elem)

        # Update documentation
        doc_text = request_class.__doc__ or f"Execute {clean_type} request"
        self.info_message.value = doc_text

        # Check if request type is usable
        if not request_info.has_results:
            error_msg = ParameterMessage(
                variant="error",
                value=f"Cannot use {clean_type}: corresponding Success and Failure result classes not found",
                name="error_message",
            )
            self.add_node_element(error_msg)
            return

        # Create request parameters
        self._create_request_parameters(request_class)

        # Create result parameters
        self._create_result_parameters(request_info)

    def _create_request_parameters(self, request_class: type) -> None:
        """Create input parameters for the request class."""
        if not (dataclasses.is_dataclass(request_class) and dataclasses.fields(request_class)):
            return

        # Only create parameters if there are fields to show (excluding request_id)
        fields_to_show = [f for f in dataclasses.fields(request_class) if f.name != "request_id"]
        if not fields_to_show:
            return

        # Get resolved type hints to handle string annotations
        try:
            type_hints = get_type_hints(request_class)
        except Exception:
            # Fallback to field.type if get_type_hints fails
            type_hints = {}

        for field in fields_to_show:
            param = self._create_input_parameter_for_field(field, type_hints)
            self.add_parameter(param)

    def _create_input_parameter_for_field(self, field: Any, type_hints: dict) -> Parameter:
        """Create an input parameter for a dataclass field."""
        # Use resolved type hint if available, otherwise fall back to field.type
        field_type = type_hints.get(field.name, field.type)

        # Get input types for Union types, or single type for simple types
        input_types = self._get_input_types_for_field(field_type)

        # Determine default value
        default_value = self._get_field_default_value(field)

        tooltip = f"Input for {field.name} (accepts: {', '.join(input_types)})"
        if field.metadata.get("description"):
            tooltip = f"{field.metadata['description']} (accepts: {', '.join(input_types)})"

        # Add (optional) suffix for Optional fields
        display_name = field.name
        if self._is_optional_type(field_type):
            display_name += " (optional)"

        return Parameter(
            name=f"{self._INPUT_PARAMETER_NAME_PREFIX}{field.name}",
            tooltip=tooltip,
            input_types=input_types,
            default_value=default_value,
            allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            ui_options={"display_name": display_name},
            user_defined=True,
        )

    def _get_field_default_value(self, field: Any) -> Any:
        """Get the default value for a dataclass field."""
        if field.default != dataclasses.MISSING:
            return field.default
        if field.default_factory != dataclasses.MISSING:
            try:
                return field.default_factory()
            except Exception:
                return None
        return None

    def _get_input_types_for_field(self, python_type: Any) -> list[str]:
        """Convert Python type annotation to list of input types for Parameter."""
        if self._is_union_type(python_type):
            # For Union types, convert each non-None type to a string
            input_types = [
                self._python_type_to_param_type(arg)
                for arg in python_type.__args__
                if arg is not type(None)  # Skip None types
            ]
            return input_types if input_types else [ParameterTypeBuiltin.ANY.value]
        # For single types, return a list with one element
        return [self._python_type_to_param_type(python_type)]

    def _get_output_type_for_field(self, python_type: Any) -> str:
        """Convert Python type annotation to single output type for Parameter."""
        if self._is_union_type(python_type):
            # For Union types on outputs, we need to pick one type
            # For Optional[T], return T; for other unions, return first non-None type
            for arg in python_type.__args__:
                if arg is not type(None):
                    return self._python_type_to_param_type(arg)
            return ParameterTypeBuiltin.NONE.value  # If somehow all types are None
        # For single types
        return self._python_type_to_param_type(python_type)

    def _create_result_parameters(self, request_info: RequestInfo) -> None:
        """Create Success and Failure output parameters."""
        success_class = request_info.success_class
        failure_class = request_info.failure_class

        # Add Success Parameters if success class exists
        if success_class:
            success_doc = success_class.__doc__ if success_class.__doc__ else success_class.__name__
            success_header = ParameterMessage(
                variant="info",
                value=f"Success Parameters: {success_doc}",
                name="success_header",
            )
            self.add_node_element(success_header)

            self._create_output_parameters_for_class(success_class, "success", self._SKIP_RESULT_FIELDS)

        # Add Failure Parameters if failure class exists
        if failure_class:
            failure_doc = failure_class.__doc__ if failure_class.__doc__ else failure_class.__name__
            failure_header = ParameterMessage(
                variant="info",
                value=f"Failure Parameters: {failure_doc}",
                name="failure_header",
            )
            self.add_node_element(failure_header)

            self._create_output_parameters_for_class(failure_class, "failure", self._SKIP_RESULT_FIELDS)

    def _create_output_parameters_for_class(self, result_class: Any, prefix: str, skip_fields: set) -> None:
        """Create output parameters for a result class."""
        if not (result_class and dataclasses.is_dataclass(result_class)):
            return

        fields_to_show = [f for f in dataclasses.fields(result_class) if f.name not in skip_fields]
        if not fields_to_show:
            return

        # Get resolved type hints to handle string annotations
        try:
            type_hints = get_type_hints(result_class)
        except Exception:
            # Fallback to field.type if get_type_hints fails
            type_hints = {}

        for field in fields_to_show:
            param = self._create_output_parameter_for_field(field, prefix, type_hints)
            self.add_parameter(param)

    def _create_output_parameter_for_field(self, field: Any, prefix: str, type_hints: dict) -> Parameter:
        """Create an output parameter for a dataclass field."""
        # Use resolved type hint if available, otherwise fall back to field.type
        field_type = type_hints.get(field.name, field.type)

        # For output parameters, we need a single output type
        output_type = self._get_output_type_for_field(field_type)

        tooltip = f"Output from {prefix} result: {field.name} (type: {output_type})"
        if field.metadata.get("description"):
            tooltip = f"{field.metadata['description']} (type: {output_type})"

        # Add (optional) suffix for Optional fields
        display_name = field.name
        if self._is_optional_type(field_type):
            display_name += " (optional)"

        return Parameter(
            name=f"{self._OUTPUT_SUCCESS_PARAMETER_NAME_PREFIX if prefix == 'success' else self._OUTPUT_FAILURE_PARAMETER_NAME_PREFIX}{field.name}",
            tooltip=tooltip,
            output_type=output_type,
            allowed_modes={ParameterMode.OUTPUT},
            ui_options={"display_name": display_name},
            user_defined=True,
        )

    def _python_type_to_param_type(self, python_type: Any) -> str:
        """Convert Python type annotation to parameter type string."""
        # Handle typing module types
        origin = get_origin(python_type)

        if origin is not None:
            return self._handle_generic_type(origin)

        return self._handle_basic_type(python_type)

    def _handle_generic_type(self, origin: type) -> str:
        """Handle generic types like list, dict, etc."""
        type_name = origin.__name__

        # Try to get builtin type from ParameterType first
        builtin_type = ParameterType.attempt_get_builtin(type_name)
        if builtin_type:
            return builtin_type.value

        # For generic types not in builtin types, return the type name directly
        return type_name.lower()

    def _handle_basic_type(self, python_type: Any) -> str:
        """Handle basic Python types."""
        # Get the type name as a string
        if isinstance(python_type, str):
            type_name = python_type
        else:
            type_name = python_type.__name__

        # Try to get builtin type from ParameterType
        builtin_type = ParameterType.attempt_get_builtin(type_name)
        if builtin_type:
            return builtin_type.value

        # For unknown types, return the type name directly
        return type_name.lower()

    def _build_request_kwargs(self, request_class: type) -> dict:
        """Build request kwargs from input parameters."""
        request_kwargs = {}

        if not dataclasses.is_dataclass(request_class):
            return request_kwargs

        for field in dataclasses.fields(request_class):
            if field.name == "request_id":
                continue

            param_name = f"{self._INPUT_PARAMETER_NAME_PREFIX}{field.name}"
            if param_name in [p.name for p in self.parameters]:
                value = self.get_parameter_value(param_name)

                # Apply conversion based on field metadata
                converted_value = self._convert_value_for_field(value, field)

                if converted_value is not None:
                    request_kwargs[field.name] = converted_value

        return request_kwargs

    def _convert_value_for_field(self, value: Any, field: Any) -> Any:
        """Convert value based on field type."""
        if value == "" and self._is_optional_type(field.type):
            return None  # Convert empty string to None for optional fields

        return value

    def _is_union_type(self, python_type: Any) -> bool:
        """Check if a type is a Union type (either typing.Union or types.UnionType)."""
        origin = get_origin(python_type)
        return origin is Union or origin is types.UnionType

    def _is_optional_type(self, python_type: Any) -> bool:
        """Check if a type is Optional[T] (Union[T, None])."""
        if not self._is_union_type(python_type):
            return False
        args = python_type.__args__
        # Optional[T] is Union[T, None] which has exactly 2 args with None as one of them
        optional_args_count = 2
        return len(args) == optional_args_count and type(None) in args

    def _execute_request(self, request_class: type, request_kwargs: dict) -> None:
        """Execute the request and handle the result."""
        try:
            request_instance = request_class(**request_kwargs)
            result = GriptapeNodes.handle_request(request_instance)
            self._handle_result(result)
        except Exception as e:
            self._handle_execution_error(str(e))

    def _handle_result(self, result: Any) -> None:
        """Handle successful request execution result."""
        if result.succeeded():
            self._populate_success_outputs(result)
            self._execution_succeeded = True
        else:
            self._populate_failure_outputs(result)
            self._execution_succeeded = False

    def _populate_success_outputs(self, result: Any) -> None:
        """Populate success output parameters."""
        if not dataclasses.is_dataclass(result):
            return

        for field in dataclasses.fields(result):
            if field.name in self._SKIP_RESULT_FIELDS:
                continue
            output_param_name = f"{self._OUTPUT_SUCCESS_PARAMETER_NAME_PREFIX}{field.name}"
            value = getattr(result, field.name)
            self.parameter_output_values[output_param_name] = value

    def _populate_failure_outputs(self, result: Any) -> None:
        """Populate failure output parameters."""
        if not dataclasses.is_dataclass(result):
            return

        for field in dataclasses.fields(result):
            if field.name in self._SKIP_RESULT_FIELDS:
                continue
            output_param_name = f"{self._OUTPUT_FAILURE_PARAMETER_NAME_PREFIX}{field.name}"
            value = getattr(result, field.name)
            self.parameter_output_values[output_param_name] = value

    def _handle_execution_error(self, error_message: str) -> None:
        """Handle execution error."""
        self.parameter_output_values[f"{self._OUTPUT_FAILURE_PARAMETER_NAME_PREFIX}exception"] = error_message
        self._execution_succeeded = False
