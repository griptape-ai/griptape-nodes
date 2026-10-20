"""Node-facing code acts on its node's workflow even from a thread that lost the binding.

Two workflows are open and the code runs on a plain `threading.Thread`, which copies no context, so it
is bound to nothing. A request or lookup that relied on the bound workflow would fail there ("several
workflows are open and the request names none"). Each test builds its nodes in workflow A and asks
from the thread, so the only way to reach A is through the node.
"""

from __future__ import annotations

import threading
from typing import TYPE_CHECKING, Any, TypeVar
from unittest.mock import patch

import pytest

from griptape_nodes.exe_types.base_iterative_nodes import _incoming_connection_exists
from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.flow import ControlFlow
from griptape_nodes.exe_types.node_groups.subflow_node_group import SubflowNodeGroup
from griptape_nodes.exe_types.node_types import BaseNode
from griptape_nodes.exe_types.param_components.project_file_parameter import ProjectFileParameter
from griptape_nodes.exe_types.workflow_node import _get_flow_or_none
from griptape_nodes.files.project_file import ProjectFileDestination
from griptape_nodes.retained_mode.events.connection_events import (
    CreateConnectionRequest,
    CreateConnectionResultSuccess,
)
from griptape_nodes.retained_mode.events.node_events import CreateNodeRequest, CreateNodeResultSuccess
from griptape_nodes.retained_mode.events.open_workflow_events import OpenWorkflowRequest, OpenWorkflowResultSuccess
from griptape_nodes.retained_mode.runtime.binding import bound_workflow_id

if TYPE_CHECKING:
    from collections.abc import Callable

    from griptape_nodes.exe_types.node_types import AsyncResult
    from griptape_nodes.files.file import FileDestination
    from griptape_nodes.retained_mode.engine import Engine
    from griptape_nodes.retained_mode.runtime.workflow_runtime import WorkflowRuntime

ResultT = TypeVar("ResultT")


class _SettingsNode(BaseNode):
    """Stands in for FileOutputSettings: provides a FileDestination from its `file_destination` output."""

    def __init__(self, name: str, destination: FileDestination, **kwargs: Any) -> None:
        super().__init__(name=name, **kwargs)
        self._destination = destination
        self.add_parameter(
            Parameter(
                name="file_destination",
                type="str",
                output_type="str",
                allowed_modes={ParameterMode.OUTPUT},
                tooltip="test",
            )
        )

    @property
    def file_destination(self) -> FileDestination:
        return self._destination

    def process(self) -> AsyncResult | None:
        return None


class _Group(SubflowNodeGroup):
    """A subflow group that needs no subflow of its own for these tests."""

    async def aprocess(self) -> None:
        return

    def process(self) -> AsyncResult | None:
        return None


class _WriterNode(BaseNode):
    """A node with a ProjectFileParameter, like the nodes that save a file."""

    def __init__(self, name: str, **kwargs: Any) -> None:
        super().__init__(name=name, **kwargs)
        self.file_param = ProjectFileParameter(self, "output_file", default_filename="out.png")
        self.file_param.add_parameter()

    def process(self) -> AsyncResult | None:
        return None


def _open_workflow(engine: Engine, display_name: str) -> WorkflowRuntime:
    opened = engine.handle_request(OpenWorkflowRequest(display_name=display_name))
    assert isinstance(opened, OpenWorkflowResultSuccess), opened
    node = engine.handle_request(
        CreateNodeRequest(node_type="Note", node_name=f"{display_name}Note"), workflow_id=opened.workflow_id
    )
    assert isinstance(node, CreateNodeResultSuccess), node
    runtime = engine.find_workflow_runtime(opened.workflow_id)
    assert runtime is not None
    return runtime


def _add_node(engine: Engine, runtime: WorkflowRuntime, node: BaseNode, flow_name: str) -> None:
    """Put a node in the workflow's flow the way CreateNodeRequest does."""
    flow = runtime.objects.get_as_type(flow_name, ControlFlow)
    assert flow is not None
    flow.add_node(node)
    engine.object_manager.add_object_by_name(runtime, node.name, node)
    runtime.nodes.name_to_parent_flow_name[node.name] = flow_name
    node.workflow_runtime = runtime


def _in_unbound_thread[ResultT](call: Callable[[], ResultT]) -> ResultT:
    """Run `call` on a plain thread, which has none of this thread's context."""
    outcome: list[ResultT] = []
    errors: list[BaseException] = []

    def run() -> None:
        assert bound_workflow_id() is None
        try:
            outcome.append(call())
        except BaseException as e:
            errors.append(e)

    thread = threading.Thread(target=run)
    thread.start()
    thread.join()
    if errors:
        raise errors[0]
    return outcome[0]


@pytest.fixture
def two_workflows(engine: Engine) -> tuple[WorkflowRuntime, WorkflowRuntime, str]:
    """Workflows A and B, with B open too so nothing resolves to A by being the only one. Returns A's flow name."""
    runtime_a = _open_workflow(engine, "A")
    runtime_b = _open_workflow(engine, "B")
    flow_name = runtime_a.nodes.parent_flow_name("ANote")
    return runtime_a, runtime_b, flow_name


def _connect(engine: Engine, runtime: WorkflowRuntime, source: BaseNode, target: BaseNode, **names: str) -> None:
    result = engine.handle_request(
        CreateConnectionRequest(
            source_node_name=source.name,
            source_parameter_name=names["source_parameter"],
            target_node_name=target.name,
            target_parameter_name=names["target_parameter"],
        ),
        workflow_id=runtime.workflow_id,
    )
    assert isinstance(result, CreateConnectionResultSuccess), result


class TestNodeAddressesItsOwnWorkflow:
    def test_a_project_file_parameter_finds_the_connected_settings_node(
        self, engine: Engine, two_workflows: tuple[WorkflowRuntime, WorkflowRuntime, str]
    ) -> None:
        runtime_a, _runtime_b, flow_name = two_workflows
        destination = ProjectFileDestination("{outputs}/connected.png")
        with engine.bind_workflow(runtime_a):
            settings = _SettingsNode("Settings", destination)
            writer = _WriterNode("Writer")
        _add_node(engine, runtime_a, settings, flow_name)
        _add_node(engine, runtime_a, writer, flow_name)
        _connect(
            engine, runtime_a, settings, writer, source_parameter="file_destination", target_parameter="output_file"
        )

        built = _in_unbound_thread(writer.file_param.build_file)

        assert built is destination

    def test_a_node_with_the_same_name_in_another_workflow_is_not_the_one_found(
        self, engine: Engine, two_workflows: tuple[WorkflowRuntime, WorkflowRuntime, str]
    ) -> None:
        runtime_a, runtime_b, flow_name_a = two_workflows
        flow_name_b = runtime_b.nodes.parent_flow_name("BNote")
        destination_a = ProjectFileDestination("{outputs}/a.png")
        destination_b = ProjectFileDestination("{outputs}/b.png")
        for runtime, flow_name, destination in (
            (runtime_a, flow_name_a, destination_a),
            (runtime_b, flow_name_b, destination_b),
        ):
            with engine.bind_workflow(runtime):
                settings = _SettingsNode("Settings", destination)
                writer = _WriterNode("Writer")
            _add_node(engine, runtime, settings, flow_name)
            _add_node(engine, runtime, writer, flow_name)
            _connect(
                engine, runtime, settings, writer, source_parameter="file_destination", target_parameter="output_file"
            )
        writer_a = runtime_a.objects.get_as_type("Writer", _WriterNode)
        assert writer_a is not None

        built = _in_unbound_thread(writer_a.file_param.build_file)

        assert built is destination_a

    def test_build_file_resolves_its_situation_in_the_nodes_workflow(
        self, engine: Engine, two_workflows: tuple[WorkflowRuntime, WorkflowRuntime, str]
    ) -> None:
        runtime_a, _runtime_b, flow_name = two_workflows
        with engine.bind_workflow(runtime_a):
            writer = _WriterNode("Writer")
        _add_node(engine, runtime_a, writer, flow_name)
        seen: list[str | None] = []

        def from_situation(*_args: object, **_kwargs: object) -> str:
            seen.append(bound_workflow_id())
            return "destination"

        with patch.object(ProjectFileDestination, "from_situation", side_effect=from_situation):
            _in_unbound_thread(writer.file_param.build_file)

        assert seen == [runtime_a.workflow_id]

    def test_a_connection_check_asks_the_nodes_workflow(
        self, engine: Engine, two_workflows: tuple[WorkflowRuntime, WorkflowRuntime, str]
    ) -> None:
        runtime_a, _runtime_b, flow_name = two_workflows
        with engine.bind_workflow(runtime_a):
            settings = _SettingsNode("Settings", ProjectFileDestination("{outputs}/x.png"))
            writer = _WriterNode("Writer")
        _add_node(engine, runtime_a, settings, flow_name)
        _add_node(engine, runtime_a, writer, flow_name)
        _connect(
            engine, runtime_a, settings, writer, source_parameter="file_destination", target_parameter="output_file"
        )

        connected = _in_unbound_thread(lambda: _incoming_connection_exists(writer, "Writer", "output_file"))

        assert connected is True

    @pytest.mark.usefixtures("engine")
    def test_a_node_with_no_workflow_recorded_binds_nothing(self) -> None:
        node = _WriterNode("Loose")
        node.workflow_runtime = None

        with node.in_own_workflow():
            assert bound_workflow_id() is None

    def test_in_own_workflow_binds_the_nodes_workflow_for_the_block(
        self, engine: Engine, two_workflows: tuple[WorkflowRuntime, WorkflowRuntime, str]
    ) -> None:
        runtime_a, _runtime_b, flow_name = two_workflows
        with engine.bind_workflow(runtime_a):
            writer = _WriterNode("Writer")
        _add_node(engine, runtime_a, writer, flow_name)

        def bound_inside() -> tuple[str | None, str | None]:
            with writer.in_own_workflow():
                inside = bound_workflow_id()
            return inside, bound_workflow_id()

        assert _in_unbound_thread(bound_inside) == (runtime_a.workflow_id, None)

    def test_variable_substitution_reads_the_nodes_workflow(
        self, engine: Engine, two_workflows: tuple[WorkflowRuntime, WorkflowRuntime, str]
    ) -> None:
        runtime_a, _runtime_b, flow_name = two_workflows
        with engine.bind_workflow(runtime_a):
            writer = _WriterNode("Writer")
        _add_node(engine, runtime_a, writer, flow_name)

        resolved = _in_unbound_thread(lambda: writer._resolve_variables_in_string("plain text"))

        assert resolved == "plain text"

    def test_a_flow_is_looked_up_in_the_nodes_workflow(
        self, engine: Engine, two_workflows: tuple[WorkflowRuntime, WorkflowRuntime, str]
    ) -> None:
        runtime_a, _runtime_b, flow_name = two_workflows
        with engine.bind_workflow(runtime_a):
            writer = _WriterNode("Writer")
        _add_node(engine, runtime_a, writer, flow_name)

        flow = _in_unbound_thread(lambda: _get_flow_or_none(writer, flow_name))

        assert flow is runtime_a.objects.get_as_type(flow_name, ControlFlow)

    def test_a_group_finds_the_flow_it_lives_in(
        self, engine: Engine, two_workflows: tuple[WorkflowRuntime, WorkflowRuntime, str]
    ) -> None:
        runtime_a, _runtime_b, flow_name = two_workflows
        with engine.bind_workflow(runtime_a):
            group = _Group("Group")
        _add_node(engine, runtime_a, group, flow_name)

        parent_flow_name = _in_unbound_thread(lambda: group.parent_flow_name)

        assert parent_flow_name == flow_name
