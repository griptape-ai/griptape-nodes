from dataclasses import dataclass, field

from griptape_nodes.exe_types.core_types import Trait
from traits.button import Button


@dataclass(eq=False)
class AddParameterButton(Trait):
    type: str = field(default_factory=lambda: "AddParameter")
    element_id: str = field(default_factory=lambda: "Button")

    def __init__(self) -> None:
        super().__init__(element_id=self.element_id)
        self.add_child(Button(button_type="AddParameter"))

    @classmethod
    def get_trait_keys(cls) -> list[str]:
        return ["button", "addbutton"]

    def ui_options_for_trait(self) -> dict:
        return {"button": self.type}
