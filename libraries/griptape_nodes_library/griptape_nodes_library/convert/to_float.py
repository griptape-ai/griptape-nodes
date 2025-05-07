import re
from typing import Any

from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import BaseNode, DataNode
from griptape_nodes.retained_mode.griptape_nodes import logger


class ToFloat(DataNode):
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
                output_type="float",
                type="float",
                tooltip="The converted data as a float",
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

    def to_float(self, input_value: Any) -> float:
        result = 0.0  # Default return value

        try:
            # Direct conversion for simple types
            if isinstance(input_value, (int, float)):
                result = float(input_value)

            # String handling with number extraction
            elif isinstance(input_value, str) and input_value.strip():
                numbers = re.findall(r"-?\d+\.\d+|-?\d+", input_value)
                if numbers:
                    result = float(numbers[0])

            # Dict handling - look for first usable number
            elif isinstance(input_value, dict):
                for value in input_value.values():
                    # Try to get a non-zero result from any value
                    temp = self.to_float(value)
                    if temp != 0.0:
                        result = temp
                        break

            # Last attempt for other types
            elif input_value is not None:
                result = float(input_value)

        except Exception as e:
            logger.debug(f"Exception in to_float conversion: {e}")

        return result

    def process(self) -> None:
        # Get the input value
        params = self.parameter_values

        input_value = params.get("from", "")

        # Convert the input value to text
        self.parameter_output_values["output"] = self.to_float(input_value)
