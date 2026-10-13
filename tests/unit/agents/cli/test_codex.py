"""Tests for the Codex harness's command line and stream parsing.

Records are shaped like real ``codex exec --json`` output (codex-cli 0.162): the
``thread.started``, ``error`` and ``turn.failed`` records were captured from a run
without credentials, and the item records follow ``ThreadItemDetails`` in the
openai/codex repository (``codex-rs/exec/src/exec_events.rs``).
"""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any

from griptape_nodes.agents.cli.base import (
    CliMCPServer,
    CliTurnContext,
    PromptImage,
    SessionStarted,
    TurnEnded,
)
from griptape_nodes.agents.cli.codex import CodexHarness, CodexStreamParser
from griptape_nodes.agents.harness import TextDelta, ThinkingDelta, ToolCall, ToolResult


def _harness() -> CodexHarness:
    return CodexHarness(workspace_root=Path("/ws"), storage=None, engine_mcp_url="http://localhost:1/mcp/")  # type: ignore[arg-type]


def _context(**overrides: Any) -> CliTurnContext:
    values: dict[str, Any] = {
        "prompt_text": "Build a flow",
        "images": [],
        "instructions": 'Be "brief".\nThanks.',
        "resume_session_id": None,
        "new_session_id": "new-id",
        "mcp_servers": [CliMCPServer(name="GriptapeNodes", transport="streamable_http", url="http://localhost:1/mcp/")],
        "model": "gpt-5",
        "max_turns": 60,
        "workspace_root": Path("/ws"),
        "scratch_dir": Path("scratch"),
    }
    values.update(overrides)
    return CliTurnContext(**values)


def _overrides(args: list[str]) -> dict[str, Any]:
    """Return the ``-c key=value`` overrides, parsed as Codex parses them: the value is TOML."""
    overrides: dict[str, Any] = {}
    for index, arg in enumerate(args):
        if arg == "-c":
            key, _, value = args[index + 1].partition("=")
            overrides[key] = tomllib.loads(f"v = {value}")["v"]
    return overrides


def test_new_session_runs_exec_with_the_prompt_on_stdin() -> None:
    """A new session runs `codex exec` with auto-approval, and the prompt goes on stdin."""
    invocation = _harness().build_invocation(_context())
    args = list(invocation.args)

    assert args[0] == "exec"
    assert "resume" not in args
    assert "--json" in args
    assert "--dangerously-bypass-approvals-and-sandbox" in args
    assert args[args.index("--model") + 1] == "gpt-5"
    assert "--" not in args
    assert invocation.stdin == b"Build a flow"
    assert invocation.env == {}


def test_existing_session_is_resumed_with_the_prompt_read_from_stdin() -> None:
    """A known session is resumed, with its id and a dash for stdin after the options."""
    args = list(_harness().build_invocation(_context(resume_session_id="thread-1")).args)

    assert args[:2] == ["exec", "resume"]
    assert args[-3:] == ["--", "thread-1", "-"]
    assert args.index("--json") < args.index("--")


def test_unset_options_are_left_to_codex() -> None:
    """Options with no value are left to Codex's defaults."""
    args = list(_harness().build_invocation(_context(model=None, instructions="")).args)

    assert "--model" not in args
    assert "developer_instructions" not in " ".join(args)


def test_instructions_become_developer_instructions() -> None:
    """Instructions are passed as a TOML string that survives quotes and newlines."""
    overrides = _overrides(list(_harness().build_invocation(_context()).args))

    assert overrides["developer_instructions"] == 'Be "brief".\nThanks.'


def test_mcp_servers_are_translated_to_codex_config() -> None:
    """Engine MCP configs become mcp_servers tables, and unsupported transports are skipped."""
    servers = [
        CliMCPServer(name="GriptapeNodes", transport="streamable_http", url="http://localhost:1/mcp/"),
        CliMCPServer(name="files", transport="stdio", command="npx", args=["-y", "fs"], env={"K": "V"}, cwd="/data"),
        CliMCPServer(name="remote api", transport="streamable_http", url="http://s/mcp", headers={"X-Key": "B"}),
        CliMCPServer(name="legacy", transport="sse", url="http://s/sse"),
    ]
    overrides = _overrides(list(_harness().build_invocation(_context(mcp_servers=servers)).args))

    approve = {"default_tools_approval_mode": "approve"}
    assert {key: value for key, value in overrides.items() if key.startswith("mcp_servers.")} == {
        "mcp_servers.GriptapeNodes": {"url": "http://localhost:1/mcp/", **approve},
        "mcp_servers.files": {"command": "npx", "args": ["-y", "fs"], "env": {"K": "V"}, "cwd": "/data", **approve},
        "mcp_servers.remote_api": {"url": "http://s/mcp", "http_headers": {"X-Key": "B"}, **approve},
    }


def test_images_are_attached_before_the_positional_arguments() -> None:
    """Each image is attached with --image, ahead of the `--` so it doesn't take the session id."""
    images = [
        PromptImage(data=b"1", media_type="image/png", path=Path("scratch/a.png")),
        PromptImage(data=b"2", media_type="image/png", path=Path("scratch/b.png")),
    ]
    args = list(_harness().build_invocation(_context(images=images, resume_session_id="thread-1")).args)

    assert [args[i + 1] for i, arg in enumerate(args) if arg == "--image"] == ["scratch/a.png", "scratch/b.png"]
    assert args.index("--image") < args.index("--")


def test_mcp_tool_names_match_the_names_codex_gives_them() -> None:
    """Codex names MCP tools mcp__server__tool."""
    assert _harness().mcp_tool_name("GriptapeNodes", "CreateNodeRequest") == "mcp__GriptapeNodes__CreateNodeRequest"


def _feed(records: list[dict[str, Any]]) -> list[Any]:
    parser = CodexStreamParser()
    return [event for record in records for event in parser.feed(record)]


def test_a_turn_with_commands_and_tool_calls_is_parsed_in_order() -> None:
    """A turn's thread, reasoning, command, MCP call, patch, message, and end come out in order."""
    events = _feed(
        [
            {"type": "thread.started", "thread_id": "01a136b1-ebb6-72a1-ab56-134441f2dbea"},
            {"type": "turn.started"},
            {"type": "item.completed", "item": {"id": "item_0", "type": "reasoning", "text": "**Listing files**"}},
            {
                "type": "item.started",
                "item": {
                    "id": "item_1",
                    "type": "command_execution",
                    "command": "bash -lc ls",
                    "aggregated_output": "",
                    "exit_code": None,
                    "status": "in_progress",
                },
            },
            {
                "type": "item.completed",
                "item": {
                    "id": "item_1",
                    "type": "command_execution",
                    "command": "bash -lc ls",
                    "aggregated_output": "a.py\nb.py\n",
                    "exit_code": 0,
                    "status": "completed",
                },
            },
            {
                "type": "item.started",
                "item": {
                    "id": "item_2",
                    "type": "mcp_tool_call",
                    "server": "GriptapeNodes",
                    "tool": "CreateNodeRequest",
                    "arguments": {"node_type": "Agent"},
                    "result": None,
                    "error": None,
                    "status": "in_progress",
                },
            },
            {
                "type": "item.completed",
                "item": {
                    "id": "item_2",
                    "type": "mcp_tool_call",
                    "server": "GriptapeNodes",
                    "tool": "CreateNodeRequest",
                    "arguments": {"node_type": "Agent"},
                    "result": {"content": [{"type": "text", "text": "ok"}], "structured_content": None},
                    "error": None,
                    "status": "completed",
                },
            },
            {
                "type": "item.completed",
                "item": {
                    "id": "item_3",
                    "type": "file_change",
                    "changes": [{"path": "/ws/a.py", "kind": "update"}],
                    "status": "completed",
                },
            },
            {"type": "item.completed", "item": {"id": "item_4", "type": "agent_message", "text": "Done."}},
            {"type": "turn.completed", "usage": {"input_tokens": 10, "output_tokens": 2}},
        ]
    )

    assert events == [
        SessionStarted(session_id="01a136b1-ebb6-72a1-ab56-134441f2dbea"),
        ThinkingDelta(delta="**Listing files**"),
        ToolCall(tool_call_id="item_1", tool_name="shell", args='{"command": "bash -lc ls"}'),
        ToolResult(tool_call_id="item_1", tool_name="shell", content="a.py\nb.py\n"),
        ToolCall(tool_call_id="item_2", tool_name="GriptapeNodes_CreateNodeRequest", args='{"node_type": "Agent"}'),
        ToolResult(tool_call_id="item_2", tool_name="GriptapeNodes_CreateNodeRequest", content="ok"),
        ToolCall(
            tool_call_id="item_3", tool_name="apply_patch", args='{"changes": [{"path": "/ws/a.py", "kind": "update"}]}'
        ),
        ToolResult(tool_call_id="item_3", tool_name="apply_patch", content="update /ws/a.py"),
        TextDelta(delta="Done."),
        TurnEnded(),
    ]


def test_failed_commands_and_tool_calls_are_flagged() -> None:
    """A failed command and a failed MCP call are flagged as errors."""
    events = _feed(
        [
            {
                "type": "item.completed",
                "item": {
                    "id": "item_1",
                    "type": "command_execution",
                    "command": "false",
                    "aggregated_output": "",
                    "exit_code": 1,
                    "status": "failed",
                },
            },
            {
                "type": "item.completed",
                "item": {
                    "id": "item_2",
                    "type": "mcp_tool_call",
                    "server": "demo",
                    "tool": "fail_tool",
                    "arguments": {},
                    "result": None,
                    "error": {"message": "boom"},
                    "status": "failed",
                },
            },
        ]
    )

    assert events[1] == ToolResult(tool_call_id="item_1", tool_name="shell", content="", is_error=True)
    assert events[3] == ToolResult(tool_call_id="item_2", tool_name="demo_fail_tool", content="boom", is_error=True)


def test_progress_errors_and_other_items_are_skipped() -> None:
    """Reconnect notes, to-do lists, and subagent calls don't reach the sidebar."""
    events = _feed(
        [
            {"type": "error", "message": "Reconnecting... 2/5 (unexpected status 401 Unauthorized)"},
            {"type": "item.completed", "item": {"id": "item_0", "type": "error", "message": "Falling back to HTTPS"}},
            {"type": "item.updated", "item": {"id": "item_1", "type": "todo_list", "items": []}},
            {
                "type": "item.started",
                "item": {"id": "item_2", "type": "collab_tool_call", "tool": "spawn_agent", "status": "in_progress"},
            },
        ]
    )

    assert events == []


def test_failed_turn_reports_codexs_error() -> None:
    """A failed turn carries Codex's error text."""
    message = "unexpected status 401 Unauthorized: Missing bearer or basic authentication in header"

    assert _feed([{"type": "error", "message": message}, {"type": "turn.failed", "error": {"message": message}}]) == [
        TurnEnded(error=message)
    ]
