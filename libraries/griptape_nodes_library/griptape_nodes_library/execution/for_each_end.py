from typing import Any

from griptape_nodes_library.execution.base_iterative_nodes import BaseIterativeEndNode


class ForEachEndNode(BaseIterativeEndNode):
    """For Each End Node that completes a loop iteration and connects back to the ForEachStartNode.

    This node marks the end of a loop body and signals the ForEachStartNode to continue with the next item
    or to complete the loop if all items have been processed.

    CONDITIONAL DEPENDENCY RESOLUTION:
    This node implements conditional evaluation similar to the IfElse pattern.
    We will ONLY evaluate the current item Parameter if we enter into the node via "Add Item to Output".
    This prevents unnecessary computation when taking alternative control paths like "Skip" or "Break".
    """

    def __init__(self, name: str, metadata: dict[Any, Any] | None = None) -> None:
        super().__init__(name, metadata)

    def _get_compatible_start_classes(self) -> set[type]:
        """Return the set of Start node classes that this End node can connect to."""
        from griptape_nodes_library.execution.for_each_start import ForEachStartNode

        return {ForEachStartNode}
