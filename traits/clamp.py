from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from griptape_nodes.exe_types.core_types import Trait
from traits.minmax import MinMax


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
