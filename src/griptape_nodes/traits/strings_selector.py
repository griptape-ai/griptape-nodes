from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from griptape_nodes.exe_types.core_types import Parameter, ParameterMode, Trait


@dataclass(eq=False)
class StringsSelector(Trait):
    defaults: dict[str, list[str]] = field(kw_only=True)
    placeholder: str = "Type and press Enter..."
    max_items_per_category: int | None = None
    element_id: str = field(default_factory=lambda: "StringsSelector")

    _allowed_modes: set = field(default_factory=lambda: {ParameterMode.PROPERTY})

    def __init__(
        self,
        defaults: dict[str, list[str]],
        placeholder: str = "Type and press Enter...",
        max_items_per_category: int | None = None,
    ) -> None:
        super().__init__()
        self.defaults = defaults
        self.placeholder = placeholder
        self.max_items_per_category = max_items_per_category

    @classmethod
    def get_trait_keys(cls) -> list[str]:
        return ["strings_selector"]

    def ui_options_for_trait(self) -> dict:
        return {
            "strings_selector": {
                "placeholder": self.placeholder,
                "max_items_per_category": self.max_items_per_category,
                "defaults": self.defaults,
            }
        }

    def display_options_for_trait(self) -> dict:
        return {}

    def converters_for_trait(self) -> list[Callable]:
        return []

    def validators_for_trait(self) -> list[Callable[..., Any]]:
        def validate(_param: Parameter, value: Any) -> None:
            if value is None:
                return

            if not isinstance(value, dict):
                msg = "StringsSelector value must be a dictionary"
                raise TypeError(msg)

            for key, val in value.items():
                if not isinstance(key, str):
                    msg = f"StringsSelector keys must be strings, got {type(key)}"
                    raise TypeError(msg)

                if not isinstance(val, list):
                    msg = f"StringsSelector values must be lists, got {type(val)} for key '{key}'"
                    raise TypeError(msg)

                for item in val:
                    if not isinstance(item, str):
                        msg = f"StringsSelector list items must be strings, got {type(item)} in key '{key}'"
                        raise TypeError(msg)

                if self.max_items_per_category is not None and len(val) > self.max_items_per_category:
                    msg = f"Category '{key}' has {len(val)} items, exceeds maximum of {self.max_items_per_category}"
                    raise ValueError(msg)

        return [validate]
