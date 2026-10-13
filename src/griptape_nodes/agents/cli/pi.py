"""pi as a chat-sidebar agent harness.

Runs ``pi --mode json -p``. The user's message goes in on stdin and images
travel as ``@path`` arguments, which pi attaches to the first prompt. pi never
asks before running a tool, so there is no permission flag to pass.

pi has no command line option for MCP servers, so the turn's servers go in a
generated extension file, loaded with ``-e``, that registers each one with
``pi.registerMcpServer``. Nothing is written to the workspace or to pi's own
``mcp.json``. Each server is registered with ``exposure: "direct"``: pi's
default hides MCP tools behind a ``codemode`` script, and the sidebar's tool
cards should show the tool the model called.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, ClassVar

from griptape_nodes.agents.cli.base import (
    CliEvent,
    CliHarness,
    CliInvocation,
    CliStreamParser,
    CliTurnContext,
    SessionStarted,
    TurnEnded,
)
from griptape_nodes.agents.harness import TextDelta, ThinkingDelta, ToolCall, ToolResult, stringify

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    from griptape_nodes.agents.cli.base import CliMCPServer

logger = logging.getLogger("griptape_nodes")

_EXTENSION_FILE_NAME = "gtn-mcp-servers.js"


@dataclass
class PiHarness(CliHarness):
    harness_id: ClassVar[str] = "pi"
    display_name: ClassVar[str] = "pi"
    executable: ClassVar[str] = "pi"
    install_hint: ClassVar[str] = (
        "Install pi from https://pi.dev (`npm install -g @earendil-works/pi-coding-agent`), "
        "then run `pi` once to sign in."
    )

    def mcp_tool_name(self, server: str, tool: str) -> str:
        # pi replaces every character other than letters, digits, and `_` in the whole name.
        return re.sub(r"[^A-Za-z0-9_]", "_", f"mcp__{_server_name(server)}__{tool}")

    def build_invocation(self, context: CliTurnContext) -> CliInvocation:
        args = ["--mode", "json", "-p"]
        if context.model:
            args += ["--model", context.model]
        if context.instructions:
            args += ["--append-system-prompt", context.instructions]
        if context.resume_session_id:
            args += ["--session", context.resume_session_id]
        else:
            args += ["--session-id", context.new_session_id]
        extension_path = context.scratch_dir / _EXTENSION_FILE_NAME
        extension_path.write_text(_extension_source(context.mcp_servers), encoding="utf-8")
        args += ["--extension", str(extension_path)]
        args += [f"@{image.path}" for image in context.images]
        return CliInvocation(args=args, stdin=context.prompt_text.encode("utf-8"))

    def new_parser(self) -> CliStreamParser:
        return PiStreamParser(normalize_tool_name=self.normalize_tool_name)


class PiStreamParser(CliStreamParser):
    """Parses ``pi --mode json``.

    Text and thinking come from ``message_update`` deltas; a block that never
    streamed is taken from its ``*_end`` record. Tool calls and results come from
    ``tool_execution_start`` and ``tool_execution_end``. Calls that one tool makes
    through another, such as the tools a ``codemode`` script runs, carry a
    ``parentToolCallId`` and are skipped: the sidebar shows the call the model made.

    pi reports a failed reply as an assistant message with ``stopReason: "error"``,
    then exits with code 0, so the turn's end is read from that message.
    """

    def __init__(self, *, normalize_tool_name: Callable[[str], str]) -> None:
        self._normalize_tool_name = normalize_tool_name
        self._tool_names: dict[str, str] = {}
        self._streamed_blocks: set[tuple[str, int]] = set()
        self._stop_reason: str | None = None
        self._error_message: str | None = None

    def feed(self, record: dict[str, Any]) -> list[CliEvent]:
        if record.get("parentToolCallId"):
            return []
        events: list[CliEvent]
        match record.get("type"):
            case "session":
                events = _session_started(record)
            case "message_start" if (record.get("message") or {}).get("role") == "assistant":
                self._streamed_blocks.clear()
                events = []
            case "message_update":
                events = self._block_update(record.get("assistantMessageEvent") or {})
            case "message_end" if (record.get("message") or {}).get("role") == "assistant":
                self._stop_reason = record["message"].get("stopReason")
                self._error_message = record["message"].get("errorMessage")
                events = []
            case "tool_execution_start":
                events = [self._tool_call(record)]
            case "tool_execution_end":
                events = [self._tool_result(record)]
            case "agent_end" if not record.get("willRetry"):
                events = [self._turn_ended(aborted=False)]
            case "agent_settled":
                events = [self._turn_ended(aborted=bool(record.get("aborted")))]
            case _:
                events = []
        return events

    def _block_update(self, event: dict[str, Any]) -> list[CliEvent]:
        event_type = event.get("type")
        index = int(event.get("contentIndex") or 0)
        if event_type == "text_delta" and event.get("delta"):
            self._streamed_blocks.add(("text", index))
            return [TextDelta(delta=str(event["delta"]))]
        if event_type == "thinking_delta" and event.get("delta"):
            self._streamed_blocks.add(("thinking", index))
            return [ThinkingDelta(delta=str(event["delta"]))]
        if event_type == "text_end" and ("text", index) not in self._streamed_blocks and event.get("content"):
            return [TextDelta(delta=str(event["content"]))]
        if event_type == "thinking_end" and ("thinking", index) not in self._streamed_blocks and event.get("content"):
            return [ThinkingDelta(delta=str(event["content"]))]
        return []

    def _tool_call(self, record: dict[str, Any]) -> CliEvent:
        tool_call_id = str(record.get("toolCallId") or "")
        tool_name = self._normalize_tool_name(str(record.get("toolName") or "?"))
        self._tool_names[tool_call_id] = tool_name
        return ToolCall(
            tool_call_id=tool_call_id, tool_name=tool_name, args=json.dumps(record.get("args") or {}, default=str)
        )

    def _tool_result(self, record: dict[str, Any]) -> CliEvent:
        tool_call_id = str(record.get("toolCallId") or "")
        return ToolResult(
            tool_call_id=tool_call_id,
            tool_name=self._tool_names.get(tool_call_id, "?"),
            content=_tool_result_text((record.get("result") or {}).get("content")),
            is_error=bool(record.get("isError")),
        )

    def _turn_ended(self, *, aborted: bool) -> CliEvent:
        if self._stop_reason == "error":
            return TurnEnded(error=self._error_message or "pi reported an error without saying what it was.")
        if aborted or self._stop_reason == "aborted":
            return TurnEnded(error="pi stopped before finishing the reply.")
        return TurnEnded(truncated=self._stop_reason == "length")


def _session_started(record: dict[str, Any]) -> list[CliEvent]:
    session_id = record.get("id")
    if not isinstance(session_id, str) or not session_id:
        return []
    return [SessionStarted(session_id=session_id)]


def _tool_result_text(content: Any) -> str:
    if not isinstance(content, list):
        return stringify(content)
    parts = []
    for item in content:
        if isinstance(item, dict) and item.get("type") == "text":
            parts.append(str(item.get("text") or ""))
        elif isinstance(item, dict):
            parts.append(f"[{item.get('type', 'content')}]")
    return "\n".join(parts)


def _server_name(name: str) -> str:
    """Return ``name`` with the characters pi allows in a server name: letters, digits, ``_`` and ``-``."""
    return re.sub(r"[^A-Za-z0-9_-]", "_", name)


def _extension_source(servers: Sequence[CliMCPServer]) -> str:
    """Return a pi extension that registers ``servers`` for the session."""
    config = json.dumps(_mcp_config(servers))
    return (
        "export default function (pi) {\n"
        f"  const servers = {config};\n"
        "  for (const [name, server] of Object.entries(servers)) {\n"
        "    pi.registerMcpServer(name, server);\n"
        "  }\n"
        "}\n"
    )


def _mcp_config(servers: Sequence[CliMCPServer]) -> dict[str, dict[str, Any]]:
    config: dict[str, dict[str, Any]] = {}
    for server in servers:
        name = _server_name(server.name)
        if server.transport == "stdio" and server.command:
            config[name] = {
                "command": server.command,
                "args": list(server.args),
                "env": dict(server.env),
                "exposure": "direct",
            }
            if server.cwd:
                config[name]["cwd"] = server.cwd
        elif server.transport == "streamable_http" and server.url:
            config[name] = {"url": server.url, "headers": dict(server.headers), "exposure": "direct"}
        else:
            logger.warning(
                "Attempted to give pi MCP server '%s'. Failed because its %s connection is not one "
                "pi supports, so it will run without it.",
                server.name,
                server.transport,
            )
    return config
