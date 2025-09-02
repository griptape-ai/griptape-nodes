import dataclasses
import inspect
import logging
import types
from enum import Enum
from typing import Any, ClassVar, NamedTuple, Union, get_origin, get_type_hints

from griptape_nodes.exe_types.core_types import (
    ControlParameterOutput,
    Parameter,
    ParameterGroup,
    ParameterMessage,
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


class ResultType(Enum):
    """Enum for result parameter types to avoid magic strings."""

    SUCCESS = "success"
    FAILURE = "failure"


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

        # Track dynamically created parameters for easier management
        self._dynamic_input_parameters: list[Parameter] = []
        self._dynamic_output_parameters: list[Parameter] = []

        # Create parameter groups for organizing inputs and outputs with their info messages
        with ParameterGroup(name="Input Parameters") as input_group:
            # Documentation message for the selected request type
            self.documentation_message = ParameterMessage(
                variant="info",
                value="Select a request type to see its documentation and parameters.",
                name="documentation",
            )
        self.input_group = input_group
        self.add_node_element(self.input_group)

        with ParameterGroup(name="Success Outputs") as success_group:
            # Info message for success outputs (will be updated dynamically)
            self.success_info_message = ParameterMessage(
                variant="success",
                value="",  # Will be populated when needed
                name="success_info",
            )
        self.success_output_group = success_group
        self.add_node_element(self.success_output_group)

        with ParameterGroup(name="Failure Outputs") as failure_group:
            # Info message for failure outputs (will be updated dynamically)
            self.failure_info_message = ParameterMessage(
                variant="warning",
                value="",  # Will be populated when needed
                name="failure_info",
            )
        self.failure_output_group = failure_group
        self.add_node_element(self.failure_output_group)

        # Create static UI elements that will be populated dynamically
        self.error_message = ParameterMessage(
            variant="error",
            value="",  # Will be populated when needed
            name="error_message",
        )
        self.add_node_element(self.error_message)

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
        super().set_parameter_value(
            param_name,
            value,
            initial_setup=initial_setup,
            emit_change=emit_change,
            skip_before_value_set=skip_before_value_set,
        )

        if param_name == self.request_selector.name:
            self._update_parameters_for_request_type(value)

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

    def _transition_parameters_smartly(self, old_request_info: RequestInfo, new_request_info: RequestInfo) -> None:
        """Intelligently transition parameters, preserving connections where possible."""
        logger.info(
            "Smart transition from %s to %s",
            old_request_info.request_class.__name__,
            new_request_info.request_class.__name__,
        )

        # Analyze which parameters can survive the transition
        surviving_params = self._analyze_parameter_compatibility(old_request_info, new_request_info)

        # Remove parameters that won't survive (using events for proper cleanup)
        self._remove_non_surviving_parameters(surviving_params)

        # Clear all UI elements except survivors
        self._clear_non_surviving_dynamic_elements(surviving_params=surviving_params)

        # Create new parameters (skipping survivors)
        self._create_request_parameters(new_request_info.request_class, skip_existing=surviving_params)
        self._create_result_parameters(new_request_info, skip_existing=surviving_params)

    def _analyze_parameter_compatibility(
        self, old_request_info: RequestInfo, new_request_info: RequestInfo
    ) -> set[str]:
        """Determine which parameters can survive the transition with their connections intact."""
        surviving_params = set()

        if not (old_request_info.request_class and new_request_info.request_class):
            return surviving_params

        # Get field information for both request types
        try:
            old_fields = {
                f.name: f for f in dataclasses.fields(old_request_info.request_class) if f.name != "request_id"
            }
            old_hints = get_type_hints(old_request_info.request_class)
        except Exception:
            # dataclasses.fields or get_type_hints can fail with malformed classes or missing imports
            # Fallback: treat as having no compatible fields to preserve connections safely
            old_fields, old_hints = {}, {}

        try:
            new_fields = {
                f.name: f for f in dataclasses.fields(new_request_info.request_class) if f.name != "request_id"
            }
            new_hints = get_type_hints(new_request_info.request_class)
        except Exception:
            # dataclasses.fields or get_type_hints can fail with malformed classes or missing imports
            # Fallback: treat as having no compatible fields to preserve connections safely
            new_fields, new_hints = {}, {}

        # Check input parameters for compatibility
        for field_name in old_fields:
            if field_name in new_fields:
                old_param_name = f"{self._INPUT_PARAMETER_NAME_PREFIX}{field_name}"

                try:
                    old_field_type = old_hints.get(field_name, old_fields[field_name].type)
                    new_field_type = new_hints.get(field_name, new_fields[field_name].type)
                except Exception as e:
                    # Field type access can fail with complex generics or malformed annotations
                    # Fallback: skip this field to avoid breaking the entire compatibility analysis
                    logger.debug("Failed to get field types for %s: %s", field_name, e)
                    continue

                old_output_type = self._get_output_type_for_field(old_field_type)
                new_input_types = self._get_input_types_for_field(new_field_type)

                if self._types_are_compatible(old_output_type, new_input_types):
                    surviving_params.add(old_param_name)
                    logger.debug("Input parameter %s will survive transition", old_param_name)

        # Check output parameters for compatibility
        self._analyze_result_parameter_compatibility(old_request_info, new_request_info, surviving_params)

        return surviving_params

    def _types_are_compatible(self, old_output_type: str, new_input_types: list[str]) -> bool:
        """Check if an old output type is compatible with new input types using ParameterType's built-in logic."""
        for input_type in new_input_types:
            if ParameterType.are_types_compatible(source_type=old_output_type, target_type=input_type):
                return True
        return False

    def _analyze_result_parameter_compatibility(
        self, old_request_info: RequestInfo, new_request_info: RequestInfo, surviving_params: set[str]
    ) -> None:
        """Analyze result parameter compatibility and add survivors."""
        # Check success parameters
        if old_request_info.success_class and new_request_info.success_class:
            self._analyze_result_class_compatibility(
                old_class=old_request_info.success_class,
                new_class=new_request_info.success_class,
                prefix=ResultType.SUCCESS,
                surviving_params=surviving_params,
            )

        # Check failure parameters
        if old_request_info.failure_class and new_request_info.failure_class:
            self._analyze_result_class_compatibility(
                old_class=old_request_info.failure_class,
                new_class=new_request_info.failure_class,
                prefix=ResultType.FAILURE,
                surviving_params=surviving_params,
            )

    def _analyze_result_class_compatibility(
        self, old_class: type, new_class: type, prefix: ResultType, surviving_params: set[str]
    ) -> None:
        """Analyze compatibility between old and new result classes."""
        old_fields = {f.name: f for f in dataclasses.fields(old_class) if f.name not in self._SKIP_RESULT_FIELDS}
        new_fields = {f.name: f for f in dataclasses.fields(new_class) if f.name not in self._SKIP_RESULT_FIELDS}

        try:
            old_hints = get_type_hints(old_class)
        except Exception:
            # get_type_hints can fail with string annotations or missing imports
            # Fallback: use raw field.type attributes instead of resolved types
            old_hints = {}

        try:
            new_hints = get_type_hints(new_class)
        except Exception:
            # get_type_hints can fail with string annotations or missing imports
            # Fallback: use raw field.type attributes instead of resolved types
            new_hints = {}

        match prefix:
            case ResultType.SUCCESS:
                prefix_str = self._OUTPUT_SUCCESS_PARAMETER_NAME_PREFIX
            case ResultType.FAILURE:
                prefix_str = self._OUTPUT_FAILURE_PARAMETER_NAME_PREFIX
            case _:
                msg = f"Invalid result type prefix: {prefix}"
                raise ValueError(msg)

        for field_name, old_field in old_fields.items():
            if field_name not in new_fields:
                continue

            new_field = new_fields[field_name]

            try:
                old_field_type = old_hints.get(field_name, old_field.type)
                new_field_type = new_hints.get(field_name, new_field.type)
            except Exception as e:
                # Field type access can fail with complex generics or malformed annotations
                # Fallback: skip this field to avoid breaking the entire compatibility analysis
                logger.debug("Failed to get field types for %s: %s", field_name, e)
                continue

            old_output_type = self._get_output_type_for_field(old_field_type)
            new_output_type = self._get_output_type_for_field(new_field_type)

            if old_output_type == new_output_type:
                param_name = f"{prefix_str}{field_name}"
                surviving_params.add(param_name)
                logger.debug("Output parameter %s will survive transition", param_name)

    def _remove_non_surviving_parameters(self, surviving_params: set[str]) -> None:
        """Remove parameters that won't survive the transition using proper events."""
        from griptape_nodes.retained_mode.events.parameter_events import (
            RemoveParameterFromNodeRequest,
            RemoveParameterFromNodeResultSuccess,
        )
        from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

        # Find all dynamic parameters that aren't surviving
        params_to_remove = self._find_parameters_to_remove(surviving_params=surviving_params)

        # Remove them using the proper event system
        for param_name in params_to_remove:
            logger.debug("Removing non-surviving parameter: %s", param_name)
            remove_request = RemoveParameterFromNodeRequest(parameter_name=param_name, node_name=self.name)
            remove_result = GriptapeNodes.handle_request(remove_request)
            if not isinstance(remove_result, RemoveParameterFromNodeResultSuccess):
                logger.error("Failed to remove parameter %s: %s", param_name, remove_result.result_details)

    def _find_parameters_to_remove(self, surviving_params: set[str]) -> list[str]:
        """Find dynamic parameters that need to be removed during transition."""
        params_to_remove = []
        for param in self.parameters:
            is_dynamic = self._is_dynamic_parameter(parameter_name=param.name)
            is_surviving = param.name in surviving_params
            if is_dynamic and not is_surviving:
                params_to_remove.append(param.name)
        return params_to_remove

    def _clear_non_surviving_dynamic_elements(self, surviving_params: set[str]) -> None:
        """Clear dynamic parameters and UI elements that aren't surviving the transition."""
        from griptape_nodes.retained_mode.events.parameter_events import RemoveParameterFromNodeRequest
        from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

        # Remove non-surviving dynamic input parameters using proper events
        for param in self._dynamic_input_parameters[:]:
            if param.name not in surviving_params:
                remove_request = RemoveParameterFromNodeRequest(parameter_name=param.name, node_name=self.name)
                GriptapeNodes.handle_request(remove_request)
                self._dynamic_input_parameters.remove(param)

        # Remove non-surviving dynamic output parameters using proper events
        for param in self._dynamic_output_parameters[:]:
            if param.name not in surviving_params:
                remove_request = RemoveParameterFromNodeRequest(parameter_name=param.name, node_name=self.name)
                GriptapeNodes.handle_request(remove_request)
                self._dynamic_output_parameters.remove(param)

        # Clear static UI elements content
        self.success_info_message.value = ""
        self.failure_info_message.value = ""
        self.error_message.value = ""

    def _clear_all_dynamic_elements(self) -> None:
        """Clear all dynamic parameters and UI elements for fresh start."""
        from griptape_nodes.retained_mode.events.parameter_events import RemoveParameterFromNodeRequest
        from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

        # Remove all dynamic input parameters using proper events
        for param in self._dynamic_input_parameters[:]:
            remove_request = RemoveParameterFromNodeRequest(parameter_name=param.name, node_name=self.name)
            GriptapeNodes.handle_request(remove_request)

        # Remove all dynamic output parameters using proper events
        for param in self._dynamic_output_parameters[:]:
            remove_request = RemoveParameterFromNodeRequest(parameter_name=param.name, node_name=self.name)
            GriptapeNodes.handle_request(remove_request)

        # Clear static UI elements content
        self.success_info_message.value = ""
        self.failure_info_message.value = ""
        self.error_message.value = ""

        # Clear the tracking lists
        self._dynamic_input_parameters.clear()
        self._dynamic_output_parameters.clear()

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
        """Update node parameters based on selected request type with smart connection preservation."""
        # Remove asterisk if present
        clean_type = selected_type.rstrip(" *")

        if clean_type not in self._request_types:
            return

        # Get old and new request information
        current_type = self.get_parameter_value(self.request_selector.name)
        if current_type:
            current_clean_type = current_type.rstrip(" *")
            old_request_info = self._request_types.get(current_clean_type)
        else:
            old_request_info = None

        new_request_info = self._request_types[clean_type]
        new_request_class = new_request_info.request_class

        # Update documentation
        doc_text = new_request_class.__doc__ or f"Execute {clean_type} request"
        self.documentation_message.value = doc_text

        # Check if request type is usable
        if not new_request_info.has_results:
            self.error_message.value = (
                f"Cannot use {clean_type}: corresponding Success and Failure result classes not found"
            )
            return

        # Clear error message for usable request types
        self.error_message.value = ""

        # Perform smart parameter transition
        if old_request_info:
            self._transition_parameters_smartly(old_request_info, new_request_info)
        else:
            # First time setup - just create all parameters
            self._clear_all_dynamic_elements()
            self._create_request_parameters(new_request_class)
            self._create_result_parameters(new_request_info)

    def _create_request_parameters(self, request_class: type, skip_existing: set[str] | None = None) -> None:
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

        skip_existing = skip_existing or set()
        from griptape_nodes.retained_mode.events.parameter_events import (
            AddParameterToNodeRequest,
            AddParameterToNodeResultSuccess,
        )
        from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

        for field in fields_to_show:
            param_name = f"{self._INPUT_PARAMETER_NAME_PREFIX}{field.name}"
            if param_name not in skip_existing:
                # Get field type information
                field_type = type_hints.get(field.name, field.type)
                input_types = self._get_input_types_for_field(field_type)

                # Build tooltip
                tooltip = f"Input for {field.name}"
                if field.metadata.get("description"):
                    tooltip = field.metadata["description"]

                # Build display name
                display_name = field.name
                if self._is_optional_type(field_type):
                    display_name += " (optional)"

                # Get default value
                default_value = self._get_field_default_value(field)

                # Create parameter using the event system
                add_request = AddParameterToNodeRequest(
                    node_name=self.name,
                    parameter_name=param_name,
                    input_types=input_types,
                    tooltip=tooltip,
                    mode_allowed_input=True,
                    mode_allowed_property=True,
                    mode_allowed_output=False,
                    default_value=default_value,
                    ui_options={"display_name": display_name},
                    is_user_defined=True,
                )

                result = GriptapeNodes.handle_request(add_request)
                if isinstance(result, AddParameterToNodeResultSuccess):
                    # Get the parameter and add it to the input group
                    param = self.get_parameter_by_name(param_name)
                    if param:
                        # Remove from root level and add to input group
                        self.root_ui_element.remove_child(param)
                        self.input_group.add_child(param)
                        self._dynamic_input_parameters.append(param)

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

    def _create_result_parameters(self, request_info: RequestInfo, skip_existing: set[str] | None = None) -> None:
        """Create Success and Failure output parameters."""
        success_class = request_info.success_class
        failure_class = request_info.failure_class
        skip_existing = skip_existing or set()

        # Add Success Parameters if success class exists
        if success_class:
            success_doc = success_class.__doc__ if success_class.__doc__ else success_class.__name__
            self.success_info_message.value = f"Success Result: {success_doc}"
            self._create_output_parameters_for_class(
                success_class, ResultType.SUCCESS, self._SKIP_RESULT_FIELDS, skip_existing
            )
        else:
            # Clear success info if no success class
            self.success_info_message.value = ""

        # Add Failure Parameters if failure class exists
        if failure_class:
            failure_doc = failure_class.__doc__ if failure_class.__doc__ else failure_class.__name__
            self.failure_info_message.value = f"Failure Result: {failure_doc}"
            self._create_output_parameters_for_class(
                failure_class, ResultType.FAILURE, self._SKIP_RESULT_FIELDS, skip_existing
            )
        else:
            # Clear failure info if no failure class
            self.failure_info_message.value = ""

    def _create_output_parameters_for_class(
        self, result_class: Any, prefix: ResultType, skip_fields: set, skip_existing: set[str] | None = None
    ) -> None:
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

        skip_existing = skip_existing or set()
        prefix_str = self._get_prefix_string(prefix)

        for field in fields_to_show:
            param_name = f"{prefix_str}{field.name}"
            if param_name not in skip_existing:
                field_type = type_hints.get(field.name, field.type)
                self._create_single_output_parameter(field, field_type, param_name, prefix)

    def _get_prefix_string(self, prefix: ResultType) -> str:
        """Get the parameter name prefix string for a result type."""
        match prefix:
            case ResultType.SUCCESS:
                return self._OUTPUT_SUCCESS_PARAMETER_NAME_PREFIX
            case ResultType.FAILURE:
                return self._OUTPUT_FAILURE_PARAMETER_NAME_PREFIX
            case _:
                msg = f"Invalid result type prefix: {prefix}"
                raise ValueError(msg)

    def _create_single_output_parameter(self, field: Any, field_type: Any, param_name: str, prefix: ResultType) -> None:
        """Create a single output parameter using the event system."""
        from griptape_nodes.retained_mode.events.parameter_events import (
            AddParameterToNodeRequest,
            AddParameterToNodeResultSuccess,
        )
        from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

        output_type = self._get_output_type_for_field(field_type)

        tooltip = f"Output from {prefix.value} result: {field.name} (type: {output_type})"
        if field.metadata.get("description"):
            tooltip = f"{field.metadata['description']} (type: {output_type})"

        display_name = field.name
        if self._is_optional_type(field_type):
            display_name += " (optional)"

        add_request = AddParameterToNodeRequest(
            node_name=self.name,
            parameter_name=param_name,
            output_type=output_type,
            tooltip=tooltip,
            mode_allowed_input=False,
            mode_allowed_property=False,
            mode_allowed_output=True,
            ui_options={"display_name": display_name},
            is_user_defined=True,
        )

        result = GriptapeNodes.handle_request(add_request)
        if isinstance(result, AddParameterToNodeResultSuccess):
            # Get the parameter and add it to the appropriate output group
            param = self.get_parameter_by_name(param_name)
            if param:
                # Remove from root level and add to appropriate group
                self.root_ui_element.remove_child(param)
                target_group = self.success_output_group if prefix == ResultType.SUCCESS else self.failure_output_group
                target_group.add_child(param)
                self._dynamic_output_parameters.append(param)

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
