"""The context stack of one open workflow: the flows, nodes, and elements entered in it.

Flows own Nodes, and Nodes own Elements. `WorkflowContextStack` is the state a `WorkflowRuntime` keeps
as `context`. It holds no workflow entry: the runtime it belongs to is the workflow. It raises the
errors below when a context is asked for or left that isn't there. `ContextManager` is the front that
resolves which stack the current work means.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from types import TracebackType

    from griptape_nodes.exe_types.core_types import BaseNodeElement
    from griptape_nodes.exe_types.flow import ControlFlow
    from griptape_nodes.exe_types.node_types import BaseNode


class WorkflowContextError(Exception):
    """Base exception for workflow context errors."""


class NoActiveFlowError(WorkflowContextError):
    """No active flow context error."""


class EmptyStackError(WorkflowContextError):
    """Empty stack error."""


class NodeContextState:
    """A Node entered in a Flow, which owns a stack of node elements."""

    def __init__(self, node: BaseNode) -> None:
        self.node = node
        self.element_stack: list[BaseNodeElement] = []

    def push_element(self, element: BaseNodeElement) -> BaseNodeElement:
        self.element_stack.append(element)
        return element

    def pop_element(self) -> BaseNodeElement:
        if not self.element_stack:
            msg = f"Cannot pop Element: no active Elements in Node '{self.node.name}'"
            raise EmptyStackError(msg)

        return self.element_stack.pop()

    def get_current_element(self) -> BaseNodeElement:
        if not self.element_stack:
            msg = f"No active Element in Node '{self.node.name}'"
            raise EmptyStackError(msg)

        return self.element_stack[-1]

    def has_current_element(self) -> bool:
        return len(self.element_stack) > 0


class FlowContextState:
    """A Flow entered in a workflow, which owns a stack of nodes."""

    def __init__(self, flow: ControlFlow) -> None:
        self.flow = flow
        self.node_stack: list[NodeContextState] = []

    def push_node(self, node: BaseNode) -> BaseNode:
        self.node_stack.append(NodeContextState(node))
        return node

    def pop_node(self) -> BaseNode:
        if not self.node_stack:
            msg = f"Cannot pop Node: no active Nodes in Flow '{self.flow.name}'"
            raise EmptyStackError(msg)

        return self.node_stack.pop().node

    def get_current_node(self) -> BaseNode:
        if not self.node_stack:
            msg = f"No active Node in Flow '{self.flow.name}'"
            raise EmptyStackError(msg)

        return self.node_stack[-1].node

    def has_current_node(self) -> bool:
        return len(self.node_stack) > 0


class FlowContext:
    """Enters a Flow in a workflow's context for the length of a `with` block."""

    def __init__(self, context: WorkflowContextStack, flow: ControlFlow) -> None:
        self._context = context
        self._flow = flow

    def __enter__(self) -> ControlFlow:
        return self._context.push_flow(self._flow)

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        exc_traceback: TracebackType | None,
    ) -> None:
        self._context.pop_flow()


class NodeContext:
    """Enters a Node in the current Flow of a workflow's context for the length of a `with` block."""

    def __init__(self, context: WorkflowContextStack, node: BaseNode) -> None:
        self._context = context
        self._node = node

    def __enter__(self) -> BaseNode:
        return self._context.push_node(self._node)

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        exc_traceback: TracebackType | None,
    ) -> None:
        self._context.pop_node()


class ElementContext:
    """Enters an Element in the current Node of a workflow's context for the length of a `with` block."""

    def __init__(self, context: WorkflowContextStack, element: BaseNodeElement) -> None:
        self._context = context
        self._element = element

    def __enter__(self) -> BaseNodeElement:
        return self._context.push_element(self._element)

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        exc_traceback: TracebackType | None,
    ) -> None:
        self._context.pop_element()


class WorkflowContextStack:
    """The flows, nodes, and elements entered in one workflow.

    Asking for a context that isn't entered raises the error for the missing level, so a caller that
    is unsure asks `has_current_*` first.
    """

    def __init__(self) -> None:
        self.flow_stack: list[FlowContextState] = []

    def has_current_flow(self) -> bool:
        return len(self.flow_stack) > 0

    def has_current_node(self) -> bool:
        if not self.has_current_flow():
            return False
        return self.flow_stack[-1].has_current_node()

    def has_current_element(self) -> bool:
        if not self.has_current_node():
            return False
        return self.flow_stack[-1].node_stack[-1].has_current_element()

    def get_current_flow(self) -> ControlFlow:
        """The current Flow.

        Raises:
            NoActiveFlowError: If no Flow context is active.
        """
        if not self.has_current_flow():
            msg = "No active Flow context"
            raise NoActiveFlowError(msg)

        return self.flow_stack[-1].flow

    def get_current_node(self) -> BaseNode:
        """The current Node within the current Flow.

        Raises:
            NoActiveFlowError: If no Flow context is active.
            EmptyStackError: If the current Flow has no active Nodes.
        """
        if not self.has_current_flow():
            msg = "No active Flow context"
            raise NoActiveFlowError(msg)

        return self.flow_stack[-1].get_current_node()

    def get_current_element(self) -> BaseNodeElement:
        """The current element within the current node.

        Raises:
            NoActiveFlowError: If no Flow context is active.
            EmptyStackError: If the current Flow has no active Nodes or Elements.
        """
        if not self.has_current_flow():
            msg = "No active Flow context"
            raise NoActiveFlowError(msg)

        current_flow = self.flow_stack[-1]
        if not current_flow.has_current_node():
            msg = "No active Node context"
            raise EmptyStackError(msg)

        return current_flow.node_stack[-1].get_current_element()

    def push_flow(self, flow: ControlFlow) -> ControlFlow:
        """Enter a Flow context."""
        self.flow_stack.append(FlowContextState(flow))
        return flow

    def pop_flow(self) -> ControlFlow:
        """Leave the current Flow context, returning the Flow.

        Raises:
            EmptyStackError: If no Flow is active.
        """
        if not self.flow_stack:
            msg = "Cannot pop Flow: no active Flows"
            raise EmptyStackError(msg)

        return self.flow_stack.pop().flow

    def push_node(self, node: BaseNode) -> BaseNode:
        """Enter a Node context in the current Flow.

        Raises:
            NoActiveFlowError: If no Flow context is active.
        """
        if not self.has_current_flow():
            msg = f"Cannot enter a Node context '{node.name}' without an active Flow context"
            raise NoActiveFlowError(msg)

        return self.flow_stack[-1].push_node(node)

    def pop_node(self) -> BaseNode:
        """Leave the current Node context, returning the Node.

        Raises:
            NoActiveFlowError: If no Flow context is active.
            EmptyStackError: If the current Flow has no active Nodes.
        """
        if not self.has_current_flow():
            msg = "Cannot pop Node: no active Flow context"
            raise NoActiveFlowError(msg)

        return self.flow_stack[-1].pop_node()

    def push_element(self, element: BaseNodeElement) -> BaseNodeElement:
        """Enter an Element context in the current Node.

        Raises:
            NoActiveFlowError: If no Flow context is active.
            EmptyStackError: If the current Flow has no active Node.
        """
        if not self.has_current_flow():
            msg = f"Cannot enter an Element context '{element.name}' without an active Flow context"
            raise NoActiveFlowError(msg)

        current_flow = self.flow_stack[-1]
        if not current_flow.has_current_node():
            msg = "Cannot enter an Element context without an active Node context"
            raise EmptyStackError(msg)

        return current_flow.node_stack[-1].push_element(element)

    def pop_element(self) -> BaseNodeElement:
        """Leave the current Element context, returning the Element.

        Raises:
            NoActiveFlowError: If no Flow context is active.
            EmptyStackError: If the current Flow has no active Node, or the Node no active Element.
        """
        if not self.has_current_flow():
            msg = "Cannot pop Element: no active Flow context"
            raise NoActiveFlowError(msg)

        current_flow = self.flow_stack[-1]
        if not current_flow.has_current_node():
            msg = "Cannot pop Element: no active Node context"
            raise EmptyStackError(msg)

        return current_flow.node_stack[-1].pop_element()
