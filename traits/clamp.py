from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from griptape_nodes.exe_types.core_types import Trait
from traits.minmax import MinMax


@dataclass
class Clamp(Trait):
    min: Any = 0
    max: Any = 100
    element_id: str = field(default_factory=lambda: "ClampTrait")

    def __init__(self, min_val:float, max_val:float) -> None:
        super().__init__()
        self.min = min_val
        self.max = max_val
        self.add_child(MinMax(self.min,self.max))

    @classmethod
    def get_trait_keys(cls) -> list[str]:
        return ["clamp"]

    def converters_for_trait(self) -> list[Callable]:
        def clamp(value: Any) -> Any:
            if isinstance(value, (str, list)):
                if len(value) > self.max:
                    return value[:self.max]
                return value
            if value > self.max:
                return self.max
            if value < self.min:
                return self.min
            return value

        return [clamp]
