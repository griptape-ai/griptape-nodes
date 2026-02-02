from dataclasses import dataclass, field

from griptape_nodes.exe_types.core_types import Trait


@dataclass(eq=False, kw_only=True)
class Component(Trait):
    """Associates a parameter with a UI component from a library.

    Components are JavaScript modules that render parameter UI.
    The component must be registered in the library's components list.
    """

    library: str  # Library that provides the component (e.g., "example_nodes_template")
    element_id: str = field(default_factory=lambda: "Component")

    def __init__(self, name: str, library: str) -> None:
        super().__init__()
        self.name = name
        self.library = library

    @classmethod
    def get_trait_keys(cls) -> list[str]:
        return ["component"]

    def ui_options_for_trait(self) -> dict:
        return {
            "component": self.name,
            "library": self.library,
        }
