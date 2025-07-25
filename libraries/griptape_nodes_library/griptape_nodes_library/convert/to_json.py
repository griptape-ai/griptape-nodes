from typing import Any

from json_repair import repair_json

from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import BaseNode, DataNode


class ToJson(DataNode):
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
                output_type="json",
                type="json",
                tooltip="The converted data as json",
                ui_options={"hide_property": True},
                allowed_modes={ParameterMode.OUTPUT, ParameterMode.PROPERTY},
            )
        )

    def after_incoming_connection(
        self,
        source_node: BaseNode,
        source_parameter: Parameter,
        target_parameter: Parameter,
    ) -> None:
        pass

    def process(self) -> None:
        # Get the input value
        params = self.parameter_values

        input_value = params.get("from", {})

        # Convert to JSON using json-repair
        if isinstance(input_value, dict):
            # If it's already a dict, use it as is
            result = input_value
        elif isinstance(input_value, str):
            # If it's a string, try to repair and parse it
            try:
                result = repair_json(input_value)
            except Exception:
                # If repair fails, try to parse as regular JSON
                import json

                result = json.loads(input_value)
        else:
            # For other types, convert to string and try to repair
            try:
                result = repair_json(str(input_value))
            except Exception:
                # Fallback to empty dict
                result = {}

        self.parameter_output_values["output"] = result
