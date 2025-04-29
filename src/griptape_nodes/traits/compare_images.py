from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from griptape_nodes.exe_types.core_types import Parameter, Trait


@dataclass(eq=False)
class CompareImagesTrait(Trait):
    element_id: str = field(default_factory=lambda: "CompareImagesTrait")

    def __init__(self) -> None:
        super().__init__()

    @classmethod
    def get_trait_keys(cls) -> list[str]:
        return ["compare_images"]

    def validators_for_trait(self) -> list[Callable[[Parameter, Any], Any]]:
        invalid_type_msg = "Value must be a dictionary"
        invalid_keys_msg = "Dictionary must contain exactly 'image_1' and 'image_2' keys"

        def validate_image_comparison(parameter: Parameter, value: Any) -> Any:
            _ = parameter  # no-op to satisfy linter
            if not isinstance(value, dict):
                raise TypeError(f"Value must be a dictionary, got {type(value).__name__} instead.")

            expected_keys = {"image_1", "image_2"}
            actual_keys = set(value.keys())
            if actual_keys != expected_keys:
                missing = expected_keys - actual_keys
                extra = actual_keys - expected_keys
                details = []
                if missing:
                    details.append(f"missing keys: {sorted(missing)}")
                if extra:
                    details.append(f"unexpected keys: {sorted(extra)}")
                detail_msg = "; ".join(details)
                raise ValueError(f"Dictionary must contain exactly 'image_1' and 'image_2' keys; {detail_msg}")

            return value

        return [validate_image_comparison]
