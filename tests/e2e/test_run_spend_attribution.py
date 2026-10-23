"""End-to-end coverage for attributing spend to the workflow run that made it (issue #5945).

Griptape Cloud totals what one run cost by filtering spend rows on their `run_id` tag, so every
model call a run makes has to carry the same id, and the next run a different one. The unit tests
prove `_build_tags` reads the id; this suite proves the id reaches Cloud. It runs a real three-node
flow whose nodes report their cost from inside `process()`, the way the standard library does,
against a stub Cloud that records each report it receives. Then it checks the reports against the
id the run announced on `FlowRunStartedEvent`.
"""

from __future__ import annotations

import asyncio
import contextlib
import itertools
import json
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import TYPE_CHECKING, Any, NamedTuple, cast

import pytest

from griptape_nodes.drivers.cloud_credentials import API_KEY_SECRET_NAME, BASE_URL_SETTING_NAME
from griptape_nodes.node_library.workflow_registry import WorkflowMetadata
from griptape_nodes.retained_mode.events.budget_events import ReportUsageRequest
from griptape_nodes.retained_mode.events.execution_events import (
    CancelFlowRequest,
    ControlFlowCancelledEvent,
    ControlFlowResolvedEvent,
    FlowRunStartedEvent,
    ResolveNodeRequest,
    ResolveNodeResultSuccess,
    StartFlowRequest,
    StartFlowResultSuccess,
)
from griptape_nodes.retained_mode.events.flow_events import (
    CreateFlowRequest,
    CreateFlowResultSuccess,
    SerializeFlowToCommandsRequest,
    SerializeFlowToCommandsResultSuccess,
)
from griptape_nodes.retained_mode.events.library_events import (
    RegisterLibraryFromFileRequest,
    RegisterLibraryFromFileResultSuccess,
)
from griptape_nodes.retained_mode.events.node_events import CreateNodeRequest, CreateNodeResultSuccess
from griptape_nodes.retained_mode.events.parameter_events import SetParameterValueRequest
from tests.e2e.waits import wait_until_resolving

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator

    from griptape_nodes.retained_mode.engine import Engine

pytestmark = pytest.mark.timeout(300, method="thread")

FIXTURE_LIBRARY_DIR = Path(__file__).parent / "fixtures" / "run_spend_library"
FIXTURE_LIBRARY_JSON_TEMPLATE = FIXTURE_LIBRARY_DIR / "griptape_nodes_library.json"
FIXTURE_NODE_FILE = FIXTURE_LIBRARY_DIR / "run_spend_nodes.py"
LIBRARY_NAME = "Run Spend Library"
NODE_TYPE = "SpendingNode"
NODE_NAMES = ("Draft", "Refine", "Caption")

LOOP_LIBRARY_DIR = Path(__file__).parent / "fixtures" / "iterative_group_library"
LOOP_LIBRARY_JSON_TEMPLATE = LOOP_LIBRARY_DIR / "griptape_nodes_library.json"
LOOP_NODE_FILE = LOOP_LIBRARY_DIR / "iterative_group_nodes.py"
# The packager asks for its flow endpoints from a library with exactly this name.
LOOP_LIBRARY_NAME = "Griptape Nodes Library"
# `ProbeForEachGroupNode` iterates a fixed three-item list.
LOOP_ITERATIONS = 3

SPEND_PATH = "/api/spend"
REPORT_WAIT_SECONDS = 10.0
RUN_TIMEOUT_SECONDS = 30.0


class _StubSpendServer(ThreadingHTTPServer):
    """Records every usage report posted to it, in the order they arrive."""

    def __init__(self) -> None:
        super().__init__(("127.0.0.1", 0), _StubSpendHandler)
        self.reports: list[dict[str, Any]] = []
        self.lock = threading.Lock()
        # Seconds to hold each reply, so a report is still in flight when a short-lived engine ends.
        self.reply_delay = 0.0

    async def wait_for_reports(self, count: int) -> list[dict[str, Any]]:
        """Wait for `count` reports, since the engine posts them from a background thread.

        Waits with `asyncio.sleep`, so the engine's event loop keeps running meanwhile.
        """
        deadline = time.monotonic() + REPORT_WAIT_SECONDS
        while time.monotonic() < deadline:
            with self.lock:
                if len(self.reports) >= count:
                    return list(self.reports)
            await asyncio.sleep(0.05)
        with self.lock:
            return list(self.reports)


class _StubSpendHandler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:  # BaseHTTPRequestHandler's spelling
        length = int(self.headers.get("Content-Length", "0"))
        body = json.loads(self.rfile.read(length))
        server = cast("_StubSpendServer", self.server)
        time.sleep(server.reply_delay)
        if self.path == SPEND_PATH:
            with server.lock:
                server.reports.append(body)
        self.send_response(201)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", "2")
        self.end_headers()
        self.wfile.write(b"{}")

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002  # the base class names it this
        """Swallow the per-request line the base class writes to stderr."""


@pytest.fixture
def stub_cloud(engine: Engine, monkeypatch: pytest.MonkeyPatch) -> Iterator[_StubSpendServer]:
    """Run a stub Griptape Cloud and point the engine's spend reports at it."""
    server = _StubSpendServer()
    host, port = server.server_address[0], server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    monkeypatch.setenv(BASE_URL_SETTING_NAME, f"http://{host}:{port}")
    engine.secrets_manager.set_secret(API_KEY_SECRET_NAME, "gt-test-key")
    try:
        yield server
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


@pytest.fixture
def three_node_flow(
    engine: Engine,
    tmp_path: Path,
    materialize_library: Callable[..., Path],
    create_node: Callable[..., str],
    connect: Callable[..., None],
) -> str:
    """A flow of three spending nodes in a row, as a short image pipeline might be."""
    library_json = materialize_library(
        tmp_path / "library", template=FIXTURE_LIBRARY_JSON_TEMPLATE, node_file=FIXTURE_NODE_FILE
    )
    result = engine.handle_request(RegisterLibraryFromFileRequest(file_path=str(library_json)))
    assert isinstance(result, RegisterLibraryFromFileResultSuccess), result

    engine.context_manager.push_workflow(workflow_name="run_spend_wf")
    flow_result = engine.handle_request(CreateFlowRequest(parent_flow_name=None, flow_name="Flow"))
    assert isinstance(flow_result, CreateFlowResultSuccess), flow_result
    flow_name = flow_result.flow_name

    for node_name in NODE_NAMES:
        create_node(NODE_TYPE, node_name, flow_name, library_name=LIBRARY_NAME)
    for source, target in itertools.pairwise(NODE_NAMES):
        connect(source, "exec_out", target, "exec_in")
    return flow_name


def _announced_run_ids(payloads: list[Any]) -> list[str]:
    return [payload.run_id for payload in payloads if isinstance(payload, FlowRunStartedEvent)]


@pytest.mark.asyncio
async def test_every_call_in_a_run_carries_the_id_the_run_announced(
    engine: Engine,
    record_published: Callable[..., list[Any]],
    stub_cloud: _StubSpendServer,
    three_node_flow: str,
) -> None:
    """One run, three calls: Cloud can total the run because all three carry its id."""
    payloads = record_published(object)

    result = await engine.ahandle_request(StartFlowRequest(flow_name=three_node_flow))
    assert isinstance(result, StartFlowResultSuccess), result

    announced = _announced_run_ids(payloads)
    assert len(announced) == 1, f"A run should announce exactly one id, got {announced}"
    reports = await stub_cloud.wait_for_reports(len(NODE_NAMES))
    assert [report["tags"].get("run_id") for report in reports] == announced * len(NODE_NAMES), (
        f"Every call in the run should carry the run's id, so Cloud can total it: {reports}"
    )
    resolved = [payload.run_id for payload in payloads if isinstance(payload, ControlFlowResolvedEvent)]
    assert resolved == announced, "The run's end event should name the run its start event announced."


@pytest.mark.asyncio
async def test_the_next_run_gets_a_different_id(
    engine: Engine,
    record_published: Callable[..., list[Any]],
    stub_cloud: _StubSpendServer,
    three_node_flow: str,
) -> None:
    """Two runs of one workflow write two separate totals, not one."""
    payloads = record_published(object)

    for _ in range(2):
        result = await engine.ahandle_request(StartFlowRequest(flow_name=three_node_flow))
        assert isinstance(result, StartFlowResultSuccess), result

    first, second = _announced_run_ids(payloads)
    assert first != second, "Two runs of one workflow must not share an id, or Cloud adds them together."
    reports = await stub_cloud.wait_for_reports(2 * len(NODE_NAMES))
    run_ids = [report["tags"].get("run_id") for report in reports]
    assert run_ids == [first] * len(NODE_NAMES) + [second] * len(NODE_NAMES), run_ids


@pytest.mark.usefixtures("three_node_flow")
@pytest.mark.asyncio
async def test_running_one_node_is_a_run_of_its_own(
    engine: Engine, record_published: Callable[..., list[Any]], stub_cloud: _StubSpendServer
) -> None:
    """Running a single node from the editor is a run, and its calls are totalled as one."""
    payloads = record_published(object)

    result = await engine.ahandle_request(ResolveNodeRequest(node_name=NODE_NAMES[0]))
    assert isinstance(result, ResolveNodeResultSuccess), result

    announced = _announced_run_ids(payloads)
    assert len(announced) == 1, f"Running one node should announce one run, got {announced}"
    reports = await stub_cloud.wait_for_reports(1)
    assert [report["tags"].get("run_id") for report in reports] == announced


@pytest.mark.asyncio
async def test_spend_outside_a_run_carries_no_run_id(engine: Engine, stub_cloud: _StubSpendServer) -> None:
    """A call made between runs, such as from the agent chat, belongs to no run."""
    engine.handle_request(ReportUsageRequest(declared_cost_micro_usd=1, model="gpt-5-nano"))

    reports = await stub_cloud.wait_for_reports(1)
    assert len(reports) == 1, reports
    assert "run_id" not in reports[0]["tags"], reports[0]


class _LoopFlow(NamedTuple):
    flow_name: str
    group: str


@pytest.fixture(params=["Run Group Items One at a Time", "Run Group Items All at Once"])
def loop_flow(
    request: pytest.FixtureRequest,
    engine: Engine,
    tmp_path: Path,
    materialize_library: Callable[..., Path],
    connect: Callable[..., None],
) -> _LoopFlow:
    """A three-iteration ForEach group whose body is a spending node, in each group execution mode."""
    for library_json in (
        materialize_library(
            tmp_path / "loop_library",
            template=LOOP_LIBRARY_JSON_TEMPLATE,
            node_file=LOOP_NODE_FILE,
            name=LOOP_LIBRARY_NAME,
        ),
        materialize_library(
            tmp_path / "spend_library", template=FIXTURE_LIBRARY_JSON_TEMPLATE, node_file=FIXTURE_NODE_FILE
        ),
    ):
        result = engine.handle_request(RegisterLibraryFromFileRequest(file_path=str(library_json)))
        assert isinstance(result, RegisterLibraryFromFileResultSuccess), result

    engine.context_manager.push_workflow(workflow_name="run_spend_loop_wf")
    flow_result = engine.handle_request(CreateFlowRequest(parent_flow_name=None, flow_name="Flow"))
    assert isinstance(flow_result, CreateFlowResultSuccess), flow_result
    flow_name = flow_result.flow_name

    with engine.context_manager.flow(flow_name):
        group_result = engine.handle_request(
            CreateNodeRequest(node_type="ProbeForEachGroupNode", specific_library_name=LOOP_LIBRARY_NAME)
        )
        assert isinstance(group_result, CreateNodeResultSuccess), group_result
        body_result = engine.handle_request(
            CreateNodeRequest(
                node_type=NODE_TYPE, specific_library_name=LIBRARY_NAME, parent_group_name=group_result.node_name
            )
        )
        assert isinstance(body_result, CreateNodeResultSuccess), body_result
    group, body = group_result.node_name, body_result.node_name
    connect(group, "on_each", body, "exec_in")
    connect(body, "exec_out", group, "loop_complete")
    engine.handle_request(
        SetParameterValueRequest(parameter_name="execution_mode", node_name=group, value=request.param)
    )
    return _LoopFlow(flow_name=flow_name, group=group)


@pytest.mark.asyncio
async def test_a_loop_s_iterations_count_toward_the_run_that_started_them(
    engine: Engine,
    record_published: Callable[..., list[Any]],
    stub_cloud: _StubSpendServer,
    loop_flow: _LoopFlow,
) -> None:
    """Each iteration runs as its own isolated subflow, and must not start a run of its own."""
    payloads = record_published(object)

    with engine.context_manager.flow(loop_flow.flow_name):
        run_result = await engine.ahandle_request(
            StartFlowRequest(flow_name=loop_flow.flow_name, flow_node_name=loop_flow.group)
        )
    assert isinstance(run_result, StartFlowResultSuccess), run_result

    announced = _announced_run_ids(payloads)
    assert len(announced) == 1, f"Only the run the artist started should announce an id, got {announced}"
    reports = await stub_cloud.wait_for_reports(LOOP_ITERATIONS)
    assert [report["tags"].get("run_id") for report in reports] == announced * LOOP_ITERATIONS, reports


@pytest.mark.asyncio
async def test_a_group_run_for_another_engine_counts_toward_that_engine_s_run(
    engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
    record_published: Callable[..., list[Any]],
    stub_cloud: _StubSpendServer,
    three_node_flow: str,
) -> None:
    """The engine that runs a node group in its own process reports under the parent's run.

    It sends no start event and no end event with the id either, so the parent's own end event is
    the only one that says the run is over.
    """
    monkeypatch.setattr(engine.flow_manager, "parent_run_id", "parent-run")
    payloads = record_published(object)

    result = await engine.ahandle_request(StartFlowRequest(flow_name=three_node_flow))
    assert isinstance(result, StartFlowResultSuccess), result

    assert _announced_run_ids(payloads) == []
    resolved = [payload.run_id for payload in payloads if isinstance(payload, ControlFlowResolvedEvent)]
    assert resolved == [None], resolved
    reports = await stub_cloud.wait_for_reports(len(NODE_NAMES))
    assert [report["tags"].get("run_id") for report in reports] == ["parent-run"] * len(NODE_NAMES), reports


@pytest.mark.usefixtures("execution_mode")
@pytest.mark.asyncio
async def test_a_cancelled_run_names_itself_on_its_cancelled_event_only(
    engine: Engine,
    tmp_path: Path,
    record_published: Callable[..., list[Any]],
    three_node_flow: str,
) -> None:
    """Cancelling mid-run passes the run through its normal ending on the way out.

    That ending must not carry the run's id: a client that closes a run on its end event would
    otherwise record a cancelled run as finished, then see a second end event for it.
    """
    gate = tmp_path / "gates" / "first.gate"
    engine.handle_request(
        SetParameterValueRequest(parameter_name="gate_file", node_name=NODE_NAMES[0], value=str(gate))
    )
    payloads = record_published(object)

    run = asyncio.create_task(engine.ahandle_request(StartFlowRequest(flow_name=three_node_flow)))
    await wait_until_resolving(engine, NODE_NAMES[0])
    cancelled = await engine.ahandle_request(CancelFlowRequest(flow_name=three_node_flow))
    assert cancelled.succeeded(), cancelled
    gate.parent.mkdir(parents=True, exist_ok=True)
    gate.write_text("open")
    with contextlib.suppress(TimeoutError, asyncio.CancelledError):
        await asyncio.wait_for(asyncio.shield(run), timeout=RUN_TIMEOUT_SECONDS)
    run.cancel()

    announced = _announced_run_ids(payloads)
    assert len(announced) == 1, announced
    ends_with_id = [
        type(payload).__name__
        for payload in payloads
        if isinstance(payload, (ControlFlowResolvedEvent, ControlFlowCancelledEvent)) and payload.run_id is not None
    ]
    assert ends_with_id == ["ControlFlowCancelledEvent"], ends_with_id
    cancelled_ids = [payload.run_id for payload in payloads if isinstance(payload, ControlFlowCancelledEvent)]
    assert announced[0] in cancelled_ids, cancelled_ids


def _runnable_workflow_source(engine: Engine, flow_name: str) -> str:
    """Serialize the flow to a workflow file that runs itself once, the way a one-off engine does."""
    serialized = engine.handle_request(SerializeFlowToCommandsRequest(flow_name=flow_name))
    assert isinstance(serialized, SerializeFlowToCommandsResultSuccess), serialized
    metadata = WorkflowMetadata(
        name="run_spend_exit_wf",
        schema_version=WorkflowMetadata.LATEST_SCHEMA_VERSION,
        engine_version_created_with="0.0.0",
        node_libraries_referenced=list(serialized.serialized_flow_commands.node_dependencies.libraries),
        workflow_shape=None,
    )
    source = engine.workflow_manager.codegen.generate_workflow_file_content(
        serialized_flow_commands=serialized.serialized_flow_commands,
        workflow_metadata=metadata,
    )
    return (
        source
        + """

import asyncio as _e2e_asyncio

from griptape_nodes.bootstrap.workflow_executors.local_workflow_executor import (
    LocalWorkflowExecutor as _E2ELocalWorkflowExecutor,
)
from griptape_nodes.drivers.storage.storage_backend import StorageBackend as _E2EStorageBackend
from griptape_nodes.retained_mode.events.flow_events import (
    GetTopLevelFlowRequest as _E2EGetTopLevelFlowRequest,
    GetTopLevelFlowResultSuccess as _E2EGetTopLevelFlowResultSuccess,
)
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes as _E2EGriptapeNodes


async def _e2e_run() -> None:
    await build_workflow()  # noqa: F821 - defined by the generated workflow source above
    context_manager = _E2EGriptapeNodes.ContextManager()
    if not context_manager.has_current_flow():
        top_level = _E2EGriptapeNodes.handle_request(_E2EGetTopLevelFlowRequest())
        if isinstance(top_level, _E2EGetTopLevelFlowResultSuccess) and top_level.flow_name is not None:
            context_manager.push_flow(_E2EGriptapeNodes.FlowManager().get_flow_by_name(top_level.flow_name))
    executor = _E2ELocalWorkflowExecutor(
        storage_backend=_E2EStorageBackend.LOCAL, skip_library_loading=True, workflows_to_register=[__file__]
    )
    async with executor as running:
        await running.arun(flow_input={})


if __name__ == "__main__":
    _e2e_asyncio.run(_e2e_run())
"""
    )


def test_an_engine_that_exits_after_its_run_still_sends_its_reports(  # noqa: PLR0913
    tmp_path: Path,
    engine: Engine,
    stub_cloud: _StubSpendServer,
    *,
    engine_subprocess_env: Callable[..., dict[str, str]],
    materialize_library: Callable[..., Path],
    write_isolated_config: Callable[..., None],
    create_node: Callable[..., str],
) -> None:
    """A one-off engine reports a call in its last node, then exits as soon as the run ends.

    The report thread is a daemon, so without waiting for it the process ends with the report
    unsent. Cloud's reply is held long enough that the report is still in flight at that point.
    """
    library_json = materialize_library(
        tmp_path / "library", template=FIXTURE_LIBRARY_JSON_TEMPLATE, node_file=FIXTURE_NODE_FILE
    )
    registered = engine.handle_request(RegisterLibraryFromFileRequest(file_path=str(library_json)))
    assert isinstance(registered, RegisterLibraryFromFileResultSuccess), registered
    engine.context_manager.push_workflow(workflow_name="run_spend_exit_wf")
    flow = engine.handle_request(CreateFlowRequest(parent_flow_name=None, flow_name="Flow"))
    assert isinstance(flow, CreateFlowResultSuccess), flow
    create_node(NODE_TYPE, "Spender", flow.flow_name, library_name=LIBRARY_NAME)
    workflow_path = tmp_path / "run_spend_exit_wf.py"
    workflow_path.write_text(_runnable_workflow_source(engine, flow.flow_name))

    workspace = tmp_path / "workspace"
    workspace.mkdir(exist_ok=True)
    config_root = tmp_path / "xdg_config"
    write_isolated_config(config_root, workspace=workspace, library_path=library_json)
    host, port = stub_cloud.server_address[0], stub_cloud.server_address[1]
    stub_cloud.reply_delay = 1.0

    result = subprocess.run(  # noqa: S603
        [sys.executable, str(workflow_path)],
        env=engine_subprocess_env(XDG_CONFIG_HOME=str(config_root), **{BASE_URL_SETTING_NAME: f"http://{host}:{port}"}),
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )

    diagnostic = f"exit code {result.returncode}\n--- stdout ---\n{result.stdout}\n--- stderr ---\n{result.stderr}"
    assert result.returncode == 0, diagnostic
    with stub_cloud.lock:
        reports = list(stub_cloud.reports)
    assert len(reports) == 1, f"The engine exited without sending its report to Cloud.\n{diagnostic}"
