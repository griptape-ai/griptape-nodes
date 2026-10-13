"""Codex as a chat-sidebar agent harness.

Runs ``codex exec --json``, or ``codex exec resume --json`` to continue a
session. ``--dangerously-bypass-approvals-and-sandbox`` skips Codex's approval
prompts and its sandbox, which would otherwise keep it from editing files outside
the workspace and from reaching the network. The user's message goes in on stdin
(``-``) and images travel as ``--image`` files.

Codex has no command line option for MCP servers or instructions, but ``-c``
overrides any config key for one run. Each MCP server becomes a
``mcp_servers.<name>`` table and the instructions become ``developer_instructions``.
Nothing is written to ``~/.codex/config.toml``. Servers get
``default_tools_approval_mode = "approve"`` so that tools an MCP server marks as
changing things run without asking.

Codex prints a message, a command, or a tool call once it is complete, not token by
token, so text arrives as one ``TextDelta`` per message.
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
    from collections.abc import Mapping, Sequence

    from griptape_nodes.agents.cli.base import CliMCPServer

logger = logging.getLogger("griptape_nodes")

_SHELL_TOOL_NAME = "shell"
_PATCH_TOOL_NAME = "apply_patch"
_SEARCH_TOOL_NAME = "web_search"


@dataclass
class CodexHarness(CliHarness):
    harness_id: ClassVar[str] = "codex"
    display_name: ClassVar[str] = "Codex"
    executable: ClassVar[str] = "codex"
    install_hint: ClassVar[str] = (
        "Install Codex with `npm install -g @openai/codex` (see https://developers.openai.com/codex/cli), "
        "then run `codex` once to sign in."
    )

    def mcp_tool_name(self, server: str, tool: str) -> str:
        return f"mcp__{_server_name(server)}__{tool}"

    def build_invocation(self, context: CliTurnContext) -> CliInvocation:
        args = ["exec"]
        if context.resume_session_id:
            args.append("resume")
        args += ["--json", "--skip-git-repo-check", "--dangerously-bypass-approvals-and-sandbox"]
        if context.model:
            args += ["--model", context.model]
        if context.instructions:
            args += ["-c", f"developer_instructions={_toml_string(context.instructions)}"]
        for name, table in _mcp_config(context.mcp_servers).items():
            args += ["-c", f"mcp_servers.{name}={table}"]
        for image in context.images:
            args += ["--image", str(image.path)]
        # `--image` takes several values, so it would swallow a session id that followed it.
        # After `--`, `-` reads the prompt from stdin.
        if context.resume_session_id:
            args += ["--", context.resume_session_id, "-"]
        return CliInvocation(args=args, stdin=context.prompt_text.encode("utf-8"))

    def new_parser(self) -> CliStreamParser:
        return CodexStreamParser()


class CodexStreamParser(CliStreamParser):
    """Parses ``codex exec --json``.

    Codex reports each unit of work as an item that starts and then completes.
    Commands, MCP tool calls, and web searches become a tool call when they start
    and a tool result when they complete; file changes are only reported complete,
    so they produce both at once. Messages and reasoning are reported complete.

    ``error`` records are progress notes such as "Reconnecting... 2/5"; the failure
    that ends a turn is ``turn.failed``. Other items, such as the to-do list and
    calls to Codex's own subagents, are skipped.
    """

    def __init__(self) -> None:
        self._announced: dict[str, str] = {}

    def feed(self, record: dict[str, Any]) -> list[CliEvent]:
        events: list[CliEvent]
        match record.get("type"):
            case "thread.started":
                events = _session_started(record)
            case "item.started":
                events = self._item_started(record.get("item") or {})
            case "item.completed":
                events = self._item_completed(record.get("item") or {})
            case "turn.completed":
                events = [TurnEnded()]
            case "turn.failed":
                message = (record.get("error") or {}).get(
                    "message"
                ) or "Codex reported an error without saying what it was."
                events = [TurnEnded(error=str(message))]
            case _:
                events = []
        return events

    def _item_started(self, item: dict[str, Any]) -> list[CliEvent]:
        call = self._tool_call(item)
        if call is None:
            return []
        return [call]

    def _item_completed(self, item: dict[str, Any]) -> list[CliEvent]:
        item_type = item.get("type")
        if item_type == "agent_message" and item.get("text"):
            return [TextDelta(delta=str(item["text"]))]
        if item_type == "reasoning" and item.get("text"):
            return [ThinkingDelta(delta=str(item["text"]))]
        call = self._tool_call(item)
        result = _tool_result(item, tool_name=self._announced.get(str(item.get("id") or ""), "?"))
        if result is None:
            return []
        if call is None:
            return [result]
        return [call, result]

    def _tool_call(self, item: dict[str, Any]) -> ToolCall | None:
        """Return the call ``item`` stands for, unless it was reported before or is not a tool call."""
        item_id = str(item.get("id") or "")
        tool_name = _tool_name(item)
        if tool_name is None or item_id in self._announced:
            return None
        self._announced[item_id] = tool_name
        return ToolCall(tool_call_id=item_id, tool_name=tool_name, args=json.dumps(_tool_args(item), default=str))


def _session_started(record: dict[str, Any]) -> list[CliEvent]:
    thread_id = record.get("thread_id")
    if not isinstance(thread_id, str) or not thread_id:
        return []
    return [SessionStarted(session_id=thread_id)]


def _tool_name(item: dict[str, Any]) -> str | None:
    match item.get("type"):
        case "command_execution":
            return _SHELL_TOOL_NAME
        case "file_change":
            return _PATCH_TOOL_NAME
        case "web_search":
            return _SEARCH_TOOL_NAME
        case "mcp_tool_call":
            return f"{item.get('server')}_{item.get('tool')}"
        case _:
            return None


def _tool_args(item: dict[str, Any]) -> Any:
    match item.get("type"):
        case "command_execution":
            return {"command": item.get("command")}
        case "file_change":
            return {"changes": item.get("changes") or []}
        case "web_search":
            return {"query": item.get("query")}
        case _:
            return item.get("arguments") or {}


def _tool_result(item: dict[str, Any], *, tool_name: str) -> ToolResult | None:
    item_id = str(item.get("id") or "")
    failed = item.get("status") in ("failed", "declined")
    match item.get("type"):
        case "command_execution":
            return ToolResult(
                tool_call_id=item_id,
                tool_name=tool_name,
                content=str(item.get("aggregated_output") or ""),
                is_error=failed,
            )
        case "file_change":
            changes = "\n".join(f"{change.get('kind')} {change.get('path')}" for change in item.get("changes") or [])
            return ToolResult(tool_call_id=item_id, tool_name=tool_name, content=changes, is_error=failed)
        case "web_search":
            return ToolResult(tool_call_id=item_id, tool_name=tool_name, content=stringify(item.get("results")))
        case "mcp_tool_call":
            error = item.get("error")
            if error:
                return ToolResult(
                    tool_call_id=item_id, tool_name=tool_name, content=str(error.get("message") or ""), is_error=True
                )
            return ToolResult(
                tool_call_id=item_id,
                tool_name=tool_name,
                content=_mcp_result_text(item.get("result") or {}),
                is_error=failed,
            )
        case _:
            return None


def _mcp_result_text(result: dict[str, Any]) -> str:
    parts = []
    for block in result.get("content") or []:
        if isinstance(block, dict) and block.get("type") == "text":
            parts.append(str(block.get("text") or ""))
        elif isinstance(block, dict):
            parts.append(f"[{block.get('type', 'content')}]")
    if parts:
        return "\n".join(parts)
    return stringify(result.get("structured_content"))


def _server_name(name: str) -> str:
    """Return ``name`` with the characters Codex allows in a server name: letters, digits, ``_`` and ``-``."""
    return re.sub(r"[^A-Za-z0-9_-]", "_", name)


def _toml_string(value: str) -> str:
    """Return ``value`` as a TOML basic string. JSON's escapes are TOML's, except for DEL."""
    return json.dumps(value).replace("\x7f", "\\u007f")


def _toml_table(values: Mapping[str, str]) -> str:
    return "{" + ", ".join(f"{_toml_string(key)} = {_toml_string(value)}" for key, value in values.items()) + "}"


def _mcp_config(servers: Sequence[CliMCPServer]) -> dict[str, str]:
    """Return each server's TOML inline table, by the name Codex will know it as."""
    config: dict[str, str] = {}
    for server in servers:
        fields: list[str]
        if server.transport == "stdio" and server.command:
            fields = [
                f"command = {_toml_string(server.command)}",
                f"args = [{', '.join(_toml_string(arg) for arg in server.args)}]",
            ]
            if server.env:
                fields.append(f"env = {_toml_table(server.env)}")
            if server.cwd:
                fields.append(f"cwd = {_toml_string(server.cwd)}")
        elif server.transport == "streamable_http" and server.url:
            fields = [f"url = {_toml_string(server.url)}"]
            if server.headers:
                fields.append(f"http_headers = {_toml_table(server.headers)}")
        else:
            logger.warning(
                "Attempted to give Codex MCP server '%s'. Failed because its %s connection is not one "
                "Codex supports, so it will run without it.",
                server.name,
                server.transport,
            )
            continue
        fields.append('default_tools_approval_mode = "approve"')
        config[_server_name(server.name)] = "{" + ", ".join(fields) + "}"
    return config
