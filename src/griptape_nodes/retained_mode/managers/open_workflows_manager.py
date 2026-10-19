"""Opening, listing, closing, and rebuilding the workflows an engine holds at once.

The engine owns the runtimes (see `retained_mode/workflow_runtime.py`); this manager decides what goes
in them. Opening a workflow builds it in a fresh runtime with the same requests a single-workflow
engine uses, bound to that runtime, so nothing that builds a workflow needs to know others are open.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, ClassVar

from griptape_nodes.retained_mode.engine import EngineScoped
from griptape_nodes.retained_mode.events.base_events import AppEvent
from griptape_nodes.retained_mode.events.context_events import SetWorkflowContextRequest, SetWorkflowContextSuccess
from griptape_nodes.retained_mode.events.flow_events import (
    CreateFlowRequest,
    DeserializeFlowFromCommandsRequest,
    GetTopLevelFlowRequest,
    GetTopLevelFlowResultSuccess,
    SerializedFlowCommands,
    SerializeFlowToCommandsRequest,
    SerializeFlowToCommandsResultSuccess,
)
from griptape_nodes.retained_mode.events.open_workflow_events import (
    CloseWorkflowRequest,
    CloseWorkflowResultFailure,
    CloseWorkflowResultSuccess,
    ListOpenWorkflowsRequest,
    ListOpenWorkflowsResultSuccess,
    OpenWorkflow,
    OpenWorkflowRequest,
    OpenWorkflowResultFailure,
    OpenWorkflowResultSuccess,
    OpenWorkflowsChanged,
)
from griptape_nodes.retained_mode.events.workflow_events import RunWorkflowFromRegistryRequest
from griptape_nodes.retained_mode.request_handlers import RequestScope, handles
from griptape_nodes.utils.keyed_mutex import KeyedMutex

if TYPE_CHECKING:
    from griptape_nodes.retained_mode.engine import Engine
    from griptape_nodes.retained_mode.events.base_events import ResultPayload
    from griptape_nodes.retained_mode.managers.event_manager import EventManager
    from griptape_nodes.retained_mode.runtime.workflow_runtime import WorkflowRuntime

logger = logging.getLogger("griptape_nodes")


_OPEN_WORKFLOWS_KEY = "open-workflows"


@dataclass
class SuspendedWorkflow:
    """What it takes to rebuild an open workflow in its own runtime after its objects were cleared.

    Args:
        runtime: The runtime it stays open in, so its id survives the rebuild.
        workflow_name: Its registry key.
        working_directory: The folder an unsaved workflow belongs to, if it was given one.
        commands: Its graph as it was in memory, unsaved edits included, or None when it could not be
            serialized. A saved workflow is then rebuilt from its file instead.
    """

    runtime: WorkflowRuntime
    workflow_name: str
    working_directory: str | None
    commands: SerializedFlowCommands | None


@dataclass
class WorkflowRebuildFailure:
    """An open workflow that could not be rebuilt. It stays open, with whatever could be built."""

    workflow_name: str
    details: str


class OpenWorkflowsManager(EngineScoped):
    request_scope: ClassVar[RequestScope] = RequestScope.HOST

    def __init__(self, event_manager: EventManager, *, engine: Engine | None = None) -> None:
        super().__init__(engine)
        # Opening awaits while it builds, so two opens of one workflow could each find it closed and
        # open it twice. Open and close one at a time. A KeyedMutex rather than an asyncio.Lock
        # because requests reach these handlers on more than one event loop.
        self._mutex = KeyedMutex()
        event_manager.register_request_handlers(self)

    @handles(OpenWorkflowRequest)
    async def on_open_workflow_request(self, request: OpenWorkflowRequest) -> ResultPayload:
        async with self._mutex.locked(_OPEN_WORKFLOWS_KEY):
            return await self._open_workflow(request)

    @handles(CloseWorkflowRequest)
    async def on_close_workflow_request(
        self,
        request: CloseWorkflowRequest,  # noqa: ARG002
        workflow: WorkflowRuntime,
    ) -> ResultPayload:
        async with self._mutex.locked(_OPEN_WORKFLOWS_KEY):
            workflow_name = self.workflow_name_in(workflow) or "the workflow"
            failure = await self.close_workflow_runtime(workflow)
        if failure is not None:
            details = f"Attempted to close workflow '{workflow_name}'. Failed due to: {failure}"
            return CloseWorkflowResultFailure(result_details=details)
        return CloseWorkflowResultSuccess(result_details=f"Closed workflow '{workflow_name}'.")

    @handles(ListOpenWorkflowsRequest)
    def on_list_open_workflows_request(self, request: ListOpenWorkflowsRequest) -> ResultPayload:  # noqa: ARG002
        workflows = self.list_open_workflows()
        return ListOpenWorkflowsResultSuccess(workflows=workflows, result_details=f"{len(workflows)} workflow(s) open.")

    def list_open_workflows(self) -> list[OpenWorkflow]:
        """The open workflows, in the order they were opened."""
        workflows = []
        for runtime in self.engine.workflow_runtimes:
            name = self.workflow_name_in(runtime)
            if name is None:
                continue
            workflows.append(
                OpenWorkflow(
                    workflow_id=runtime.workflow_id,
                    workflow_name=name,
                    display_name=self._display_name_of(name),
                    is_running=self.engine.is_workflow_running(runtime),
                )
            )
        return workflows

    async def close_workflow_runtime(self, runtime: WorkflowRuntime) -> str | None:
        """Clear a runtime's objects and forget it. Returns why it failed, or None."""
        engine = self.engine
        failure = await engine.object_manager.clear_workflow(runtime)
        if failure is not None:
            return failure
        engine.remove_workflow_runtime(runtime)
        self.announce_change()
        return None

    def announce_change(self) -> None:
        """Tell clients the set of open workflows changed."""
        self.engine.event_manager.put_event(AppEvent(payload=OpenWorkflowsChanged()))

    async def suspend_open_workflows(self) -> list[SuspendedWorkflow]:
        """Record each open workflow as it is, then clear its objects, keeping its runtime and id.

        For a library reload: every open workflow holds nodes built from the old library classes, so
        each is emptied before the libraries are unloaded and rebuilt by `resume_open_workflows` once
        they are back.

        Raises:
            RuntimeError: A workflow could not be cleared.
        """
        suspended = []
        for runtime in self.engine.workflow_runtimes:
            with self.engine.bind_workflow(runtime):
                record = await self._snapshot_current_workflow(runtime)
                failure = await self.engine.object_manager.clear_workflow(runtime, keep_variables=True)
            if failure is not None:
                msg = f"Attempted to clear workflow '{self.workflow_name_in(runtime)}' for a rebuild. Failed due to: {failure}"
                raise RuntimeError(msg)
            if record is not None:
                suspended.append(record)
        return suspended

    async def resume_open_workflows(self, suspended: list[SuspendedWorkflow]) -> list[WorkflowRebuildFailure]:
        """Rebuild each suspended workflow in its own runtime. Returns the ones that failed."""
        failures = []
        for record in suspended:
            if record.runtime not in self.engine.workflow_runtimes:
                continue
            with self.engine.bind_workflow(record.runtime), record.runtime.loading.squelch_altered():
                failure = await self._rebuild_current_workflow(record)
            if failure is not None:
                failures.append(WorkflowRebuildFailure(workflow_name=record.workflow_name, details=failure))
        self.announce_change()
        return failures

    def rekey_open_workflow(self, old_name: str, new_name: str, file_path: str) -> None:
        """Keep the workflow open from `old_name` open under `new_name`, after a rename or move.

        Its runtime and id stay as they are, so clients showing it keep showing it.
        """
        runtime = self.find_runtime_by_name(old_name)
        if runtime is None:
            return
        runtime.context.rekey_workflow(old_name, new_name, file_path)
        self.announce_change()

    def find_runtime_by_name(self, workflow_name: str) -> WorkflowRuntime | None:
        """The open runtime whose workflow has this registry key, if any."""
        for runtime in self.engine.workflow_runtimes:
            if self.workflow_name_in(runtime) == workflow_name:
                return runtime
        return None

    def workflow_name_in(self, runtime: WorkflowRuntime) -> str | None:
        """The registry key of the workflow open in `runtime`, or None when it is empty."""
        if not runtime.context.has_current_workflow():
            return None
        return runtime.context.get_current_workflow_name()

    def display_name_in(self, runtime: WorkflowRuntime) -> str | None:
        """The name users see for the workflow open in `runtime`, or None when it is empty."""
        name = self.workflow_name_in(runtime)
        if name is None:
            return None
        return self._display_name_of(name)

    async def _open_workflow(self, request: OpenWorkflowRequest) -> ResultPayload:
        engine = self.engine
        if request.workflow_name is not None:
            existing = self.find_runtime_by_name(request.workflow_name)
            if existing is not None:
                return OpenWorkflowResultSuccess(
                    workflow_id=existing.workflow_id,
                    workflow_name=request.workflow_name,
                    already_open=True,
                    result_details=f"Workflow '{request.workflow_name}' is already open.",
                )
            if not engine.workflow_registry.has_workflow_with_name(request.workflow_name):
                details = (
                    f"Attempted to open workflow '{request.workflow_name}'. "
                    "Failed because it isn't in the workflow list. It may have been deleted or moved."
                )
                return OpenWorkflowResultFailure(result_details=details)

        runtime = engine.open_workflow_runtime()
        with engine.bind_workflow(runtime):
            failure = await self._build_workflow(request)
            if failure is not None:
                await engine.object_manager.clear_workflow(runtime)
        if failure is not None:
            engine.remove_workflow_runtime(runtime)
            return OpenWorkflowResultFailure(result_details=failure)

        workflow_name = self.workflow_name_in(runtime)
        if workflow_name is None:
            engine.remove_workflow_runtime(runtime)
            details = "Attempted to open a workflow. Failed because nothing was loaded."
            return OpenWorkflowResultFailure(result_details=details)

        self.announce_change()
        return OpenWorkflowResultSuccess(
            workflow_id=runtime.workflow_id,
            workflow_name=workflow_name,
            already_open=False,
            result_details=f"Opened workflow '{workflow_name}'.",
        )

    async def _build_workflow(self, request: OpenWorkflowRequest) -> str | None:
        """Build the requested workflow in the current runtime. Returns why it failed, or None."""
        engine = self.engine
        name = request.workflow_name
        if name is not None and engine.workflow_registry.get_workflow_by_name(name).is_saved:
            return await self._build_from_file(name)

        # A new workflow, or an unsaved one whose nodes lived only in a previous engine's memory: name
        # it, and give it an empty flow to build in.
        context_result = await engine.ahandle_request(
            SetWorkflowContextRequest(
                workflow_name=name, display_name=request.display_name, working_directory=request.working_directory
            )
        )
        if not isinstance(context_result, SetWorkflowContextSuccess):
            return f"Attempted to start a new workflow. Failed due to: {context_result.result_details}"
        return await self._create_empty_flow()

    async def _build_from_file(self, workflow_name: str) -> str | None:
        result = await self.engine.ahandle_request(
            RunWorkflowFromRegistryRequest(workflow_name=workflow_name, run_with_clean_slate=False)
        )
        if result.failed():
            return f"Attempted to open workflow '{workflow_name}'. Failed due to: {result.result_details}"
        return None

    async def _create_empty_flow(self) -> str | None:
        flow_result = await self.engine.ahandle_request(
            CreateFlowRequest(parent_flow_name=None, set_as_new_context=True)
        )
        if flow_result.failed():
            return f"Attempted to start a new workflow. Failed due to: {flow_result.result_details}"
        return None

    async def _snapshot_current_workflow(self, runtime: WorkflowRuntime) -> SuspendedWorkflow | None:
        """Record the current workflow for `resume_open_workflows`, or None when the runtime is empty."""
        engine = self.engine
        if not runtime.context.has_current_workflow():
            return None
        workflow_name = runtime.context.get_current_workflow_name()
        working_directory = runtime.context.get_current_workflow_working_directory()

        commands = None
        top_level = await engine.ahandle_request(GetTopLevelFlowRequest())
        if isinstance(top_level, GetTopLevelFlowResultSuccess) and top_level.flow_name is not None:
            serialized = await engine.ahandle_request(SerializeFlowToCommandsRequest(flow_name=top_level.flow_name))
            if isinstance(serialized, SerializeFlowToCommandsResultSuccess):
                commands = serialized.serialized_flow_commands
            else:
                logger.warning(
                    "Could not record workflow '%s' as it is before rebuilding it: %s",
                    workflow_name,
                    serialized.result_details,
                )
        return SuspendedWorkflow(
            runtime=runtime, workflow_name=workflow_name, working_directory=working_directory, commands=commands
        )

    async def _rebuild_current_workflow(self, record: SuspendedWorkflow) -> str | None:
        """Rebuild a suspended workflow in the current runtime. Returns why it failed, or None."""
        engine = self.engine
        registry = engine.workflow_registry
        is_saved = registry.has_workflow_with_name(record.workflow_name) and (
            registry.get_workflow_by_name(record.workflow_name).is_saved
        )
        if record.commands is None and is_saved:
            # The file creates the variables it records.
            record.runtime.variables.clear()
            return await self._build_from_file(record.workflow_name)

        engine.context_manager.push_workflow_into(
            record.runtime, workflow_name=record.workflow_name, working_directory=record.working_directory
        )
        if record.commands is None:
            return await self._create_empty_flow()
        result = await engine.ahandle_request(
            DeserializeFlowFromCommandsRequest(serialized_flow_commands=record.commands, pop_flow_context_after=False)
        )
        if result.failed():
            return f"Attempted to rebuild workflow '{record.workflow_name}'. Failed due to: {result.result_details}"
        return None

    def _display_name_of(self, workflow_name: str) -> str:
        registry = self.engine.workflow_registry
        if not registry.has_workflow_with_name(workflow_name):
            return workflow_name
        return registry.get_workflow_by_name(workflow_name).metadata.name or workflow_name
