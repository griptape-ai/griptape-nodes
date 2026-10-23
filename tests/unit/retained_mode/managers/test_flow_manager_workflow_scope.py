"""FlowManager handlers act on the workflow dispatch hands them; its edge methods act on the open one."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from unittest.mock import MagicMock, patch

import pytest

from griptape_nodes.retained_mode.events.connection_events import (
    CreateConnectionRequest,
    CreateConnectionResultFailure,
    DeleteConnectionRequest,
    DeleteConnectionResultFailure,
)
from griptape_nodes.retained_mode.events.execution_events import (
    StartLocalSubflowRequest,
    StartLocalSubflowResultFailure,
)
from griptape_nodes.retained_mode.events.flow_events import (
    CreateFlowRequest,
    CreateFlowResultSuccess,
    DeleteFlowRequest,
    DeleteFlowResultSuccess,
    ExtractFlowCommandsFromImageMetadataRequest,
    GetTopLevelFlowRequest,
    GetTopLevelFlowResultSuccess,
    ListFlowsInCurrentContextRequest,
    ListFlowsInFlowRequest,
    ListNodesInFlowRequest,
    ListNodesInFlowResultFailure,
    ListNodesInFlowResultSuccess,
    SerializeFlowToCommandsRequest,
    SerializeFlowToCommandsResultSuccess,
)
from griptape_nodes.retained_mode.events.node_events import (
    CreateNodeRequest,
    CreateNodeResultSuccess,
    DeleteNodeRequest,
    SerializeNodeToCommandsRequest,
)
from griptape_nodes.retained_mode.managers.flow_manager import FlowManager
from griptape_nodes.retained_mode.request_handlers import RequestScope, handled_request_scope, handled_request_types
from griptape_nodes.retained_mode.runtime.workflow_runtime import WorkflowRuntime
from tests.workflow_context import push_unsaved_workflow

if TYPE_CHECKING:
    from griptape_nodes.retained_mode.engine import Engine

# A FlowManager request that works with no workflow open; every other one acts on a workflow.
_OPTIONAL_WORKFLOW_REQUESTS = {GetTopLevelFlowRequest, ExtractFlowCommandsFromImageMetadataRequest}


def _create_canvas(engine: Engine, **envelope: Any) -> str:
    result = engine.handle_request(CreateFlowRequest(parent_flow_name=None, flow_name="canvas"), **envelope)
    assert isinstance(result, CreateFlowResultSuccess)
    return result.flow_name


class TestFlowManagerScopes:
    def test_every_handler_declares_its_scope(self) -> None:
        scopes = {
            request_type: handled_request_scope(attr)
            for attr in vars(FlowManager).values()
            for request_type in handled_request_types(attr)
        }

        assert scopes, "FlowManager registers no handlers"
        for request_type, scope in scopes.items():
            expected = RequestScope.WORKFLOW
            if request_type in _OPTIONAL_WORKFLOW_REQUESTS:
                expected = RequestScope.OPTIONAL_WORKFLOW
            assert scope is expected, f"{request_type.__name__} is {scope}, expected {expected}"


class TestHandlersActOnTheWorkflowTheyAreHanded:
    def test_a_request_with_no_envelope_id_acts_on_the_open_workflow(self, engine: Engine) -> None:
        push_unsaved_workflow(engine)

        flow_name = _create_canvas(engine)

        assert engine.open_workflows.sole_workflow().flows.name_to_parent_name == {flow_name: None}

    def test_a_request_with_an_envelope_id_acts_on_that_workflow(self, engine: Engine) -> None:
        entry = push_unsaved_workflow(engine)

        flow_name = _create_canvas(engine, workflow_id=entry.workflow_id)

        assert engine.open_workflows.get(entry.workflow_id).flows.name_to_parent_name == {flow_name: None}

    def test_a_request_naming_a_workflow_that_is_not_open_changes_nothing(self, engine: Engine) -> None:
        push_unsaved_workflow(engine)

        result = engine.handle_request(
            CreateFlowRequest(parent_flow_name=None, flow_name="canvas"), workflow_id="not-open"
        )

        assert result.failed()
        assert "isn't open" in str(result.result_details)
        assert engine.open_workflows.sole_workflow().flows.name_to_parent_name == {}

    def test_a_handler_uses_the_workflow_it_is_handed_rather_than_the_open_one(self, engine: Engine) -> None:
        push_unsaved_workflow(engine)
        other = WorkflowRuntime("other", engine)

        result = engine.flow_manager.on_create_flow_request(
            CreateFlowRequest(parent_flow_name=None, flow_name="canvas"), other
        )

        assert isinstance(result, CreateFlowResultSuccess)
        assert other.flows.name_to_parent_name == {"canvas": None}
        assert other.objects.has("canvas")
        assert engine.open_workflows.sole_workflow().flows.name_to_parent_name == {}
        assert not engine.object_manager.has_object_with_name("canvas")


class TestNestedRequestsCarryTheHandlersWorkflow:
    """The requests a FlowManager handler sends name its workflow. What their own handlers send is theirs."""

    @staticmethod
    def _assert_addressed(handle_request: MagicMock, request_types: set[type], workflow: WorkflowRuntime) -> None:
        sent = []
        for call in handle_request.call_args_list:
            request = call.kwargs.get("request")
            if request is None:
                request = call.args[0]
            if type(request) in request_types:
                sent.append((request, call.kwargs.get("workflow_id")))
        assert {type(request) for request, _ in sent} == request_types
        for request, workflow_id in sent:
            assert workflow_id == workflow.workflow_id, request

    def _workflow_with_a_node(self, engine: Engine) -> WorkflowRuntime:
        push_unsaved_workflow(engine)
        flow_name = _create_canvas(engine)
        with engine.context_manager.flow(flow_name):
            created = engine.handle_request(CreateNodeRequest(node_type="Note", node_name="note"))
        assert isinstance(created, CreateNodeResultSuccess)
        return engine.open_workflows.sole_workflow()

    def test_serializing_a_flow_addresses_every_nested_request_to_its_workflow(self, engine: Engine) -> None:
        workflow = self._workflow_with_a_node(engine)

        with patch.object(engine, "handle_request", wraps=engine.handle_request) as handle_request:
            result = engine.flow_manager.on_serialize_flow_to_commands(
                SerializeFlowToCommandsRequest(flow_name="canvas"), workflow
            )

        assert isinstance(result, SerializeFlowToCommandsResultSuccess)
        self._assert_addressed(
            handle_request,
            {ListNodesInFlowRequest, SerializeNodeToCommandsRequest, ListFlowsInFlowRequest},
            workflow,
        )

    def test_deleting_a_flow_addresses_every_nested_request_to_its_workflow(self, engine: Engine) -> None:
        workflow = self._workflow_with_a_node(engine)

        with patch.object(engine, "handle_request", wraps=engine.handle_request) as handle_request:
            result = engine.flow_manager.on_delete_flow_request(DeleteFlowRequest(flow_name="canvas"), workflow)

        assert isinstance(result, DeleteFlowResultSuccess)
        self._assert_addressed(
            handle_request, {ListFlowsInCurrentContextRequest, ListNodesInFlowRequest, DeleteNodeRequest}, workflow
        )


class TestEdgeMethodsDelegateWithTheOpenWorkflow:
    @pytest.mark.parametrize(
        ("edge_name", "explicit_name", "args"),
        [
            ("get_flow_by_name", "get_flow_by_name_in", ("canvas",)),
            ("get_parent_flow", "get_parent_flow_in", ("canvas",)),
            ("check_for_existing_running_flow", "check_for_existing_running_flow_in", ()),
            ("flow_state", "flow_state_in", ("flow",)),
            ("get_start_node_queue", "get_start_node_queue_in", ()),
            ("classify_nodes_for_dag", "classify_nodes_for_dag_in", (["node"],)),
            ("get_connected_output_parameters", "get_connected_output_parameters_in", ("node", "param")),
            ("has_connection", "has_connection_in", ("source", "source_param", "target", "target_param")),
            ("get_start_node_from_node", "get_start_node_from_node_in", ("flow", "node")),
            ("get_prev_node", "get_prev_node_in", ("flow", "node")),
        ],
    )
    def test_an_edge_method_hands_the_open_workflow_to_its_explicit_twin(
        self, engine: Engine, edge_name: str, explicit_name: str, args: tuple
    ) -> None:
        push_unsaved_workflow(engine)
        flow_manager = engine.flow_manager

        with patch.object(flow_manager, explicit_name, return_value=MagicMock()) as explicit:
            returned = getattr(flow_manager, edge_name)(*args)

        explicit.assert_called_once_with(engine.open_workflows.sole_workflow(), *args)
        assert returned is explicit.return_value

    @pytest.mark.parametrize(
        ("edge_name", "handler_name", "request_payload"),
        [
            (
                "create_connection",
                "on_create_connection_request",
                CreateConnectionRequest(
                    source_parameter_name="out", target_parameter_name="in", source_node_name="a", target_node_name="b"
                ),
            ),
            (
                "delete_connection",
                "on_delete_connection_request",
                DeleteConnectionRequest(
                    source_parameter_name="out", target_parameter_name="in", source_node_name="a", target_node_name="b"
                ),
            ),
        ],
    )
    def test_a_connection_edge_method_hands_the_open_workflow_to_the_handler(
        self, engine: Engine, edge_name: str, handler_name: str, request_payload: Any
    ) -> None:
        push_unsaved_workflow(engine)
        flow_manager = engine.flow_manager

        with patch.object(flow_manager, handler_name, return_value=MagicMock()) as handler:
            returned = getattr(flow_manager, edge_name)(request_payload)

        handler.assert_called_once_with(request_payload, engine.open_workflows.sole_workflow())
        assert returned is handler.return_value

    @pytest.mark.asyncio
    async def test_start_local_subflow_hands_the_open_workflow_to_the_handler(self, engine: Engine) -> None:
        push_unsaved_workflow(engine)
        flow_manager = engine.flow_manager
        request = StartLocalSubflowRequest(flow_name="subflow")

        with patch.object(flow_manager, "on_start_local_subflow_request", return_value=MagicMock()) as handler:
            await flow_manager.start_local_subflow(request)

        handler.assert_awaited_once_with(request, engine.open_workflows.sole_workflow())

    @pytest.mark.asyncio
    async def test_edge_methods_report_failure_with_no_workflow_open(self, engine: Engine) -> None:
        flow_manager = engine.flow_manager

        created = flow_manager.create_connection(
            CreateConnectionRequest(
                source_parameter_name="out", target_parameter_name="in", source_node_name="a", target_node_name="b"
            )
        )
        deleted = flow_manager.delete_connection(
            DeleteConnectionRequest(
                source_parameter_name="out", target_parameter_name="in", source_node_name="a", target_node_name="b"
            )
        )
        started = await flow_manager.start_local_subflow(StartLocalSubflowRequest(flow_name="subflow"))

        assert isinstance(created, CreateConnectionResultFailure)
        assert isinstance(deleted, DeleteConnectionResultFailure)
        assert isinstance(started, StartLocalSubflowResultFailure)
        assert not flow_manager.check_for_existing_running_flow()
        assert flow_manager.flow_state(MagicMock()) == ([], [], [])
        with pytest.raises(KeyError, match="doesn't exist"):
            flow_manager.get_flow_by_name("canvas")


class TestHandlersNodeLibrariesCallDirectly:
    """Shipped node libraries call these by name with only a request, so those calls keep working."""

    def test_get_top_level_flow_takes_only_a_request(self, engine: Engine) -> None:
        push_unsaved_workflow(engine)
        flow_name = _create_canvas(engine)

        result = engine.flow_manager.on_get_top_level_flow_request(GetTopLevelFlowRequest())

        assert isinstance(result, GetTopLevelFlowResultSuccess)
        assert result.flow_name == flow_name

    def test_get_top_level_flow_finds_none_with_no_workflow_open(self, engine: Engine) -> None:
        result = engine.flow_manager.on_get_top_level_flow_request(GetTopLevelFlowRequest())

        assert isinstance(result, GetTopLevelFlowResultSuccess)
        assert result.flow_name is None

    def test_list_nodes_in_flow_takes_only_a_request(self, engine: Engine) -> None:
        push_unsaved_workflow(engine)
        flow_name = _create_canvas(engine)
        with engine.context_manager.flow(flow_name):
            created = engine.handle_request(CreateNodeRequest(node_type="Note", node_name="note"))
        assert isinstance(created, CreateNodeResultSuccess)

        result = engine.flow_manager.on_list_nodes_in_flow_request(ListNodesInFlowRequest(flow_name=flow_name))

        assert isinstance(result, ListNodesInFlowResultSuccess)
        assert result.node_names == [created.node_name]

    def test_list_nodes_in_flow_fails_with_no_workflow_open(self, engine: Engine) -> None:
        result = engine.flow_manager.on_list_nodes_in_flow_request(ListNodesInFlowRequest(flow_name="canvas"))

        assert isinstance(result, ListNodesInFlowResultFailure)
