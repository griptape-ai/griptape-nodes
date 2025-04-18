from typing import Any

from griptape_nodes.exe_types.core_types import (
    Parameter,
    ParameterMode,
)
from griptape_nodes.exe_types.node_types import DataNode


class RulesetList(DataNode):
    """Combine rulesets to give an agent a more complex set of behaviors."""

    def __init__(self, name: str, metadata: dict[Any, Any] | None = None) -> None:
        super().__init__(name, metadata)

        # Add a parameter for a list of Rulesets
        self.add_parameter(
            Parameter(
                name="ruleset_1",
                input_types=["Ruleset"],
                allowed_modes={ParameterMode.INPUT},
                default_value=None,
                tooltip="Ruleset to add to the list",
            )
        )
        self.add_parameter(
            Parameter(
                name="ruleset_2",
                input_types=["Ruleset"],
                allowed_modes={ParameterMode.INPUT},
                default_value=None,
                tooltip="Ruleset to add to the list",
            )
        )
        self.add_parameter(
            Parameter(
                name="ruleset_3",
                input_types=["Ruleset"],
                allowed_modes={ParameterMode.INPUT},
                default_value=None,
                tooltip="Ruleset to add to the list",
            )
        )
        self.add_parameter(
            Parameter(
                name="ruleset_4",
                input_types=["Ruleset"],
                allowed_modes={ParameterMode.INPUT},
                default_value=None,
                tooltip="Ruleset to add to the list",
            )
        )

        # Add output parameter for the combined Ruleset list
        self.add_parameter(
            Parameter(
                name="rulesets",
                output_type="list[Ruleset]",
                allowed_modes={ParameterMode.OUTPUT},
                default_value=None,
                tooltip="Combined list of Rulesets",
            )
        )

    def process(self) -> None:
        """Process the node by combining Rulesets into a list."""
        # Get the input rulesets
        ruleset_1 = self.parameter_values.get("ruleset_1", None)
        ruleset_2 = self.parameter_values.get("ruleset_2", None)
        ruleset_3 = self.parameter_values.get("ruleset_3", None)
        ruleset_4 = self.parameter_values.get("ruleset_4", None)

        # Combine the tools into a list
        rulesets = [ruleset for ruleset in [ruleset_1, ruleset_2, ruleset_3, ruleset_4] if ruleset is not None]

        # Set output values
        self.parameter_output_values["rulesets"] = rulesets
