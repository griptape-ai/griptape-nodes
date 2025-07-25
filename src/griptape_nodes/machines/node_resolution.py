from __future__ import annotations

import logging

from griptape_nodes.exe_types.node_types import BaseNode
from griptape_nodes.machines.fsm import FSM
from griptape_nodes.machines.execution_utils import ResolutionContext
from griptape_nodes.machines.execution_utils import CompleteState
from griptape_nodes.machines.evaluate_parameter import EvaluateParameterState

logger = logging.getLogger("griptape_nodes")

class NodeResolutionMachine(FSM[ResolutionContext]):
    """Finite state machine for resolving nodes and their dependencies."""
    def __init__(self) -> None:
        """Initialize the node resolution machine with a new context."""
        resolution_context = ResolutionContext()
        super().__init__(resolution_context)

    def resolve_node(self, node: BaseNode) -> None:
        """Resolve the given node and its dependencies."""
        self._context.root_node_resolving = node
        self.start(EvaluateParameterState)

    def change_debug_mode(self, debug_mode: bool) -> None:
        """Change the debug mode for the resolution machine."""
        self._debug_mode = debug_mode

    def is_complete(self) -> bool:
        """Return True if the resolution is complete."""
        return (self._current_state == CompleteState)

    def is_started(self) -> bool:
        """Return True if the resolution has started."""
        return self._current_state is not None

    def reset_machine(self) -> None:
        """Reset the resolution machine to its initial state."""
        self._context.reset()
        self._current_state = None