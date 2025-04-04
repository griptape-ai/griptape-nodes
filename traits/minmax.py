from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from griptape_nodes.exe_types.core_types import Parameter, ParameterMode, Trait

@dataclass
class MinMax(Trait):
    min: Any = 10
    max: Any = 30
    element_id: str = field(default_factory=lambda: "MinMaxTrait")

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
    element_id: str = field(default_factory=lambda: "ClampTrait")

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
    element_id: str = field(default_factory=lambda: "CapybaraTrait")
    choices: list[str] = field(default_factory=lambda: ["1", "2", "3", "4"])

    @classmethod
    def get_trait_keys(cls) -> list[str]:
        return ["Capybara","new zealand"]

    def converters_for_trait(self) -> list[Callable]:
        def convert(value:Any) -> Any:
            if isinstance(value,str):
                return "Capybara\n"* len(value.split(" "))
            if isinstance(value,list):
                self.choices = value
                return value
            return value
        return [convert]


    def ui_options_for_trait(self) -> list:
        return ["multiline",{"placeholder_text":"Hi"}, {"simple_dropdown":self.choices}]



@dataclass
class ModelTrait(Trait):
    choices: list[str] = field(default_factory=lambda: ["gpt-4o", "gpt-4o-mini", "gpt-3.5-turbo", "gpt-4"])
    element_id: str = field(default_factory=lambda: "ModelTrait")

    @classmethod
    def get_trait_keys(cls) -> list[str]:
        return ["model"]

    def converters_for_trait(self) -> list[Callable]:
        def converter(value:Any) -> Any:
            if value not in self.choices:
                return self.choices[0]
            return value
        return [converter]

    def validators_for_trait(self) -> list[Callable[[Parameter, Any], Any]]:
        def validator(param:Parameter,value:Any)-> None:
            if value not in self.choices:
                msg = "Choice not allowed"
                raise ValueError(msg)
        return [validator]

    def ui_options_for_trait(self) -> list:
        return [{"simple_dropdown":self.choices}]


# These Traits get added to a list on the parameter. When they are added they apply their functions to the parameter.
