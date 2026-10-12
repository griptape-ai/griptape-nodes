"""Tests for the approval card round trip through `AgentManager`.

A real `PydanticAgentRunner` on real thread storage talks to a scripted
`FunctionModel`, so pausing, resuming, grants, and denials are checked against
the history the editor would reload, while the engine around the manager is a
stand-in.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING, Any

import pytest
from pydantic_ai.messages import ModelRequest, ToolReturnPart, UserPromptPart

from griptape_nodes.agents.pydantic_ai.mcp_toolset_cache import MCPToolsetCache
from griptape_nodes.agents.pydantic_ai.tool_approval import TOOL_DENIED_BY_NEW_MESSAGE, TOOL_DENIED_BY_USER_MESSAGE
from griptape_nodes.drivers.thread_storage.local_thread_storage_driver import LocalThreadStorageDriver
from griptape_nodes.retained_mode.events.agent_events import (
    ClearToolGrantsRequest,
    ClearToolGrantsResultFailure,
    ClearToolGrantsResultSuccess,
    ResolveToolApprovalsRequest,
    RunAgentRequest,
    RunAgentResultFailure,
    RunAgentResultSuccess,
    ToolApprovalDecision,
)
from griptape_nodes.retained_mode.events.budget_events import GetAttributionContextResultFailure
from griptape_nodes.retained_mode.events.mcp_events import GetEnabledMCPServersResultSuccess
from griptape_nodes.retained_mode.managers.agent_manager import AgentManager, ComposedPrompt
from tests.unit.agents.pydantic_ai.test_tool_approval import ScriptedModel, runner_with

if TYPE_CHECKING:
    from pathlib import Path

    from griptape_nodes.agents.pydantic_ai.runner import PydanticAgentRunner
    from griptape_nodes.retained_mode.events.agent_events import RunAgentRequestArtifact

_AGENT_MANAGER_MODULE = "griptape_nodes.retained_mode.managers.agent_manager"

START = "GriptapeNodes_StartFlowRequest"
LIST = "GriptapeNodes_ListFlowsInCurrentContextRequest"
BATCH = "GriptapeNodes_EventRequestBatch"


async def _plain_prompt(text: str, _url_artifacts: list[RunAgentRequestArtifact]) -> ComposedPrompt:
    return ComposedPrompt(live=text, persist=text)


async def _no_attribution(_request: object) -> GetAttributionContextResultFailure:
    return GetAttributionContextResultFailure(result_details="no project")


class _Harness:
    """An `AgentManager` wired to one runner, with tool approval switched on or off."""

    def __init__(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, model: ScriptedModel, *, approval_on: bool
    ) -> None:
        self.ran: list[str] = []
        self.model = model
        self.runner: PydanticAgentRunner = runner_with(tmp_path, model, self.ran)
        self.storage: LocalThreadStorageDriver = self.runner.storage  # type: ignore[assignment]
        self.manager = _manager_on(self.storage, self.runner, monkeypatch, approval_on=approval_on)

    def thread(self) -> str:
        thread_id, _ = self.storage.create_thread()
        return thread_id

    async def send(self, thread_id: str, text: str) -> RunAgentResultSuccess:
        result = await self.manager.on_handle_run_agent_request(
            RunAgentRequest(input=text, url_artifacts=[], thread_id=thread_id)
        )
        assert isinstance(result, RunAgentResultSuccess), result
        return result

    async def resolve(self, thread_id: str, **decisions: str) -> Any:
        return await self.manager.on_handle_resolve_tool_approvals_request(
            ResolveToolApprovalsRequest(
                thread_id=thread_id,
                decisions=[ToolApprovalDecision(tool_call_id=key, decision=value) for key, value in decisions.items()],
            )
        )

    def tool_returns(self, thread_id: str) -> dict[str, str]:
        return {
            part.tool_call_id: str(part.content)
            for message in self.storage.load_history(thread_id)
            if isinstance(message, ModelRequest)
            for part in message.parts
            if isinstance(part, ToolReturnPart)
        }


def _manager_on(
    storage: LocalThreadStorageDriver,
    runner: PydanticAgentRunner,
    monkeypatch: pytest.MonkeyPatch,
    *,
    approval_on: bool,
) -> AgentManager:
    config = {"beta_features.agent_tool_approval": approval_on}
    manager = AgentManager.__new__(AgentManager)
    manager._active_runs = {}
    manager._mcp_toolsets = MCPToolsetCache()
    manager._thread_storage = storage
    manager._providers = []
    manager._active_provider_name = "griptape_cloud"
    monkeypatch.setattr(manager, "_build_runner", lambda *_a, **_k: runner)
    monkeypatch.setattr(_AGENT_MANAGER_MODULE + "._compose_prompt", _plain_prompt)
    manager._engine = SimpleNamespace(  # type: ignore[assignment]
        event_manager=SimpleNamespace(put_event=lambda _e: None),
        handle_request=lambda _r: GetEnabledMCPServersResultSuccess(servers={}, result_details="none"),
        ahandle_request=_no_attribution,
        config_manager=SimpleNamespace(get_config_value=lambda key, **_kw: config.get(key)),
    )
    return manager


@pytest.mark.asyncio
class TestPausing:
    async def test_approval_off_never_pauses(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        harness = _Harness(tmp_path, monkeypatch, ScriptedModel([(START, {}, "c1")], "Started."), approval_on=False)

        result = await harness.send(harness.thread(), "Run the flow.")

        assert harness.ran == ["StartFlowRequest"]
        assert result.output["pending_approvals"] == []
        assert "approval" not in (harness.model.requests[0][0].instructions or "")  # type: ignore[union-attr]

    async def test_a_gated_call_pauses_with_a_card_to_answer(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        harness = _Harness(
            tmp_path, monkeypatch, ScriptedModel([(START, {"flow_name": "main"}, "c1")]), approval_on=True
        )

        result = await harness.send(harness.thread(), "Run the flow.")

        assert harness.ran == []
        assert result.output["pending_approvals"] == [
            {"tool_call_id": "c1", "tool_name": START, "args": '{"flow_name": "main"}', "grant_keys": [START]}
        ]
        assert result.output["cancelled"] is False
        assert result.output["truncated"] is False

    async def test_the_agent_is_told_to_answer_questions_in_text(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        harness = _Harness(tmp_path, monkeypatch, ScriptedModel("It wires nodes."), approval_on=True)

        await harness.send(harness.thread(), "How does this work?")

        instructions = harness.model.requests[0][0].instructions or ""  # type: ignore[union-attr]
        assert "need the user's approval" in instructions
        assert "answer in text" in instructions


@pytest.mark.asyncio
class TestResolving:
    async def test_approve_once_runs_it_and_remembers_nothing(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        harness = _Harness(
            tmp_path, monkeypatch, ScriptedModel([(START, {}, "c1")], "Started.", [(START, {}, "c2")]), approval_on=True
        )
        thread_id = harness.thread()
        await harness.send(thread_id, "Run the flow.")

        result = await harness.resolve(thread_id, c1="approve_once")

        assert isinstance(result, RunAgentResultSuccess)
        assert result.output["text"] == "Started."
        assert result.output["pending_approvals"] == []
        assert harness.ran == ["StartFlowRequest"]
        assert harness.storage.get_thread_metadata(thread_id).tool_grants == []
        # The next time, it asks again.
        again = await harness.send(thread_id, "Run it again.")
        assert [card["tool_call_id"] for card in again.output["pending_approvals"]] == ["c2"]

    async def test_approve_for_conversation_stops_asking_in_this_thread(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        harness = _Harness(
            tmp_path,
            monkeypatch,
            ScriptedModel([(START, {}, "c1")], "Started.", [(START, {}, "c2")], "Started again."),
            approval_on=True,
        )
        thread_id = harness.thread()
        await harness.send(thread_id, "Run the flow.")

        await harness.resolve(thread_id, c1="approve_for_conversation")
        again = await harness.send(thread_id, "Run it again.")

        assert harness.storage.get_thread_metadata(thread_id).tool_grants == [START]
        assert again.output["pending_approvals"] == []
        assert harness.ran == ["StartFlowRequest", "StartFlowRequest"]

    async def test_deny_tells_the_agent_not_to_retry(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        harness = _Harness(tmp_path, monkeypatch, ScriptedModel([(START, {}, "c1")], "Understood."), approval_on=True)
        thread_id = harness.thread()
        await harness.send(thread_id, "Run the flow.")

        result = await harness.resolve(thread_id, c1="deny")

        assert isinstance(result, RunAgentResultSuccess)
        assert harness.ran == []
        assert harness.tool_returns(thread_id)["c1"] == TOOL_DENIED_BY_USER_MESSAGE

    async def test_a_conversation_grant_also_approves_a_covered_sibling(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        batch_args = {"requests": [{"request_type": "StartFlowRequest", "request": {}}]}
        model = ScriptedModel([(LIST, {}, "c0"), (START, {}, "c1"), (BATCH, batch_args, "c2")], "All done.")
        harness = _Harness(tmp_path, monkeypatch, model, approval_on=True)
        thread_id = harness.thread()
        paused = await harness.send(thread_id, "Run everything.")
        assert [card["tool_call_id"] for card in paused.output["pending_approvals"]] == ["c1", "c2"]

        result = await harness.resolve(thread_id, c1="approve_for_conversation")

        assert isinstance(result, RunAgentResultSuccess)
        assert result.output["text"] == "All done."
        # The read-only call ran once, before the pause, and is not run again.
        assert harness.ran == ["ListFlowsInCurrentContextRequest", "StartFlowRequest", "EventRequestBatch"]

    async def test_survives_an_engine_restart(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        harness = _Harness(tmp_path, monkeypatch, ScriptedModel([(START, {}, "c1")], "Started."), approval_on=True)
        thread_id = harness.thread()
        await harness.send(thread_id, "Run the flow.")

        reopened = LocalThreadStorageDriver(harness.storage.threads_directory, None, None)  # type: ignore[arg-type]
        harness.runner.storage = reopened
        restarted = _manager_on(reopened, harness.runner, monkeypatch, approval_on=True)
        result = await restarted.on_handle_resolve_tool_approvals_request(
            ResolveToolApprovalsRequest(
                thread_id=thread_id, decisions=[ToolApprovalDecision(tool_call_id="c1", decision="approve_once")]
            )
        )

        assert isinstance(result, RunAgentResultSuccess)
        assert harness.ran == ["StartFlowRequest"]


@pytest.mark.asyncio
class TestResolvingFailures:
    @staticmethod
    async def _paused(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[_Harness, str]:
        model = ScriptedModel([(START, {}, "c1"), (START, {"flow_name": "other"}, "c2")])
        harness = _Harness(tmp_path, monkeypatch, model, approval_on=True)
        thread_id = harness.thread()
        await harness.send(thread_id, "Run both.")
        return harness, thread_id

    async def test_a_call_left_undecided_fails(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        harness, thread_id = await self._paused(tmp_path, monkeypatch)

        result = await harness.resolve(thread_id, c1="approve_once")

        assert isinstance(result, RunAgentResultFailure)
        assert "still waiting for you to approve or deny" in result.error["message"]
        assert harness.ran == []

    async def test_an_unknown_call_fails(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        harness, thread_id = await self._paused(tmp_path, monkeypatch)

        result = await harness.resolve(thread_id, c1="approve_once", c2="approve_once", nope="deny")

        assert isinstance(result, RunAgentResultFailure)
        assert "not waiting on that call" in result.error["message"]

    async def test_an_unknown_choice_fails_without_saving_grants(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        harness, thread_id = await self._paused(tmp_path, monkeypatch)

        result = await harness.resolve(thread_id, c1="approve_for_conversation", c2="maybe")

        assert isinstance(result, RunAgentResultFailure)
        assert "'maybe' is not a choice" in result.error["message"]
        assert harness.storage.get_thread_metadata(thread_id).tool_grants == []

    async def test_a_thread_that_is_not_paused_fails(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        harness = _Harness(tmp_path, monkeypatch, ScriptedModel("Hi."), approval_on=True)
        thread_id = harness.thread()
        await harness.send(thread_id, "Hello.")

        result = await harness.resolve(thread_id, c1="approve_once")

        assert isinstance(result, RunAgentResultFailure)
        assert "not waiting for approval" in result.error["message"]

    async def test_a_missing_thread_fails(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        harness = _Harness(tmp_path, monkeypatch, ScriptedModel(), approval_on=True)

        result = await harness.resolve("missing", c1="approve_once")

        assert isinstance(result, RunAgentResultFailure)
        assert "does not exist" in result.error["message"]


@pytest.mark.asyncio
async def test_a_new_message_declines_what_was_pending(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Sending a message instead of answering the card declines it, and the agent answers the message."""
    harness = _Harness(tmp_path, monkeypatch, ScriptedModel([(START, {}, "c1")], "Here is how."), approval_on=True)
    thread_id = harness.thread()
    await harness.send(thread_id, "Run the flow.")

    result = await harness.send(thread_id, "Wait, how does this work?")

    assert result.output["text"] == "Here is how."
    assert result.output["pending_approvals"] == []
    assert harness.ran == []
    assert harness.tool_returns(thread_id)["c1"] == TOOL_DENIED_BY_NEW_MESSAGE
    # The decline and the new message reach the model together.
    last_request = harness.model.requests[-1][-1]
    assert isinstance(last_request, ModelRequest)
    assert [type(part) for part in last_request.parts] == [ToolReturnPart, UserPromptPart]


class TestClearToolGrants:
    @pytest.mark.asyncio
    async def test_clearing_makes_the_agent_ask_again(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        harness = _Harness(
            tmp_path, monkeypatch, ScriptedModel([(START, {}, "c1")], "Started.", [(START, {}, "c2")]), approval_on=True
        )
        thread_id = harness.thread()
        await harness.send(thread_id, "Run the flow.")
        await harness.resolve(thread_id, c1="approve_for_conversation")

        cleared = harness.manager.on_handle_clear_tool_grants_request(ClearToolGrantsRequest(thread_id=thread_id))
        again = await harness.send(thread_id, "Run it again.")

        assert isinstance(cleared, ClearToolGrantsResultSuccess)
        assert cleared.thread_id == thread_id
        assert harness.storage.get_thread_metadata(thread_id).tool_grants == []
        assert [card["tool_call_id"] for card in again.output["pending_approvals"]] == ["c2"]

    def test_a_missing_thread_fails(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        harness = _Harness(tmp_path, monkeypatch, ScriptedModel(), approval_on=True)

        result = harness.manager.on_handle_clear_tool_grants_request(ClearToolGrantsRequest(thread_id="missing"))

        assert isinstance(result, ClearToolGrantsResultFailure)
