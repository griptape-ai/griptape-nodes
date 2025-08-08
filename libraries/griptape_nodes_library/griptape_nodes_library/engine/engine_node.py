import dataclasses
import inspect
from typing import Any, get_origin

from griptape_nodes.exe_types.core_types import (
    ControlParameterOutput,
    Parameter,
    ParameterMessage,
    ParameterMode,
)
from griptape_nodes.exe_types.node_types import DataNode
from griptape_nodes.retained_mode.events.base_events import (
    RequestPayload,
    ResultPayloadFailure,
    ResultPayloadSuccess,
)
from griptape_nodes.retained_mode.events.payload_registry import PayloadRegistry
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
from griptape_nodes.traits.options import Options


class EngineNode(DataNode):
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)

        # Store discovered request types and their result mappings
        self._request_types = self._discover_request_types()

        # Create request type selector dropdown
        self.request_options = []
        for request_name, info in self._request_types.items():
            display_name = request_name
            if not info["has_results"]:
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

    def _discover_request_types(self) -> dict[str, dict]:
        """Discover all RequestPayload types and their corresponding Result types."""
        registry = PayloadRegistry.get_registry()
        request_types = {}

        for name, cls in registry.items():
            if inspect.isclass(cls) and issubclass(cls, RequestPayload) and cls != RequestPayload:
                # Find corresponding result classes using heuristics
                success_class, failure_class = self._find_result_classes(name, registry)

                request_types[name] = {
                    "class": cls,
                    "success_class": success_class,
                    "failure_class": failure_class,
                    "has_results": success_class is not None and failure_class is not None,
                }

        return request_types

    def _find_result_classes(self, request_name: str, registry: dict) -> tuple[type | None, type | None]:
        """Find corresponding Success and Failure result classes for a request."""
        if not request_name.endswith("Request"):
            return None, None

        base_name = request_name[:-7]  # Remove "Request"

        # Try different patterns for success/failure class names
        success_patterns = [
            f"{base_name}ResultSuccess",
            f"{base_name}_ResultSuccess",
            f"{base_name}Result_Success",
        ]

        failure_patterns = [
            f"{base_name}ResultFailure",
            f"{base_name}_ResultFailure",
            f"{base_name}Result_Failure",
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

        return success_class, failure_class

    def _update_parameters_for_request_type(self, selected_type: str) -> None:
        """Update node parameters based on selected request type."""
        # Remove asterisk if present
        clean_type = selected_type.rstrip(" *")

        if clean_type not in self._request_types:
            return

        request_info = self._request_types[clean_type]
        request_class = request_info["class"]

        # Clear existing dynamic parameters (keep core ones)
        core_params = {"request_type", "documentation", "success", "failure"}

        # Remove dynamic parameters and messages
        elements_to_remove = [
            elem for elem in self.root_ui_element._children if hasattr(elem, "name") and elem.name not in core_params
        ]
        for elem in elements_to_remove:
            self.remove_parameter_element(elem)

        # Update documentation
        doc_text = request_class.__doc__ or f"Execute {clean_type} request"
        self.info_message.value = doc_text

        # Check if request type is usable
        if not request_info["has_results"]:
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

        for field in fields_to_show:
            param = self._create_input_parameter_for_field(field)
            self.add_parameter(param)

    def _create_input_parameter_for_field(self, field: Any) -> Parameter:
        """Create an input parameter for a dataclass field."""
        param_type = self._python_type_to_param_type(field.type)

        # Determine default value
        default_value = self._get_field_default_value(field)

        tooltip = f"Input for {field.name}"
        if hasattr(field, "metadata") and field.metadata.get("description"):
            tooltip = field.metadata["description"]

        return Parameter(
            name=f"input_{field.name}",
            tooltip=tooltip,
            type=param_type,
            default_value=default_value,
            allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            ui_options={"display_name": field.name},
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

    def _create_result_parameters(self, request_info: dict) -> None:
        """Create Success and Failure output parameters."""
        success_class = request_info["success_class"]
        failure_class = request_info["failure_class"]

        # Add Success Parameters header
        success_doc = success_class.__doc__ if success_class.__doc__ else success_class.__name__
        success_header = ParameterMessage(
            variant="info",
            value=f"Success Parameters: {success_doc}",
            name="success_header",
        )
        self.add_node_element(success_header)

        self._create_output_parameters_for_class(success_class, "success", {"result_details", "altered_workflow_state"})

        # Add Failure Parameters header
        failure_doc = failure_class.__doc__ if failure_class.__doc__ else failure_class.__name__
        failure_header = ParameterMessage(
            variant="info",
            value=f"Failure Parameters: {failure_doc}",
            name="failure_header",
        )
        self.add_node_element(failure_header)

        self._create_output_parameters_for_class(
            failure_class, "failure", {"result_details", "altered_workflow_state", "exception"}
        )

    def _create_output_parameters_for_class(self, result_class: Any, prefix: str, skip_fields: set) -> None:
        """Create output parameters for a result class."""
        if not (result_class and dataclasses.is_dataclass(result_class)):
            return

        fields_to_show = [f for f in dataclasses.fields(result_class) if f.name not in skip_fields]
        if not fields_to_show:
            return

        for field in fields_to_show:
            param = self._create_output_parameter_for_field(field, prefix)
            self.add_parameter(param)

    def _create_output_parameter_for_field(self, field: Any, prefix: str) -> Parameter:
        """Create an output parameter for a dataclass field."""
        param_type = self._python_type_to_param_type(field.type)

        tooltip = f"Output from {prefix} result: {field.name}"
        if hasattr(field, "metadata") and field.metadata.get("description"):
            tooltip = field.metadata["description"]

        return Parameter(
            name=f"output_{prefix}_{field.name}",
            tooltip=tooltip,
            type=param_type,
            allowed_modes={ParameterMode.OUTPUT},
            ui_options={"display_name": field.name},
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
        type_mapping = {
            list: "list",
            dict: "dict",
            tuple: "tuple",
            set: "set",
        }
        return type_mapping.get(origin, "any")

    def _handle_basic_type(self, python_type: Any) -> str:
        """Handle basic Python types."""
        type_mapping = {
            str: "str",
            int: "int",
            float: "float",
            bool: "bool",
        }

        if python_type in type_mapping:
            return type_mapping[python_type]

        if hasattr(python_type, "__name__"):
            return python_type.__name__

        return "any"

    def process(self) -> None:
        """Execute the selected request and handle the result."""
        selected_type = self.get_parameter_value("request_type")
        if not selected_type:
            return

        clean_type = selected_type.rstrip(" *")
        if clean_type not in self._request_types:
            return

        request_info = self._request_types[clean_type]
        if not request_info["has_results"]:
            return

        request_kwargs = self._build_request_kwargs(request_info["class"])
        self._execute_request(request_info["class"], request_kwargs)

    def _build_request_kwargs(self, request_class: type) -> dict:
        """Build request kwargs from input parameters."""
        request_kwargs = {}

        if not dataclasses.is_dataclass(request_class):
            return request_kwargs

        for field in dataclasses.fields(request_class):
            if field.name == "request_id":
                continue

            param_name = f"input_{field.name}"
            if param_name in [p.name for p in self.parameters]:
                value = self.get_parameter_value(param_name)
                if value is not None:
                    request_kwargs[field.name] = value

        return request_kwargs

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
            self.parameter_output_values["success"] = True
        else:
            self._populate_failure_outputs(result)
            self.parameter_output_values["failure"] = True

    def _populate_success_outputs(self, result: Any) -> None:
        """Populate success output parameters."""
        if not dataclasses.is_dataclass(result):
            return

        for field in dataclasses.fields(result):
            if field.name in {"result_details", "altered_workflow_state"}:
                continue
            output_param_name = f"output_success_{field.name}"
            if hasattr(result, field.name):
                value = getattr(result, field.name)
                self.parameter_output_values[output_param_name] = value

    def _populate_failure_outputs(self, result: Any) -> None:
        """Populate failure output parameters."""
        if not dataclasses.is_dataclass(result):
            return

        for field in dataclasses.fields(result):
            if field.name in {"result_details", "altered_workflow_state"}:
                continue
            output_param_name = f"output_failure_{field.name}"
            if hasattr(result, field.name):
                value = getattr(result, field.name)
                self.parameter_output_values[output_param_name] = value

    def _handle_execution_error(self, error_message: str) -> None:
        """Handle execution error."""
        self.parameter_output_values["output_failure_exception"] = error_message
        self.parameter_output_values["failure"] = True

    def after_value_set(self, parameter: Parameter, value: Any) -> None:
        """Handle parameter value changes."""
        if parameter.name == "request_type":
            self._update_parameters_for_request_type(value)

        return super().after_value_set(parameter, value)
