from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from griptape_nodes.retained_mode.events.context_events import (
    GetWorkflowContextRequest,
    GetWorkflowContextSuccess,
    SetWorkflowContextFailure,
    SetWorkflowContextRequest,
    SetWorkflowContextSuccess,
)

if TYPE_CHECKING:
    from types import TracebackType

    from griptape_nodes.retained_mode.events.base_events import ResultPayload
    from griptape_nodes.retained_mode.managers.event_manager import EventManager

logger = logging.getLogger("griptape_nodes")


class ContextManager:
    """Context manager for Workflow, Flow, Node, and Element contexts.

    Workflows own Flows, Flows own Nodes, and Nodes own Elements.
    There must always be a Workflow context active.
    Clients can push/pop Workflow contexts, Flow contexts, Node contexts, and Element contexts.
    """

    _workflow_stack: list[ContextManager.WorkflowContextState]

    class WorkflowContextError(Exception):
        """Base exception for workflow context errors."""

    class NoActiveWorkflowError(WorkflowContextError):
        """No active workflow context error."""

    class NoActiveFlowError(WorkflowContextError):
        """No active flow context error."""

    class EmptyStackError(WorkflowContextError):
        """Empty stack error."""

    class WorkflowContextState:
        """Internal class that represents a Workflow's state which owns a stack of flow names."""

        _name: str
        _flow_stack: list[ContextManager.FlowContextState]

        def __init__(self, name: str):
            self._name = name
            self._flow_stack = []

        def push_flow(self, flow_name: str) -> str:
            """Push a flow name onto this workflow's flow stack."""
            flow_context = ContextManager.FlowContextState(flow_name)
            self._flow_stack.append(flow_context)
            return flow_name

        def pop_flow(self) -> str:
            """Pop the top flow from this workflow's flow stack."""
            if not self._flow_stack:
                msg = f"Cannot pop Flow: no active Flows in Workflow '{self._name}'"
                raise ContextManager.EmptyStackError(msg)

            flow_context = self._flow_stack.pop()
            return flow_context._name

        def has_current_flow(self) -> bool:
            """Check if this workflow has an active flow."""
            return len(self._flow_stack) > 0

        def get_current_flow_name(self) -> str:
            """Get the name of the current flow in this workflow."""
            if not self._flow_stack:
                msg = f"No active Flow in Workflow '{self._name}'"
                raise ContextManager.EmptyStackError(msg)

            flow_context = self._flow_stack[-1]
            return flow_context._name

    class WorkflowContext:
        """A context manager for a Workflow."""

        _manager: ContextManager
        _workflow_name: str

        def __init__(self, manager: ContextManager, workflow_name: str):
            self._manager = manager
            self._workflow_name = workflow_name

        def __enter__(self) -> None:
            self._manager.push_workflow(self._workflow_name)

        def __exit__(
            self,
            exc_type: type[BaseException] | None,
            exc_value: BaseException | None,
            exc_traceback: TracebackType | None,
        ) -> None:
            self._manager.pop_workflow()

    class FlowContextState:
        """Internal class that represents a Flow's state which owns a stack of node names."""

        _name: str
        _node_stack: list[ContextManager.NodeContextState]

        def __init__(self, name: str):
            self._name = name
            self._node_stack = []

        def push_node(self, node_name: str) -> str:
            """Push a node name onto this flow's node stack."""
            node_context = ContextManager.NodeContextState(node_name)
            self._node_stack.append(node_context)
            return node_name

        def pop_node(self) -> str:
            """Pop the top node from this flow's node stack."""
            if not self._node_stack:
                msg = f"Cannot pop Node: no active Nodes in Flow '{self._name}'"
                raise ContextManager.EmptyStackError(msg)

            node_context = self._node_stack.pop()
            return node_context.node_name

        def get_current_node_name(self) -> str:
            """Get the name of the current node in this flow."""
            if not self._node_stack:
                msg = f"No active Node in Flow '{self._name}'"
                raise ContextManager.EmptyStackError(msg)

            node_context = self._node_stack[-1]
            return node_context.node_name

        def has_current_node(self) -> bool:
            """Check if this flow has an active node."""
            return len(self._node_stack) > 0

    class NodeContextState:
        """Internal class that represents a Node's state which owns a stack of node elements."""

        node_name: str
        _element_stack: list[str]

        def __init__(self, node_name: str):
            self.node_name = node_name
            self._element_stack = []

        def push_element(self, element_name: str) -> str:
            """Push an element name onto this node's element stack."""
            self._element_stack.append(element_name)
            return element_name

        def pop_element(self) -> str:
            """Pop the top element from this node's element stack."""
            if not self._element_stack:
                msg = f"Cannot pop Element: no active Elements in Node '{self.node_name}'"
                raise ContextManager.EmptyStackError(msg)

            element_name = self._element_stack.pop()
            return element_name

        def get_current_element_name(self) -> str:
            """Get the name of the current element in this node."""
            if not self._element_stack:
                msg = f"No active Element in Node '{self.node_name}'"
                raise ContextManager.EmptyStackError(msg)

            return self._element_stack[-1]

        def has_current_element(self) -> bool:
            """Check if this node has an active element."""
            return len(self._element_stack) > 0

    # The admittedly-confusing term for using these as a Python context (e.g., the `with` keyword)
    class FlowContext:
        """A context manager for a Flow."""

        _manager: ContextManager
        _flow_name: str

        def __init__(self, manager: ContextManager, flow_name: str):
            self._manager = manager
            self._flow_name = flow_name

        def __enter__(self) -> str:
            return self._manager.push_flow(self._flow_name)

        def __exit__(
            self,
            exc_type: type[BaseException] | None,
            exc_value: BaseException | None,
            exc_traceback: TracebackType | None,
        ) -> None:
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

        def __exit__(
            self,
            exc_type: type[BaseException] | None,
            exc_value: BaseException | None,
            exc_traceback: TracebackType | None,
        ) -> None:
            self._manager.pop_node()

    class ElementContext:
        """A context manager for an Element within a Node."""

        def __init__(self, manager: ContextManager, element_name: str):
            self._manager = manager
            self._element_name = element_name

        def __enter__(self) -> str:
            return self._manager.push_element(self._element_name)

        def __exit__(
            self,
            exc_type: type[BaseException] | None,
            exc_value: BaseException | None,
            exc_traceback: TracebackType | None,
        ) -> None:
            self._manager.pop_element()

    def __init__(self, event_manager: EventManager) -> None:
        """Initialize the context manager with empty workflow and flow stacks."""
        self._workflow_stack = []

        event_manager.assign_manager_to_request_type(
            request_type=SetWorkflowContextRequest, callback=self.on_set_workflow_context_request
        )
        event_manager.assign_manager_to_request_type(
            request_type=GetWorkflowContextRequest, callback=self.on_get_workflow_context_request
        )

    def on_set_workflow_context_request(self, request: SetWorkflowContextRequest) -> ResultPayload:
        # As of today, we only allow a single Workflow context at a time. This may change in the future.
        if self.has_current_workflow():
            msg = f"Attempted to set the Workflow '{request.workflow_name}' as the Current Context. Failed because an existing workflow, '{self.get_current_workflow_name()}', is already in the Current Context. In order to clear the existing workflow and remove all objects and references to it, issue a ClearAllObjectState request."
            logger.error(msg)
            return SetWorkflowContextFailure()

        self.push_workflow(request.workflow_name)
        msg = f"Successfully set the Workflow '{request.workflow_name}' as the Current Context."
        logger.debug(msg)
        return SetWorkflowContextSuccess()

    def on_get_workflow_context_request(self, request: GetWorkflowContextRequest) -> ResultPayload:  # noqa: ARG002
        workflow_name = None
        if self.has_current_workflow():
            workflow_name = self.get_current_workflow_name()
        return GetWorkflowContextSuccess(workflow_name=workflow_name)

    def workflow(self, workflow_name: str) -> ContextManager.WorkflowContext:
        """Create a context manager for a Workflow context.

        Args:
            workflow_name: The name of the Workflow to enter.

        Returns:
            A context manager for the Workflow context.
        """
        return self.WorkflowContext(self, workflow_name)

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

    def element(self, element_name: str) -> ContextManager.ElementContext:
        """Create a context manager for an Element context.

        Args:
            element_name: The name of the Element to enter.

        Returns:
            A context manager for the Element context.
        """
        return self.ElementContext(self, element_name)

    def has_current_workflow(self) -> bool:
        """Check if there is an active Workflow context."""
        return len(self._workflow_stack) > 0

    def has_current_flow(self) -> bool:
        """Check if there is an active Flow context within the current Workflow."""
        if not self.has_current_workflow():
            return False

        current_workflow = self._workflow_stack[-1]
        return current_workflow.has_current_flow()

    def has_current_node(self) -> bool:
        """Check if there is an active Node within the current Flow."""
        if not self.has_current_flow():
            return False

        current_workflow = self._workflow_stack[-1]
        current_flow = current_workflow._flow_stack[-1]
        return current_flow.has_current_node()

    def has_current_element(self) -> bool:
        """Check if there is an active Element within the current Node."""
        if not self.has_current_node():
            return False

        current_workflow = self._workflow_stack[-1]
        current_flow = current_workflow._flow_stack[-1]
        current_node = current_flow._node_stack[-1]
        return current_node.has_current_element()

    def get_current_workflow_name(self) -> str:
        """Get the name of the current Workflow context.

        Returns:
            The name of the current Workflow.

        Raises:
            NoActiveWorkflowError: If no Workflow context is active.
        """
        if not self.has_current_workflow():
            msg = "No active Workflow context"
            raise self.NoActiveWorkflowError(msg)

        current_workflow = self._workflow_stack[-1]
        return current_workflow._name

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

        current_workflow = self._workflow_stack[-1]
        return current_workflow.get_current_flow_name()

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

        current_workflow = self._workflow_stack[-1]
        current_flow = current_workflow._flow_stack[-1]
        return current_flow.get_current_node_name()

    def get_current_element_name(self) -> str:
        """Get the name of the current element within the current node.

        Returns:
            The name of the current element.

        Raises:
            NoActiveFlowError: If no Flow context is active.
            EmptyStackError: If the current Flow has no active Nodes or Elements.
        """
        if not self.has_current_flow():
            msg = "No active Flow context"
            raise self.NoActiveFlowError(msg)

        current_workflow = self._workflow_stack[-1]
        current_flow = current_workflow._flow_stack[-1]

        if not current_flow.has_current_node():
            msg = "No active Node context"
            raise self.EmptyStackError(msg)

        current_node = current_flow._node_stack[-1]
        return current_node.get_current_element_name()

    def push_workflow(self, workflow_name: str) -> str:
        """Push a new Workflow context onto the stack.

        Args:
            workflow_name: The name of the Workflow to enter.

        Returns:
            The name of the Workflow that was entered.
        """
        workflow_context_state = self.WorkflowContextState(workflow_name)
        self._workflow_stack.append(workflow_context_state)
        return workflow_name

    def pop_workflow(self) -> str:
        """Pop the top Workflow from the stack.

        Returns:
            The name of the Workflow that was popped.

        Raises:
            EmptyStackError: If there are no active Workflows.
        """
        if not self._workflow_stack:
            msg = "Cannot pop Workflow: no active Workflows"
            raise self.EmptyStackError(msg)

        workflow_context = self._workflow_stack.pop()
        return workflow_context._name

    def push_flow(self, flow_name: str) -> str:
        """Push a new Flow context onto the stack for the current Workflow.

        Args:
            flow_name: The name of the Flow to enter.

        Returns:
            The name of the Flow that was entered.

        Raises:
            NoActiveWorkflowError: If no Workflow context is active.
        """
        if not self.has_current_workflow():
            msg = f"Cannot enter a Flow context '{flow_name}' without an active Workflow context"
            raise self.NoActiveWorkflowError(msg)

        current_workflow = self._workflow_stack[-1]
        return current_workflow.push_flow(flow_name)

    def pop_flow(self) -> str:
        """Pop the current Flow context from the stack.

        Returns:
            The name of the Flow that was popped.

        Raises:
            EmptyStackError: If no Flow is active.
        """
        if not self.has_current_workflow():
            msg = "Cannot pop Flow: stack is empty"
            raise self.EmptyStackError(msg)

        current_workflow = self._workflow_stack[-1]
        return current_workflow.pop_flow()

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
            msg = f"Cannot enter a Node context '{node_name}' without an active Flow context"
            raise self.NoActiveFlowError(msg)

        current_workflow = self._workflow_stack[-1]
        current_flow = current_workflow._flow_stack[-1]
        return current_flow.push_node(node_name)

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

        current_workflow = self._workflow_stack[-1]
        current_flow = current_workflow._flow_stack[-1]
        return current_flow.pop_node()

    def push_element(self, element_name: str) -> str:
        """Push a new element onto the stack for the current node.

        Args:
            element_name: The name of the element to enter.

        Returns:
            The name of the element that was entered.

        Raises:
            NoActiveFlowError: If no Flow context is active.
            EmptyStackError: If the current Flow has no active Nodes.
        """
        if not self.has_current_flow():
            msg = f"Cannot enter an Element context '{element_name}' without an active Flow context"
            raise self.NoActiveFlowError(msg)

        current_workflow = self._workflow_stack[-1]
        current_flow = current_workflow._flow_stack[-1]

        if not current_flow.has_current_node():
            msg = "Cannot enter an Element context without an active Node context"
            raise self.EmptyStackError(msg)

        current_node = current_flow._node_stack[-1]
        return current_node.push_element(element_name)

    def pop_element(self) -> str:
        """Pop the current element from the stack for the current node.

        Returns:
            The name of the element that was popped.

        Raises:
            NoActiveFlowError: If no Flow context is active.
            EmptyStackError: If the current Flow has no active Nodes or Elements.
        """
        if not self.has_current_flow():
            msg = "Cannot pop Element: no active Flow context"
            raise self.NoActiveFlowError(msg)

        current_workflow = self._workflow_stack[-1]
        current_flow = current_workflow._flow_stack[-1]

        if not current_flow.has_current_node():
            msg = "Cannot pop Element: no active Node context"
            raise self.EmptyStackError(msg)

        current_node = current_flow._node_stack[-1]
        return current_node.pop_element()
