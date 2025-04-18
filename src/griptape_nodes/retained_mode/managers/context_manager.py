from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from griptape_nodes.retained_mode.managers.event_manager import EventManager


class ContextManager:
    """Context manager for Flow and Node contexts.

    Flows own Nodes, and there must always be a Flow context active.
    Clients can push/pop Flow contexts and Node contexts within the current Flow.
    """

    _flow_stacklist: list[ContextManager.FlowContextState]

    class FlowContextError(Exception):
        """Base exception for flow context errors."""

    class NoActiveFlowError(FlowContextError):
        """Exception raised when trying to access flow when none is active."""

    class EmptyStackError(FlowContextError):
        """Exception raised when trying to pop from an empty stack."""

    class FlowContextState:
        """Internal class that represents a Flow's state which owns a stack of node names."""

        _name: str
        _node_stack: list[str]

        def __init__(self, name: str):
            self._name = name
            self._node_stack = []

        def push_node(self, node_name: str) -> str:
            """Push a node name onto this flow's node stack."""
            self._node_stack.append(node_name)
            return node_name

        def pop_node(self) -> str:
            """Pop the top node from this flow's node stack."""
            if not self._node_stack:
                msg = f"Cannot pop Node: no active Nodes in Flow '{self._name}'"
                raise ContextManager.EmptyStackError(msg)

            node_name = self._node_stack.pop()
            return node_name

        def get_current_node_name(self) -> str:
            """Get the name of the current node in this flow."""
            if not self._node_stack:
                msg = f"No active Node in Flow '{self._name}'"
                raise ContextManager.EmptyStackError(msg)

            node_name = self._node_stack[-1]
            return node_name

        def has_current_node(self) -> bool:
            """Check if this flow has an active node."""
            return len(self._node_stack) > 0

    class FlowContext:
        """A context manager for a Flow."""

        _manager: ContextManager
        _flow_name: str

        def __init__(self, manager: ContextManager, flow_name: str):
            self._manager = manager
            self._flow_name = flow_name

        def __enter__(self) -> str:
            return self._manager.push_flow(self._flow_name)

        def __exit__(self, exc_type, exc_val, exc_tb) -> None:
            self._manager.pop_flow()

    class NodeContext:
        """A context manager for a Node within a Flow."""

        _manager: ContextManager
        _node_name: str

        def __init__(self, manager: ContextManager, node_name: str):
            self._manager = manager
            self._node_name = node_name

        def __enter__(self) -> str:
            return self._manager.push_node(self._node_name)

        def __exit__(self, exc_type, exc_val, exc_tb) -> None:
            self._manager.pop_node()

    def __init__(self, event_manager: EventManager) -> None:  # noqa: ARG002
        """Initialize the context manager with an empty flow stack."""
        self._flow_stack = []

    def has_current_flow(self) -> bool:
        """Check if there is an active Flow context."""
        return len(self._flow_stack) > 0

    def has_current_node(self) -> bool:
        """Check if there is an active Node within the current Flow."""
        if not self.has_current_flow():
            return False

        current_flow = self._flow_stack[-1]
        return current_flow.has_current_node()

    def get_current_flow_name(self) -> str:
        """Get the name of the current Flow context.

        Returns:
            The name of the current Flow.

        Raises:
            NoActiveFlowError: If no Flow context is active.
        """
        if not self.has_current_flow():
            msg = "No active Flow context"
            raise self.NoActiveFlowError(msg)

        current_flow = self._flow_stack[-1]
        return current_flow._name

    def get_current_node_name(self) -> str:
        """Get the name of the current Node within the current Flow.

        Returns:
            The name of the current Node.

        Raises:
            NoActiveFlowError: If no Flow context is active.
            EmptyStackError: If the current Flow has no active Nodes.
        """
        if not self.has_current_flow():
            msg = "No active Flow context"
            raise self.NoActiveFlowError(msg)

        current_flow = self._flow_stack[-1]
        return current_flow.get_current_node_name()

    def push_flow(self, flow_name: str) -> str:
        """Push a new Flow context onto the stack.

        Args:
            flow_name: The name of the Flow to enter.

        Returns:
            The name of the Flow that was entered.
        """
        flow_context_state = self.FlowContextState(flow_name)
        self._flow_stack.append(flow_context_state)
        return flow_name

    def pop_flow(self) -> str:
        """Pop the current Flow context from the stack.

        Returns:
            The name of the Flow that was popped.

        Raises:
            EmptyStackError: If no Flow is active.
        """
        if not self.has_current_flow():
            msg = "Cannot pop Flow: stack is empty"
            raise self.EmptyStackError(msg)

        flow = self._flow_stack.pop()
        flow_name = flow._name
        return flow_name

    def push_node(self, node_name: str) -> str:
        """Push a new Node context onto the stack for the current Flow.

        Args:
            node_name: The name of the Node to enter.

        Returns:
            The name of the Node that was entered.

        Raises:
            NoActiveFlowError: If no Flow context is active.
        """
        if not self.has_current_flow():
            msg = "Cannot enter a Node context without an active Flow context"
            raise self.NoActiveFlowError(msg)

        current_flow = self._flow_stack[-1]
        result = current_flow.push_node(node_name)
        return result

    def pop_node(self) -> str:
        """Pop the current Node context from the stack for the current Flow.

        Returns:
            The name of the Node that was popped.

        Raises:
            NoActiveFlowError: If no Flow context is active.
            EmptyStackError: If the current Flow has no active Nodes.
        """
        if not self.has_current_flow():
            msg = "Cannot pop Node: no active Flow context"
            raise self.NoActiveFlowError(msg)

        current_flow = self._flow_stack[-1]
        node_name = current_flow.pop_node()
        return node_name

    def flow(self, flow_name: str) -> ContextManager.FlowContext:
        """Create a context manager for a Flow context.

        Args:
            flow_name: The name of the Flow to enter.

        Returns:
            A context manager for the Flow context.
        """
        return self.FlowContext(self, flow_name)

    def node(self, node_name: str) -> ContextManager.NodeContext:
        """Create a context manager for a Node context.

        Args:
            node_name: The name of the Node to enter.

        Returns:
            A context manager for the Node context.
        """
        return self.NodeContext(self, node_name)
