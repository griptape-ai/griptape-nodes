from typing import Any

from griptape_nodes_library.lists.base_create_list import BaseCreateListNode


class CreateTextList(BaseCreateListNode):
    """CreateTextList Node that that creates a list with items provided."""

    def __init__(self, name: str, metadata: dict[Any, Any] | None = None) -> None:
        super().__init__(
            name,
            metadata,
            input_types=["str"],
            output_type="list[str]",
            default_value=None,
            items_tooltip="List of text items to add to",
            ui_options={"hide_property": False},
        )
