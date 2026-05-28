"""Unit tests for `PydanticAgentRunner`.

These swap in `FunctionModel` so we exercise the persistence + streaming
plumbing without hitting Griptape Cloud.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest
from pydantic_ai import Agent
from pydantic_ai.messages import (
    ModelMessage,
    TextPart,
    ToolCallPart,
)
from pydantic_ai.models.function import AgentInfo, DeltaToolCall, FunctionModel

from griptape_nodes.agents.pydantic_ai.runner import (
    PydanticAgentRunner,
    RunEvent,
    TextDelta,
    ToolCall,
    ToolResult,
)
from griptape_nodes.agents.pydantic_ai.workspace_tools import WorkspaceToolsetConfig
from griptape_nodes.drivers.thread_storage.local_thread_storage_driver import LocalThreadStorageDriver

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Callable
    from pathlib import Path


def _runner_with_function_model(
    workspace: Path,
    threads_dir: Path,
    function: Callable[..., AsyncIterator[Any]],
) -> PydanticAgentRunner:
    """Build a runner whose Agent uses a FunctionModel instead of GriptapeCloudModel."""
    storage = LocalThreadStorageDriver(threads_dir, config_manager=None, secrets_manager=None)  # type: ignore[arg-type]
    runner = PydanticAgentRunner(
        model_name="test",
        api_key="dummy",
        workspace_root=workspace,
        storage=storage,
        instructions="Be concise.",
        workspace_config=WorkspaceToolsetConfig(workspace_root=workspace, shell_enabled=False),
    )
    new_agent: Agent[None, str] = Agent(FunctionModel(stream_function=function), instructions="Be concise.")
    runner._toolset.register_on(new_agent)
    runner._agent = new_agent
    return runner


@pytest.mark.asyncio
async def test_run_streams_tokens_and_persists_history(tmp_path: Path) -> None:
    """Tokens stream to the sink as they arrive and history persists to disk."""
    workspace = tmp_path / "ws"
    workspace.mkdir()
    threads_dir = tmp_path / "threads"

    async def stream(_messages: list[ModelMessage], _info: AgentInfo) -> AsyncIterator[str]:
        yield "Hi"
        yield " there"

    runner = _runner_with_function_model(workspace, threads_dir, stream)

    received: list[str] = []
    result = await runner.run("Greet me.", token_sink=received.append)

    assert result.output == "Hi there"
    assert "".join(received) == "Hi there"
    assert result.message_count >= 2  # noqa: PLR2004

    reloaded = runner.storage.load_history(result.thread_id)
    assert any(isinstance(p, TextPart) and "Hi there" in p.content for m in reloaded for p in getattr(m, "parts", []))


@pytest.mark.asyncio
async def test_history_carries_across_runs(tmp_path: Path) -> None:
    """Calling `run` with the same thread_id feeds prior history back to the model."""
    workspace = tmp_path / "ws"
    workspace.mkdir()
    threads_dir = tmp_path / "threads"

    seen_history: list[int] = []

    async def stream(messages: list[ModelMessage], _info: AgentInfo) -> AsyncIterator[str]:
        seen_history.append(len(messages))
        yield "ok"

    runner = _runner_with_function_model(workspace, threads_dir, stream)

    first = await runner.run("turn 1")
    second = await runner.run("turn 2", thread_id=first.thread_id)

    assert seen_history[0] < seen_history[1]
    assert first.thread_id == second.thread_id


@pytest.mark.asyncio
async def test_tool_call_round_trips_through_runner(tmp_path: Path) -> None:
    """A tool call from the model invokes the workspace tool and lands in history."""
    workspace = tmp_path / "ws"
    workspace.mkdir()
    (workspace / "data.txt").write_text("payload-7")
    threads_dir = tmp_path / "threads"

    call_count = 0

    async def stream(_messages: list[ModelMessage], _info: AgentInfo) -> AsyncIterator[Any]:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            yield {0: DeltaToolCall(name="read_file", json_args='{"path": "data.txt"}', tool_call_id="c1")}
            return
        for ch in "Got it.":
            yield ch

    runner = _runner_with_function_model(workspace, threads_dir, stream)
    result = await runner.run("Read data.txt and confirm.")
    assert "Got it." in result.output
    history = runner.storage.load_history(result.thread_id)
    assert any(
        isinstance(p, ToolCallPart) and p.tool_name == "read_file" for m in history for p in getattr(m, "parts", [])
    )


@pytest.mark.asyncio
async def test_event_sink_receives_text_tool_call_and_tool_result(tmp_path: Path) -> None:
    """The structured event sink sees text deltas, tool calls, and tool results.

    The chat sidebar drives tool-call cards and the streaming text bubble off
    these events, so this guards the wire format.
    """
    workspace = tmp_path / "ws"
    workspace.mkdir()
    (workspace / "data.txt").write_text("payload-7")
    threads_dir = tmp_path / "threads"

    call_count = 0

    async def stream(_messages: list[ModelMessage], _info: AgentInfo) -> AsyncIterator[Any]:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            yield {0: DeltaToolCall(name="read_file", json_args='{"path": "data.txt"}', tool_call_id="c1")}
            return
        for ch in "Got it.":
            yield ch

    runner = _runner_with_function_model(workspace, threads_dir, stream)

    events: list[RunEvent] = []
    await runner.run("Read data.txt and confirm.", event_sink=events.append)

    tool_calls = [e for e in events if isinstance(e, ToolCall)]
    tool_results = [e for e in events if isinstance(e, ToolResult)]
    text_deltas = [e for e in events if isinstance(e, TextDelta)]

    assert len(tool_calls) == 1
    assert tool_calls[0].tool_name == "read_file"
    assert tool_calls[0].tool_call_id == "c1"
    assert '"path": "data.txt"' in tool_calls[0].args

    assert len(tool_results) == 1
    assert tool_results[0].tool_call_id == "c1"
    assert "payload-7" in tool_results[0].content
    assert tool_results[0].is_error is False

    assert "".join(d.delta for d in text_deltas) == "Got it."
