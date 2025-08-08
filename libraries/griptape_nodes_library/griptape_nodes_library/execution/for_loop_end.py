from typing import Any

from griptape_nodes_library.execution.base_iterative_nodes import BaseIterativeEndNode


class ForLoopEndNode(BaseIterativeEndNode):
    """For Loop End Node that completes a loop iteration and connects back to the ForLoopStartNode.

    This node marks the end of a loop body and signals the ForLoopStartNode to continue with the next iteration
    or to complete the loop if all iterations have been processed.
    """

    def __init__(self, name: str, metadata: dict[Any, Any] | None = None) -> None:
        super().__init__(name, metadata)

    def _get_compatible_start_classes(self) -> set[type]:
        """Return the set of Start node classes that this End node can connect to."""
        from griptape_nodes_library.execution.for_loop_start import ForLoopStartNode

        return {ForLoopStartNode}
