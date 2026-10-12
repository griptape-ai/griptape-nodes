"""Tests for pausing chat-agent tool calls until the user approves them.

Covers which calls are gated and with which grant keys, how a paused turn is
found in saved history, and the runner's pause and resume round trip against a
`FunctionModel`, so no MCP server or Griptape Cloud call is involved.
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any, cast

import pytest
from pydantic_ai import Agent, Tool
from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)
from pydantic_ai.models.function import AgentInfo, DeltaToolCall, FunctionModel
from pydantic_ai.tools import DeferredToolResults, ToolDenied
from pydantic_ai.toolsets import FunctionToolset

from griptape_nodes.agents.pydantic_ai.mcp_servers import (
    GTN_APPROVAL_REQUIRED_REQUESTS,
    GTN_BATCH_TOOL_NAME,
    GTN_SERVER_NAME,
    _compose,
    _gtn_tool_requires_approval,
    _user_tool_requires_approval,
    grant_keys_for_call,
)
from griptape_nodes.agents.pydantic_ai.runner import PendingApproval, PydanticAgentRunner
from griptape_nodes.agents.pydantic_ai.tool_approval import ToolApprovalDeps, needs_approval, pending_tool_calls
from griptape_nodes.drivers.thread_storage.local_thread_storage_driver import LocalThreadStorageDriver
from griptape_nodes.servers.mcp import EVENT_REQUEST_BATCH_TOOL_NAME, SUPPORTED_REQUEST_EVENTS

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Callable
    from pathlib import Path

    from pydantic_ai import RunContext
    from pydantic_ai.tools import ToolDefinition


ON = ToolApprovalDeps(enabled=True)
OFF = ToolApprovalDeps(enabled=False)


def _ctx(deps: ToolApprovalDeps) -> RunContext[Any]:
    return cast("RunContext[Any]", SimpleNamespace(deps=deps))


def _tool(name: str) -> ToolDefinition:
    return cast("ToolDefinition", SimpleNamespace(name=name))


def _batch(*request_types: str) -> dict[str, Any]:
    return {"requests": [{"request_type": request_type, "request": {}} for request_type in request_types]}


class TestGatedSetMatchesTheEngineServer:
    """The agent-side gate names engine tools by string; these hold it to the server's names."""

    def test_every_gated_request_is_a_tool_the_server_offers(self) -> None:
        assert set(GTN_APPROVAL_REQUIRED_REQUESTS) <= set(SUPPORTED_REQUEST_EVENTS)

    def test_batch_tool_name_matches_the_server(self) -> None:
        assert f"{GTN_SERVER_NAME}_{EVENT_REQUEST_BATCH_TOOL_NAME}" == GTN_BATCH_TOOL_NAME


class TestGrantKeysForCall:
    def test_a_single_call_is_keyed_by_its_own_name(self) -> None:
        assert grant_keys_for_call("GriptapeNodes_StartFlowRequest", {"flow_name": "f"}) == [
            "GriptapeNodes_StartFlowRequest"
        ]

    def test_image_and_user_tools_are_keyed_by_their_own_name(self) -> None:
        assert grant_keys_for_call("generate_image", {"prompt": "a cat"}) == ["generate_image"]
        assert grant_keys_for_call("brave_search", {"q": "x"}) == ["brave_search"]

    def test_a_batch_is_keyed_by_its_gated_inner_requests_in_order_without_repeats(self) -> None:
        args = _batch(
            "CreateNodeRequest",
            "ResolveNodeRequest",
            "SetParameterValueRequest",
            "StartFlowRequest",
            "ResolveNodeRequest",
        )

        assert grant_keys_for_call(GTN_BATCH_TOOL_NAME, args) == [
            "GriptapeNodes_ResolveNodeRequest",
            "GriptapeNodes_StartFlowRequest",
        ]

    def test_a_batch_of_edits_has_nothing_to_grant(self) -> None:
        assert grant_keys_for_call(GTN_BATCH_TOOL_NAME, _batch("CreateNodeRequest", "CreateConnectionRequest")) == []

    @pytest.mark.parametrize("args", [{}, {"requests": "nope"}, {"requests": ["nope", {"request": {}}]}])
    def test_a_malformed_batch_has_nothing_to_grant(self, args: dict[str, Any]) -> None:
        assert grant_keys_for_call(GTN_BATCH_TOOL_NAME, args) == []


class TestNeedsApproval:
    def test_off_never_asks(self) -> None:
        assert needs_approval(OFF, ["generate_image"]) is False

    def test_on_asks_until_every_key_is_granted(self) -> None:
        partly = ToolApprovalDeps(enabled=True, granted=frozenset({"GriptapeNodes_ResolveNodeRequest"}))
        fully = ToolApprovalDeps(
            enabled=True,
            granted=frozenset({"GriptapeNodes_ResolveNodeRequest", "GriptapeNodes_StartFlowRequest"}),
        )
        keys = ["GriptapeNodes_ResolveNodeRequest", "GriptapeNodes_StartFlowRequest"]

        assert needs_approval(ON, keys) is True
        assert needs_approval(partly, keys) is True
        assert needs_approval(fully, keys) is False

    def test_nothing_to_grant_never_asks(self) -> None:
        assert needs_approval(ON, []) is False


class TestGtnToolRequiresApproval:
    @pytest.mark.parametrize("request_type", sorted(GTN_APPROVAL_REQUIRED_REQUESTS))
    def test_tools_that_run_work_ask(self, request_type: str) -> None:
        assert _gtn_tool_requires_approval(_ctx(ON), _tool(f"GriptapeNodes_{request_type}"), {}) is True

    @pytest.mark.parametrize(
        "request_type", ["CreateNodeRequest", "SaveWorkflowRequest", "ListFlowsInCurrentContextRequest"]
    )
    def test_tools_that_only_edit_or_read_never_ask(self, request_type: str) -> None:
        assert _gtn_tool_requires_approval(_ctx(ON), _tool(f"GriptapeNodes_{request_type}"), {}) is False

    def test_nothing_asks_when_approval_is_off(self) -> None:
        assert _gtn_tool_requires_approval(_ctx(OFF), _tool("GriptapeNodes_StartFlowRequest"), {}) is False

    def test_a_granted_tool_runs_without_asking(self) -> None:
        deps = ToolApprovalDeps(enabled=True, granted=frozenset({"GriptapeNodes_StartFlowRequest"}))

        assert _gtn_tool_requires_approval(_ctx(deps), _tool("GriptapeNodes_StartFlowRequest"), {}) is False

    def test_a_batch_asks_only_when_it_holds_an_ungranted_gated_request(self) -> None:
        mixed = _batch("CreateNodeRequest", "StartFlowRequest")
        granted = ToolApprovalDeps(enabled=True, granted=frozenset({"GriptapeNodes_StartFlowRequest"}))
        batch = _tool(GTN_BATCH_TOOL_NAME)

        assert _gtn_tool_requires_approval(_ctx(ON), batch, _batch("CreateNodeRequest")) is False
        assert _gtn_tool_requires_approval(_ctx(ON), batch, mixed) is True
        assert _gtn_tool_requires_approval(_ctx(granted), batch, mixed) is False


class TestUserToolRequiresApproval:
    def test_every_tool_asks_when_approval_is_on(self) -> None:
        assert _user_tool_requires_approval(_ctx(ON), _tool("brave_search"), {}) is True

    def test_nothing_asks_when_approval_is_off(self) -> None:
        assert _user_tool_requires_approval(_ctx(OFF), _tool("brave_search"), {}) is False

    def test_a_granted_tool_runs_without_asking(self) -> None:
        deps = ToolApprovalDeps(enabled=True, granted=frozenset({"brave_search"}))

        assert _user_tool_requires_approval(_ctx(deps), _tool("brave_search"), {}) is False


def _call(tool_call_id: str, tool_name: str = "GriptapeNodes_StartFlowRequest") -> ToolCallPart:
    return ToolCallPart(tool_name=tool_name, args={}, tool_call_id=tool_call_id)


def _return(tool_call_id: str) -> ToolReturnPart:
    return ToolReturnPart(
        tool_name="GriptapeNodes_ListFlowsInCurrentContextRequest", content="ok", tool_call_id=tool_call_id
    )


class TestPendingToolCalls:
    def test_a_completed_turn_has_nothing_pending(self) -> None:
        history: list[ModelMessage] = [
            ModelRequest(parts=[UserPromptPart(content="hi")]),
            ModelResponse(parts=[TextPart(content="hello")]),
        ]

        assert pending_tool_calls(history) == []

    def test_a_response_ending_in_calls_is_waiting_on_all_of_them(self) -> None:
        history: list[ModelMessage] = [
            ModelRequest(parts=[UserPromptPart(content="run it")]),
            ModelResponse(parts=[_call("a"), _call("b")]),
        ]

        assert [call.tool_call_id for call in pending_tool_calls(history)] == ["a", "b"]

    def test_calls_that_already_ran_are_not_pending(self) -> None:
        history: list[ModelMessage] = [
            ModelRequest(parts=[UserPromptPart(content="run it")]),
            ModelResponse(parts=[_call("list"), _call("start")]),
            ModelRequest(parts=[_return("list")]),
        ]

        assert [call.tool_call_id for call in pending_tool_calls(history)] == ["start"]

    def test_a_trailing_user_prompt_is_not_a_paused_turn(self) -> None:
        history: list[ModelMessage] = [
            ModelResponse(parts=[_call("a")]),
            ModelRequest(parts=[UserPromptPart(content="orphan")]),
        ]

        assert pending_tool_calls(history) == []

    def test_empty_history_has_nothing_pending(self) -> None:
        assert pending_tool_calls([]) == []


class ScriptedModel:
    """Streams one scripted turn per model request: text, or a list of tool calls."""

    def __init__(self, *turns: str | list[tuple[str, dict[str, Any], str]]) -> None:
        self._turns = list(turns)
        self.requests: list[list[ModelMessage]] = []
        self.infos: list[AgentInfo] = []

    async def stream(self, messages: list[ModelMessage], info: AgentInfo) -> AsyncIterator[Any]:
        self.requests.append(list(messages))
        self.infos.append(info)
        turn = self._turns.pop(0)
        if isinstance(turn, str):
            yield turn
            return
        yield {
            index: DeltaToolCall(name=name, json_args=json.dumps(args), tool_call_id=tool_call_id)
            for index, (name, args, tool_call_id) in enumerate(turn)
        }


def gtn_like_toolset(ran: list[str]) -> Any:
    """Stand in for the engine's MCP server, composed and gated exactly as the real one is."""

    def recorder(name: str) -> Callable[..., str]:
        def run(**_kwargs: Any) -> str:
            ran.append(name)
            return f"{name} ok"

        return run

    tools = [
        Tool(recorder(name), name=name, takes_ctx=False)
        for name in ("StartFlowRequest", "ListFlowsInCurrentContextRequest", "EventRequestBatch")
    ]
    return _compose(GTN_SERVER_NAME, FunctionToolset(tools=tools), requires_approval=_gtn_tool_requires_approval)


def runner_with(tmp_path: Path, model: ScriptedModel, ran: list[str]) -> PydanticAgentRunner:
    """A runner on real thread storage whose agent talks to `model` and has the gated toolset."""
    workspace = tmp_path / "ws"
    workspace.mkdir(exist_ok=True)
    storage = LocalThreadStorageDriver(tmp_path / "threads", config_manager=None, secrets_manager=None)  # type: ignore[arg-type]
    runner = PydanticAgentRunner(model_name="test", api_key="dummy", workspace_root=workspace, storage=storage)
    runner._agent = Agent(FunctionModel(stream_function=model.stream), toolsets=[gtn_like_toolset(ran)])
    return runner


class TestRunnerPauseAndResume:
    @pytest.mark.asyncio
    async def test_approval_off_runs_the_call_without_pausing(self, tmp_path: Path) -> None:
        ran: list[str] = []
        model = ScriptedModel([("GriptapeNodes_StartFlowRequest", {}, "c1")], "Done.")
        runner = runner_with(tmp_path, model, ran)

        result = await runner.run("Run the flow.", approval=OFF)

        assert ran == ["StartFlowRequest"]
        assert result.pending_approvals == []
        assert result.output == "Done."

    @pytest.mark.asyncio
    async def test_a_gated_call_pauses_the_turn_without_running(self, tmp_path: Path) -> None:
        ran: list[str] = []
        model = ScriptedModel(
            [
                ("GriptapeNodes_ListFlowsInCurrentContextRequest", {}, "c0"),
                ("GriptapeNodes_StartFlowRequest", {"flow_name": "main"}, "c1"),
            ]
        )
        runner = runner_with(tmp_path, model, ran)

        result = await runner.run("Run the flow.", approval=ON)

        assert ran == ["ListFlowsInCurrentContextRequest"]
        assert result.pending_approvals == [
            PendingApproval(
                tool_call_id="c1",
                tool_name="GriptapeNodes_StartFlowRequest",
                args='{"flow_name": "main"}',
                grant_keys=["GriptapeNodes_StartFlowRequest"],
            )
        ]
        # The paused turn is saved, and what it is waiting on can be read back from it.
        history = runner.storage.load_history(result.thread_id)
        assert [call.tool_call_id for call in pending_tool_calls(history)] == ["c1"]

    @pytest.mark.asyncio
    async def test_resuming_with_an_approval_runs_the_call_and_finishes_the_turn(self, tmp_path: Path) -> None:
        ran: list[str] = []
        model = ScriptedModel([("GriptapeNodes_StartFlowRequest", {}, "c1")], "Flow started.")
        runner = runner_with(tmp_path, model, ran)
        paused = await runner.run("Run the flow.", approval=ON)

        resumed = await runner.run(
            None,
            thread_id=paused.thread_id,
            approval=ON,
            deferred_tool_results=DeferredToolResults(approvals={"c1": True}),
        )

        assert ran == ["StartFlowRequest"]
        assert resumed.pending_approvals == []
        assert resumed.output == "Flow started."
        assert pending_tool_calls(runner.storage.load_history(paused.thread_id)) == []

    @pytest.mark.asyncio
    async def test_a_prompt_can_ride_along_with_the_answers(self, tmp_path: Path) -> None:
        """The answers and the new prompt reach the model in one request, answers first."""
        ran: list[str] = []
        model = ScriptedModel([("GriptapeNodes_StartFlowRequest", {}, "c1")], "Okay, I won't.")
        runner = runner_with(tmp_path, model, ran)
        paused = await runner.run("Run the flow.", approval=ON)

        await runner.run(
            "Actually, just explain it.",
            thread_id=paused.thread_id,
            approval=ON,
            deferred_tool_results=DeferredToolResults(approvals={"c1": ToolDenied("skipped")}),
        )

        last_request = model.requests[-1][-1]
        assert isinstance(last_request, ModelRequest)
        kinds = [type(part) for part in last_request.parts]
        assert kinds == [ToolReturnPart, UserPromptPart]
        assert ran == []

    @pytest.mark.asyncio
    async def test_a_paused_thread_refuses_a_run_that_does_not_answer_it(self, tmp_path: Path) -> None:
        ran: list[str] = []
        model = ScriptedModel([("GriptapeNodes_StartFlowRequest", {}, "c1")])
        runner = runner_with(tmp_path, model, ran)
        paused = await runner.run("Run the flow.", approval=ON)

        with pytest.raises(ValueError, match="waiting for approval"):
            await runner.run("Something else.", thread_id=paused.thread_id, approval=ON)
