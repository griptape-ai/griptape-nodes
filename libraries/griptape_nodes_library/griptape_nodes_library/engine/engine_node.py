import dataclasses
import inspect
import logging
import types
from enum import Enum
from typing import Any, ClassVar, NamedTuple, Union, get_origin, get_type_hints

from griptape_nodes.exe_types.core_types import (
    Parameter,
    ParameterMessage,
    ParameterType,
    ParameterTypeBuiltin,
)
from griptape_nodes.exe_types.node_types import NodeResolutionState, SuccessFailureNode
from griptape_nodes.retained_mode.events.base_events import (
    RequestPayload,
    ResultDetails,
    ResultPayload,
    ResultPayloadFailure,
    ResultPayloadSuccess,
)
from griptape_nodes.retained_mode.events.parameter_events import (
    AddParameterToNodeRequest,
    RemoveParameterFromNodeRequest,
)
from griptape_nodes.retained_mode.events.payload_registry import PayloadRegistry
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
from griptape_nodes.traits.options import Options

logger = logging.getLogger("griptape_nodes")


class ParamType(Enum):
    """Enum for parameter types to avoid magic strings."""

    INPUT = "input"
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


class CategorizedParameters(NamedTuple):
    """Categorized dynamic parameters for the EngineNode."""

    input_parameters: list[Parameter]
    success_output_parameters: list[Parameter]
    failure_output_parameters: list[Parameter]


class TransitionPlan(NamedTuple):
    """Generic plan for transitioning a set of parameters."""

    to_preserve: set[str]
    to_remove: set[str]
    to_add: set[str]


class EngineNode(SuccessFailureNode):
    # Fields to skip when creating output parameters from result classes
    _SKIP_RESULT_FIELDS: ClassVar[set[str]] = {"result_details", "altered_workflow_state"}

    # Parameter name prefixes
    _INPUT_PARAMETER_NAME_PREFIX = "input_"
    _OUTPUT_SUCCESS_PARAMETER_NAME_PREFIX = "output_success_"
    _OUTPUT_FAILURE_PARAMETER_NAME_PREFIX = "output_failure_"

    # Default selection option constant
    _DEFAULT_SELECTION_TEXT = "Select an Engine Request Type"

    # Default message box text constants
    _SUCCESS_MESSAGE_DEFAULT = (
        "Success Output Parameters: These values will be populated only after the request executes successfully."
    )
    _FAILURE_MESSAGE_DEFAULT = (
        "Failure Output Parameters: These values will be populated only after the request fails or encounters errors."
    )
    _SUCCESS_MESSAGE_WITH_DOC_TEMPLATE = "Success Output Parameters: {doc}\n\nThese values will be populated only after the request executes successfully."
    _FAILURE_MESSAGE_WITH_DOC_TEMPLATE = "Failure Output Parameters: {doc}\n\nThese values will be populated only after the request fails or encounters errors."

    # Documentation message constants
    _SELECT_REQUEST_TYPE_MESSAGE = "Select a request type to see its documentation and parameters."

    # Error message constants
    _RESULT_CLASSES_NOT_FOUND_ERROR = "corresponding Success and Failure result classes not found"

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)

        # Store discovered request types and their result mappings
        self._request_types = self._discover_request_types()

        # Parameters will be categorized dynamically by scanning once and grouping by name patterns

        # Track if we've done initial parameter setup
        self._initial_parameters_created = False

        # Create request type selector dropdown - build options first
        self.request_options = []
        for request_name, info in sorted(self._request_types.items()):
            display_name = request_name
            if not info.has_results:
                display_name += " *"
            self.request_options.append(display_name)

        # Always add the default selection option as the first choice
        all_options = [self._DEFAULT_SELECTION_TEXT]
        if self.request_options:
            all_options.extend(self.request_options)
        else:
            all_options.append("No requests available")

        self.request_selector = Parameter(
            name="request_type",
            tooltip="Select the RequestPayload type to execute",
            type="str",
            default_value=self._DEFAULT_SELECTION_TEXT,
            traits={Options(choices=all_options)},
        )
        self.add_parameter(self.request_selector)

        # Documentation message for the selected request type
        self.documentation_message = ParameterMessage(
            variant="info",
            value=self._SELECT_REQUEST_TYPE_MESSAGE,
            name="documentation",
        )
        self.add_node_element(self.documentation_message)

        # Info message for success outputs (will be updated dynamically)
        self.success_info_message = ParameterMessage(
            variant="success",
            value=self.__class__._SUCCESS_MESSAGE_DEFAULT,
            name="success_info",
        )
        self.add_node_element(self.success_info_message)

        # Info message for failure outputs (will be updated dynamically)
        self.failure_info_message = ParameterMessage(
            variant="error",
            value=self.__class__._FAILURE_MESSAGE_DEFAULT,
            name="failure_info",
        )
        self.add_node_element(self.failure_info_message)

        # Create status parameters using SuccessFailureNode helper
        self._create_status_parameters(
            result_details_tooltip="Details about the execution result",
            result_details_placeholder="Details on the request execution will be presented here.",
            parameter_group_initially_collapsed=False,  # Show Status group expanded by default for EngineNode
        )

        # Initial parameter creation will be deferred to validate_before_workflow_run
        # to ensure the node is properly registered first

    # Public Methods
    def process(self) -> None:
        """Execute the selected request and handle the result."""
        # Step 1: Reset execution state and result details at the start of each run
        self._clear_execution_status()

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
            logger.error(
                "Could not find corresponding ResultPayload classes for request type '%s' - execution skipped",
                clean_type,
            )
            msg = f"Cannot execute '{clean_type}': {self._RESULT_CLASSES_NOT_FOUND_ERROR} in the system."
            raise ValueError(msg)

        # Step 5: Build the request arguments from input parameters
        request_kwargs = self._build_request_kwargs(request_info.request_class)

        # Step 6: Execute the request and handle success/failure routing
        try:
            self._execute_request(request_info.request_class, request_kwargs)
        except Exception as e:
            self._handle_execution_error(str(e))

    def get_next_control_output(self) -> Parameter | None:
        """Determine which control output to follow based on execution result."""
        if self._execution_succeeded is None:
            # Execution hasn't completed yet
            self.stop_flow = True
            return None

        if self._execution_succeeded:
            return self.control_parameter_out
        return self.failure_output

    def validate_before_workflow_run(self) -> list[Exception] | None:
        """Engine nodes have side effects and need to execute every workflow run."""
        # Call parent's validation first
        parent_exceptions = super().validate_before_workflow_run()

        # Engine-specific logic: force unresolved state for every run
        self.make_node_unresolved(
            current_states_to_trigger_change_event={NodeResolutionState.RESOLVED, NodeResolutionState.RESOLVING}
        )

        return parent_exceptions

    def validate_before_node_run(self) -> list[Exception] | None:
        """Engine nodes have side effects and need to execute every time they run."""
        # Call parent's validation first
        parent_exceptions = super().validate_before_node_run()

        # Engine-specific logic: force unresolved state for every node run
        self.make_node_unresolved(
            current_states_to_trigger_change_event={NodeResolutionState.RESOLVED, NodeResolutionState.RESOLVING}
        )

        return parent_exceptions

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
        # Store old value before updating if this is the request selector
        old_value = None
        if param_name == self.request_selector.name:
            old_value = self.get_parameter_value(self.request_selector.name)

        super().set_parameter_value(
            param_name,
            value,
            initial_setup=initial_setup,
            emit_change=emit_change,
            skip_before_value_set=skip_before_value_set,
        )

        if param_name == self.request_selector.name:
            self._update_parameters_for_request_type(value, old_value)

    def _get_current_dynamic_parameters(self) -> CategorizedParameters:
        """Get current dynamic parameters categorized by type.

        Returns:
            CategorizedParameters: Named tuple with input, success, and failure parameter lists
        """
        input_parameters = []
        success_output_parameters = []
        failure_output_parameters = []

        for param in self.parameters:
            if param.name.startswith(self._INPUT_PARAMETER_NAME_PREFIX):
                input_parameters.append(param)
            elif param.name.startswith(self._OUTPUT_SUCCESS_PARAMETER_NAME_PREFIX):
                success_output_parameters.append(param)
            elif param.name.startswith(self._OUTPUT_FAILURE_PARAMETER_NAME_PREFIX):
                failure_output_parameters.append(param)

        return CategorizedParameters(input_parameters, success_output_parameters, failure_output_parameters)

    def _execute_systematic_parameter_transition(
        self,
        _old_request_info: RequestInfo | None,
        new_request_info: RequestInfo,
    ) -> None:
        """Execute systematic parameter transition following the outlined approach."""
        # Clear ALL parameter output values to prevent contamination between request types
        self.parameter_output_values.clear()

        # Step 1: Outline all parameters that need to be preserved, removed, and added
        current_params = self._get_current_dynamic_parameters()

        input_plan = self._outline_parameter_transition_plan(
            current_names={p.name for p in current_params.input_parameters},
            desired_names=self._get_desired_input_parameter_names(new_request_info.request_class),
        )

        success_plan = self._outline_parameter_transition_plan(
            current_names={p.name for p in current_params.success_output_parameters},
            desired_names=self._get_desired_output_parameter_names(new_request_info.success_class, ParamType.SUCCESS),
        )

        failure_plan = self._outline_parameter_transition_plan(
            current_names={p.name for p in current_params.failure_output_parameters},
            desired_names=self._get_desired_output_parameter_names(new_request_info.failure_class, ParamType.FAILURE),
        )

        # Step 2: For each group, remove parameters by name, then add new parameters
        self._execute_transition_plan(
            plan=input_plan, param_class=new_request_info.request_class, param_type=ParamType.INPUT
        )
        self._execute_transition_plan(
            plan=success_plan, param_class=new_request_info.success_class, param_type=ParamType.SUCCESS
        )
        self._execute_transition_plan(
            plan=failure_plan, param_class=new_request_info.failure_class, param_type=ParamType.FAILURE
        )

        # Update success and failure message boxes with docstrings
        self._update_result_message_boxes(new_request_info)

        # Step 3: Sort parameters into their respective groups (using ParameterGroups)
        self._reorder_all_elements()

    def _update_result_message_boxes(self, request_info: RequestInfo) -> None:
        """Update success and failure message boxes with docstrings from result classes."""
        success_class = request_info.success_class
        failure_class = request_info.failure_class

        if success_class:
            success_doc = success_class.__doc__ if success_class.__doc__ else success_class.__name__
            self.success_info_message.value = self.__class__._SUCCESS_MESSAGE_WITH_DOC_TEMPLATE.format(doc=success_doc)
        else:
            self.success_info_message.value = self.__class__._SUCCESS_MESSAGE_DEFAULT

        if failure_class:
            failure_doc = failure_class.__doc__ if failure_class.__doc__ else failure_class.__name__
            self.failure_info_message.value = self.__class__._FAILURE_MESSAGE_WITH_DOC_TEMPLATE.format(doc=failure_doc)
        else:
            self.failure_info_message.value = self.__class__._FAILURE_MESSAGE_DEFAULT

    def _outline_parameter_transition_plan(self, current_names: set[str], desired_names: set[str]) -> TransitionPlan:
        """Create a generic transition plan for a set of parameters."""
        to_preserve = current_names & desired_names
        to_remove = current_names - desired_names
        to_add = desired_names - current_names

        return TransitionPlan(
            to_preserve=to_preserve,
            to_remove=to_remove,
            to_add=to_add,
        )

    def _get_desired_input_parameter_names(self, request_class: type) -> set[str]:
        """Get the set of input parameter names that should exist for this request class."""
        if not (dataclasses.is_dataclass(request_class) and dataclasses.fields(request_class)):
            return set()

        fields_to_show = [f for f in dataclasses.fields(request_class) if f.name != "request_id"]
        return {f"{self._INPUT_PARAMETER_NAME_PREFIX}{field.name}" for field in fields_to_show}

    def _get_desired_output_parameter_names(self, result_class: type | None, prefix: ParamType) -> set[str]:
        """Get the set of output parameter names that should exist for this result class."""
        if not (result_class and dataclasses.is_dataclass(result_class)):
            return set()

        fields_to_show = [f for f in dataclasses.fields(result_class) if f.name not in self._SKIP_RESULT_FIELDS]
        prefix_str = self._get_prefix_string(prefix)
        return {f"{prefix_str}{field.name}" for field in fields_to_show}

    def _execute_transition_plan(self, plan: TransitionPlan, param_class: type | None, param_type: ParamType) -> None:
        """Execute a single transition plan by removing and adding parameters by name."""
        # Remove parameters by name (not by index)
        for param_name in plan.to_remove:
            remove_request = RemoveParameterFromNodeRequest(parameter_name=param_name, node_name=self.name)
            result = GriptapeNodes.handle_request(remove_request)
            if not result.succeeded():
                logger.error("Failed to remove parameter %s: %s", param_name, result.result_details)

        # Add new parameters for this group
        if plan.to_add and param_class:
            if param_type == ParamType.INPUT:
                self._create_request_parameters(request_class=param_class, skip_existing=plan.to_preserve)
            elif param_type in (ParamType.SUCCESS, ParamType.FAILURE):
                self._create_output_parameters_for_class(
                    result_class=param_class,
                    prefix=param_type,
                    skip_fields=self._SKIP_RESULT_FIELDS,
                    skip_existing=plan.to_preserve,
                )

    def _reorder_all_elements(self) -> None:
        """Reorder all elements in the correct sequence from scratch."""
        new_order = []

        # 1. Control input
        new_order.append(self.control_parameter_in.name)

        # 2. Control outputs
        new_order.append(self.control_parameter_out.name)
        new_order.append(self.failure_output.name)

        # 3. request_type selector
        new_order.append(self.request_selector.name)

        # 4. Status group (contains was_successful and result_details)
        new_order.append(self.status_component.get_parameter_group().name)

        # 5. documentation ParameterMessage
        new_order.append(self.documentation_message.name)

        # 6. All input parameters
        input_params = [p for p in self.parameters if p.name.startswith(self._INPUT_PARAMETER_NAME_PREFIX)]
        new_order.extend(param.name for param in input_params)

        # 7. Success ParameterMessage
        new_order.append(self.success_info_message.name)

        # 8. All success parameters
        success_params = [p for p in self.parameters if p.name.startswith(self._OUTPUT_SUCCESS_PARAMETER_NAME_PREFIX)]
        new_order.extend(param.name for param in success_params)

        # 9. Failure ParameterMessage
        new_order.append(self.failure_info_message.name)

        # 10. All failure parameters
        failure_params = [p for p in self.parameters if p.name.startswith(self._OUTPUT_FAILURE_PARAMETER_NAME_PREFIX)]
        new_order.extend(param.name for param in failure_params)

        # Use the BaseNode's reorder_elements method
        try:
            self.reorder_elements(element_order=new_order)
        except Exception as e:
            logger.error("Failed to reorder all elements: %s", e)

    def _clear_all_dynamic_elements(self, current_params: CategorizedParameters) -> None:
        """Clear all dynamic parameters and UI elements for fresh start."""
        # Clear ALL parameter output values to prevent dirty values from carrying over
        self.parameter_output_values.clear()

        # Remove all parameters using the provided current_params
        all_dynamic_params = (
            current_params.input_parameters
            + current_params.success_output_parameters
            + current_params.failure_output_parameters
        )

        for param in all_dynamic_params:
            # Check if parameter still exists before trying to remove it
            if self.get_parameter_by_name(param.name) is not None:
                remove_request = RemoveParameterFromNodeRequest(parameter_name=param.name, node_name=self.name)
                result = GriptapeNodes.handle_request(remove_request)
                if not result.succeeded():
                    logger.error("Failed to remove parameter %s: %s", param.name, result.result_details)

        # Reset static UI elements to explanatory content
        self.success_info_message.value = self._SUCCESS_MESSAGE_DEFAULT
        self.failure_info_message.value = self._FAILURE_MESSAGE_DEFAULT

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

    def _update_parameters_for_request_type(self, selected_type: str, _old_type: str | None = None) -> None:
        """Update node parameters based on selected request type with smart connection preservation."""
        # Remove asterisk if present
        clean_type = selected_type.rstrip(" *")

        # Handle the default selection option
        if clean_type == self._DEFAULT_SELECTION_TEXT:
            # Clear all dynamic parameters and reset messages
            current_params = self._get_current_dynamic_parameters()
            self._clear_all_dynamic_elements(current_params)

            # Reset all messages to default state
            self.documentation_message.value = self._SELECT_REQUEST_TYPE_MESSAGE
            self.success_info_message.value = self._SUCCESS_MESSAGE_DEFAULT
            self.failure_info_message.value = self._FAILURE_MESSAGE_DEFAULT
            return

        if clean_type not in self._request_types:
            return

        new_request_info = self._request_types[clean_type]
        new_request_class = new_request_info.request_class

        # Update documentation
        doc_text = new_request_class.__doc__ or f"Execute {clean_type} request"
        self.documentation_message.value = doc_text

        # Check if request type is usable
        if not new_request_info.has_results:
            # Set result_details to show the error instead of using error_message
            self._set_status_results(
                was_successful=False,
                result_details=f"ERROR: Cannot use {clean_type}: {self._RESULT_CLASSES_NOT_FOUND_ERROR}",
            )
            return

        # Clear result_details for usable request types
        self._set_status_results(was_successful=False, result_details="")

        # Systematic parameter transition approach
        if _old_type:
            old_clean_type = _old_type.rstrip(" *")
            old_request_info = self._request_types.get(old_clean_type)
            self._execute_systematic_parameter_transition(old_request_info, new_request_info)
        else:
            # First time setup - just create all parameters
            current_params = self._get_current_dynamic_parameters()
            self._clear_all_dynamic_elements(current_params)
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

        for field in fields_to_show:
            param_name = f"{self._INPUT_PARAMETER_NAME_PREFIX}{field.name}"
            if param_name not in skip_existing:
                field_type = type_hints.get(field.name, field.type)
                self._create_single_input_parameter(field, field_type, param_name)

    def _create_single_input_parameter(self, field: Any, field_type: Any, param_name: str) -> None:
        """Create a single input parameter and position it correctly."""
        input_types = self._get_input_types_for_field(field_type)

        # Build tooltip with type information
        input_type_str = ", ".join(input_types) if input_types else "any"
        tooltip = f"Input for {field.name} (type: {input_type_str})"
        if field.metadata.get("description"):
            tooltip = f"{field.metadata['description']} (type: {input_type_str})"

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
        if not result.succeeded():
            logger.error(
                "Failed to create input parameter %s: %s",
                param_name,
                result.result_details,
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
        """Convert Python type annotation to single output type for Parameter.

        Note: Any output types are converted to All for output parameters.
        An output of Any can ONLY connect to something that accepts Any,
        while an output of All can connect to any other Parameter,
        which is useful for debugging or instances where the customer knows what they are doing.
        """
        if self._is_union_type(python_type):
            # For Union types on outputs, we need to pick one type
            # For Optional[T], return T; for other unions, return first non-None type
            for arg in python_type.__args__:
                if arg is not type(None):
                    output_type = self._python_type_to_param_type(arg)
                    if output_type.lower() == ParameterTypeBuiltin.ANY.value.lower():
                        return ParameterTypeBuiltin.ALL.value
                    return output_type
            return ParameterTypeBuiltin.NONE.value  # If somehow all types are None
        # For single types
        output_type = self._python_type_to_param_type(python_type)
        if output_type.lower() == ParameterTypeBuiltin.ANY.value.lower():
            return ParameterTypeBuiltin.ALL.value
        return output_type

    def _create_result_parameters(self, request_info: RequestInfo, skip_existing: set[str] | None = None) -> None:
        """Create Success and Failure output parameters."""
        success_class = request_info.success_class
        failure_class = request_info.failure_class
        skip_existing = skip_existing or set()

        # Update message boxes with docstrings
        self._update_result_message_boxes(request_info)

        # Add Success Parameters if success class exists
        if success_class:
            self._create_output_parameters_for_class(
                success_class, ParamType.SUCCESS, self._SKIP_RESULT_FIELDS, skip_existing
            )

        # Add Failure Parameters if failure class exists
        if failure_class:
            self._create_output_parameters_for_class(
                failure_class, ParamType.FAILURE, self._SKIP_RESULT_FIELDS, skip_existing
            )

    def _create_output_parameters_for_class(
        self, result_class: Any, prefix: ParamType, skip_fields: set, skip_existing: set[str] | None = None
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

    def _get_prefix_string(self, prefix: ParamType) -> str:
        """Get the parameter name prefix string for a result type."""
        match prefix:
            case ParamType.SUCCESS:
                return self._OUTPUT_SUCCESS_PARAMETER_NAME_PREFIX
            case ParamType.FAILURE:
                return self._OUTPUT_FAILURE_PARAMETER_NAME_PREFIX
            case _:
                msg = f"Invalid result type prefix: {prefix}"
                raise ValueError(msg)

    def _create_single_output_parameter(self, field: Any, field_type: Any, param_name: str, prefix: ParamType) -> None:
        """Create a single output parameter using the event system."""
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
        if not result.succeeded():
            logger.error(
                "Failed to create output parameter %s: %s",
                param_name,
                result.result_details,
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

                # Convert empty string to None for optional fields
                if value == "" and self._is_optional_type(field.type):
                    converted_value = None
                else:
                    converted_value = value

                if converted_value is not None:
                    request_kwargs[field.name] = converted_value

        return request_kwargs

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

    def _handle_result(self, result: ResultPayload) -> None:
        """Handle successful request execution result."""
        if result.succeeded():
            self._populate_success_outputs(result)
            # Handle result_details for success
            success_details = self._format_result_details(result.result_details)
            self._set_status_results(was_successful=True, result_details=f"SUCCESS: {success_details}")
        else:
            self._populate_failure_outputs(result)
            # Handle result_details for failure
            failure_details = self._format_result_details(result.result_details)
            self._set_status_results(was_successful=False, result_details=f"FAILURE: {failure_details}")

    def _populate_success_outputs(self, result: ResultPayload) -> None:
        """Populate success output parameters."""
        if not dataclasses.is_dataclass(result):
            return

        for field in dataclasses.fields(result):
            if field.name in self._SKIP_RESULT_FIELDS:
                continue
            output_param_name = f"{self._OUTPUT_SUCCESS_PARAMETER_NAME_PREFIX}{field.name}"
            value = getattr(result, field.name)
            self.parameter_output_values[output_param_name] = value

    def _populate_failure_outputs(self, result: ResultPayload) -> None:
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
        self._set_status_results(was_successful=False, result_details=f"ERROR: {error_message}")

    def _format_result_details(self, result_details: ResultDetails | str) -> str:
        """Format result_details for display, handling ResultDetails or str."""
        if isinstance(result_details, ResultDetails):
            return "\n".join(f"[{detail.level}] {detail.message}" for detail in result_details.result_details)
        return str(result_details)
