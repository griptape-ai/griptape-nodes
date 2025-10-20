"""ParameterNumber base class for numeric parameters with step validation support."""

from collections.abc import Callable
from typing import Any

from griptape_nodes.exe_types.core_types import Parameter, ParameterMode, Trait

# Floating point precision tolerance for step validation
_FLOAT_PRECISION_TOLERANCE = 1e-10


class ParameterNumber(Parameter):
    """Base class for numeric parameters with step validation support.

    This class provides common functionality for numeric parameters including
    step validation, UI options, and type conversion. Subclasses should set
    the appropriate type and conversion methods.
    """

    def __init__(
        self,
        name: str,
        tooltip: str | None = None,
        *,
        type: str,  # noqa: A002
        input_types: list[str] | None = None,  # noqa: ARG002
        output_type: str,
        default_value: Any = None,
        tooltip_as_input: str | None = None,
        tooltip_as_property: str | None = None,
        tooltip_as_output: str | None = None,
        allowed_modes: set[ParameterMode] | None = None,
        traits: set[type[Trait] | Trait] | None = None,
        converters: list[Callable[[Any], Any]] | None = None,
        validators: list[Callable[[Parameter, Any], None]] | None = None,
        ui_options: dict | None = None,
        step: float | None = None,
        accept_any: bool = True,
        hide: bool = False,
        hide_label: bool = False,
        hide_property: bool = False,
        allow_input: bool = True,
        allow_property: bool = True,
        allow_output: bool = True,
        settable: bool = True,
        serializable: bool = True,
        user_defined: bool = False,
        element_id: str | None = None,
        element_type: str | None = None,
        parent_container_name: str | None = None,
    ) -> None:
        """Initialize a numeric parameter with step validation.

        Args:
            name: Parameter name
            tooltip: Parameter tooltip
            type: Parameter type (should be "int" or "float")
            input_types: Allowed input types
            output_type: Output type (should be "int" or "float")
            default_value: Default parameter value
            tooltip_as_input: Tooltip for input mode
            tooltip_as_property: Tooltip for property mode
            tooltip_as_output: Tooltip for output mode
            allowed_modes: Allowed parameter modes
            traits: Parameter traits
            converters: Parameter converters
            validators: Parameter validators
            ui_options: Dictionary of UI options
            step: Step size for numeric input controls
            accept_any: Whether to accept any input type and convert to number (default: True)
            hide: Whether to hide the entire parameter
            hide_label: Whether to hide the parameter label
            hide_property: Whether to hide the parameter in property mode
            allow_input: Whether to allow input mode
            allow_property: Whether to allow property mode
            allow_output: Whether to allow output mode
            settable: Whether the parameter is settable
            serializable: Whether the parameter is serializable
            user_defined: Whether the parameter is user-defined
            element_id: Element ID
            element_type: Element type
            parent_container_name: Name of parent container
        """
        # Build ui_options dictionary from the provided UI-specific parameters
        if ui_options is None:
            ui_options = {}
        else:
            ui_options = ui_options.copy()

        # Add numeric-specific UI options if they have values
        if step is not None:
            ui_options["step"] = step

        # Set up numeric conversion based on accept_any setting
        if converters is None:
            existing_converters = []
        else:
            existing_converters = converters

        if accept_any:
            final_input_types = ["any"]
            final_converters = [self._convert_to_number, *existing_converters]
        else:
            final_input_types = [type]
            final_converters = existing_converters

        # Set up validators
        if validators is None:
            existing_validators = []
        else:
            existing_validators = validators

        # Add step validator if step is specified
        final_validators = existing_validators.copy()
        if step is not None:
            final_validators.append(self._create_step_validator(step))

        # Call parent with explicit parameters, following ControlParameter pattern
        super().__init__(
            name=name,
            tooltip=tooltip,
            type=type,
            input_types=final_input_types,
            output_type=output_type,
            default_value=default_value,
            tooltip_as_input=tooltip_as_input,
            tooltip_as_property=tooltip_as_property,
            tooltip_as_output=tooltip_as_output,
            allowed_modes=allowed_modes,
            traits=traits,
            converters=final_converters,
            validators=final_validators,
            ui_options=ui_options,
            hide=hide,
            hide_label=hide_label,
            hide_property=hide_property,
            allow_input=allow_input,
            allow_property=allow_property,
            allow_output=allow_output,
            settable=settable,
            serializable=serializable,
            user_defined=user_defined,
            element_id=element_id,
            element_type=element_type,
            parent_container_name=parent_container_name,
        )

    def _create_step_validator(self, step_value: float) -> Callable[[Parameter, Any], None]:
        """Create a validator function that enforces step constraints for numbers.

        Args:
            step_value: The step size to enforce

        Returns:
            A validator function that raises ValueError if the value is not a multiple of step
        """

        def validate_step(param: Parameter, value: Any) -> None:
            if value is None:
                return

            if not isinstance(value, (int, float)):
                return  # Let other validators handle type issues

            # Get the current step value from the parameter's UI options
            current_step = param.ui_options.get("step")
            if current_step is None:
                return  # No step constraint

            # For numbers, we need to check if the value is approximately a multiple of step
            # due to floating point precision issues
            remainder = abs(value % current_step)
            # Allow for small floating point errors
            if remainder > _FLOAT_PRECISION_TOLERANCE and abs(remainder - current_step) > _FLOAT_PRECISION_TOLERANCE:
                msg = f"Value {value} is not a multiple of step {current_step}"
                raise ValueError(msg)

        return validate_step

    def _convert_to_number(self, value: Any) -> int | float:
        """Convert any input value to a number.

        This is an abstract method that subclasses must implement to provide
        the appropriate type conversion (int or float).

        Args:
            value: The value to convert

        Returns:
            The converted number

        Raises:
            NotImplementedError: If not implemented by subclass
        """
        msg = f"{self.name}: Subclasses must implement _convert_to_number"
        raise NotImplementedError(msg)
