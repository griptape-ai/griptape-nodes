import random
from typing import Any

from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import BaseNode
from griptape_nodes.exe_types.param_types.parameter_bool import ParameterBool
from griptape_nodes.exe_types.param_types.parameter_int import ParameterInt


class SeedParameter:
    def __init__(self, node: BaseNode, max_seed: int = 2**32 - 1) -> None:
        self._node = node
        self._max_seed = max_seed

    def add_input_parameters(self, *, inside_param_group: bool = False) -> None:
        randomize_seed_parameter = ParameterBool(
            name="randomize_seed",
            tooltip="randomize the seed on each run",
            default_value=False,
        )
        seed_parameter = ParameterInt(
            name="seed",
            tooltip="the seed to use for the generation",
            default_value=42,
        )
        if not inside_param_group:
            self._node.add_parameter(randomize_seed_parameter)
            self._node.add_parameter(seed_parameter)

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
            seed = random.randint(0, self._max_seed)  # noqa: S311
            self._node.set_parameter_value("seed", seed)
            self._node.publish_update_to_parameter("seed", seed)

    def get_seed(self) -> int:
        return int(self._node.get_parameter_value("seed"))
