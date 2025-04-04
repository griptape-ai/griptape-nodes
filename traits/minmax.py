from collections.abc import Callable
from typing import Any

from griptape_nodes.exe_types.core_types import Parameter, ParameterMode, Trait


class MinMax(Trait):
    min: Any = 10
    max: Any = 30

    _allowed_modes = {ParameterMode.PROPERTY}

    @classmethod
    def get_trait_keys(cls) -> list[str]:
        return ["min", "max", "minmax", "min_max"]

    def ui_options_for_trait(self) -> list:
        return [{"slider": {"min_val": self.min, "max_val": self.max}}, {"step": 2}]

    def display_options_for_trait(self) -> dict:
        return {}

    def converters_for_trait(self) -> list[Callable]:
        def clamp(value: Any) -> Any:
            if value > self.max:
                return self.max
            if value < self.min:
                return self.min
            return value

        return [clamp]

    def validators_for_trait(self) -> list[Callable[..., Any]]:
        def validate(param: Parameter, value:Any) -> None:
            if value > self.max or value < self.min:
                msg = "Value out of range"
                raise ValueError(msg)

        return [validate]


# These Traits get added to a list on the parameter. When they are added they apply their functions to the parameter.
