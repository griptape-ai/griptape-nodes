from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from griptape_nodes.exe_types.core_types import Parameter, Trait


@dataclass
class ModelTrait(Trait):
    choices: list[str] = field(default_factory=lambda: ["gpt-4o", "gpt-4o-mini", "gpt-3.5-turbo", "gpt-4"])
    element_id: str = field(default_factory=lambda: "ModelTrait")

    @classmethod
    def get_trait_keys(cls) -> list[str]:
        return ["model"]

    def converters_for_trait(self) -> list[Callable]:
        def converter(value: Any) -> Any:
            if value not in self.choices:
                return self.choices[0]
            return value

        return [converter]

    def validators_for_trait(self) -> list[Callable[[Parameter, Any], Any]]:
        def validator(param: Parameter, value: Any) -> None:  # noqa: ARG001
            if value not in self.choices:
                msg = "Choice not allowed"
                raise ValueError(msg)

        return [validator]

    def ui_options_for_trait(self) -> dict:
        return {"simple_dropdown": self.choices}
