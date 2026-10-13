"""Tests for the Claude Code harness's command line and stream parsing.

Records are shaped like real ``claude -p --output-format stream-json
--include-partial-messages`` output.
"""

from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Any

from griptape_nodes.agents.cli.base import (
    CliMCPServer,
    CliTurnContext,
    PromptImage,
    SessionStarted,
    TurnEnded,
)
from griptape_nodes.agents.cli.claude_code import ClaudeCodeHarness, ClaudeCodeStreamParser
from griptape_nodes.agents.harness import TextDelta, ThinkingDelta, ToolCall, ToolResult


def _harness() -> ClaudeCodeHarness:
    return ClaudeCodeHarness(workspace_root=Path("/ws"), storage=None, engine_mcp_url="http://localhost:1/mcp/")  # type: ignore[arg-type]


def _context(**overrides: Any) -> CliTurnContext:
    values: dict[str, Any] = {
        "prompt_text": "Build a flow",
        "images": [],
        "instructions": "Be brief.",
        "resume_session_id": None,
        "new_session_id": "new-id",
        "mcp_servers": [CliMCPServer(name="GriptapeNodes", transport="streamable_http", url="http://localhost:1/mcp/")],
        "model": "sonnet",
        "max_turns": 60,
        "workspace_root": Path("/ws"),
        "scratch_dir": Path("scratch"),
    }
    values.update(overrides)
    return CliTurnContext(**values)


def _flag(args: list[str], name: str) -> str:
    return args[args.index(name) + 1]


def test_new_session_is_started_with_the_chosen_id() -> None:
    """A new session uses the id the harness chose, with the turn's options."""
    invocation = _harness().build_invocation(_context())
    args = list(invocation.args)

    assert _flag(args, "--session-id") == "new-id"
    assert "--resume" not in args
    assert _flag(args, "--model") == "sonnet"
    assert _flag(args, "--max-turns") == "60"
    assert _flag(args, "--append-system-prompt") == "Be brief."
    assert _flag(args, "--permission-mode") == "bypassPermissions"
    assert invocation.env == {"CLAUDECODE": None}


def test_existing_session_is_resumed() -> None:
    """A known session is resumed rather than started."""
    args = list(_harness().build_invocation(_context(resume_session_id="old-id")).args)

    assert _flag(args, "--resume") == "old-id"
    assert "--session-id" not in args


def test_unset_options_are_left_to_claude() -> None:
    """Options with no value are left to Claude Code's defaults."""
    args = list(_harness().build_invocation(_context(model=None, max_turns=None, instructions="")).args)

    assert "--model" not in args
    assert "--max-turns" not in args
    assert "--append-system-prompt" not in args


def test_mcp_servers_are_translated_to_claude_config() -> None:
    """Engine MCP configs become Claude Code's, and unsupported transports are skipped."""
    servers = [
        CliMCPServer(name="GriptapeNodes", transport="streamable_http", url="http://localhost:1/mcp/"),
        CliMCPServer(name="files", transport="stdio", command="npx", args=["-y", "fs"], env={"K": "V"}),
        CliMCPServer(name="legacy", transport="sse", url="http://s/sse", headers={"A": "B"}),
        CliMCPServer(name="ws", transport="websocket", url="ws://x"),
    ]
    args = list(_harness().build_invocation(_context(mcp_servers=servers)).args)

    config = json.loads(_flag(args, "--mcp-config"))["mcpServers"]
    assert config == {
        "GriptapeNodes": {"type": "http", "url": "http://localhost:1/mcp/", "headers": {}},
        "files": {"type": "stdio", "command": "npx", "args": ["-y", "fs"], "env": {"K": "V"}},
        "legacy": {"type": "sse", "url": "http://s/sse", "headers": {"A": "B"}},
    }


def test_prompt_and_images_go_to_stdin_as_content_blocks() -> None:
    """The message and its images are sent on stdin as content blocks."""
    image = PromptImage(data=b"\x89PNG", media_type="image/png", path=Path("scratch/a.png"))
    invocation = _harness().build_invocation(_context(images=[image]))

    assert invocation.stdin is not None
    message = json.loads(invocation.stdin)
    assert message["type"] == "user"
    text, picture = message["message"]["content"]
    assert text == {"type": "text", "text": "Build a flow"}
    assert picture["source"] == {
        "type": "base64",
        "media_type": "image/png",
        "data": base64.b64encode(b"\x89PNG").decode(),
    }


def _feed(records: list[dict[str, Any]]) -> list[Any]:
    parser = ClaudeCodeStreamParser(normalize_tool_name=_harness().normalize_tool_name)
    return [event for record in records for event in parser.feed(record)]


def _stream(event: dict[str, Any]) -> dict[str, Any]:
    return {"type": "stream_event", "event": event, "parent_tool_use_id": None, "session_id": "s"}


def test_a_turn_with_a_tool_call_is_parsed_in_order() -> None:
    """A turn's session, thinking, tool call, result, text, and end come out in order."""
    events = _feed(
        [
            {"type": "system", "subtype": "init", "session_id": "s-1", "tools": ["Bash"]},
            _stream({"type": "message_start", "message": {"id": "m1"}}),
            _stream({"type": "content_block_delta", "delta": {"type": "thinking_delta", "thinking": "Hmm"}}),
            _stream({"type": "content_block_delta", "delta": {"type": "input_json_delta", "partial_json": "{"}}),
            {
                "type": "assistant",
                "message": {
                    "id": "m1",
                    "content": [
                        {"type": "thinking", "thinking": "Hmm"},
                        {
                            "type": "tool_use",
                            "id": "t1",
                            "name": "mcp__GriptapeNodes__CreateNodeRequest",
                            "input": {"node_type": "Agent"},
                        },
                    ],
                },
                "parent_tool_use_id": None,
            },
            {
                "type": "user",
                "message": {
                    "content": [
                        {"type": "tool_result", "tool_use_id": "t1", "content": [{"type": "text", "text": "ok"}]}
                    ]
                },
                "parent_tool_use_id": None,
            },
            _stream({"type": "message_start", "message": {"id": "m2"}}),
            _stream({"type": "content_block_delta", "delta": {"type": "text_delta", "text": "Created "}}),
            _stream({"type": "content_block_delta", "delta": {"type": "text_delta", "text": "it."}}),
            {"type": "assistant", "message": {"id": "m2", "content": [{"type": "text", "text": "Created it."}]}},
            {"type": "result", "subtype": "success", "is_error": False, "stop_reason": "end_turn", "result": "x"},
        ]
    )

    assert events == [
        SessionStarted(session_id="s-1"),
        ThinkingDelta(delta="Hmm"),
        ToolCall(tool_call_id="t1", tool_name="GriptapeNodes_CreateNodeRequest", args='{"node_type": "Agent"}'),
        ToolResult(tool_call_id="t1", tool_name="GriptapeNodes_CreateNodeRequest", content="ok"),
        TextDelta(delta="Created "),
        TextDelta(delta="it."),
        TurnEnded(),
    ]


def test_text_that_was_never_streamed_is_taken_from_the_message() -> None:
    """Text missing from the partial stream is taken from the complete message."""
    events = _feed([{"type": "assistant", "message": {"id": "m1", "content": [{"type": "text", "text": "Hi"}]}}])

    assert events == [TextDelta(delta="Hi")]


def test_subagent_records_are_skipped() -> None:
    """Subagent records don't reach the sidebar."""
    events = _feed(
        [
            {
                "type": "stream_event",
                "event": {"type": "content_block_delta", "delta": {"type": "text_delta", "text": "inner"}},
                "parent_tool_use_id": "task-1",
            }
        ]
    )

    assert events == []


def test_tool_errors_are_flagged() -> None:
    """A tool result Claude Code marks as an error is flagged."""
    events = _feed(
        [
            {"type": "assistant", "message": {"id": "m", "content": [{"type": "tool_use", "id": "t", "name": "Bash"}]}},
            {
                "type": "user",
                "message": {
                    "content": [{"type": "tool_result", "tool_use_id": "t", "content": "nope", "is_error": True}]
                },
            },
        ]
    )

    assert events[1] == ToolResult(tool_call_id="t", tool_name="Bash", content="nope", is_error=True)


def test_output_limit_and_turn_limit_mark_the_reply_truncated() -> None:
    """Hitting the output limit or the turn limit marks the reply truncated."""
    assert _feed([{"type": "result", "subtype": "success", "stop_reason": "max_tokens"}]) == [TurnEnded(truncated=True)]
    assert _feed([{"type": "result", "subtype": "error_max_turns", "is_error": True}]) == [TurnEnded(truncated=True)]


def test_failed_result_reports_claudes_error() -> None:
    """A failed result carries Claude Code's error text."""
    record = {
        "type": "result",
        "subtype": "error_during_execution",
        "is_error": True,
        "errors": ["No conversation found with session ID: x"],
        "result": None,
    }

    assert _feed([record]) == [TurnEnded(error="No conversation found with session ID: x")]
