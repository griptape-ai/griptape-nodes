from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from griptape_nodes.exe_types.core_types import Trait


@dataclass(eq=False)
class CompareImagesTrait(Trait):
    element_id: str = field(default_factory=lambda: "CompareImagesTrait")

    def __init__(self) -> None:
        super().__init__()

    @classmethod
    def get_trait_keys(cls) -> list[str]:
        return ["compare_images"]

    def converters_for_trait(self) -> list[Callable]:
        invalid_type_msg = "Value must be a dictionary"
        invalid_keys_msg = "Dictionary must contain exactly 'image_1' and 'image_2' keys"

        def validate_image_comparison(value: Any) -> Any:
            if not isinstance(value, dict):
                raise TypeError(invalid_type_msg)

            if set(value.keys()) != {"image_1", "image_2"}:
                raise ValueError(invalid_keys_msg)

            return value

        return [validate_image_comparison]
