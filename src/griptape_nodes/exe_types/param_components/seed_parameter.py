import random
from typing import Any

from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import BaseNode


class SeedParameter:
    def __init__(self, node: BaseNode):
        self._node = node

    def add_input_parameters(self) -> None:
        self._node.add_parameter(
            Parameter(
                name="randomize_seed",
                type="bool",
                output_type="bool",
                tooltip="randomize the seed on each run",
                default_value=False,
            )
        )
        self._node.add_parameter(
            Parameter(
                name="seed",
                type="int",
                tooltip="seed",
                default_value=42,
            )
        )

    def remove_input_parameters(self) -> None:
        self._node.remove_parameter_element_by_name("randomize_seed")
        self._node.remove_parameter_element_by_name("seed")

    def after_value_set(self, parameter: Parameter, value: Any) -> None:
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

    def preprocess(self) -> None:
        if self._node.get_parameter_value("randomize_seed"):
            # Not using for cryptographic purposes
            seed = random.randint(0, 2**32 - 1)  # noqa: S311
            self._node.set_parameter_value("seed", seed)
            self._node.publish_update_to_parameter("seed", seed)

    def get_seed(self) -> int:
        return int(self._node.get_parameter_value("seed"))
