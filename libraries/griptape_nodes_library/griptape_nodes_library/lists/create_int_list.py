from typing import Any

from griptape_nodes_library.lists.base_create_list import BaseCreateListNode


class CreateIntList(BaseCreateListNode):
    """CreateIntList Node that creates a list with integer items provided."""

    def __init__(self, name: str, metadata: dict[Any, Any] | None = None) -> None:
        super().__init__(
            name,
            metadata,
            input_types=["int"],
            output_type="list",
            default_value=None,
            items_tooltip="List of integer items to add to",
            ui_options={"hide_property": False},
        )
