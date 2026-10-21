from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, NamedTuple

from griptape_nodes.exe_types.flow import ControlFlow
from griptape_nodes.files.path_utils import canonicalize_for_identity
from griptape_nodes.node_library.workflow_registry import (
    DuplicateWorkflowIdError,
    WorkflowMetadata,
    WorkflowMetadataError,
    WorkflowRegistryError,
    derive_workflow_id_for_path,
    read_workflow_metadata,
)
from griptape_nodes.retained_mode.engine import EngineScoped
from griptape_nodes.retained_mode.events.context_events import (
    EnsureWorkflowAndFlowRequest,
    EnsureWorkflowAndFlowResultFailure,
    EnsureWorkflowAndFlowResultSuccess,
    GetWorkflowContextRequest,
    GetWorkflowContextSuccess,
    SetWorkflowContextFailure,
    SetWorkflowContextRequest,
    SetWorkflowContextSuccess,
)
from griptape_nodes.retained_mode.request_handlers import handles

if TYPE_CHECKING:
    from types import TracebackType

    from griptape_nodes.exe_types.core_types import BaseNodeElement
    from griptape_nodes.exe_types.node_types import BaseNode
    from griptape_nodes.node_library.workflow_registry import Workflow
    from griptape_nodes.retained_mode.engine import Engine
    from griptape_nodes.retained_mode.events.base_events import ResultPayload
    from griptape_nodes.retained_mode.managers.event_manager import EventManager

logger = logging.getLogger("griptape_nodes")


class ContextManager(EngineScoped):
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

    class UnknownWorkflowError(WorkflowContextError):
        """No registered workflow has the name or id a context push asked for."""

    class MirroredWorkflowError(WorkflowContextError):
        """A peer engine's workflow could not be registered in this engine's registry."""

    class WorkflowContextState:
        """Internal class that represents a Workflow's state which owns a stack of flow names.

        Holds only the workflow's id. Its name, file and folder live on its registry entry, so a
        save, rename, or move updates them in one place and the context never goes stale.
        """

        workflow_id: str
        _flow_stack: list[ContextManager.FlowContextState]

        def __init__(self, workflow_id: str):
            self.workflow_id = workflow_id
            self._flow_stack = []

        def push_flow(self, flow: ControlFlow) -> ControlFlow:
            """Push a flow name onto this workflow's flow stack."""
            flow_context = ContextManager.FlowContextState(flow)
            self._flow_stack.append(flow_context)
            return flow

        def pop_flow(self) -> ControlFlow:
            """Pop the top flow from this workflow's flow stack."""
            if not self._flow_stack:
                msg = f"Cannot pop Flow: no active Flows in Workflow '{self.workflow_id}'"
                raise ContextManager.EmptyStackError(msg)

            flow_context = self._flow_stack.pop()
            return flow_context._flow

        def has_current_flow(self) -> bool:
            """Check if this workflow has an active flow."""
            return len(self._flow_stack) > 0

        def get_current_flow(self) -> ControlFlow:
            """Get the current flow in this workflow."""
            if not self._flow_stack:
                msg = f"No active Flow in Workflow '{self.workflow_id}'"
                raise ContextManager.EmptyStackError(msg)

            flow_context = self._flow_stack[-1]
            return flow_context._flow

    class WorkflowContext:
        """A context manager for a Workflow."""

        _manager: ContextManager
        _workflow_name: str

        def __init__(self, manager: ContextManager, workflow_name: str):
            self._manager = manager
            self._workflow_name = workflow_name

        def __enter__(self) -> None:
            self._manager.push_workflow(workflow_name=self._workflow_name)

        def __exit__(
            self,
            exc_type: type[BaseException] | None,
            exc_value: BaseException | None,
            exc_traceback: TracebackType | None,
        ) -> None:
            self._manager.pop_workflow()

    class FlowContextState:
        """Internal class that represents a Flow's state which owns a stack of node names."""

        _flow: ControlFlow
        _node_stack: list[ContextManager.NodeContextState]

        def __init__(self, flow: ControlFlow):
            self._flow = flow
            self._node_stack = []

        def push_node(self, node: BaseNode) -> BaseNode:
            """Push a node name onto this flow's node stack."""
            node_context = ContextManager.NodeContextState(node)
            self._node_stack.append(node_context)
            return node

        def pop_node(self) -> BaseNode:
            """Pop the top node from this flow's node stack."""
            if not self._node_stack:
                msg = f"Cannot pop Node: no active Nodes in Flow '{self._flow.name}'"
                raise ContextManager.EmptyStackError(msg)

            node_context = self._node_stack.pop()
            return node_context.node

        def get_current_node(self) -> BaseNode:
            """Get the name of the current node in this flow."""
            if not self._node_stack:
                msg = f"No active Node in Flow '{self._flow.name}'"
                raise ContextManager.EmptyStackError(msg)

            node_context = self._node_stack[-1]
            return node_context.node

        def has_current_node(self) -> bool:
            """Check if this flow has an active node."""
            return len(self._node_stack) > 0

    class NodeContextState:
        """Internal class that represents a Node's state which owns a stack of node elements."""

        node: BaseNode
        _element_stack: list[BaseNodeElement]

        def __init__(self, node: BaseNode):
            self.node = node
            self._element_stack = []

        def push_element(self, element: BaseNodeElement) -> BaseNodeElement:
            """Push an element name onto this node's element stack."""
            self._element_stack.append(element)
            return element

        def pop_element(self) -> BaseNodeElement:
            """Pop the top element from this node's element stack."""
            if not self._element_stack:
                msg = f"Cannot pop Element: no active Elements in Node '{self.node.name}'"
                raise ContextManager.EmptyStackError(msg)

            element = self._element_stack.pop()
            return element

        def get_current_element(self) -> BaseNodeElement:
            """Get the name of the current element in this node."""
            if not self._element_stack:
                msg = f"No active Element in Node '{self.node.name}'"
                raise ContextManager.EmptyStackError(msg)

            return self._element_stack[-1]

        def has_current_element(self) -> bool:
            """Check if this node has an active element."""
            return len(self._element_stack) > 0

    # The admittedly-confusing term for using these as a Python context (e.g., the `with` keyword)
    class FlowContext:
        """A context manager for a Flow."""

        _manager: ContextManager
        _flow: ControlFlow

        def __init__(self, manager: ContextManager, flow: ControlFlow):
            self._manager = manager
            self._flow = flow

        def __enter__(self) -> ControlFlow:
            return self._manager.push_flow(self._flow)

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
        _node: BaseNode

        def __init__(self, manager: ContextManager, node: BaseNode):
            self._manager = manager
            self._node = node

        def __enter__(self) -> BaseNode:
            return self._manager.push_node(self._node)

        def __exit__(
            self,
            exc_type: type[BaseException] | None,
            exc_value: BaseException | None,
            exc_traceback: TracebackType | None,
        ) -> None:
            self._manager.pop_node()

    class ElementContext:
        """A context manager for an Element within a Node."""

        def __init__(self, manager: ContextManager, element: BaseNodeElement):
            self._manager = manager
            self._element = element

        def __enter__(self) -> BaseNodeElement:
            return self._manager.push_element(self._element)

        def __exit__(
            self,
            exc_type: type[BaseException] | None,
            exc_value: BaseException | None,
            exc_traceback: TracebackType | None,
        ) -> None:
            self._manager.pop_element()

    def __init__(self, event_manager: EventManager, *, engine: Engine | None = None) -> None:
        """Initialize the context manager with empty workflow and flow stacks."""
        super().__init__(engine)
        self._workflow_stack = []
        event_manager.register_request_handlers(self)

    @handles(SetWorkflowContextRequest)
    def on_set_workflow_context_request(self, request: SetWorkflowContextRequest) -> ResultPayload:
        # As of today, we only allow a single Workflow context at a time. This may change in the future.
        if self.has_current_workflow():
            msg = f"Attempted to set the Workflow '{request.workflow_name}' as the Current Context. Failed because an existing workflow, '{self.get_current_workflow_name()}', is already in the Current Context. In order to clear the existing workflow and remove all objects and references to it, issue a ClearAllObjectState request."
            return SetWorkflowContextFailure(result_details=msg)

        # Normalized here rather than at read time so `workflow_dir` never has to care whether
        # the caller sent an absolute path, a workspace-relative one, or one with a `~` in it.
        working_directory = None
        if request.working_directory is not None:
            working_directory = str(
                canonicalize_for_identity(request.working_directory, base=self.engine.config_manager.workspace_path)
            )
            # A file where a folder was meant is the one mistake worth rejecting: the value
            # becomes the parent of every path the workflow writes, so accepting it would put
            # outputs beside the file rather than in the folder the caller named -- a plausible
            # location, which is what makes it hard to notice.
            existing = Path(working_directory)
            if existing.exists() and not existing.is_dir():
                msg = (
                    f"Attempted to set the folder for a new Workflow to '{request.working_directory}'. "
                    f"Failed because that path is a file, not a folder."
                )
                return SetWorkflowContextFailure(result_details=msg)

        workflow_or_error = self._resolve_workflow_to_set(request, working_directory)
        if isinstance(workflow_or_error, str):
            return SetWorkflowContextFailure(result_details=workflow_or_error)
        workflow = workflow_or_error

        self.push_workflow(workflow_id=workflow.workflow_id)
        msg = f"Successfully set the Workflow '{workflow.name}' as the Current Context."
        return SetWorkflowContextSuccess(
            workflow_name=workflow.name, workflow_id=workflow.workflow_id, result_details=msg
        )

    def _resolve_workflow_to_set(
        self, request: SetWorkflowContextRequest, working_directory: str | None
    ) -> Workflow | str:
        """Find or register the workflow a SetWorkflowContextRequest names, or say why it cannot.

        No name registers a new unsaved workflow, so the engine owns the id namespace: callers
        doing "create a new workflow" omit the name and read it off the success result. An
        unregistered "unsaved:<id>" name registers an unsaved workflow with that id, so a
        client that kept the name of a workflow it created gets the same workflow back. Any
        other name must already be registered.
        """
        registry = self.engine.workflow_registry
        display_name = request.display_name or "Untitled"
        if request.workflow_name is None:
            return registry.register_unsaved(display_name, working_directory)

        workflow = registry.find_by_name(request.workflow_name)
        if workflow is not None:
            return workflow

        if not request.workflow_name.startswith(registry.UNSAVED_KEY_PREFIX):
            return (
                f"Attempted to set the Workflow '{request.workflow_name}' as the Current Context. "
                "Failed because no workflow has that name."
            )
        requested_id = registry.unsaved_name_workflow_id(request.workflow_name)
        if requested_id is None:
            return (
                f"Attempted to set the unsaved Workflow '{request.workflow_name}' as the Current Context. "
                "Failed because the part after 'unsaved:' must be a workflow id (a UUID)."
            )
        try:
            return registry.register_unsaved(display_name, working_directory, workflow_id=requested_id)
        except WorkflowRegistryError as err:
            return (
                f"Attempted to register unsaved workflow '{request.workflow_name}' "
                f"before setting it as the Current Context. Failed because of '{err}'."
            )

    @handles(GetWorkflowContextRequest)
    def on_get_workflow_context_request(self, request: GetWorkflowContextRequest) -> ResultPayload:  # noqa: ARG002
        workflow_name = None
        workflow_id = None
        is_saved = None
        if self.has_current_workflow():
            workflow = self.get_current_workflow()
            workflow_name = workflow.name
            workflow_id = workflow.workflow_id
            is_saved = workflow.is_saved
        return GetWorkflowContextSuccess(
            workflow_name=workflow_name,
            workflow_id=workflow_id,
            is_saved=is_saved,
            result_details=f"Successfully retrieved workflow context: {workflow_name or 'None'}",
        )

    @handles(EnsureWorkflowAndFlowRequest)
    def on_ensure_workflow_and_flow_request(self, request: EnsureWorkflowAndFlowRequest) -> ResultPayload:
        """Cold-start bootstrap that guarantees a workflow + flow context exist.

        Delegates the workflow side to SetWorkflowContextRequest so the unsaved-registry-key
        scheme ("unsaved:<workflow id>") stays the single source of truth for scratch workflows;
        composes that with CreateFlowRequest so callers can go from a blank engine to
        CreateNode in a single round trip.
        """
        # Lazy import required: context_manager is imported by griptape_nodes, creating a circular dependency.
        from griptape_nodes.retained_mode.events.flow_events import (
            CreateFlowRequest,
            CreateFlowResultSuccess,
        )

        created_workflow = False
        if self.has_current_workflow():
            workflow_name = self.get_current_workflow_name()
            workflow_id = self.get_current_workflow_id()
        else:
            set_workflow_result = self.engine.handle_request(self._set_workflow_request_for_ensure(request))
            if not isinstance(set_workflow_result, SetWorkflowContextSuccess):
                return EnsureWorkflowAndFlowResultFailure(
                    result_details=(
                        f"Attempted to ensure a workflow + flow context. Failed while setting the workflow: "
                        f"{set_workflow_result.result_details}"
                    )
                )
            workflow_name = set_workflow_result.workflow_name
            workflow_id = set_workflow_result.workflow_id
            created_workflow = True

        created_flow = False
        if self.has_current_flow():
            flow_name = self.get_current_flow().name
        else:
            create_flow_result = self.engine.handle_request(
                CreateFlowRequest(
                    parent_flow_name=None,
                    flow_name=request.flow_name,
                    set_as_new_context=True,
                )
            )
            if not isinstance(create_flow_result, CreateFlowResultSuccess):
                # Roll the workflow push back so a partial failure does not leave hanging state.
                if created_workflow:
                    self.pop_workflow()
                return EnsureWorkflowAndFlowResultFailure(
                    result_details=(
                        f"Attempted to ensure a workflow + flow context. Failed while creating the flow: "
                        f"{create_flow_result.result_details}"
                    )
                )
            flow_name = create_flow_result.flow_name
            created_flow = True

        return EnsureWorkflowAndFlowResultSuccess(
            workflow_name=workflow_name,
            workflow_id=workflow_id,
            flow_name=flow_name,
            created_workflow=created_workflow,
            created_flow=created_flow,
            result_details=(
                f"Workflow '{workflow_name}' and Flow '{flow_name}' are ready "
                f"(created_workflow={created_workflow}, created_flow={created_flow})."
            ),
        )

    def _set_workflow_request_for_ensure(self, request: EnsureWorkflowAndFlowRequest) -> SetWorkflowContextRequest:
        """The SetWorkflowContextRequest that creates or enters the workflow an Ensure names.

        A name that is registered, or is an "unsaved:<id>" name, is entered as is. Any other
        name is the name for a new workflow: Ensure creates one, so it becomes the new unsaved
        workflow's display name (unless one was given), and the result reports the workflow's
        own "unsaved:<id>" name.
        """
        workflow_name = request.workflow_name
        if workflow_name is None:
            return SetWorkflowContextRequest(
                display_name=request.display_name, working_directory=request.working_directory
            )
        registry = self.engine.workflow_registry
        if registry.find_by_name(workflow_name) is not None or workflow_name.startswith(registry.UNSAVED_KEY_PREFIX):
            return SetWorkflowContextRequest(
                workflow_name=workflow_name,
                display_name=request.display_name,
                working_directory=request.working_directory,
            )
        return SetWorkflowContextRequest(
            display_name=request.display_name or workflow_name, working_directory=request.working_directory
        )

    def workflow(self, workflow_name: str) -> ContextManager.WorkflowContext:
        """Create a context manager for a Workflow context.

        Args:
            workflow_name: The name of the Workflow to enter.

        Returns:
            A context manager for the Workflow context.
        """
        return self.WorkflowContext(self, workflow_name)

    def flow(self, flow: ControlFlow | str) -> ContextManager.FlowContext:
        """Create a context manager for a Flow context.

        Args:
            flow: The Flow object to enter.

        Returns:
            A context manager for the Flow context.
        """
        if isinstance(flow, str):
            try:
                control_flow = self.engine.object_manager.attempt_get_object_by_name_as_type(flow, ControlFlow)
                if control_flow is None:
                    msg = f"Flow '{flow}' not found in current workflow."
                    raise ValueError(msg)
                flow = control_flow
            except KeyError as e:
                msg = f"Flow '{flow}' not found in current workflow."
                raise ValueError(msg) from e
        return self.FlowContext(self, flow)

    def node(self, node: str | BaseNode) -> ContextManager.NodeContext:
        """Create a context manager for a Node context.

        Args:
            node: The Node object to enter.

        Returns:
            A context manager for the Node context.
        """
        if isinstance(node, str):
            try:
                node = self.get_current_flow().nodes[node]
            except KeyError as e:
                msg = f"Node '{node}' not found in current flow."
                raise ValueError(msg) from e
        return self.NodeContext(self, node)

    def element(self, element: BaseNodeElement | str) -> ContextManager.ElementContext:
        """Create a context manager for an Element context.

        Args:
            element: The Element object to enter.

        Returns:
            A context manager for the Element context.
        """
        if isinstance(element, str):
            try:
                node_element = self.get_current_node().root_ui_element.find_element_by_name(element)
                if node_element is None:
                    msg = f"Element '{element}' not found in current node."
                    raise ValueError(msg)
                element = node_element
            except KeyError as e:
                msg = f"Element '{element}' not found in current node."
                raise ValueError(msg) from e
        return self.ElementContext(self, element)

    def mirror_workflow_context(
        self,
        workflow_id: str | None,
        name: str | None,
        file_path: str | None,
        working_directory: str | None,
    ) -> None:
        """Adopt another engine's workflow context as this engine's own.

        A real stack entry rather than an override of the getters, because `has_current_workflow()`
        answers two questions at once -- "is identity resolvable" and "is there an entry to index"
        -- and satisfying only the first raises IndexError in `has_current_flow`, `push_flow`,
        `pop_flow`, and the context setters.

        The entry it points at is this engine's registry entry under the peer's workflow id,
        registered unlisted when this engine does not know the workflow, and moved when the peer
        has saved or moved it since. `name` is the peer's legacy name, used only for messages. The
        entry an earlier mirror registered is dropped once another workflow is mirrored.

        Idempotent and never popped: this MIRRORS a peer's context rather than nesting under it, so
        one entry is replaced in place. There is no push/pop pair whose ordering could interleave
        while a worker runs nodes concurrently.
        """
        previous_id = None
        if self._workflow_stack:
            previous_id = self._workflow_stack[-1].workflow_id

        if workflow_id is None:
            # The peer has no workflow, so this engine must have none either. A mirror left from an
            # earlier execution would resolve paths against that workflow's folder while the peer
            # resolves them workspace-relative -- the divergence this mirror exists to prevent,
            # reached from the other direction. Only a mirror is ever on a worker's stack.
            self._workflow_stack.clear()
            if previous_id is not None:
                self._drop_mirror_entry(previous_id)
            return

        mirrored_id = self._mirror_registry_entry(workflow_id, name, file_path, working_directory)
        state = self.WorkflowContextState(mirrored_id)
        if not self._workflow_stack:
            self._workflow_stack.append(state)
        elif self._workflow_stack[-1].workflow_id != mirrored_id:
            # Replace rather than append: a mirror tracks one peer context, and stacking would leave
            # the previous workflow's entry to be read by whatever runs next.
            self._workflow_stack[-1] = state

        if previous_id is not None and previous_id != mirrored_id:
            self._drop_mirror_entry(previous_id)

    def _mirror_registry_entry(
        self,
        workflow_id: str,
        name: str | None,
        file_path: str | None,
        working_directory: str | None,
    ) -> str:
        """Make this engine's registry describe the peer's workflow under the peer's id, and return that id.

        The peer's id is the authority. An entry this engine holds for the same file under another
        id is a stale view (its scan ran before the peer first saved, restamped or overwrote the
        file), so it is dropped and the file goes to the peer's id.

        Raises:
            MirroredWorkflowError: The peer's file could not be registered here, for example because
                it moved or was deleted while the node was being dispatched.
        """
        registry = self.engine.workflow_registry
        workflow = registry.find_by_id(workflow_id)

        if file_path is None:
            if workflow is None:
                workflow = registry.register_unsaved(
                    name or "Untitled", working_directory, workflow_id=workflow_id, listed=False
                )
            workflow.working_directory = working_directory
            return workflow_id

        known = registry.find_by_path(file_path)
        if known is not None and known.workflow_id == workflow_id:
            return workflow_id
        if known is not None:
            logger.debug(
                "Workflow '%s' was registered here as '%s'; the peer engine knows it as '%s'.",
                known.name,
                known.workflow_id,
                workflow_id,
            )
            if self.is_workflow_in_context(known.workflow_id):
                # The stale entry is the current mirror; the caller puts the peer's id in its place.
                self._workflow_stack.clear()
            registry.remove(known.workflow_id)

        try:
            if workflow is not None:
                # The peer saved or moved the workflow since this engine last mirrored it.
                registry.set_file_path(workflow, file_path)
            else:
                opened = read_metadata_for_open_file(Path(file_path))
                registry.register_file(
                    file_path,
                    opened.metadata.model_copy(update={"workflow_id": workflow_id}),
                    listed=False,
                    metadata_error=opened.metadata_error,
                )
        except ValueError as err:
            logger.debug("Could not mirror workflow '%s' from '%s': %s", workflow_id, file_path, err)
            if Path(file_path).exists():
                reason = "another workflow is already using that file"
            else:
                reason = "it was moved or deleted while the node was starting. Run it again"
            msg = (
                f"Attempted to run a node of workflow '{name or workflow_id}'. Failed because the workflow's "
                f"file '{file_path}' could not be opened: {reason}."
            )
            raise self.MirroredWorkflowError(msg) from err
        return workflow_id

    def _drop_mirror_entry(self, workflow_id: str) -> None:
        """Remove the entry an earlier mirror registered, now that another workflow is mirrored.

        Only unlisted entries are the mirror's own; a listed one came from this engine's scan.
        Without this a long-lived worker keeps one entry per peer workflow it ever ran a node for.
        """
        registry = self.engine.workflow_registry
        workflow = registry.find_by_id(workflow_id)
        if workflow is None or workflow.listed or self.is_workflow_in_context(workflow_id):
            return
        registry.remove(workflow_id)

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

    def is_workflow_in_context(self, workflow_id: str) -> bool:
        """Whether the workflow with this id is anywhere on the context stack."""
        return any(state.workflow_id == workflow_id for state in self._workflow_stack)

    def get_current_workflow_id(self) -> str:
        """Get the id of the current Workflow context.

        Raises:
            NoActiveWorkflowError: If no Workflow context is active.
        """
        if not self.has_current_workflow():
            msg = "No active Workflow context"
            raise self.NoActiveWorkflowError(msg)

        return self._workflow_stack[-1].workflow_id

    def get_current_workflow(self) -> Workflow:
        """Get the registry entry of the current Workflow context.

        Raises:
            NoActiveWorkflowError: If no Workflow context is active.
        """
        return self.engine.workflow_registry.get(self.get_current_workflow_id())

    def get_current_workflow_name(self) -> str:
        """Get the name of the current Workflow context.

        Returns:
            The legacy registry name of the current Workflow, read from its registry entry.

        Raises:
            NoActiveWorkflowError: If no Workflow context is active.
        """
        return self.get_current_workflow().name

    def get_current_workflow_file_path(self) -> str | None:
        """Get the absolute path of the current Workflow's file, if it has one.

        Read from the workflow's registry entry, which saves, renames and moves keep current.

        Returns:
            The absolute file path, or None for an unsaved workflow.

        Raises:
            NoActiveWorkflowError: If no Workflow context is active.
        """
        absolute_path = self.get_current_workflow().absolute_path
        if absolute_path is None:
            return None
        return str(absolute_path)

    def get_current_workflow_working_directory(self) -> str | None:
        """Get the folder the current Workflow belongs to, if one was supplied.

        This is the folder a workflow was created in before it had a file of its own -- the
        folder the caller was browsing at the time. It is a DIRECTORY, whereas
        `get_current_workflow_file_path` returns a FILE whose parent is the directory.

        Only meaningful while the workflow is unsaved: `workflow_dir` prefers the file path
        whenever there is one, so this stops mattering the moment the workflow is saved. It is
        deliberately not cleared on save -- the file path simply wins.

        Returns:
            The absolute directory path, or None when no folder was supplied.

        Raises:
            NoActiveWorkflowError: If no Workflow context is active.
        """
        return self.get_current_workflow().working_directory

    def move_current_workflow_onto(self, workflow_id: str) -> None:
        """Make the registry entry `workflow_id` the current Workflow, keeping the open flows.

        For the one case where an open workflow becomes a different registry entry: saving an
        open library workflow writes a copy, and the editor keeps working in the copy.

        Raises:
            NoActiveWorkflowError: If no Workflow context is active.
        """
        if not self.has_current_workflow():
            msg = "No active Workflow context"
            raise self.NoActiveWorkflowError(msg)

        self._workflow_stack[-1].workflow_id = workflow_id

    def get_current_flow(self) -> ControlFlow:
        """Get the current Flow object.

        Returns:
            The current Flow object.

        Raises:
            NoActiveFlowError: If no Flow context is active.
        """
        if not self.has_current_flow():
            msg = "No active Flow context"
            raise self.NoActiveFlowError(msg)

        current_workflow = self._workflow_stack[-1]
        return current_workflow.get_current_flow()

    def get_current_node(self) -> BaseNode:
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
        return current_flow.get_current_node()

    def get_current_element(self) -> BaseNodeElement:
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
        return current_node.get_current_element()

    def push_workflow(
        self,
        workflow_name: str | None = None,
        *,
        file_path: str | None = None,
        workflow_id: str | None = None,
        working_directory: str | None = None,
    ) -> str:
        """Push a new Workflow context onto the stack.

        The context holds only the workflow's id; its name, file and folder are read from its
        registry entry. Exactly one of the arguments names the workflow.

        Args:
            workflow_name: The legacy registry name of a registered Workflow.
            file_path: Path to a workflow file. Saved workflow files push themselves this way
                (`push_workflow(file_path=__file__)`). A file the registry does not know is
                registered unlisted, so it does not appear in the workflow list.
            workflow_id: The id of a registered Workflow.
            working_directory: Folder the Workflow belongs to while it has no file of its own,
                set on its registry entry. A DIRECTORY, not a file path. Never overrides the
                workflow's file: a saved workflow answers with that file's own directory.
                It stays on the entry after `pop_workflow()`.

        Returns:
            The name of the Workflow that was entered.

        Raises:
            ValueError: If not exactly one of the arguments is provided.
            UnknownWorkflowError: If no registered workflow has that name or id.
        """
        provided = [argument for argument in (workflow_name, file_path, workflow_id) if argument is not None]
        if len(provided) != 1:
            msg = "Provide exactly one of workflow_name, file_path or workflow_id."
            raise ValueError(msg)

        registry = self.engine.workflow_registry
        if workflow_name is not None:
            workflow = registry.find_by_name(workflow_name)
            if workflow is None:
                msg = f"Attempted to enter Workflow '{workflow_name}'. Failed because no workflow has that name."
                raise self.UnknownWorkflowError(msg)
        elif workflow_id is not None:
            workflow = registry.find_by_id(workflow_id)
            if workflow is None:
                msg = f"Attempted to enter Workflow '{workflow_id}'. Failed because no workflow has that id."
                raise self.UnknownWorkflowError(msg)
        else:
            workflow = self._find_or_register_open_file(str(file_path))

        if working_directory is not None:
            workflow.working_directory = working_directory
        self._workflow_stack.append(self.WorkflowContextState(workflow.workflow_id))
        return workflow.name

    def _find_or_register_open_file(self, file_path: str) -> Workflow:
        """The registry entry for a workflow file being opened, registered unlisted when there is none.

        Unlisted, so running a file from outside the workspace does not add it to the workflow
        list. A file whose header cannot be read still opens (tests and scripts push their own
        `__file__`), under a placeholder name and the id derived from its path, and its entry
        records why the header could not be read.
        """
        registry = self.engine.workflow_registry
        workflow = registry.find_by_path(file_path)
        if workflow is not None:
            return workflow
        opened = read_metadata_for_open_file(Path(file_path))
        metadata = opened.metadata
        try:
            return registry.register_file(file_path, metadata, listed=False, metadata_error=opened.metadata_error)
        except DuplicateWorkflowIdError as err:
            # A copy of a registered workflow, opened before any scan settled which file keeps the
            # id. Opening never writes, so it takes the id derived from its path for now.
            logger.warning(
                "Workflow file '%s' has the same workflow id as '%s'. Opening it under an id of its own.",
                file_path,
                err.existing.name,
            )
            derived_id = derive_workflow_id_for_path(file_path, base=self.engine.config_manager.workspace_path)
            return registry.register_file(
                file_path,
                metadata.model_copy(update={"workflow_id": derived_id}),
                listed=False,
                metadata_error=opened.metadata_error,
            )

    def pop_workflow(self) -> str:
        """Pop the top Workflow from the stack.

        Returns:
            The name of the Workflow that was popped. `get_current_workflow_id` gives its id
            beforehand.

        Raises:
            EmptyStackError: If there are no active Workflows.
        """
        if not self._workflow_stack:
            msg = "Cannot pop Workflow: no active Workflows"
            raise self.EmptyStackError(msg)

        name = self.get_current_workflow_name()
        self._workflow_stack.pop()
        return name

    def push_flow(self, flow: ControlFlow) -> ControlFlow:
        """Push a new Flow context onto the stack for the current Workflow.

        Args:
            flow: The Flow object to enter.

        Returns:
            The Flow object that was entered.

        Raises:
            NoActiveWorkflowError: If no Workflow context is active.
        """
        if not self.has_current_workflow():
            msg = f"Cannot enter a Flow context '{flow.name}' without an active Workflow context"
            raise self.NoActiveWorkflowError(msg)

        current_workflow = self._workflow_stack[-1]
        return current_workflow.push_flow(flow)

    def pop_flow(self) -> ControlFlow:
        """Pop the current Flow context from the stack.

        Returns:
            The Flow object that was popped.

        Raises:
            EmptyStackError: If no Flow is active.
        """
        if not self.has_current_workflow():
            msg = "Cannot pop Flow: stack is empty"
            raise self.EmptyStackError(msg)

        current_workflow = self._workflow_stack[-1]
        return current_workflow.pop_flow()

    def push_node(self, node: BaseNode) -> BaseNode:
        """Push a new Node context onto the stack for the current Flow.

        Args:
            node: The Node object to enter.

        Returns:
            The Node object that was entered.

        Raises:
            NoActiveFlowError: If no Flow context is active.
        """
        if not self.has_current_flow():
            msg = f"Cannot enter a Node context '{node.name}' without an active Flow context"
            raise self.NoActiveFlowError(msg)

        current_workflow = self._workflow_stack[-1]
        current_flow = current_workflow._flow_stack[-1]
        result = current_flow.push_node(node)
        return result

    def pop_node(self) -> BaseNode:
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
        result = current_flow.pop_node()
        return result

    def push_element(self, element: BaseNodeElement) -> BaseNodeElement:
        """Push a new element onto the stack for the current node.

        Args:
            element: The Element object to enter.

        Returns:
            The Element object that was entered.

        Raises:
            NoActiveFlowError: If no Flow context is active.
            EmptyStackError: If the current Flow has no active Nodes or the current Node has no active Elements.
        """
        if not self.has_current_flow():
            msg = f"Cannot enter an Element context '{element.name}' without an active Flow context"
            raise self.NoActiveFlowError(msg)

        current_workflow = self._workflow_stack[-1]
        current_flow = current_workflow._flow_stack[-1]

        if not current_flow.has_current_node():
            msg = "Cannot enter an Element context without an active Node context"
            raise self.EmptyStackError(msg)

        current_node = current_flow._node_stack[-1]
        return current_node.push_element(element)

    def pop_element(self) -> BaseNodeElement:
        """Pop the current element from the stack for the current node.

        Returns:
            The Element object that was popped.

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


class OpenedFileMetadata(NamedTuple):
    """The metadata a workflow file opens with, and why its header could not be read, if it could not."""

    metadata: WorkflowMetadata
    metadata_error: str | None


def read_metadata_for_open_file(file_path: Path) -> OpenedFileMetadata:
    """The header of a workflow file being opened, or placeholder metadata when it cannot be read.

    A file opens whether or not its header reads, so a header problem never blocks opening it.
    The problem is returned with the placeholder, for the registry entry to report.
    """
    try:
        return OpenedFileMetadata(metadata=read_workflow_metadata(file_path), metadata_error=None)
    except WorkflowMetadataError as err:
        logger.debug("Opening '%s' without its metadata header: %s", file_path, err)
        placeholder = WorkflowMetadata(
            name=file_path.stem,
            schema_version=WorkflowMetadata.LATEST_SCHEMA_VERSION,
            engine_version_created_with="",
            node_libraries_referenced=[],
        )
        return OpenedFileMetadata(metadata=placeholder, metadata_error=str(err))
