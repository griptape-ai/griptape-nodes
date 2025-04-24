from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from griptape_nodes.exe_types.core_types import Parameter, ParameterMode, Trait


@dataclass(eq=False)
class Compare(Trait):
    min_items: int = 2
    max_items: int = 2
    _allowed_modes: set = field(default_factory=lambda: {ParameterMode.INPUT})

    @classmethod
    def get_trait_keys(cls) -> list[str]:
        return ["compare"]

    def ui_options_for_trait(self) -> dict:
        return {
            "compare": {
                "min_items": self.min_items,
                "max_items": self.max_items
            }
        }

    def validators_for_trait(self) -> list[Callable[..., Any]]:
        def validate(param: Parameter, value: Any) -> None:
            if isinstance(value, list) and (len(value) < self.min_items or len(value) > self.max_items):
                msg = f"Must have exactly {self.min_items} items for comparison"
                raise ValueError(msg)

        return [validate]
