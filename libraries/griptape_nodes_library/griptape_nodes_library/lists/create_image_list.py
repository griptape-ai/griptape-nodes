from typing import Any

from griptape_nodes_library.lists.base_create_list import BaseCreateListNode


class CreateImageList(BaseCreateListNode):
    """CreateImageList Node that creates a list with image items provided."""

    def __init__(self, name: str, metadata: dict[Any, Any] | None = None) -> None:
        super().__init__(
            name,
            metadata,
            input_types=["ImageUrlArtifact", "str"],
            output_type="list",
            default_value=None,
            items_tooltip="List of image items to add to",
        )
