"""The context stack of one open workflow: its workflow entry, and the flows, nodes, and elements entered in it.

Workflows own Flows, Flows own Nodes, and Nodes own Elements. `WorkflowContextStack` is the state a
`WorkflowRuntime` keeps as `context`. It raises the errors below when a context is asked for or left
that isn't there. `ContextManager` is the front that resolves which workflow's stack the current work
means.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from griptape_nodes.common.workflow_context_handoff import WorkflowContextSnapshot

if TYPE_CHECKING:
    from types import TracebackType

    from griptape_nodes.exe_types.core_types import BaseNodeElement
    from griptape_nodes.exe_types.flow import ControlFlow
    from griptape_nodes.exe_types.node_types import BaseNode


class WorkflowContextError(Exception):
    """Base exception for workflow context errors."""


class NoActiveWorkflowError(WorkflowContextError):
    """No active workflow context error."""


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
    """A Flow entered in a Workflow, which owns a stack of nodes."""

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


class WorkflowContextState:
    """A Workflow entered in a runtime, which owns a stack of flows."""

    def __init__(self, name: str, file_path: str | None = None, working_directory: str | None = None) -> None:
        self.name = name
        # The path this context was entered WITH, when it was entered by path. Retained
        # because `name` is a registry key derived against the workspace that was active
        # at push time, so it goes stale the moment the workspace changes -- a project
        # switch re-registers workflows under the new workspace and the lookup then misses.
        # Callers that want the workflow's location (see ProjectManager's `workflow_dir`
        # builtin) read this instead of round-tripping through the workflow registry.
        self.file_path = file_path
        # The folder this workflow belongs to while it has no file of its own: the folder the
        # user was browsing when they created it. A DIRECTORY, unlike `file_path`, which is
        # a file whose PARENT is the directory. Always loses to `file_path` -- once the
        # workflow has been saved, the saved file's own location is the better answer.
        self.working_directory = working_directory
        self.flow_stack: list[FlowContextState] = []

    def push_flow(self, flow: ControlFlow) -> ControlFlow:
        self.flow_stack.append(FlowContextState(flow))
        return flow

    def pop_flow(self) -> ControlFlow:
        if not self.flow_stack:
            msg = f"Cannot pop Flow: no active Flows in Workflow '{self.name}'"
            raise EmptyStackError(msg)

        return self.flow_stack.pop().flow

    def has_current_flow(self) -> bool:
        return len(self.flow_stack) > 0

    def get_current_flow(self) -> ControlFlow:
        if not self.flow_stack:
            msg = f"No active Flow in Workflow '{self.name}'"
            raise EmptyStackError(msg)

        return self.flow_stack[-1].flow


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
    """The context stack of one open workflow.

    Holds a stack of Workflow entries, though a runtime only ever has one. Asking for a context that
    isn't entered raises the error for the missing level, so a caller that is unsure asks `has_current_*`
    first.
    """

    def __init__(self) -> None:
        self.workflow_stack: list[WorkflowContextState] = []

    def has_current_workflow(self) -> bool:
        return len(self.workflow_stack) > 0

    def has_current_flow(self) -> bool:
        if not self.has_current_workflow():
            return False
        return self.workflow_stack[-1].has_current_flow()

    def has_current_node(self) -> bool:
        if not self.has_current_flow():
            return False
        return self.workflow_stack[-1].flow_stack[-1].has_current_node()

    def has_current_element(self) -> bool:
        if not self.has_current_node():
            return False
        return self.workflow_stack[-1].flow_stack[-1].node_stack[-1].has_current_element()

    def snapshot(self) -> WorkflowContextSnapshot:
        """The workflow entry's name, file path, and working directory, or an empty snapshot when there is none."""
        if not self.has_current_workflow():
            return WorkflowContextSnapshot()
        entry = self._current_workflow_entry()
        return WorkflowContextSnapshot(
            name=entry.name, file_path=entry.file_path, working_directory=entry.working_directory
        )

    def get_current_workflow_name(self) -> str:
        """The name of the current Workflow context.

        Raises:
            NoActiveWorkflowError: If no Workflow context is active.
        """
        return self._current_workflow_entry().name

    def get_current_workflow_file_path(self) -> str | None:
        """The file path the current Workflow context was entered with, if any.

        Unlike `get_current_workflow_name()`, this does not depend on the active workspace: the name is a
        registry key derived against the workspace at push time, so switching projects re-registers
        workflows under a different key and leaves the name stale. Prefer this when you need the
        workflow's LOCATION.

        Returns:
            The absolute file path, or None when entered by name for a workflow that was
            unregistered or unsaved at push time.

        Raises:
            NoActiveWorkflowError: If no Workflow context is active.
        """
        return self._current_workflow_entry().file_path

    def get_current_workflow_working_directory(self) -> str | None:
        """The folder the current Workflow context belongs to, if one was supplied.

        This is the folder a workflow was created in before it had a file of its own -- the
        folder the caller was browsing at the time. It is a DIRECTORY, whereas
        `get_current_workflow_file_path` returns a FILE whose parent is the directory.

        Only meaningful while the workflow is unsaved: `workflow_dir` prefers the retained
        file path whenever there is one, so this stops mattering the moment the workflow is
        saved. It is deliberately not cleared on save -- the file path simply wins.

        Raises:
            NoActiveWorkflowError: If no Workflow context is active.
        """
        return self._current_workflow_entry().working_directory

    def set_current_workflow_name(self, new_name: str) -> None:
        """Update the name of the current Workflow context.

        Raises:
            NoActiveWorkflowError: If no Workflow context is active.
        """
        self._current_workflow_entry().name = new_name

    def set_current_workflow_file_path(self, new_file_path: str | None) -> None:
        """Update the file path retained on the current Workflow context.

        Anything that relocates the workflow's file on disk (Move, Rename) must call this alongside
        `set_current_workflow_name`. The retained path is the authoritative answer for the workflow's
        location, so leaving it at the pre-move value keeps `workflow_dir` pointing at the old directory
        even though the registry is correct.

        Raises:
            NoActiveWorkflowError: If no Workflow context is active.
        """
        self._current_workflow_entry().file_path = new_file_path

    def rekey_workflow(self, old_name: str, new_name: str, file_path: str) -> None:
        """Give every entry keyed `old_name` its new registry key and file.

        For a save, rename, or move, which change what the workflow is called and where it lives
        but leave it open. The path matters as much as the name: `workflow_dir` prefers the
        retained path over a registry lookup, so a stale one resolves to the folder the file left.
        """
        for entry in self.workflow_stack:
            if entry.name == old_name:
                entry.name = new_name
                entry.file_path = file_path

    def mirror_workflow_context(self, name: str | None, file_path: str | None, working_directory: str | None) -> None:
        """Adopt another engine's workflow context as this one's own.

        A real stack entry rather than an override of the getters, because `has_current_workflow()`
        answers two questions at once -- "is identity resolvable" and "is there an entry to index"
        -- and satisfying only the first raises IndexError in `has_current_flow`, `push_flow`,
        `pop_flow`, and the context setters.

        Idempotent and never popped: this MIRRORS a peer's context rather than nesting under it, so
        one entry is replaced in place. There is no push/pop pair whose ordering could interleave
        while a worker runs nodes concurrently.
        """
        if name is None:
            # The peer has no workflow, so this engine must have none either. A mirror left from an
            # earlier execution would resolve paths against that workflow's folder while the peer
            # resolves them workspace-relative -- the divergence this mirror exists to prevent,
            # reached from the other direction. Only a mirror is ever on a worker's stack.
            self.workflow_stack.clear()
            return

        entry = WorkflowContextState(name=name, file_path=file_path, working_directory=working_directory)
        if not self.workflow_stack:
            self.workflow_stack.append(entry)
            return

        current = self.workflow_stack[-1]
        if current.name == name and current.file_path == file_path:
            return

        # Replace rather than append: a mirror tracks one peer context, and stacking would leave
        # the previous workflow's entry to be read by whatever runs next.
        self.workflow_stack[-1] = entry

    def get_current_flow(self) -> ControlFlow:
        """The current Flow.

        Raises:
            NoActiveFlowError: If no Flow context is active.
        """
        if not self.has_current_flow():
            msg = "No active Flow context"
            raise NoActiveFlowError(msg)

        return self.workflow_stack[-1].get_current_flow()

    def get_current_node(self) -> BaseNode:
        """The current Node within the current Flow.

        Raises:
            NoActiveFlowError: If no Flow context is active.
            EmptyStackError: If the current Flow has no active Nodes.
        """
        if not self.has_current_flow():
            msg = "No active Flow context"
            raise NoActiveFlowError(msg)

        return self.workflow_stack[-1].flow_stack[-1].get_current_node()

    def get_current_element(self) -> BaseNodeElement:
        """The current element within the current node.

        Raises:
            NoActiveFlowError: If no Flow context is active.
            EmptyStackError: If the current Flow has no active Nodes or Elements.
        """
        if not self.has_current_flow():
            msg = "No active Flow context"
            raise NoActiveFlowError(msg)

        current_flow = self.workflow_stack[-1].flow_stack[-1]
        if not current_flow.has_current_node():
            msg = "No active Node context"
            raise EmptyStackError(msg)

        return current_flow.node_stack[-1].get_current_element()

    def push_workflow(self, name: str, file_path: str | None, working_directory: str | None) -> str:
        """Enter a Workflow context named `name`, which is already a registry key."""
        self.workflow_stack.append(WorkflowContextState(name, file_path=file_path, working_directory=working_directory))
        return name

    def pop_workflow(self) -> str:
        """Leave the current Workflow context, returning its name.

        Raises:
            EmptyStackError: If there are no active Workflows.
        """
        if not self.workflow_stack:
            msg = "Cannot pop Workflow: no active Workflows"
            raise EmptyStackError(msg)

        return self.workflow_stack.pop().name

    def push_flow(self, flow: ControlFlow) -> ControlFlow:
        """Enter a Flow context in the current Workflow.

        Raises:
            NoActiveWorkflowError: If no Workflow context is active.
        """
        if not self.has_current_workflow():
            msg = f"Cannot enter a Flow context '{flow.name}' without an active Workflow context"
            raise NoActiveWorkflowError(msg)

        return self.workflow_stack[-1].push_flow(flow)

    def pop_flow(self) -> ControlFlow:
        """Leave the current Flow context, returning the Flow.

        Raises:
            EmptyStackError: If no Flow is active.
        """
        if not self.has_current_workflow():
            msg = "Cannot pop Flow: stack is empty"
            raise EmptyStackError(msg)

        return self.workflow_stack[-1].pop_flow()

    def push_node(self, node: BaseNode) -> BaseNode:
        """Enter a Node context in the current Flow.

        Raises:
            NoActiveFlowError: If no Flow context is active.
        """
        if not self.has_current_flow():
            msg = f"Cannot enter a Node context '{node.name}' without an active Flow context"
            raise NoActiveFlowError(msg)

        return self.workflow_stack[-1].flow_stack[-1].push_node(node)

    def pop_node(self) -> BaseNode:
        """Leave the current Node context, returning the Node.

        Raises:
            NoActiveFlowError: If no Flow context is active.
            EmptyStackError: If the current Flow has no active Nodes.
        """
        if not self.has_current_flow():
            msg = "Cannot pop Node: no active Flow context"
            raise NoActiveFlowError(msg)

        return self.workflow_stack[-1].flow_stack[-1].pop_node()

    def push_element(self, element: BaseNodeElement) -> BaseNodeElement:
        """Enter an Element context in the current Node.

        Raises:
            NoActiveFlowError: If no Flow context is active.
            EmptyStackError: If the current Flow has no active Node.
        """
        if not self.has_current_flow():
            msg = f"Cannot enter an Element context '{element.name}' without an active Flow context"
            raise NoActiveFlowError(msg)

        current_flow = self.workflow_stack[-1].flow_stack[-1]
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

        current_flow = self.workflow_stack[-1].flow_stack[-1]
        if not current_flow.has_current_node():
            msg = "Cannot pop Element: no active Node context"
            raise EmptyStackError(msg)

        return current_flow.node_stack[-1].pop_element()

    def _current_workflow_entry(self) -> WorkflowContextState:
        if not self.has_current_workflow():
            msg = "No active Workflow context"
            raise NoActiveWorkflowError(msg)

        return self.workflow_stack[-1]
