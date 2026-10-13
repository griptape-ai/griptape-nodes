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
from griptape_nodes.agents.harness import TextDelta, ThinkingDelta, ToolCall, ToolResult

if TYPE_CHECKING:
    from collections.abc import Sequence

    from griptape_nodes.agents.cli.base import CliMCPServer

logger = logging.getLogger("griptape_nodes")

_INSTRUCTIONS_FILE_NAME = "gtn-instructions.md"
_STEP_REASON_TOOL_CALLS = "tool-calls"
_STEP_REASON_LENGTH = "length"


@dataclass
class OpenCodeHarness(CliHarness):
    harness_id: ClassVar[str] = "opencode"
    display_name: ClassVar[str] = "OpenCode"
    executable: ClassVar[str] = "opencode"
    install_hint: ClassVar[str] = (
        "Install OpenCode from https://opencode.ai (`npm install -g opencode-ai`), "
        "then run `opencode auth login` to sign in."
    )

    def mcp_tool_name(self, server: str, tool: str) -> str:
        return f"{_sanitize(server)}_{_sanitize(tool)}"

    def build_invocation(self, context: CliTurnContext) -> CliInvocation:
        # Non-interactive runs reject permission requests without --auto.
        args = ["run", "--format", "json", "--auto", "--thinking"]
        if context.model:
            args += ["--model", context.model]
        if context.resume_session_id:
            args += ["--session", context.resume_session_id]
        # `--file` takes several values, so it comes last. The prompt is on stdin.
        for image in context.images:
            args += ["--file", str(image.path)]
        config: dict[str, Any] = {"mcp": _mcp_config(context.mcp_servers)}
        if context.instructions:
            instructions_path = context.scratch_dir / _INSTRUCTIONS_FILE_NAME
            instructions_path.write_text(context.instructions, encoding="utf-8")
            config["instructions"] = [str(instructions_path)]
        # Inline config overlays the user's settings for this run without modifying their config file.
        return CliInvocation(
            args=args,
            stdin=context.prompt_text.encode("utf-8"),
            env={"OPENCODE_CONFIG_CONTENT": json.dumps(config)},
        )

    def new_parser(self) -> CliStreamParser:
        return OpenCodeStreamParser()


class OpenCodeStreamParser(CliStreamParser):
    """OpenCode emits complete parts; a tool part carries both input and output.

    There is no turn-end record; a step ending without tool calls ends the turn.
    """

    def __init__(self) -> None:
        self._session_reported = False
        self._reported_parts: set[str] = set()
        self._error: str | None = None

    def feed(self, record: dict[str, Any]) -> list[CliEvent]:
        events = self._session_started(record)
        part = record.get("part") or {}
        match record.get("type"):
            case "text" | "reasoning" | "tool_use" if self._already_reported(part):
                pass
            case "text" if part.get("text") and not part.get("synthetic") and not part.get("ignored"):
                events.append(TextDelta(delta=str(part["text"])))
            case "reasoning" if part.get("text"):
                events.append(ThinkingDelta(delta=str(part["text"])))
            case "tool_use":
                events += _tool_events(part)
            case "step_finish" if part.get("reason") != _STEP_REASON_TOOL_CALLS:
                events.append(TurnEnded(truncated=part.get("reason") == _STEP_REASON_LENGTH, error=self._error))
            case "error":
                # A failed run can report a second, generic error after the useful one.
                self._error = self._error or _error_message(record.get("error") or {})
                events.append(TurnEnded(error=self._error))
            case _:
                pass
        return events

    def _session_started(self, record: dict[str, Any]) -> list[CliEvent]:
        session_id = record.get("sessionID")
        if self._session_reported or not isinstance(session_id, str) or not session_id:
            return []
        self._session_reported = True
        return [SessionStarted(session_id=session_id)]

    def _already_reported(self, part: dict[str, Any]) -> bool:
        """OpenCode can repeat a finished part."""
        part_id = part.get("id")
        if not isinstance(part_id, str):
            return False
        if part_id in self._reported_parts:
            return True
        self._reported_parts.add(part_id)
        return False


def _tool_events(part: dict[str, Any]) -> list[CliEvent]:
    state = part.get("state") or {}
    tool_call_id = str(part.get("callID") or part.get("id") or "")
    tool_name = str(part.get("tool") or "?")
    is_error = state.get("status") == "error"
    content = state.get("error") if is_error else state.get("output")
    return [
        ToolCall(
            tool_call_id=tool_call_id, tool_name=tool_name, args=json.dumps(state.get("input") or {}, default=str)
        ),
        ToolResult(tool_call_id=tool_call_id, tool_name=tool_name, content=str(content or ""), is_error=is_error),
    ]


def _error_message(error: dict[str, Any]) -> str:
    message = (error.get("data") or {}).get("message")
    return str(message or error.get("name") or "OpenCode reported an error without saying what it was.")


def _sanitize(name: str) -> str:
    """Return ``name`` as OpenCode writes it into a tool name: letters, digits, ``_`` and ``-`` only."""
    return re.sub(r"[^A-Za-z0-9_-]", "_", name)


def _mcp_config(servers: Sequence[CliMCPServer]) -> dict[str, dict[str, Any]]:
    config: dict[str, dict[str, Any]] = {}
    for server in servers:
        name = _sanitize(server.name)
        if server.transport == "stdio" and server.command:
            config[name] = {
                "type": "local",
                "command": [server.command, *server.args],
                "environment": dict(server.env),
                "enabled": True,
            }
            if server.cwd:
                logger.warning(
                    "Attempted to start OpenCode MCP server '%s' in '%s'. Failed because OpenCode can't set a "
                    "working directory for a server, so it will start in the workspace.",
                    server.name,
                    server.cwd,
                )
        elif server.transport in ("streamable_http", "sse") and server.url:
            # OpenCode tries a streamable HTTP connection first and falls back to SSE.
            config[name] = {"type": "remote", "url": server.url, "headers": dict(server.headers), "enabled": True}
        else:
            logger.warning(
                "Attempted to give OpenCode MCP server '%s'. Failed because its %s connection is not one "
                "OpenCode supports, so it will run without it.",
                server.name,
                server.transport,
            )
    return config
