from dataclasses import dataclass

from griptape_nodes.exe_types.core_types import Trait


@dataclass(eq=False)
class Compare(Trait):
    @classmethod
    def get_trait_keys(cls) -> list[str]:
        return ["compare"]

    def ui_options_for_trait(self) -> dict:
        return {
            "compare": "true"
        }
