from typing import Any

import torch  # type: ignore[reportMissingImports]

from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import BaseNode


class SeedParameter:
    def __init__(self, node: BaseNode):
        self._node = node

    def add_input_parameters(self) -> None:
        self._node.add_parameter(
            Parameter(
                name="randomize_seed",
                input_types=["bool"],
                type="bool",
                output_type="bool",
                tooltip="randomize the seed on each run",
                default_value=False,
            )
        )
        self._node.add_parameter(
            Parameter(
                name="seed",
                input_types=["int"],
                type="int",
                tooltip="seed",
                default_value=42,
            )
        )

    def after_value_set(self, parameter: Parameter, value: Any, modified_parameters_set: set[str]) -> None:
        if parameter.name != "randomize_seed":
            return

        seed_parameter = self._node.get_parameter_by_name("seed")
        if not seed_parameter:
            msg = "Seed parameter not found"
            raise RuntimeError(msg)

        if value:
            # Disable editing the seed if randomize_seed is True
            seed_parameter.allowed_modes = {ParameterMode.OUTPUT}
        else:
            # Enable editing the seed if randomize_seed is False
            seed_parameter.allowed_modes = {ParameterMode.PROPERTY, ParameterMode.INPUT, ParameterMode.OUTPUT}

        modified_parameters_set.add("seed")

    def preprocess(self) -> None:
        if self._node.get_parameter_value("randomize_seed"):
            self._node.publish_update_to_parameter("seed", torch.Generator().seed())

    def get_seed(self) -> int:
        return int(self._node.get_parameter_value("seed"))

    def get_generator(self) -> torch.Generator:
        return torch.Generator().manual_seed(self.get_seed())
