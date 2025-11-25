from typing import Any

from griptape_nodes_library.lists.base_create_list import BaseCreateListNode


class CreateBoolList(BaseCreateListNode):
    """CreateBoolList Node that creates a list with boolean items provided."""

    def __init__(self, name: str, metadata: dict[Any, Any] | None = None) -> None:
        super().__init__(
            name,
            metadata,
            input_types=["bool"],
            output_type="list",
            default_value=None,
            items_tooltip="List of boolean items to add to",
        )
