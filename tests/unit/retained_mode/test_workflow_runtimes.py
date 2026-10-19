"""Several workflows open at once: each keeps its own graph, and requests act on the one they name."""

from __future__ import annotations

import asyncio
import contextvars
import threading
from dataclasses import dataclass
from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest

from griptape_nodes.retained_mode.events import converters
from griptape_nodes.retained_mode.events.app_events import EngineHeartbeatRequest, EngineHeartbeatResultSuccess
from griptape_nodes.retained_mode.events.base_events import (
    AppEvent,
    EventResultFailure,
    EventResultSuccess,
    ExecutionEvent,
    ExecutionGriptapeNodeEvent,
    GriptapeNodeEvent,
    RequestPayload,
    ResultPayload,
    ResultPayloadSuccess,
)
from griptape_nodes.retained_mode.events.context_events import SetWorkflowContextRequest
from griptape_nodes.retained_mode.events.execution_events import ParameterValueUpdateEvent
from griptape_nodes.retained_mode.events.flow_events import (
    CreateFlowRequest,
    ListNodesInFlowRequest,
    ListNodesInFlowResultSuccess,
)
from griptape_nodes.retained_mode.events.node_events import CreateNodeRequest, CreateNodeResultSuccess
from griptape_nodes.retained_mode.events.object_events import ClearAllObjectStateRequest
from griptape_nodes.retained_mode.events.open_workflow_events import (
    CloseWorkflowRequest,
    CloseWorkflowResultSuccess,
    ListOpenWorkflowsRequest,
    ListOpenWorkflowsResultSuccess,
    OpenWorkflowRequest,
    OpenWorkflowResultFailure,
    OpenWorkflowResultSuccess,
    OpenWorkflowsChanged,
)
from griptape_nodes.retained_mode.events.os_events import GetFileInfoRequest
from griptape_nodes.retained_mode.events.variable_events import (
    CreateVariableRequest,
    CreateVariableResultSuccess,
    GetVariableValueRequest,
    GetVariableValueResultFailure,
    GetVariableValueResultSuccess,
)
from griptape_nodes.retained_mode.events.workflow_events import (
    GetWorkflowMetadataRequest,
    GetWorkflowMetadataResultSuccess,
    SetWorkflowMetadataRequest,
)
from griptape_nodes.retained_mode.managers.flow_manager import FlowManager
from griptape_nodes.retained_mode.managers.workflow_manager import WorkflowManager
from griptape_nodes.retained_mode.request_handlers import RequestScope
from griptape_nodes.retained_mode.run_scheduler import RunRefusedError, current_run
from griptape_nodes.retained_mode.variable_types import VariableScope
from griptape_nodes.retained_mode.workflow_runtime import NO_WORKFLOW, WorkflowNotNamedError, bound_workflow

if TYPE_CHECKING:
    from contextlib import AbstractContextManager
    from pathlib import Path

    from griptape_nodes.retained_mode.engine import Engine
    from griptape_nodes.retained_mode.workflow_runtime import WorkflowRuntime


def _open_new_workflow_with_note(engine: Engine, note_name: str) -> OpenWorkflowResultSuccess:
    """Open a new workflow and put one node in its flow."""
    opened = engine.handle_request(OpenWorkflowRequest(display_name=note_name))
    assert isinstance(opened, OpenWorkflowResultSuccess), opened
    node = engine.handle_request(
        CreateNodeRequest(node_type="Note", node_name=note_name), workflow_id=opened.workflow_id
    )
    assert isinstance(node, CreateNodeResultSuccess), node
    return opened


def _node_names(engine: Engine, workflow_id: str | None) -> set[str]:
    """The nodes in the current flow of a workflow."""
    result = engine.handle_request(ListNodesInFlowRequest(), workflow_id=workflow_id)
    assert isinstance(result, ListNodesInFlowResultSuccess), result
    return set(result.node_names)


def _listed(engine: Engine) -> ListOpenWorkflowsResultSuccess:
    result = engine.handle_request(ListOpenWorkflowsRequest())
    assert isinstance(result, ListOpenWorkflowsResultSuccess), result
    return result


def _runtime(engine: Engine, workflow_id: str) -> WorkflowRuntime:
    runtime = engine.find_workflow_runtime(workflow_id)
    assert runtime is not None
    return runtime


def _running_only(engine: Engine, running: WorkflowRuntime | None) -> AbstractContextManager[object]:
    """Stand in for each workflow's own execution state, reporting only `running` as running."""
    return patch.object(
        FlowManager, "check_for_existing_running_flow", lambda _flow_manager: engine.current_workflow is running
    )


def _queued_events(engine: Engine) -> asyncio.Queue:
    queue: asyncio.Queue = asyncio.Queue()
    engine.event_manager.initialize_queue(queue)
    return queue


def _drain(queue: asyncio.Queue) -> list[object]:
    events = []
    while not queue.empty():
        events.append(queue.get_nowait())
    return events


@dataclass
class _ProbeHostRequest(RequestPayload):
    """A host request whose handler records the workflow binding it ran under."""


@dataclass
class _ProbeResult(ResultPayloadSuccess):
    pass


def _probe_binding(engine: Engine) -> list[object]:
    """Handle _ProbeHostRequest by recording `bound_workflow` as the handler sees it."""
    seen: list[object] = []

    def handle(_request: _ProbeHostRequest) -> ResultPayload:
        seen.append(bound_workflow.get())
        return _ProbeResult(result_details="probed")

    engine.event_manager.assign_manager_to_request_type(_ProbeHostRequest, handle, scope=RequestScope.HOST)
    return seen


class TestOpenWorkflow:
    def test_opening_another_keeps_the_first(self, engine: Engine) -> None:
        a = _open_new_workflow_with_note(engine, "NoteA")
        b = _open_new_workflow_with_note(engine, "NoteB")

        assert _node_names(engine, a.workflow_id) == {"NoteA"}
        assert _node_names(engine, b.workflow_id) == {"NoteB"}
        assert [w.workflow_id for w in _listed(engine).workflows] == [a.workflow_id, b.workflow_id]

    def test_opening_an_open_workflow_returns_its_id(self, engine: Engine) -> None:
        a = _open_new_workflow_with_note(engine, "NoteA")
        b = _open_new_workflow_with_note(engine, "NoteB")

        result = engine.handle_request(OpenWorkflowRequest(workflow_name=a.workflow_name))

        assert isinstance(result, OpenWorkflowResultSuccess), result
        assert result.already_open is True
        assert result.workflow_id == a.workflow_id
        assert [w.workflow_id for w in _listed(engine).workflows] == [a.workflow_id, b.workflow_id]

    def test_a_workflow_not_in_the_registry_fails_and_changes_nothing(self, engine: Engine) -> None:
        a = _open_new_workflow_with_note(engine, "NoteA")

        result = engine.handle_request(OpenWorkflowRequest(workflow_name="no_such_workflow"))

        assert isinstance(result, OpenWorkflowResultFailure), result
        assert [w.workflow_id for w in _listed(engine).workflows] == [a.workflow_id]

    def test_the_same_node_name_in_two_workflows(self, engine: Engine) -> None:
        a = _open_new_workflow_with_note(engine, "Note")
        b = _open_new_workflow_with_note(engine, "Note")

        with engine.bind_workflow(_runtime(engine, a.workflow_id)):
            note_a = engine.node_manager.get_node_by_name("Note")
        with engine.bind_workflow(_runtime(engine, b.workflow_id)):
            note_b = engine.node_manager.get_node_by_name("Note")

        assert note_a is not note_b
        assert note_a.workflow_id == a.workflow_id
        assert note_b.workflow_id == b.workflow_id

    def test_setting_a_workflow_context_announces_the_change(self, engine: Engine) -> None:
        queue = _queued_events(engine)

        context = engine.handle_request(SetWorkflowContextRequest(display_name="Single"))

        assert context.succeeded(), context
        assert any(
            isinstance(event, AppEvent) and isinstance(event.payload, OpenWorkflowsChanged) for event in _drain(queue)
        )

    def test_renaming_an_open_workflow_shows_in_the_open_list(self, engine: Engine) -> None:
        a = _open_new_workflow_with_note(engine, "NoteA")
        queue = _queued_events(engine)

        result = engine.handle_request(
            SetWorkflowMetadataRequest(workflow_name=a.workflow_name, workflow_metadata={"name": "Renamed"})  # type: ignore[arg-type]
        )

        assert result.succeeded(), result
        assert [w.display_name for w in _listed(engine).workflows] == ["Renamed"]
        assert any(
            isinstance(event, AppEvent) and isinstance(event.payload, OpenWorkflowsChanged) for event in _drain(queue)
        )

    def test_metadata_of_an_unregistered_open_workflow_reads_its_file_while_several_are_open(
        self, engine: Engine, tmp_path: Path
    ) -> None:
        _open_new_workflow_with_note(engine, "NoteA")
        workflow_file = tmp_path / "outside_workspace.py"
        workflow_file.write_text(
            "\n".join(
                [
                    f"# /// {WorkflowManager.WORKFLOW_METADATA_HEADER}",
                    "# [tool.griptape-nodes]",
                    '# name = "Outside Workspace"',
                    '# schema_version = "0.21.0"',
                    '# engine_version_created_with = "0.0.0"',
                    "# node_libraries_referenced = []",
                    "# ///",
                    "",
                ]
            ),
            encoding="utf-8",
        )
        with engine.bind_workflow(engine.open_workflow_runtime()):
            workflow_name = engine.context_manager.push_workflow(file_path=str(workflow_file))

        result = engine.handle_request(GetWorkflowMetadataRequest(workflow_name=workflow_name))

        assert isinstance(result, GetWorkflowMetadataResultSuccess), result
        assert result.workflow_metadata.name == "Outside Workspace"


@dataclass
class _ProbeWorkflowRequest(RequestPayload):
    """A request whose handler records the workflow dispatch passed it."""


def _probe_workflow_argument(engine: Engine, *, optional: bool) -> list[WorkflowRuntime | None]:
    """Handle _ProbeWorkflowRequest by recording its `workflow` argument."""
    seen: list[WorkflowRuntime | None] = []

    def handle_required(_request: _ProbeWorkflowRequest, workflow: WorkflowRuntime) -> ResultPayload:
        seen.append(workflow)
        return _ProbeResult(result_details="probed")

    def handle_optional(_request: _ProbeWorkflowRequest, workflow: WorkflowRuntime | None = None) -> ResultPayload:
        seen.append(workflow)
        return _ProbeResult(result_details="probed")

    if optional:
        engine.event_manager.assign_manager_to_request_type(
            _ProbeWorkflowRequest, handle_optional, scope=RequestScope.OPTIONAL_WORKFLOW
        )
    else:
        engine.event_manager.assign_manager_to_request_type(
            _ProbeWorkflowRequest, handle_required, scope=RequestScope.WORKFLOW
        )
    return seen


class TestWorkflowArgument:
    def test_a_handler_taking_a_workflow_is_passed_the_one_it_was_addressed_to(self, engine: Engine) -> None:
        a = _open_new_workflow_with_note(engine, "NoteA")
        _open_new_workflow_with_note(engine, "NoteB")
        seen = _probe_workflow_argument(engine, optional=False)

        engine.handle_request(_ProbeWorkflowRequest(), workflow_id=a.workflow_id)

        assert seen == [_runtime(engine, a.workflow_id)]

    @pytest.mark.asyncio
    async def test_the_async_path_passes_the_workflow_too(self, engine: Engine) -> None:
        a = _open_new_workflow_with_note(engine, "NoteA")
        _open_new_workflow_with_note(engine, "NoteB")
        seen = _probe_workflow_argument(engine, optional=False)

        await engine.ahandle_request(_ProbeWorkflowRequest(), workflow_id=a.workflow_id)

        assert seen == [_runtime(engine, a.workflow_id)]

    def test_an_optional_handler_is_passed_none_when_none_is_named_and_several_are_open(self, engine: Engine) -> None:
        _open_new_workflow_with_note(engine, "NoteA")
        _open_new_workflow_with_note(engine, "NoteB")
        seen = _probe_workflow_argument(engine, optional=True)

        engine.handle_request(_ProbeWorkflowRequest())

        assert seen == [None]

    def test_variables_belong_to_their_workflow(self, engine: Engine) -> None:
        a = _open_new_workflow_with_note(engine, "NoteA")
        b = _open_new_workflow_with_note(engine, "NoteB")

        created = engine.handle_request(
            CreateVariableRequest(name="seed", type="str", value="from-a", is_global=True), workflow_id=a.workflow_id
        )
        in_a = engine.handle_request(
            GetVariableValueRequest(name="seed", lookup_scope=VariableScope.GLOBAL_ONLY), workflow_id=a.workflow_id
        )
        in_b = engine.handle_request(
            GetVariableValueRequest(name="seed", lookup_scope=VariableScope.GLOBAL_ONLY), workflow_id=b.workflow_id
        )

        assert isinstance(created, CreateVariableResultSuccess), created
        assert isinstance(in_a, GetVariableValueResultSuccess), in_a
        assert in_a.value == "from-a"
        assert isinstance(in_b, GetVariableValueResultFailure), in_b


class TestRequestTargeting:
    def test_a_request_acts_on_the_workflow_it_names(self, engine: Engine) -> None:
        a = _open_new_workflow_with_note(engine, "NoteA")
        b = _open_new_workflow_with_note(engine, "NoteB")

        created = engine.handle_request(
            CreateNodeRequest(node_type="Note", node_name="Added"), workflow_id=a.workflow_id
        )

        assert isinstance(created, CreateNodeResultSuccess), created
        assert _node_names(engine, a.workflow_id) == {"NoteA", "Added"}
        assert _node_names(engine, b.workflow_id) == {"NoteB"}

    def test_a_workflow_request_naming_none_fails_while_several_are_open(self, engine: Engine) -> None:
        a = _open_new_workflow_with_note(engine, "NoteA")
        b = _open_new_workflow_with_note(engine, "NoteB")

        result = engine.handle_request(CreateNodeRequest(node_type="Note", node_name="Stray"))

        assert result.failed()
        assert isinstance(getattr(result, "exception", None), WorkflowNotNamedError)
        assert _node_names(engine, a.workflow_id) == {"NoteA"}
        assert _node_names(engine, b.workflow_id) == {"NoteB"}

    def test_a_workflow_request_naming_none_fails_while_another_workflow_runs(self, engine: Engine) -> None:
        a = _open_new_workflow_with_note(engine, "NoteA")
        b = _open_new_workflow_with_note(engine, "NoteB")
        runtime_b = _runtime(engine, b.workflow_id)

        with _running_only(engine, runtime_b):
            engine.run_scheduler.admit(runtime_b)
            result = engine.handle_request(CreateNodeRequest(node_type="Note", node_name="Stray"))

        assert result.failed()
        assert isinstance(getattr(result, "exception", None), WorkflowNotNamedError)
        assert _node_names(engine, a.workflow_id) == {"NoteA"}
        assert _node_names(engine, b.workflow_id) == {"NoteB"}

    def test_a_host_request_from_a_client_acts_on_no_workflow(self, engine: Engine) -> None:
        _open_new_workflow_with_note(engine, "NoteA")
        seen = _probe_binding(engine)

        engine.handle_request(_ProbeHostRequest())

        assert seen == [NO_WORKFLOW]

    def test_a_host_request_ignores_the_workflow_it_is_addressed_to(self, engine: Engine) -> None:
        _open_new_workflow_with_note(engine, "NoteA")
        seen = _probe_binding(engine)

        result = engine.handle_request(_ProbeHostRequest(), workflow_id="no-longer-open")

        assert result.succeeded()
        assert seen == [NO_WORKFLOW]

    def test_a_host_request_issued_within_a_workflow_keeps_it(self, engine: Engine) -> None:
        a = _open_new_workflow_with_note(engine, "NoteA")
        runtime_a = _runtime(engine, a.workflow_id)
        seen = _probe_binding(engine)

        with engine.bind_workflow(runtime_a):
            engine.handle_request(_ProbeHostRequest())

        assert seen == [runtime_a]

    def test_a_workflow_request_naming_none_acts_on_the_only_open_workflow(self, engine: Engine) -> None:
        a = _open_new_workflow_with_note(engine, "NoteA")

        created = engine.handle_request(CreateNodeRequest(node_type="Note", node_name="Added"))

        assert isinstance(created, CreateNodeResultSuccess), created
        assert _node_names(engine, a.workflow_id) == {"NoteA", "Added"}

    def test_a_workflow_request_with_none_open_opens_one(self, engine: Engine) -> None:
        context = engine.handle_request(SetWorkflowContextRequest(display_name="Single"))
        created = engine.handle_request(CreateFlowRequest(parent_flow_name=None))

        assert context.succeeded(), context
        assert created.succeeded(), created
        assert len(engine.workflow_runtimes) == 1

    def test_a_host_request_needs_no_workflow(self, engine: Engine) -> None:
        a = _open_new_workflow_with_note(engine, "NoteA")
        b = _open_new_workflow_with_note(engine, "NoteB")

        assert [w.workflow_id for w in _listed(engine).workflows] == [a.workflow_id, b.workflow_id]

    def test_an_optional_workflow_request_runs_with_no_workflow_when_none_is_named(self, engine: Engine) -> None:
        _open_new_workflow_with_note(engine, "NoteA")
        _open_new_workflow_with_note(engine, "NoteB")

        result = engine.handle_request(GetFileInfoRequest(path="no_such_file.txt"))

        assert not isinstance(getattr(result, "exception", None), WorkflowNotNamedError), result

    def test_a_request_naming_a_closed_workflow_fails(self, engine: Engine) -> None:
        a = _open_new_workflow_with_note(engine, "NoteA")
        b = _open_new_workflow_with_note(engine, "NoteB")
        engine.handle_request(CloseWorkflowRequest(), workflow_id=a.workflow_id)

        result = engine.handle_request(CreateNodeRequest(node_type="Note"), workflow_id=a.workflow_id)

        assert result.failed()
        assert _node_names(engine, b.workflow_id) == {"NoteB"}

    def test_a_workflow_result_names_its_workflow_and_a_host_result_names_none(self, engine: Engine) -> None:
        a = _open_new_workflow_with_note(engine, "NoteA")
        _open_new_workflow_with_note(engine, "NoteB")
        queue = _queued_events(engine)

        engine.handle_request(ListNodesInFlowRequest(), workflow_id=a.workflow_id)
        engine.handle_request(ListOpenWorkflowsRequest())

        results = [e.wrapped_event for e in _drain(queue) if isinstance(e, GriptapeNodeEvent)]
        workflow_result, host_result = results[-2], results[-1]
        assert isinstance(workflow_result, EventResultSuccess)
        assert (workflow_result.scope, workflow_result.workflow_id) == ("workflow", a.workflow_id)
        assert (host_result.scope, host_result.workflow_id) == ("host", None)

    def test_a_failure_for_a_closed_workflow_names_that_workflow(self, engine: Engine) -> None:
        a = _open_new_workflow_with_note(engine, "NoteA")
        _open_new_workflow_with_note(engine, "NoteB")
        engine.handle_request(CloseWorkflowRequest(), workflow_id=a.workflow_id)
        queue = _queued_events(engine)

        engine.handle_request(ListNodesInFlowRequest(), workflow_id=a.workflow_id)

        failure = next(
            e.wrapped_event
            for e in _drain(queue)
            if isinstance(e, GriptapeNodeEvent) and isinstance(e.wrapped_event, EventResultFailure)
        )
        assert (failure.scope, failure.workflow_id) == ("workflow", a.workflow_id)

    @pytest.mark.asyncio
    async def test_a_task_keeps_the_workflow_its_request_acted_on(self, engine: Engine) -> None:
        a = _open_new_workflow_with_note(engine, "NoteA")
        _open_new_workflow_with_note(engine, "NoteB")
        started = asyncio.Event()

        async def read_later() -> set[str]:
            await started.wait()
            return {node.name for node in engine.context_manager.get_current_flow().nodes.values()}

        with engine.bind_workflow(_runtime(engine, a.workflow_id)):
            task = asyncio.create_task(read_later())
        started.set()

        assert await task == {"NoteA"}

    @pytest.mark.asyncio
    async def test_a_post_dispatch_hook_acts_on_the_workflow_of_its_request(self, engine: Engine) -> None:
        a = _open_new_workflow_with_note(engine, "NoteA")
        _open_new_workflow_with_note(engine, "NoteB")
        seen: list[str] = []
        done = asyncio.Event()

        def hook(_request: object, _result: object) -> None:
            seen.append(engine.current_workflow.workflow_id)
            done.set()

        engine.event_manager.initialize_queue(asyncio.Queue())
        engine.event_manager.add_post_dispatch_hook(ListNodesInFlowRequest, hook)
        await engine.ahandle_request(ListNodesInFlowRequest(), workflow_id=a.workflow_id)
        await asyncio.wait_for(done.wait(), timeout=5)

        assert seen == [a.workflow_id]


class TestRunEvents:
    def test_an_event_emitted_while_handling_a_request_names_its_workflow(self, engine: Engine) -> None:
        a = _open_new_workflow_with_note(engine, "NoteA")
        _open_new_workflow_with_note(engine, "NoteB")
        _queued_events(engine)
        event = ExecutionGriptapeNodeEvent(
            wrapped_event=ExecutionEvent(
                payload=ParameterValueUpdateEvent(node_name="NoteA", parameter_name="p", data_type="str", value="v")
            )
        )

        with engine.bind_workflow(_runtime(engine, a.workflow_id)):
            engine.event_manager.put_event(event)

        assert (event.wrapped_event.scope, event.wrapped_event.workflow_id) == ("workflow", a.workflow_id)

    def test_an_event_from_an_unbound_thread_is_a_host_event(self, engine: Engine) -> None:
        _open_new_workflow_with_note(engine, "NoteA")
        _open_new_workflow_with_note(engine, "NoteB")
        _queued_events(engine)
        event = ExecutionGriptapeNodeEvent(
            wrapped_event=ExecutionEvent(
                payload=ParameterValueUpdateEvent(node_name="NoteA", parameter_name="p", data_type="str", value="v")
            )
        )

        thread = threading.Thread(target=engine.event_manager.put_event, args=(event,))
        thread.start()
        thread.join()

        assert (event.wrapped_event.scope, event.wrapped_event.workflow_id) == ("host", None)

    def test_a_node_names_its_workflow_from_an_unbound_thread(self, engine: Engine) -> None:
        a = _open_new_workflow_with_note(engine, "NoteA")
        _open_new_workflow_with_note(engine, "NoteB")
        with engine.bind_workflow(_runtime(engine, a.workflow_id)):
            node = engine.node_manager.get_node_by_name("NoteA")
        events: list[ExecutionGriptapeNodeEvent] = []

        def emit() -> None:
            events.append(
                node.execution_event(
                    ParameterValueUpdateEvent(node_name="NoteA", parameter_name="p", data_type="str", value="v")
                )
            )

        thread = threading.Thread(target=emit)
        thread.start()
        thread.join()

        assert events[0].wrapped_event.workflow_id == a.workflow_id

    def test_app_events_are_host_events(self, engine: Engine) -> None:
        a = _open_new_workflow_with_note(engine, "NoteA")
        queue = _queued_events(engine)

        with engine.bind_workflow(_runtime(engine, a.workflow_id)):
            engine.open_workflows_manager.announce_change()

        app_event = next(e for e in _drain(queue) if isinstance(e, AppEvent))
        assert (app_event.scope, app_event.workflow_id) == ("host", None)


class TestCloseWorkflow:
    def test_closing_one_keeps_the_others(self, engine: Engine) -> None:
        a = _open_new_workflow_with_note(engine, "NoteA")
        b = _open_new_workflow_with_note(engine, "NoteB")

        result = engine.handle_request(CloseWorkflowRequest(), workflow_id=a.workflow_id)

        assert isinstance(result, CloseWorkflowResultSuccess), result
        assert [w.workflow_id for w in _listed(engine).workflows] == [b.workflow_id]
        assert _node_names(engine, b.workflow_id) == {"NoteB"}

    def test_closing_the_last_workflow_leaves_none_open(self, engine: Engine) -> None:
        a = _open_new_workflow_with_note(engine, "NoteA")

        engine.handle_request(CloseWorkflowRequest(), workflow_id=a.workflow_id)

        assert _listed(engine).workflows == []
        assert engine.workflow_runtimes == []

    def test_clear_all_closes_every_workflow(self, engine: Engine) -> None:
        _open_new_workflow_with_note(engine, "NoteA")
        _open_new_workflow_with_note(engine, "NoteB")

        engine.handle_request(ClearAllObjectStateRequest(i_know_what_im_doing=True))

        assert _listed(engine).workflows == []
        assert engine.workflow_runtimes == []


class TestRunScheduler:
    def test_a_second_workflow_cannot_start_while_one_runs(self, engine: Engine) -> None:
        a = _open_new_workflow_with_note(engine, "NoteA")
        b = _open_new_workflow_with_note(engine, "NoteB")
        runtime_a = _runtime(engine, a.workflow_id)
        runtime_b = _runtime(engine, b.workflow_id)

        with _running_only(engine, runtime_a):
            engine.run_scheduler.admit(runtime_a)
            listed = _listed(engine)
            with pytest.raises(RunRefusedError, match="is running"):
                engine.run_scheduler.admit(runtime_b)

        assert {w.workflow_id: w.is_running for w in listed.workflows} == {
            a.workflow_id: True,
            b.workflow_id: False,
        }

    def test_advancing_a_running_workflow_joins_its_run(self, engine: Engine) -> None:
        a = _open_new_workflow_with_note(engine, "NoteA")
        runtime_a = _runtime(engine, a.workflow_id)

        with _running_only(engine, runtime_a):
            first = engine.run_scheduler.admit(runtime_a)
            again = engine.run_scheduler.admit(runtime_a)

        assert again == first

    def test_each_run_gets_its_own_id(self, engine: Engine) -> None:
        a = _open_new_workflow_with_note(engine, "NoteA")
        runtime_a = _runtime(engine, a.workflow_id)

        first = engine.run_scheduler.admit(runtime_a)
        second = engine.run_scheduler.admit(runtime_a)

        assert first.run_id != second.run_id

    def test_closing_the_running_workflow_lets_another_run(self, engine: Engine) -> None:
        a = _open_new_workflow_with_note(engine, "NoteA")
        b = _open_new_workflow_with_note(engine, "NoteB")
        runtime_a = _runtime(engine, a.workflow_id)

        with _running_only(engine, runtime_a):
            engine.run_scheduler.admit(runtime_a)
            engine.remove_workflow_runtime(runtime_a)
            run = engine.run_scheduler.admit(_runtime(engine, b.workflow_id))

        assert run.workflow_id == b.workflow_id

    @pytest.mark.asyncio
    async def test_a_run_names_itself_on_the_events_it_emits(self, engine: Engine) -> None:
        a = _open_new_workflow_with_note(engine, "NoteA")
        runtime_a = _runtime(engine, a.workflow_id)
        _queued_events(engine)
        event = ExecutionGriptapeNodeEvent(
            wrapped_event=ExecutionEvent(
                payload=ParameterValueUpdateEvent(node_name="NoteA", parameter_name="p", data_type="str", value="v")
            )
        )
        run = engine.run_scheduler.admit(runtime_a)

        token = current_run.set(run)
        try:
            with engine.bind_workflow(runtime_a):
                engine.event_manager.put_event(event)
        finally:
            current_run.reset(token)

        assert event.wrapped_event.run_id == run.run_id


class TestUnboundReads:
    def test_an_unbound_read_while_several_are_open_fails(self, engine: Engine) -> None:
        _open_new_workflow_with_note(engine, "NoteA")
        _open_new_workflow_with_note(engine, "NoteB")
        errors: list[BaseException] = []

        def read() -> None:
            try:
                _ = engine.current_workflow
            except WorkflowNotNamedError as e:
                errors.append(e)

        thread = threading.Thread(target=read)
        thread.start()
        thread.join()

        assert len(errors) == 1

    def test_an_unbound_read_during_a_run_gets_the_running_workflow(self, engine: Engine) -> None:
        a = _open_new_workflow_with_note(engine, "NoteA")
        _open_new_workflow_with_note(engine, "NoteB")
        runtime_a = _runtime(engine, a.workflow_id)
        seen: list[str] = []

        def read() -> None:
            seen.append(engine.current_workflow.workflow_id)

        with _running_only(engine, runtime_a):
            engine.run_scheduler.admit(runtime_a)
            thread = threading.Thread(target=read)
            thread.start()
            thread.join()

        assert seen == [a.workflow_id]

    def test_a_thread_started_with_a_copied_context_keeps_its_workflow(self, engine: Engine) -> None:
        a = _open_new_workflow_with_note(engine, "NoteA")
        _open_new_workflow_with_note(engine, "NoteB")
        seen: list[str] = []

        def read() -> None:
            seen.append(engine.current_workflow.workflow_id)

        with engine.bind_workflow(_runtime(engine, a.workflow_id)):
            context = contextvars.copy_context()
        thread = threading.Thread(target=context.run, args=(read,))
        thread.start()
        thread.join()

        assert seen == [a.workflow_id]


class TestRebuildInPlace:
    @pytest.mark.asyncio
    async def test_a_rebuild_keeps_each_workflow_its_id_and_graph(self, engine: Engine) -> None:
        a = _open_new_workflow_with_note(engine, "NoteA")
        b = _open_new_workflow_with_note(engine, "NoteB")
        open_workflows = engine.open_workflows_manager

        suspended = await open_workflows.suspend_open_workflows()
        failures = await open_workflows.resume_open_workflows(suspended)

        assert failures == []
        assert [w.workflow_id for w in _listed(engine).workflows] == [a.workflow_id, b.workflow_id]
        assert [w.workflow_name for w in _listed(engine).workflows] == [a.workflow_name, b.workflow_name]
        assert _node_names(engine, a.workflow_id) == {"NoteA"}
        assert _node_names(engine, b.workflow_id) == {"NoteB"}


class TestHeartbeat:
    def test_it_reports_every_open_workflow_and_whether_any_runs(self, engine: Engine) -> None:
        a = _open_new_workflow_with_note(engine, "NoteA")
        b = _open_new_workflow_with_note(engine, "NoteB")
        runtime_b = _runtime(engine, b.workflow_id)

        with _running_only(engine, runtime_b):
            result = engine.handle_request(EngineHeartbeatRequest(heartbeat_id="h"))

        assert isinstance(result, EngineHeartbeatResultSuccess), result
        assert [(w.workflow_id, w.is_running) for w in result.open_workflows] == [
            (a.workflow_id, False),
            (b.workflow_id, True),
        ]
        assert result.is_executing is True
        assert result.current_workflow == b.workflow_name

    def test_several_idle_workflows_name_no_current_one(self, engine: Engine) -> None:
        _open_new_workflow_with_note(engine, "NoteA")
        _open_new_workflow_with_note(engine, "NoteB")

        result = engine.handle_request(EngineHeartbeatRequest(heartbeat_id="h"))

        assert isinstance(result, EngineHeartbeatResultSuccess), result
        assert result.is_executing is False
        assert result.current_workflow is None


class TestResultWireFormat:
    def test_the_echoed_request_names_the_workflow_it_acted_on(self, engine: Engine) -> None:
        a = _open_new_workflow_with_note(engine, "NoteA")
        queue = _queued_events(engine)
        request = ListNodesInFlowRequest()

        engine.handle_request(request)

        result = next(e.wrapped_event for e in _drain(queue) if isinstance(e, GriptapeNodeEvent))
        wire = converters.engine.unstructure(result)
        assert wire["workflow_id"] == a.workflow_id
        assert wire["request"]["workflow_id"] == a.workflow_id

    def test_a_host_requests_echo_names_no_workflow(self, engine: Engine) -> None:
        _open_new_workflow_with_note(engine, "NoteA")
        queue = _queued_events(engine)

        engine.handle_request(ListOpenWorkflowsRequest())

        result = next(e.wrapped_event for e in _drain(queue) if isinstance(e, GriptapeNodeEvent))
        wire = converters.engine.unstructure(result)
        assert wire["scope"] == "host"
        assert "workflow_id" not in wire["request"]
