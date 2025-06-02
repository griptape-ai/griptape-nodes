from typing import Any, Optional

from griptape_nodes.exe_types.core_types import ControlParameterInput, ControlParameterOutput, Parameter
from griptape_nodes.exe_types.node_types import EndLoopNode, BaseNode


class ForEachEndNode(EndLoopNode):
    """For Each End Node that completes a loop iteration and connects back to the ForEachStartNode.

    This node marks the end of a loop body and signals the ForEachStartNode to continue with the next item
    or to complete the loop if all items have been processed.
    """

    def __init__(self, name: str, metadata: dict[Any, Any] | None = None) -> None:
        super().__init__(name, metadata)

        # Add control input parameter
        self.add_parameter(
            ControlParameterInput(tooltip="Control Input - from the last node in the loop body", name="exec_in")
        )

        # Add loop output parameter that connects back to the ForEachStartNode
        self.loop_back = ControlParameterOutput(
            tooltip="Connects back to the ForEachStartNode to continue the iteration", name="loop_back"
        )
        self.loop_back.ui_options = {"display_name": "Loop Back"}
        self.add_parameter(self.loop_back)

    def process(self) -> None:
        # Nothing special to process here - this node just signals the end of a loop iteration
        pass

    def get_next_control_output(self) -> Optional[Parameter]:
        """Return the loop_back parameter to continue the loop.

        This should connect back to the ForEachStartNode's exec_in parameter.
        """
        return self.loop_back
