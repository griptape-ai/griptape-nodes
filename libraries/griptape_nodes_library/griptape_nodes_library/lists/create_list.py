from typing import Any

from griptape_nodes.exe_types.core_types import ParameterTypeBuiltin
from griptape_nodes_library.lists.base_create_list import BaseCreateListNode


class CreateList(BaseCreateListNode):
    """CreateList Node that that creates a list with items provided."""

    def __init__(self, name: str, metadata: dict[Any, Any] | None = None) -> None:
        super().__init__(
            name,
            metadata,
            input_types=[ParameterTypeBuiltin.ANY.value],
            output_type="list",
            default_value=None,
            items_tooltip="List of items to add to",
        )
