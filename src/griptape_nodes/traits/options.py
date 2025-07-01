from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from griptape_nodes.exe_types.core_types import Parameter, Trait


@dataclass(eq=False)
class Options(Trait):
    choices: list[str] = field(default_factory=lambda: ["choice 1", "choice 2", "choice 3"])
    element_id: str = field(default_factory=lambda: "Options")

    @classmethod
    def get_trait_keys(cls) -> list[str]:
        return ["options", "models"]

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
