from __future__ import annotations

import json
import logging
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
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

_LAUNCHER_PATH = Path(__file__).with_name("mcp_env_launcher.py")
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
        # The sandbox blocks network access and edits outside the workspace.
        args += ["--json", "--skip-git-repo-check", "--dangerously-bypass-approvals-and-sandbox"]
        if context.model:
            args += ["--model", context.model]
        if context.instructions:
            args += ["-c", f"developer_instructions={_toml_string(context.instructions)}"]
        mcp = _mcp_config(context.mcp_servers, context.scratch_dir)
        for name, table in mcp.tables.items():
            args += ["-c", f"mcp_servers.{name}={table}"]
        for image in context.images:
            args += ["--image", str(image.path)]
        # `--image` takes several values, so it would swallow a session id that followed it.
        # After `--`, `-` reads the prompt from stdin.
        if context.resume_session_id:
            args += ["--", context.resume_session_id, "-"]
        return CliInvocation(args=args, stdin=context.prompt_text.encode("utf-8"), env=mcp.secret_env)

    def new_parser(self) -> CliStreamParser:
        return CodexStreamParser()


class CodexStreamParser(CliStreamParser):
    """Codex emits complete items, not token deltas.

    ``error`` records are reconnect progress; ``turn.failed`` ends a failed turn.
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
    """JSON escapes are valid in TOML basic strings, except for DEL."""
    return json.dumps(value).replace("\x7f", "\\u007f")


def _toml_table(values: Mapping[str, str]) -> str:
    return "{" + ", ".join(f"{_toml_string(key)} = {_toml_string(value)}" for key, value in values.items()) + "}"


@dataclass
class _CodexMCPConfig:
    """``tables`` go on the command line, so secrets stay out of them.

    HTTP headers are read from ``secret_env``, which Codex keeps from its shell
    commands because the names contain ``TOKEN``. Stdio servers start through
    :mod:`mcp_env_launcher`, which reads their variables from a file.
    """

    tables: dict[str, str] = field(default_factory=dict)
    secret_env: dict[str, str | None] = field(default_factory=dict)


def _mcp_config(servers: Sequence[CliMCPServer], scratch_dir: Path) -> _CodexMCPConfig:
    config = _CodexMCPConfig()
    for index, server in enumerate(servers):
        fields: list[str]
        if server.transport == "stdio" and server.command:
            command = [server.command, *server.args]
            if server.env:
                env_file = scratch_dir / f"mcp-env-{index}.json"
                env_file.write_text(json.dumps(dict(server.env)), encoding="utf-8")
                env_file.chmod(0o600)
                command = [sys.executable, str(_LAUNCHER_PATH), str(env_file), *command]
            fields = [
                f"command = {_toml_string(command[0])}",
                f"args = [{', '.join(_toml_string(arg) for arg in command[1:])}]",
            ]
            if server.cwd:
                fields.append(f"cwd = {_toml_string(server.cwd)}")
        elif server.transport == "streamable_http" and server.url:
            fields = [f"url = {_toml_string(server.url)}"]
            if server.headers:
                header_vars: dict[str, str] = {}
                for header_index, (header, value) in enumerate(server.headers.items()):
                    var = f"GTN_MCP_SECRET_TOKEN_{index}_{header_index}"
                    config.secret_env[var] = value
                    header_vars[header] = var
                fields.append(f"env_http_headers = {_toml_table(header_vars)}")
        else:
            logger.warning(
                "Attempted to give Codex MCP server '%s'. Failed because its %s connection is not one "
                "Codex supports, so it will run without it.",
                server.name,
                server.transport,
            )
            continue
        # MCP tools marked as mutating require this approval setting even with CLI prompts bypassed.
        fields.append('default_tools_approval_mode = "approve"')
        config.tables[_server_name(server.name)] = "{" + ", ".join(fields) + "}"
    return config
