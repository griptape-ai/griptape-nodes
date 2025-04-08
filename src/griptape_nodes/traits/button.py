from dataclasses import dataclass, field

from griptape_nodes.exe_types.core_types import Trait


@dataclass(eq=False)
class Button(Trait):
    type: str = field(default_factory=lambda: "Generic")
    element_id: str = field(default_factory=lambda: "Button")

    def __init__(self, button_type: str | None = None) -> None:
        super().__init__(element_id="Button")
        if button_type:
            self.type = button_type

    @classmethod
    def get_trait_keys(cls) -> list[str]:
        return ["button", "addbutton"]

    def ui_options_for_trait(self) -> dict:
        return {"button": self.type}
