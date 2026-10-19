from __future__ import annotations

import logging
import uuid
from pathlib import Path
from typing import TYPE_CHECKING

from griptape_nodes.exe_types.flow import ControlFlow
from griptape_nodes.files.path_utils import canonicalize_for_identity, derive_registry_key
from griptape_nodes.retained_mode.context_types import (
    ElementContext,
    EmptyStackError,
    FlowContext,
    NoActiveFlowError,
    NoActiveWorkflowError,
    NodeContext,
    WorkflowContextError,
    WorkflowContextStack,
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
    from griptape_nodes.retained_mode.engine import Engine
    from griptape_nodes.retained_mode.events.base_events import ResultPayload
    from griptape_nodes.retained_mode.managers.event_manager import EventManager
    from griptape_nodes.retained_mode.workflow_runtime import WorkflowRuntime

logger = logging.getLogger("griptape_nodes")


class ContextManager(EngineScoped):
    """Context manager for Workflow, Flow, Node, and Element contexts.

    Workflows own Flows, Flows own Nodes, and Nodes own Elements.
    There must always be a Workflow context active.
    Clients can push/pop Workflow contexts, Flow contexts, Node contexts, and Element contexts.

    Each workflow keeps its own stack, as `WorkflowRuntime.context`. The methods here are for code that
    can't be handed a workflow, such as saved workflow files and node libraries: they act on the current
    workflow. Engine code that has the workflow reads `workflow.context`.
    """

    WorkflowContextError = WorkflowContextError
    NoActiveWorkflowError = NoActiveWorkflowError
    NoActiveFlowError = NoActiveFlowError
    EmptyStackError = EmptyStackError

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

    def __init__(self, event_manager: EventManager, *, engine: Engine | None = None) -> None:
        """Initialize the context manager, whose stacks live on each workflow's runtime."""
        super().__init__(engine)
        event_manager.register_request_handlers(self)

    @handles(SetWorkflowContextRequest)
    def on_set_workflow_context_request(
        self, request: SetWorkflowContextRequest, workflow: WorkflowRuntime
    ) -> ResultPayload:
        # One workflow per runtime. OpenWorkflowRequest opens another one alongside.
        if workflow.context.has_current_workflow():
            msg = f"Attempted to set the Workflow '{request.workflow_name}' as the Current Context. Failed because an existing workflow, '{workflow.context.get_current_workflow_name()}', is already in the Current Context. To work on another workflow alongside it, open it with an OpenWorkflowRequest."
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

        # When no workflow_name is supplied, mint a fresh "unsaved:<uuid>" key here so the
        # engine owns the namespace. Callers doing "create a new workflow" should omit the
        # name and read the resolved key off the success result.
        resolved_name = request.workflow_name or f"{self.engine.workflow_registry.UNSAVED_KEY_PREFIX}{uuid.uuid4()}"

        # Auto-register an unsaved registry entry when the caller is activating an
        # "unsaved:<uuid>" key. This makes every workflow (saved or not) a first-class
        # registry entry, so list/metadata/etc. calls don't need special-casing for
        # pre-save state. `ensure_unsaved` is idempotent.
        if resolved_name.startswith(self.engine.workflow_registry.UNSAVED_KEY_PREFIX):
            try:
                self.engine.workflow_registry.ensure_unsaved(
                    key=resolved_name, display_name=request.display_name or "Untitled"
                )
            except ValueError as err:
                msg = (
                    f"Attempted to auto-register unsaved workflow '{resolved_name}' "
                    f"before setting it as the Current Context. Failed because of '{err}'."
                )
                return SetWorkflowContextFailure(result_details=msg)

        self.push_workflow_into(workflow, resolved_name, working_directory=working_directory)
        self.engine.open_workflows_manager.announce_change()
        msg = f"Successfully set the Workflow '{resolved_name}' as the Current Context."
        return SetWorkflowContextSuccess(workflow_name=resolved_name, result_details=msg)

    @handles(GetWorkflowContextRequest)
    def on_get_workflow_context_request(
        self,
        request: GetWorkflowContextRequest,  # noqa: ARG002
        workflow: WorkflowRuntime,
    ) -> ResultPayload:
        workflow_name = None
        is_saved = None
        if workflow.context.has_current_workflow():
            workflow_name = workflow.context.get_current_workflow_name()
            if self.engine.workflow_registry.has_workflow_with_name(workflow_name):
                is_saved = self.engine.workflow_registry.get_workflow_by_name(workflow_name).is_saved
        return GetWorkflowContextSuccess(
            workflow_name=workflow_name,
            is_saved=is_saved,
            result_details=f"Successfully retrieved workflow context: {workflow_name or 'None'}",
        )

    @handles(EnsureWorkflowAndFlowRequest)
    def on_ensure_workflow_and_flow_request(
        self, request: EnsureWorkflowAndFlowRequest, workflow: WorkflowRuntime
    ) -> ResultPayload:
        """Cold-start bootstrap that guarantees a workflow + flow context exist.

        Delegates the workflow side to SetWorkflowContextRequest so the unsaved-registry-key
        scheme ("unsaved:<uuid>") stays the single source of truth for scratch workflows;
        composes that with CreateFlowRequest so callers can go from a blank engine to
        CreateNode in a single round trip.
        """
        # Lazy import required: context_manager is imported by griptape_nodes, creating a circular dependency.
        from griptape_nodes.retained_mode.events.flow_events import (
            CreateFlowRequest,
            CreateFlowResultSuccess,
        )

        created_workflow = False
        if workflow.context.has_current_workflow():
            workflow_name = workflow.context.get_current_workflow_name()
        else:
            set_workflow_result = self.engine.handle_request(
                SetWorkflowContextRequest(
                    workflow_name=request.workflow_name,
                    display_name=request.display_name,
                    working_directory=request.working_directory,
                ),
                workflow_id=workflow.workflow_id,
            )
            if not isinstance(set_workflow_result, SetWorkflowContextSuccess):
                return EnsureWorkflowAndFlowResultFailure(
                    result_details=(
                        f"Attempted to ensure a workflow + flow context. Failed while setting the workflow: "
                        f"{set_workflow_result.result_details}"
                    )
                )
            workflow_name = set_workflow_result.workflow_name
            created_workflow = True

        created_flow = False
        if workflow.context.has_current_flow():
            flow_name = workflow.context.get_current_flow().name
        else:
            create_flow_result = self.engine.handle_request(
                CreateFlowRequest(
                    parent_flow_name=None,
                    flow_name=request.flow_name,
                    set_as_new_context=True,
                ),
                workflow_id=workflow.workflow_id,
            )
            if not isinstance(create_flow_result, CreateFlowResultSuccess):
                # Roll the workflow push back so a partial failure does not leave hanging state.
                if created_workflow:
                    workflow.context.pop_workflow()
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
            flow_name=flow_name,
            created_workflow=created_workflow,
            created_flow=created_flow,
            result_details=(
                f"Workflow '{workflow_name}' and Flow '{flow_name}' are ready "
                f"(created_workflow={created_workflow}, created_flow={created_flow})."
            ),
        )

    def workflow(self, workflow_name: str) -> ContextManager.WorkflowContext:
        """Create a context manager for a Workflow context.

        Args:
            workflow_name: The name of the Workflow to enter.

        Returns:
            A context manager for the Workflow context.
        """
        return self.WorkflowContext(self, workflow_name)

    def flow(self, flow: ControlFlow | str) -> FlowContext:
        """Create a context manager for a Flow context in the current workflow.

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
        return FlowContext(self._current_context(), flow)

    def node(self, node: str | BaseNode) -> NodeContext:
        """Create a context manager for a Node context in the current workflow.

        Args:
            node: The Node object to enter.

        Returns:
            A context manager for the Node context.
        """
        context = self._current_context()
        if isinstance(node, str):
            try:
                node = context.get_current_flow().nodes[node]
            except KeyError as e:
                msg = f"Node '{node}' not found in current flow."
                raise ValueError(msg) from e
        return NodeContext(context, node)

    def element(self, element: BaseNodeElement | str) -> ElementContext:
        """Create a context manager for an Element context in the current workflow.

        Args:
            element: The Element object to enter.

        Returns:
            A context manager for the Element context.
        """
        context = self._current_context()
        if isinstance(element, str):
            try:
                node_element = context.get_current_node().root_ui_element.find_element_by_name(element)
                if node_element is None:
                    msg = f"Element '{element}' not found in current node."
                    raise ValueError(msg)
                element = node_element
            except KeyError as e:
                msg = f"Element '{element}' not found in current node."
                raise ValueError(msg) from e
        return ElementContext(context, element)

    def mirror_workflow_context(self, name: str | None, file_path: str | None, working_directory: str | None) -> None:
        """Adopt another engine's workflow context as the current workflow's own."""
        workflow = self.engine.current_workflow
        workflow.context.mirror_workflow_context(name, file_path, working_directory)

    def has_current_workflow(self) -> bool:
        """Check if there is an active Workflow context.

        False, rather than an error, when no workflow is open for the current work: asking is how
        callers find out whether there is one.
        """
        return self._current_context().has_current_workflow()

    def has_current_flow(self) -> bool:
        """Check if there is an active Flow context within the current Workflow."""
        return self._current_context().has_current_flow()

    def has_current_node(self) -> bool:
        """Check if there is an active Node within the current Flow."""
        return self._current_context().has_current_node()

    def has_current_element(self) -> bool:
        """Check if there is an active Element within the current Node."""
        return self._current_context().has_current_element()

    def get_current_workflow_name(self) -> str:
        """Get the name of the current Workflow context.

        Raises:
            NoActiveWorkflowError: If no Workflow context is active.
        """
        return self._current_context().get_current_workflow_name()

    def get_current_workflow_file_path(self) -> str | None:
        """Get the file path the current Workflow context was entered with, if any.

        See `WorkflowContextStack.get_current_workflow_file_path`.

        Raises:
            NoActiveWorkflowError: If no Workflow context is active.
        """
        return self._current_context().get_current_workflow_file_path()

    def get_current_workflow_working_directory(self) -> str | None:
        """Get the folder the current Workflow context belongs to, if one was supplied.

        See `WorkflowContextStack.get_current_workflow_working_directory`.

        Raises:
            NoActiveWorkflowError: If no Workflow context is active.
        """
        return self._current_context().get_current_workflow_working_directory()

    def set_current_workflow_name(self, new_name: str) -> None:
        """Update the name of the current Workflow context.

        Raises:
            NoActiveWorkflowError: If no Workflow context is active.
        """
        self._current_context().set_current_workflow_name(new_name)

    def set_current_workflow_file_path(self, new_file_path: str | None) -> None:
        """Update the file path retained on the current Workflow context.

        See `WorkflowContextStack.set_current_workflow_file_path`.

        Raises:
            NoActiveWorkflowError: If no Workflow context is active.
        """
        self._current_context().set_current_workflow_file_path(new_file_path)

    def rekey_workflow(self, old_name: str, new_name: str, file_path: str) -> None:
        """Give every context of the current workflow keyed `old_name` its new registry key and file."""
        self._current_context().rekey_workflow(old_name, new_name, file_path)

    def get_current_flow(self) -> ControlFlow:
        """Get the current Flow object.

        Raises:
            NoActiveFlowError: If no Flow context is active.
        """
        return self._current_context().get_current_flow()

    def get_current_node(self) -> BaseNode:
        """Get the current Node within the current Flow.

        Raises:
            NoActiveFlowError: If no Flow context is active.
            EmptyStackError: If the current Flow has no active Nodes.
        """
        return self._current_context().get_current_node()

    def get_current_element(self) -> BaseNodeElement:
        """Get the current element within the current node.

        Raises:
            NoActiveFlowError: If no Flow context is active.
            EmptyStackError: If the current Flow has no active Nodes or Elements.
        """
        return self._current_context().get_current_element()

    def push_workflow(
        self,
        workflow_name: str | None = None,
        *,
        file_path: str | None = None,
        working_directory: str | None = None,
    ) -> str:
        """Push a new Workflow context onto the current workflow's stack.

        See `push_workflow_into`, which this resolves the workflow for.
        """
        workflow = self.engine.current_workflow
        return self.push_workflow_into(
            workflow, workflow_name, file_path=file_path, working_directory=working_directory
        )

    def pop_workflow(self) -> str:
        """Pop the top Workflow from the current workflow's stack.

        Returns:
            The name of the Workflow that was popped.

        Raises:
            EmptyStackError: If there are no active Workflows.
        """
        return self._current_context().pop_workflow()

    def push_flow(self, flow: ControlFlow) -> ControlFlow:
        """Push a new Flow context onto the stack for the current Workflow.

        Raises:
            NoActiveWorkflowError: If no Workflow context is active.
        """
        return self._current_context().push_flow(flow)

    def pop_flow(self) -> ControlFlow:
        """Pop the current Flow context from the stack.

        Raises:
            EmptyStackError: If no Flow is active.
        """
        return self._current_context().pop_flow()

    def push_node(self, node: BaseNode) -> BaseNode:
        """Push a new Node context onto the stack for the current Flow.

        Raises:
            NoActiveFlowError: If no Flow context is active.
        """
        return self._current_context().push_node(node)

    def pop_node(self) -> BaseNode:
        """Pop the current Node context from the stack for the current Flow.

        Raises:
            NoActiveFlowError: If no Flow context is active.
            EmptyStackError: If the current Flow has no active Nodes.
        """
        return self._current_context().pop_node()

    def push_element(self, element: BaseNodeElement) -> BaseNodeElement:
        """Push a new element onto the stack for the current node.

        Raises:
            NoActiveFlowError: If no Flow context is active.
            EmptyStackError: If the current Flow has no active Nodes.
        """
        return self._current_context().push_element(element)

    def pop_element(self) -> BaseNodeElement:
        """Pop the current element from the stack for the current node.

        Raises:
            NoActiveFlowError: If no Flow context is active.
            EmptyStackError: If the current Flow has no active Nodes or Elements.
        """
        return self._current_context().pop_element()

    def push_workflow_into(
        self,
        workflow: WorkflowRuntime,
        workflow_name: str | None = None,
        *,
        file_path: str | None = None,
        working_directory: str | None = None,
    ) -> str:
        """Push a new Workflow context onto `workflow`'s stack.

        The workflow's file path is captured here, while the registry key is still valid, and
        retained on the context (see `get_current_workflow_file_path`). `resolved_name` is a key
        derived against the CURRENT workspace, so it goes stale as soon as the workspace changes:
        switching projects re-registers every workflow under the new workspace, after which a
        lookup by the old key misses even though nothing about the file changed.

        Args:
            workflow: The runtime to enter the Workflow in.
            workflow_name: The name of the Workflow to enter. Use this when the registry key is already known.
            file_path: Path to the workflow file. The registry key will be derived from this path,
                using a workspace-relative path if possible. Mutually exclusive with workflow_name.
            working_directory: Folder the Workflow belongs to while it has no file of its own,
                for a workflow that has never been saved. A DIRECTORY, not a file path. Never
                affects the registry key, and never overrides `file_path`: a workflow that has
                a file answers with that file's own directory. Expected to be absolute --
                `on_set_workflow_context_request` normalizes before it reaches here.

        Returns:
            The name of the Workflow that was entered.

        Raises:
            ValueError: If neither or both of workflow_name and file_path are provided.
        """
        if workflow_name is not None and file_path is not None:
            msg = "Provide either workflow_name or file_path, not both."
            raise ValueError(msg)
        if workflow_name is not None:
            resolved_name = workflow_name
            # Entered by key, so resolve the path NOW rather than at read time: the key is
            # only guaranteed to resolve against the workspace that is active right now.
            # Best-effort -- an unregistered or unsaved workflow simply has no path, which
            # callers already handle.
            if file_path is None:
                try:
                    registered = self.engine.workflow_registry.get_workflow_by_name(resolved_name)
                except KeyError:
                    file_path = None
                else:
                    if registered.file_path is not None:
                        file_path = self.engine.workflow_registry.get_complete_file_path(registered.file_path)
        elif file_path is not None:
            resolved = canonicalize_for_identity(file_path)
            workspace_path = canonicalize_for_identity(self.engine.config_manager.workspace_path)
            if resolved.is_relative_to(workspace_path):
                path_for_key = str(resolved.relative_to(workspace_path))
            else:
                path_for_key = str(resolved)
            resolved_name = derive_registry_key(path_for_key)
        else:
            msg = "Either workflow_name or file_path must be provided."
            raise ValueError(msg)

        return workflow.context.push_workflow(resolved_name, file_path, working_directory)

    def _current_context(self) -> WorkflowContextStack:
        """The current workflow's context stack, or an empty one when no workflow is open.

        Asking about a context must not open a workflow, so with none open this answers as an empty
        stack does: nothing is entered, and leaving or reading a context raises its usual error.
        """
        workflow = self.engine.current_workflow_or_none()
        if workflow is None:
            return WorkflowContextStack()
        return workflow.context
