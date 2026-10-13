"""Fixtures follow OpenCode 1.19.

The ``error`` record was captured without credentials. Parts follow ``TextPart``,
``ReasoningPart``, ``ToolPart`` and ``StepFinishPart`` in anomalyco/opencode's
``packages/sdk/js/src/gen/types.gen.ts``; the emitter is ``packages/opencode/src/cli/cmd/run.ts``.
"""

from __future__ import annotations

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
from griptape_nodes.agents.cli.opencode import OpenCodeHarness, OpenCodeStreamParser
from griptape_nodes.agents.harness import TextDelta, ThinkingDelta, ToolCall, ToolResult


def _harness() -> OpenCodeHarness:
    return OpenCodeHarness(workspace_root=Path("/ws"), storage=None, engine_mcp_url="http://localhost:1/mcp/")  # type: ignore[arg-type]


def _context(scratch_dir: Path, **overrides: Any) -> CliTurnContext:
    values: dict[str, Any] = {
        "prompt_text": "Build a flow",
        "images": [],
        "instructions": "Be brief.",
        "resume_session_id": None,
        "new_session_id": "new-id",
        "mcp_servers": [CliMCPServer(name="GriptapeNodes", transport="streamable_http", url="http://localhost:1/mcp/")],
        "model": "anthropic/claude-sonnet-4-5",
        "max_turns": 60,
        "workspace_root": Path("/ws"),
        "scratch_dir": scratch_dir,
    }
    values.update(overrides)
    return CliTurnContext(**values)


def _flag(args: list[str], name: str) -> str:
    return args[args.index(name) + 1]


def _config(env: dict[str, str | None]) -> dict[str, Any]:
    config = env["OPENCODE_CONFIG_CONTENT"]
    assert config is not None
    return json.loads(config)


def test_new_session_runs_json_with_auto_approval(tmp_path: Path) -> None:
    """Run with JSON output, auto-approval, thinking, and stdin text."""
    invocation = _harness().build_invocation(_context(tmp_path))
    args = list(invocation.args)

    assert args[:4] == ["run", "--format", "json", "--auto"]
    assert "--thinking" in args
    assert "--session" not in args
    assert _flag(args, "--model") == "anthropic/claude-sonnet-4-5"
    assert invocation.stdin == b"Build a flow"


def test_existing_session_is_resumed(tmp_path: Path) -> None:
    """Pass the existing session ID."""
    args = list(_harness().build_invocation(_context(tmp_path, resume_session_id="ses_abc")).args)

    assert _flag(args, "--session") == "ses_abc"


def test_unset_options_are_left_to_opencode(tmp_path: Path) -> None:
    """Omit unset model and instruction options."""
    invocation = _harness().build_invocation(_context(tmp_path, model=None, instructions=""))

    assert "--model" not in invocation.args
    assert "instructions" not in _config(dict(invocation.env))


def test_instructions_are_listed_as_a_file_in_the_inline_config(tmp_path: Path) -> None:
    """Reference scratch-file instructions in inline config."""
    config = _config(dict(_harness().build_invocation(_context(tmp_path)).env))

    assert config["instructions"] == [str(tmp_path / "gtn-instructions.md")]
    assert (tmp_path / "gtn-instructions.md").read_text() == "Be brief."


def test_mcp_servers_are_translated_to_opencode_config(tmp_path: Path) -> None:
    """Translate local and remote MCP transports; skip unsupported ones."""
    servers = [
        CliMCPServer(name="GriptapeNodes", transport="streamable_http", url="http://localhost:1/mcp/"),
        CliMCPServer(name="files", transport="stdio", command="npx", args=["-y", "fs"], env={"K": "V"}),
        CliMCPServer(name="legacy api", transport="sse", url="http://s/sse", headers={"A": "B"}),
        CliMCPServer(name="ws", transport="websocket", url="ws://x"),
    ]
    config = _config(dict(_harness().build_invocation(_context(tmp_path, mcp_servers=servers)).env))

    assert config["mcp"] == {
        "GriptapeNodes": {"type": "remote", "url": "http://localhost:1/mcp/", "headers": {}, "enabled": True},
        "files": {"type": "local", "command": ["npx", "-y", "fs"], "environment": {"K": "V"}, "enabled": True},
        "legacy_api": {"type": "remote", "url": "http://s/sse", "headers": {"A": "B"}, "enabled": True},
    }


def test_images_are_attached_as_files_after_the_other_options(tmp_path: Path) -> None:
    """``--file`` consumes multiple values, so it must follow the other options."""
    images = [PromptImage(data=b"1", media_type="image/png", path=tmp_path / "a.png")]
    args = list(_harness().build_invocation(_context(tmp_path, images=images, resume_session_id="ses_abc")).args)

    assert args[-2:] == ["--file", str(tmp_path / "a.png")]


def test_mcp_tool_names_match_the_names_opencode_gives_them() -> None:
    """Match OpenCode's punctuation-normalized MCP names."""
    harness = _harness()

    assert harness.mcp_tool_name("GriptapeNodes", "CreateNodeRequest") == "GriptapeNodes_CreateNodeRequest"
    assert harness.mcp_tool_name("my server", "get.thing") == "my_server_get_thing"
    assert harness.normalize_tool_name("GriptapeNodes_CreateNodeRequest") == "GriptapeNodes_CreateNodeRequest"


def _feed(records: list[dict[str, Any]]) -> list[Any]:
    parser = OpenCodeStreamParser()
    return [event for record in records for event in parser.feed(record)]


def _record(record_type: str, part: dict[str, Any], session_id: str = "ses_1") -> dict[str, Any]:
    return {"type": record_type, "timestamp": 1791919425619, "sessionID": session_id, "part": part}


def test_a_turn_with_a_tool_call_is_parsed_in_order() -> None:
    """Preserve event order across tool-calling steps."""
    events = _feed(
        [
            _record("step_start", {"id": "prt_1", "type": "step-start"}),
            _record(
                "reasoning", {"id": "prt_2", "type": "reasoning", "text": "Need a node", "time": {"start": 1, "end": 2}}
            ),
            _record(
                "tool_use",
                {
                    "id": "prt_3",
                    "type": "tool",
                    "callID": "call_1",
                    "tool": "GriptapeNodes_CreateNodeRequest",
                    "state": {
                        "status": "completed",
                        "input": {"node_type": "Agent"},
                        "output": "ok",
                        "title": "CreateNodeRequest",
                        "metadata": {},
                        "time": {"start": 1, "end": 2},
                    },
                },
            ),
            _record("step_finish", {"id": "prt_4", "type": "step-finish", "reason": "tool-calls", "cost": 0}),
            _record("step_start", {"id": "prt_5", "type": "step-start"}),
            _record("text", {"id": "prt_6", "type": "text", "text": "Created it.", "time": {"start": 1, "end": 2}}),
            _record("step_finish", {"id": "prt_7", "type": "step-finish", "reason": "stop", "cost": 0}),
        ]
    )

    assert events == [
        SessionStarted(session_id="ses_1"),
        ThinkingDelta(delta="Need a node"),
        ToolCall(tool_call_id="call_1", tool_name="GriptapeNodes_CreateNodeRequest", args='{"node_type": "Agent"}'),
        ToolResult(tool_call_id="call_1", tool_name="GriptapeNodes_CreateNodeRequest", content="ok"),
        TextDelta(delta="Created it."),
        TurnEnded(),
    ]


def test_parts_reported_twice_are_reported_once() -> None:
    """Deduplicate repeated parts."""
    part = {"id": "prt_6", "type": "text", "text": "Hi", "time": {"start": 1, "end": 2}}

    assert _feed([_record("text", part), _record("text", part)]) == [
        SessionStarted(session_id="ses_1"),
        TextDelta(delta="Hi"),
    ]


def test_synthetic_text_is_skipped() -> None:
    """Text OpenCode adds on the user's behalf is not the agent's reply."""
    part = {"id": "prt_6", "type": "text", "text": "Called the Read tool", "synthetic": True}

    assert _feed([_record("text", part)]) == [SessionStarted(session_id="ses_1")]


def test_tool_errors_are_flagged() -> None:
    """Preserve tool error messages and flags."""
    events = _feed(
        [
            _record(
                "tool_use",
                {
                    "id": "prt_3",
                    "type": "tool",
                    "callID": "call_1",
                    "tool": "bash",
                    "state": {
                        "status": "error",
                        "input": {"command": "false"},
                        "error": "exit 1",
                        "time": {"start": 1, "end": 2},
                    },
                },
            )
        ]
    )

    assert events[2] == ToolResult(tool_call_id="call_1", tool_name="bash", content="exit 1", is_error=True)


def test_output_limit_marks_the_reply_truncated() -> None:
    """Treat the final step's output limit as truncation."""
    events = _feed([_record("step_finish", {"id": "prt_7", "type": "step-finish", "reason": "length"})])

    assert events[1] == TurnEnded(truncated=True)


def test_error_record_reports_opencodes_error() -> None:
    """Keep errors when a later step finishes."""
    error = {"name": "UnknownError", "data": {"message": "Unexpected server error. Check server logs for details."}}
    events = _feed(
        [
            {"type": "error", "timestamp": 1791919425619, "sessionID": "ses_1", "error": error},
            _record("step_finish", {"id": "prt_7", "type": "step-finish", "reason": "stop"}),
        ]
    )

    expected = TurnEnded(error="Unexpected server error. Check server logs for details.")
    assert events == [SessionStarted(session_id="ses_1"), expected, expected]


def test_the_first_of_several_errors_is_the_one_reported() -> None:
    """Keep the specific error rather than its generic follow-up."""
    first = {"name": "UnknownError", "data": {"message": "Model not found: x/y."}}
    second = {"name": "UnknownError", "data": {"message": "Unexpected server error."}}
    events = _feed(
        [
            {"type": "error", "sessionID": "ses_1", "error": first},
            {"type": "error", "sessionID": "ses_1", "error": second},
        ]
    )

    assert events[1:] == [TurnEnded(error="Model not found: x/y."), TurnEnded(error="Model not found: x/y.")]
