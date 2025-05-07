from typing import Any

from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import BaseNode, DataNode
from griptape_nodes.retained_mode.griptape_nodes import logger


class ToBool(DataNode):
    def __init__(
        self,
        name: str,
        metadata: dict[Any, Any] | None = None,
        value: str = "",
    ) -> None:
        super().__init__(name, metadata)

        self.add_parameter(
            Parameter(
                name="from",
                default_value=value,
                input_types=["any"],
                tooltip="The data to convert",
                allowed_modes={ParameterMode.INPUT},
            )
        )
        self.add_parameter(
            Parameter(
                name="output",
                default_value=value,
                output_type="bool",
                type="bool",
                tooltip="The converted data as a bool",
                allowed_modes={ParameterMode.OUTPUT, ParameterMode.PROPERTY},
            )
        )

    def after_incoming_connection(
        self,
        source_node: BaseNode,
        source_parameter: Parameter,
        target_parameter: Parameter,
        modified_parameters_set: set[str],
    ) -> None:
        pass

    def to_bool(self, input_value: Any) -> bool:
        result = False  # Default return value

        try:
            # Handle None
            if input_value is None:
                result = False

            # Direct boolean
            elif isinstance(input_value, bool):
                result = input_value

            # Common truthy/falsy string values
            elif isinstance(input_value, str):
                input_lower = input_value.lower().strip()
                if input_lower in ("true", "yes", "y", "1", "t"):
                    result = True
                elif input_lower in ("false", "no", "n", "0", "f"):
                    result = False
                else:
                    # Non-empty string that doesn't match above patterns
                    result = bool(input_value.strip())

            # Numbers
            elif isinstance(input_value, (int, float)):
                result = input_value != 0

            # For collections, check if they're non-empty
            elif isinstance(input_value, (dict, list, tuple, set)):
                result = bool(input_value)

            # Default Python truthiness for other types
            else:
                result = bool(input_value)

        except Exception as e:
            logger.debug(f"Exception in to_bool conversion: {e}")

        return result

    def process(self) -> None:
        # Get the input value
        params = self.parameter_values

        input_value = params.get("from", "")

        # Convert the input value to text
        self.parameter_output_values["output"] = self.to_bool(input_value)
