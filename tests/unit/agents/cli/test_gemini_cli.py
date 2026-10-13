"""Tests for the Gemini CLI harness's command line, scratch home, and stream parsing.

Records are shaped like real ``gemini --output-format stream-json`` output (Gemini CLI
0.63): the ``init`` and user ``message`` records were captured from a run with an invalid
API key, and the others follow ``JsonStreamEvent`` in google-gemini/gemini-cli
(``packages/core/src/output/types.ts``).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from griptape_nodes.agents.cli.base import (
    CliMCPServer,
    CliTurnContext,
    PromptImage,
    SessionStarted,
    TurnEnded,
)
from griptape_nodes.agents.cli.gemini_cli import GeminiCliHarness, GeminiCliStreamParser
from griptape_nodes.agents.harness import TextDelta, ToolCall, ToolResult


def _harness() -> GeminiCliHarness:
    return GeminiCliHarness(workspace_root=Path("/ws"), storage=None, engine_mcp_url="http://localhost:1/mcp/")  # type: ignore[arg-type]


def _context(scratch_dir: Path, **overrides: Any) -> CliTurnContext:
    values: dict[str, Any] = {
        "prompt_text": "Build a flow",
        "images": [],
        "instructions": "",
        "resume_session_id": None,
        "new_session_id": "new-id",
        "mcp_servers": [CliMCPServer(name="GriptapeNodes", transport="streamable_http", url="http://localhost:1/mcp/")],
        "model": "gemini-2.5-pro",
        "max_turns": 60,
        "workspace_root": Path("/ws"),
        "scratch_dir": scratch_dir,
    }
    values.update(overrides)
    return CliTurnContext(**values)


@pytest.fixture
def user_gemini_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """The user's ``.gemini`` directory, with sign-in, settings, and a saved session."""
    home = tmp_path / "user-home"
    gemini_dir = home / ".gemini"
    (gemini_dir / "tmp" / "project" / "chats").mkdir(parents=True)
    (gemini_dir / "tmp" / "project" / "chats" / "session-1.json").write_text("{}")
    (gemini_dir / "oauth_creds.json").write_text('{"refresh_token": "r"}')
    (gemini_dir / "settings.json").write_text(
        json.dumps({"security": {"auth": {"selectedType": "oauth-personal"}}, "mcpServers": {"mine": {"command": "x"}}})
    )
    monkeypatch.setenv("GEMINI_CLI_HOME", str(home))
    return gemini_dir


def _flag(args: list[str], name: str) -> str:
    return args[args.index(name) + 1]


@pytest.mark.usefixtures("user_gemini_dir")
def test_new_session_is_started_with_the_chosen_id(tmp_path: Path) -> None:
    """A new session uses the id the harness chose, runs headless with auto-approval, and reads stdin."""
    invocation = _harness().build_invocation(_context(tmp_path / "scratch"))
    args = list(invocation.args)

    assert _flag(args, "--output-format") == "stream-json"
    assert _flag(args, "--approval-mode") == "yolo"
    assert _flag(args, "--session-id") == "new-id"
    assert "--resume" not in args
    assert _flag(args, "--model") == "gemini-2.5-pro"
    assert "--include-directories" not in args
    assert invocation.stdin == b"Build a flow"
    assert invocation.env["GEMINI_CLI_TRUST_WORKSPACE"] == "true"


@pytest.mark.usefixtures("user_gemini_dir")
def test_existing_session_is_resumed(tmp_path: Path) -> None:
    """A known session is resumed rather than started."""
    args = list(_harness().build_invocation(_context(tmp_path / "scratch", resume_session_id="old-id")).args)

    assert _flag(args, "--resume") == "old-id"
    assert "--session-id" not in args


def test_instructions_go_in_the_prompt() -> None:
    """Gemini CLI has no system prompt option, so the base puts instructions in the prompt."""
    assert _harness().supports_system_prompt is False


@pytest.mark.usefixtures("user_gemini_dir")
def test_images_are_mentioned_in_the_prompt(tmp_path: Path) -> None:
    """Images are mentioned as @path and their directory is made readable."""
    scratch = tmp_path / "my scratch"
    image = PromptImage(data=b"\x89PNG", media_type="image/png", path=scratch / "attachment-0.png")
    invocation = _harness().build_invocation(_context(scratch, images=[image]))

    assert _flag(list(invocation.args), "--include-directories") == str(scratch)
    assert invocation.stdin is not None
    assert invocation.stdin.decode().split("\n") == [
        "Build a flow",
        f"@{(scratch / 'attachment-0.png').as_posix().replace(' ', chr(92) + ' ')}",
    ]


def test_scratch_home_carries_over_the_users_files_and_adds_mcp_servers(tmp_path: Path, user_gemini_dir: Path) -> None:
    """The scratch home links the user's files, and its settings are theirs plus the turn's MCP servers."""
    servers = [
        CliMCPServer(name="GriptapeNodes", transport="streamable_http", url="http://localhost:1/mcp/"),
        CliMCPServer(name="files", transport="stdio", command="npx", args=["-y", "fs"], env={"K": "V"}, cwd="/data"),
        CliMCPServer(name="remote_api", transport="streamable_http", url="http://s/mcp", headers={"A": "B"}),
        CliMCPServer(name="legacy", transport="sse", url="http://s/sse"),
        CliMCPServer(name="ws", transport="websocket", url="ws://x"),
    ]
    invocation = _harness().build_invocation(_context(tmp_path / "scratch", mcp_servers=servers))

    scratch_gemini_dir = Path(str(invocation.env["GEMINI_CLI_HOME"])) / ".gemini"
    assert (scratch_gemini_dir / "oauth_creds.json").read_text() == '{"refresh_token": "r"}'
    assert (scratch_gemini_dir / "tmp" / "project" / "chats" / "session-1.json").exists()
    settings = json.loads((scratch_gemini_dir / "settings.json").read_text())
    assert settings["security"] == {"auth": {"selectedType": "oauth-personal"}}
    assert settings["mcpServers"] == {
        "mine": {"command": "x"},
        "GriptapeNodes": {"httpUrl": "http://localhost:1/mcp/", "headers": {}, "trust": True},
        "files": {"command": "npx", "args": ["-y", "fs"], "env": {"K": "V"}, "trust": True, "cwd": "/data"},
        "remote-api": {"httpUrl": "http://s/mcp", "headers": {"A": "B"}, "trust": True},
        "legacy": {"url": "http://s/sse", "type": "sse", "headers": {}, "trust": True},
    }
    assert json.loads((user_gemini_dir / "settings.json").read_text())["mcpServers"] == {"mine": {"command": "x"}}


@pytest.mark.usefixtures("user_gemini_dir")
def test_scratch_home_can_be_built_again_for_a_retry(tmp_path: Path) -> None:
    """Building the command line twice in one scratch directory, as a retry without a session does, works."""
    context = _context(tmp_path / "scratch")

    first = _harness().build_invocation(context)
    second = _harness().build_invocation(context)

    assert first.env["GEMINI_CLI_HOME"] == second.env["GEMINI_CLI_HOME"]


def test_scratch_home_works_without_a_users_gemini_directory(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A user who has never run Gemini CLI still gets the MCP servers."""
    monkeypatch.setenv("GEMINI_CLI_HOME", str(tmp_path / "empty-home"))
    invocation = _harness().build_invocation(_context(tmp_path / "scratch"))

    settings_path = Path(str(invocation.env["GEMINI_CLI_HOME"])) / ".gemini" / "settings.json"
    assert list(json.loads(settings_path.read_text())["mcpServers"]) == ["GriptapeNodes"]


def test_mcp_tool_names_match_the_names_gemini_gives_them() -> None:
    """Gemini CLI names MCP tools mcp_server_tool, and the parser reports server_tool."""
    harness = _harness()

    assert harness.mcp_tool_name("GriptapeNodes", "CreateNodeRequest") == "mcp_GriptapeNodes_CreateNodeRequest"
    assert harness.mcp_tool_name("my_server", "get tool") == "mcp_my-server_get_tool"
    assert harness.normalize_tool_name("mcp_GriptapeNodes_CreateNodeRequest") == "GriptapeNodes_CreateNodeRequest"
    assert harness.normalize_tool_name("run_shell_command") == "run_shell_command"


def _feed(records: list[dict[str, Any]]) -> list[Any]:
    parser = GeminiCliStreamParser(normalize_tool_name=_harness().normalize_tool_name)
    return [event for record in records for event in parser.feed(record)]


def test_a_turn_with_a_tool_call_is_parsed_in_order() -> None:
    """A turn's session, text, tool call, result, and end come out in order, and the echoed prompt is skipped."""
    events = _feed(
        [
            {"type": "init", "timestamp": "2026-10-13T19:19:31.844Z", "session_id": "s-1", "model": "auto"},
            {"type": "message", "timestamp": "2026-10-13T19:19:31.844Z", "role": "user", "content": "Build\n"},
            {"type": "message", "role": "assistant", "content": "I'll create ", "delta": True},
            {"type": "message", "role": "assistant", "content": "the node.", "delta": True},
            {
                "type": "tool_use",
                "tool_name": "mcp_GriptapeNodes_CreateNodeRequest",
                "tool_id": "call-1",
                "parameters": {"node_type": "Agent"},
            },
            {"type": "tool_result", "tool_id": "call-1", "status": "success", "output": "ok"},
            {"type": "message", "role": "assistant", "content": "Done.", "delta": True},
            {"type": "result", "status": "success", "stats": {"total_tokens": 10}},
        ]
    )

    assert events == [
        SessionStarted(session_id="s-1"),
        TextDelta(delta="I'll create "),
        TextDelta(delta="the node."),
        ToolCall(tool_call_id="call-1", tool_name="GriptapeNodes_CreateNodeRequest", args='{"node_type": "Agent"}'),
        ToolResult(tool_call_id="call-1", tool_name="GriptapeNodes_CreateNodeRequest", content="ok"),
        TextDelta(delta="Done."),
        TurnEnded(),
    ]


def test_tool_errors_are_flagged() -> None:
    """A tool result Gemini CLI marks as an error carries its message and is flagged."""
    events = _feed(
        [
            {"type": "tool_use", "tool_name": "run_shell_command", "tool_id": "c", "parameters": {"command": "false"}},
            {
                "type": "tool_result",
                "tool_id": "c",
                "status": "error",
                "error": {"type": "TOOL_EXECUTION_ERROR", "message": "exit 1"},
            },
        ]
    )

    assert events[1] == ToolResult(tool_call_id="c", tool_name="run_shell_command", content="exit 1", is_error=True)


def test_warnings_are_skipped() -> None:
    """Warning records don't reach the sidebar or end the turn."""
    assert _feed([{"type": "error", "severity": "warning", "message": "Loop detected"}]) == []


def test_failed_result_reports_geminis_error() -> None:
    """A failed result carries Gemini CLI's error text."""
    record = {
        "type": "result",
        "status": "error",
        "error": {"type": "Error", "message": "API key not valid. Please pass a valid API key."},
    }

    assert _feed([record]) == [TurnEnded(error="API key not valid. Please pass a valid API key.")]
