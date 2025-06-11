from typing import Any

from griptape_nodes.exe_types.core_types import (
    Parameter,
    ParameterMode,
)
from griptape_nodes.exe_types.node_types import DataNode


class IntegerInput(DataNode):
    def __init__(
        self,
        name: str,
        metadata: dict[Any, Any] | None = None,
        value: int = 0,
    ) -> None:
        super().__init__(name, metadata)

        self.value = value
        self.add_parameter(
            Parameter(
                name="integer",
                default_value=self.value,
                output_type="int",
                type="int",
                allowed_modes={ParameterMode.OUTPUT, ParameterMode.PROPERTY},
                tooltip="An integer",
                widget="custom",
                widget_asset_url="https://cloud.griptape.ai/api/buckets/ce2c95bc-63c2-44da-8acd-553adcf47e4a/asset-urls/TestComponent.tsx",
            )
        )

        self.add_parameter(
            Parameter(
                name="integer",
                default_value=self.value,
                output_type="int",
                type="int",
                allowed_modes={ParameterMode.OUTPUT, ParameterMode.PROPERTY},
                tooltip="An integer",
                widget="number_slider", 
                widget_options={
                    "min": 0,
                    "max": 100,
                    "step": 1,
                }
            )
        )

    def process(self) -> None:
        self.parameter_output_values["integer"] = self.parameter_values.get("integer")
