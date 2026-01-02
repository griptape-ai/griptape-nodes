from typing import Any

from griptape_nodes_library.lists.base_create_list import BaseCreateListNode


class CreateFloatList(BaseCreateListNode):
    """CreateFloatList Node that creates a list with float items provided."""

    def __init__(self, name: str, metadata: dict[Any, Any] | None = None) -> None:
        super().__init__(
            name,
            metadata,
            input_types=["float"],
            output_type="list",
            default_value=0.0,
            items_tooltip="List of float items to add to",
            ui_options={"hide_property": False},
        )
