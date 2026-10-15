"""Opening, listing, and closing the workflows an engine holds at once.

The engine owns the runtimes (see `retained_mode/workflow_runtime.py`); this manager decides what goes
in them. Opening a workflow builds it in a fresh runtime with the same requests a single-workflow
engine uses, bound to that runtime, so nothing that builds a workflow needs to know others are open.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from griptape_nodes.retained_mode.engine import EngineScoped
from griptape_nodes.retained_mode.events.base_events import AppEvent
from griptape_nodes.retained_mode.events.context_events import SetWorkflowContextRequest, SetWorkflowContextSuccess
from griptape_nodes.retained_mode.events.flow_events import CreateFlowRequest
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
from griptape_nodes.retained_mode.request_handlers import handles
from griptape_nodes.utils.keyed_mutex import KeyedMutex

if TYPE_CHECKING:
    from griptape_nodes.retained_mode.engine import Engine
    from griptape_nodes.retained_mode.events.base_events import ResultPayload
    from griptape_nodes.retained_mode.managers.event_manager import EventManager
    from griptape_nodes.retained_mode.workflow_runtime import WorkflowRuntime

logger = logging.getLogger("griptape_nodes")


_OPEN_WORKFLOWS_KEY = "open-workflows"


class OpenWorkflowsManager(EngineScoped):
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
    async def on_close_workflow_request(self, request: CloseWorkflowRequest) -> ResultPayload:  # noqa: ARG002
        async with self._mutex.locked(_OPEN_WORKFLOWS_KEY):
            # Dispatch bound this request to the workflow it names.
            runtime = self.engine.workflow_runtime
            workflow_name = self.workflow_name_in(runtime) or "the workflow"
            failure = await self.close_workflow_runtime(runtime)
        if failure is not None:
            details = f"Attempted to close workflow '{workflow_name}'. Failed due to: {failure}"
            return CloseWorkflowResultFailure(result_details=details)
        return CloseWorkflowResultSuccess(result_details=f"Closed workflow '{workflow_name}'.")

    @handles(ListOpenWorkflowsRequest)
    def on_list_open_workflows_request(self, request: ListOpenWorkflowsRequest) -> ResultPayload:  # noqa: ARG002
        engine = self.engine
        workflows = []
        for runtime in engine.workflow_runtimes:
            name = self.workflow_name_in(runtime)
            if name is None:
                continue
            with engine.bind_workflow_runtime(runtime):
                is_running = engine.flow_manager.check_for_existing_running_flow()
            workflows.append(
                OpenWorkflow(
                    workflow_id=runtime.workflow_id,
                    workflow_name=name,
                    display_name=self._display_name_of(name),
                    is_running=is_running,
                )
            )

        active_workflow_id = None
        if self.workflow_name_in(engine.active_workflow_runtime) is not None:
            active_workflow_id = engine.active_workflow_runtime.workflow_id
        return ListOpenWorkflowsResultSuccess(
            workflows=workflows,
            active_workflow_id=active_workflow_id,
            result_details=f"{len(workflows)} workflow(s) open.",
        )

    async def close_workflow_runtime(self, runtime: WorkflowRuntime) -> str | None:
        """Clear a runtime's objects and forget it. Returns why it failed, or None."""
        engine = self.engine
        with engine.bind_workflow_runtime(runtime):
            failure = await engine.object_manager.clear_current_workflow()
        if failure is not None:
            return failure
        engine.remove_workflow_runtime(runtime)
        self.announce_change()
        return None

    def announce_change(self) -> None:
        """Tell clients the set of open workflows changed."""
        self.engine.event_manager.put_event(AppEvent(payload=OpenWorkflowsChanged()))

    def saved_open_workflow_names(self) -> list[str]:
        """Registry keys of the open workflows saved to a file, the active one last.

        What `reopen_workflows` needs to restore the open workflows after a change that closes them.
        """
        engine = self.engine
        registry = engine.workflow_registry
        names = []
        active_name = None
        for runtime in engine.workflow_runtimes:
            name = self.workflow_name_in(runtime)
            if name is None or not registry.has_workflow_with_name(name):
                continue
            if not registry.get_workflow_by_name(name).is_saved:
                continue
            if runtime is engine.active_workflow_runtime:
                active_name = name
            else:
                names.append(name)
        if active_name is not None:
            names.append(active_name)
        return names

    async def reopen_workflows(self, workflow_names: list[str]) -> None:
        """Open each workflow from its file, leaving the last one active. One that fails is logged and skipped."""
        for workflow_name in workflow_names:
            result = await self.engine.ahandle_request(OpenWorkflowRequest(workflow_name=workflow_name))
            if result.failed():
                logger.warning("Could not reopen workflow '%s': %s", workflow_name, result.result_details)

    def find_runtime_by_name(self, workflow_name: str) -> WorkflowRuntime | None:
        """The open runtime whose workflow has this registry key, if any."""
        for runtime in self.engine.workflow_runtimes:
            if self.workflow_name_in(runtime) == workflow_name:
                return runtime
        return None

    def workflow_name_in(self, runtime: WorkflowRuntime) -> str | None:
        """The registry key of the workflow open in `runtime`, or None when it is empty."""
        engine = self.engine
        with engine.bind_workflow_runtime(runtime):
            if not engine.context_manager.has_current_workflow():
                return None
            return engine.context_manager.get_current_workflow_name()

    async def _open_workflow(self, request: OpenWorkflowRequest) -> ResultPayload:
        engine = self.engine
        if request.workflow_name is not None:
            existing = self.find_runtime_by_name(request.workflow_name)
            if existing is not None:
                engine.activate_workflow_runtime(existing)
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

        previous = engine.active_workflow_runtime
        runtime = engine.create_workflow_runtime()
        with engine.bind_workflow_runtime(runtime):
            failure = await self._build_workflow(request)
            if failure is not None:
                await engine.object_manager.clear_current_workflow()
        if failure is not None:
            engine.remove_workflow_runtime(runtime)
            return OpenWorkflowResultFailure(result_details=failure)

        workflow_name = self.workflow_name_in(runtime)
        if workflow_name is None:
            engine.remove_workflow_runtime(runtime)
            details = "Attempted to open a workflow. Failed because nothing was loaded."
            return OpenWorkflowResultFailure(result_details=details)

        engine.activate_workflow_runtime(runtime)
        # An engine starts with an empty runtime for requests to act on. Once a workflow is open, it has
        # no further use.
        # It may be gone already, if clearing every workflow ran while this one was building.
        if previous in engine.workflow_runtimes and self.workflow_name_in(previous) is None:
            engine.remove_workflow_runtime(previous)
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
            result = await engine.ahandle_request(
                RunWorkflowFromRegistryRequest(workflow_name=name, run_with_clean_slate=False)
            )
            if result.failed():
                return f"Attempted to open workflow '{name}'. Failed due to: {result.result_details}"
            return None

        # A new workflow, or an unsaved one whose nodes lived only in a previous engine's memory: name
        # it, and give it an empty flow to build in.
        context_result = await engine.ahandle_request(
            SetWorkflowContextRequest(
                workflow_name=name, display_name=request.display_name, working_directory=request.working_directory
            )
        )
        if not isinstance(context_result, SetWorkflowContextSuccess):
            return f"Attempted to start a new workflow. Failed due to: {context_result.result_details}"
        flow_result = await engine.ahandle_request(CreateFlowRequest(parent_flow_name=None, set_as_new_context=True))
        if flow_result.failed():
            return f"Attempted to start a new workflow. Failed due to: {flow_result.result_details}"
        return None

    def _display_name_of(self, workflow_name: str) -> str:
        registry = self.engine.workflow_registry
        if not registry.has_workflow_with_name(workflow_name):
            return workflow_name
        return registry.get_workflow_by_name(workflow_name).metadata.name or workflow_name
