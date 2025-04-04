from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from griptape_nodes.exe_types.core_types import Parameter, ParameterMode, Trait

@dataclass
class MinMax(Trait):
    min: Any = 10
    max: Any = 30

    _allowed_modes = {ParameterMode.PROPERTY}

    @classmethod
    def get_trait_keys(cls) -> list[str]:
        return ["min", "max", "minmax", "min_max"]

    def ui_options_for_trait(self) -> list:
        return [{"slider": {"min_val": self.min, "max_val": self.max}},{"step": 2}, "multiline" ]

    def display_options_for_trait(self) -> dict:
        return {}

    def converters_for_trait(self) -> list[Callable]:
        return []

    def validators_for_trait(self) -> list[Callable[..., Any]]:
        def validate(param: Parameter, value:Any) -> None:
            if value > self.max or value < self.min:
                msg = "Value out of range"
                raise ValueError(msg)

        return [validate]

@dataclass
class Clamp(Trait):
    min: Any = 10
    max: Any = 30

    def __init__(self) -> None:
        super().__init__()
        self.add_child(MinMax())

    @classmethod
    def get_trait_keys(cls) -> list[str]:
        return ["clamp"]

    def converters_for_trait(self) -> list[Callable]:
        def clamp(value: Any) -> Any:
            if value > self.max:
                return self.max
            if value < self.min:
                return self.min
            return value

        return [clamp]

@dataclass
class CapybaraTrait(Trait):

    choices: list[str] = field(default=["1","2","3","4"])

    @classmethod
    def get_trait_keys(cls) -> list[str]:
        return ["Capybara","new zealand"]

    def converters_for_trait(self) -> list[Callable]:
        def convert_str(value:str) -> str:
            return "Capybara\n"* len(value.split(" "))
        def convert_list(value:list) -> list:
            self.choices = value
            return value
        return [convert_str,convert_list]


    def ui_options_for_trait(self) -> list:
        return ["multiline",{"placeholder_text":"Hi"}, {"simple_dropdown":self.choices}]



@dataclass
class ModelTrait(Trait):

    @classmethod
    def get_trait_keys(cls) -> list[str]:
        return ["model"]

    def converters_for_trait(self) -> list[Callable]:
        def convert(value:str) -> str:
            return "Capybara\n"* len(value.split(" "))
        return [convert]

    def ui_options_for_trait(self) -> list:
        return ["multiline",{"placeholder_text":"Hi"}, {"simple_dropdown":["Rodent","Fish","magical","cool","fun"]}]


# These Traits get added to a list on the parameter. When they are added they apply their functions to the parameter.
