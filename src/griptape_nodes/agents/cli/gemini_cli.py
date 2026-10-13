"""Gemini CLI as a chat-sidebar agent harness.

Runs ``gemini --output-format stream-json``. Standard input that is not a
terminal puts Gemini CLI in its headless mode, so no ``-p`` is needed and the
user's message goes in on stdin. ``--approval-mode yolo`` skips its permission
prompts, and ``GEMINI_CLI_TRUST_WORKSPACE`` lets it do so in a folder it has not
been told to trust.

Gemini CLI has no option for MCP servers, and the one file it would read them from
without touching the user's config (``GEMINI_CLI_SYSTEM_SETTINGS_PATH``) is ignored
unless root owns it. So each turn runs with ``GEMINI_CLI_HOME`` pointing at a
scratch home whose ``.gemini`` links to everything in the user's own, so sign-in
and saved sessions carry over, except for a ``settings.json`` that is the user's
settings plus the turn's MCP servers. The user's files are only read.

Gemini CLI has no option to add to its system prompt, so the instructions go at the
start of the prompt (``supports_system_prompt``). Images are mentioned in the prompt
as ``@path``, which Gemini CLI attaches; ``--include-directories`` lets it read
them from outside the workspace.
"""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
from dataclasses import dataclass
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
from griptape_nodes.agents.harness import TextDelta, ToolCall, ToolResult

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    from griptape_nodes.agents.cli.base import CliMCPServer, PromptImage

logger = logging.getLogger("griptape_nodes")

_SCRATCH_HOME_NAME = "gemini-home"
_SETTINGS_FILE_NAME = "settings.json"
_MCP_TOOL_PREFIX = "mcp_"


@dataclass
class GeminiCliHarness(CliHarness):
    harness_id: ClassVar[str] = "gemini_cli"
    display_name: ClassVar[str] = "Gemini CLI"
    executable: ClassVar[str] = "gemini"
    install_hint: ClassVar[str] = (
        "Install Gemini CLI with `npm install -g @google/gemini-cli` (see https://geminicli.com), "
        "then run `gemini` once to sign in."
    )
    supports_system_prompt: ClassVar[bool] = False

    def mcp_tool_name(self, server: str, tool: str) -> str:
        return re.sub(r"[^A-Za-z0-9_\-.:]", "_", f"{_MCP_TOOL_PREFIX}{_server_name(server)}_{tool}")

    def normalize_tool_name(self, name: str) -> str:
        # Gemini CLI reports an MCP tool as `mcp_<server>_<tool>`, which is the engine's name behind a prefix.
        return name.removeprefix(_MCP_TOOL_PREFIX)

    def build_invocation(self, context: CliTurnContext) -> CliInvocation:
        args = ["--output-format", "stream-json", "--approval-mode", "yolo"]
        if context.model:
            args += ["--model", context.model]
        if context.resume_session_id:
            args += ["--resume", context.resume_session_id]
        else:
            args += ["--session-id", context.new_session_id]
        if context.images:
            args += ["--include-directories", str(context.scratch_dir)]
        prompt = _prompt_with_images(context.prompt_text, context.images)
        env: dict[str, str | None] = {
            "GEMINI_CLI_TRUST_WORKSPACE": "true",
            "GEMINI_CLI_HOME": str(_write_scratch_home(context)),
        }
        return CliInvocation(args=args, stdin=prompt.encode("utf-8"), env=env)

    def new_parser(self) -> CliStreamParser:
        return GeminiCliStreamParser(normalize_tool_name=self.normalize_tool_name)


class GeminiCliStreamParser(CliStreamParser):
    """Parses ``gemini --output-format stream-json``.

    Assistant ``message`` records are text chunks. Gemini CLI reports no thinking.
    A ``tool_result`` names its call only by id, so the parser remembers the names
    from ``tool_use``. ``error`` records are warnings or notes that precede the
    ``result`` record, which says whether the turn succeeded.
    """

    def __init__(self, *, normalize_tool_name: Callable[[str], str]) -> None:
        self._normalize_tool_name = normalize_tool_name
        self._tool_names: dict[str, str] = {}

    def feed(self, record: dict[str, Any]) -> list[CliEvent]:
        events: list[CliEvent]
        match record.get("type"):
            case "init":
                events = _session_started(record)
            case "message" if record.get("role") == "assistant" and record.get("content"):
                events = [TextDelta(delta=str(record["content"]))]
            case "tool_use":
                events = [self._tool_call(record)]
            case "tool_result":
                events = [self._tool_result(record)]
            case "result":
                events = [_turn_ended(record)]
            case _:
                events = []
        return events

    def _tool_call(self, record: dict[str, Any]) -> CliEvent:
        tool_call_id = str(record.get("tool_id") or "")
        tool_name = self._normalize_tool_name(str(record.get("tool_name") or "?"))
        self._tool_names[tool_call_id] = tool_name
        return ToolCall(
            tool_call_id=tool_call_id, tool_name=tool_name, args=json.dumps(record.get("parameters") or {}, default=str)
        )

    def _tool_result(self, record: dict[str, Any]) -> CliEvent:
        tool_call_id = str(record.get("tool_id") or "")
        is_error = record.get("status") == "error"
        if is_error:
            content = str((record.get("error") or {}).get("message") or record.get("output") or "")
        else:
            content = str(record.get("output") or "")
        return ToolResult(
            tool_call_id=tool_call_id,
            tool_name=self._tool_names.get(tool_call_id, "?"),
            content=content,
            is_error=is_error,
        )


def _session_started(record: dict[str, Any]) -> list[CliEvent]:
    session_id = record.get("session_id")
    if not isinstance(session_id, str) or not session_id:
        return []
    return [SessionStarted(session_id=session_id)]


def _turn_ended(record: dict[str, Any]) -> TurnEnded:
    if record.get("status") == "success":
        return TurnEnded()
    message = (record.get("error") or {}).get("message") or "Gemini CLI reported an error without saying what it was."
    return TurnEnded(error=str(message))


def _prompt_with_images(text: str, images: Sequence[PromptImage]) -> str:
    # `@path` mentions use forward slashes and escape spaces.
    mentions = [f"@{image.path.as_posix().replace(' ', chr(92) + ' ')}" for image in images]
    return "\n".join([text, *mentions])


def _server_name(name: str) -> str:
    """Return ``name`` as Gemini CLI wants server names: no underscores, which separate the server from the tool."""
    return re.sub(r"[^A-Za-z0-9-]", "-", name)


def _write_scratch_home(context: CliTurnContext) -> Path:
    """Build the home directory the turn runs with, and return it."""
    home = context.scratch_dir / _SCRATCH_HOME_NAME
    scratch_gemini_dir = home / ".gemini"
    # The base builds the command line again, in the same scratch directory, to retry without a session.
    scratch_gemini_dir.mkdir(parents=True, exist_ok=True)
    user_gemini_dir = _user_gemini_dir()
    if user_gemini_dir.is_dir():
        for entry in user_gemini_dir.iterdir():
            if entry.name != _SETTINGS_FILE_NAME:
                _link_or_copy(entry, scratch_gemini_dir / entry.name)

    settings = _read_settings(user_gemini_dir / _SETTINGS_FILE_NAME)
    user_servers = settings.get("mcpServers")
    settings["mcpServers"] = {
        **(user_servers if isinstance(user_servers, dict) else {}),
        **_mcp_config(context.mcp_servers),
    }
    (scratch_gemini_dir / _SETTINGS_FILE_NAME).write_text(json.dumps(settings), encoding="utf-8")
    return home


def _user_gemini_dir() -> Path:
    home = os.environ.get("GEMINI_CLI_HOME")
    if home:
        return Path(home) / ".gemini"
    return Path.home() / ".gemini"


def _link_or_copy(source: Path, target: Path) -> None:
    """Make ``source`` available at ``target``, as a link so that changes reach the original."""
    if target.is_symlink() or target.exists():
        return
    try:
        target.symlink_to(source, target_is_directory=source.is_dir())
    except OSError:
        # Windows only allows symbolic links with developer mode or administrator rights.
        # Copy files such as the sign-in, but not directories: they hold every saved
        # session and can be large. Sessions then don't carry over between turns, and
        # the harness catches each new session up on the conversation instead.
        if source.is_file():
            shutil.copy2(source, target)


def _read_settings(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        settings = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        logger.warning(
            "Attempted to read Gemini CLI settings from '%s'. Failed because %s, so this turn runs without them.",
            path,
            e,
        )
        return {}
    if not isinstance(settings, dict):
        return {}
    return settings


def _mcp_config(servers: Sequence[CliMCPServer]) -> dict[str, dict[str, Any]]:
    config: dict[str, dict[str, Any]] = {}
    for server in servers:
        name = _server_name(server.name)
        if server.transport == "stdio" and server.command:
            config[name] = {
                "command": server.command,
                "args": list(server.args),
                "env": dict(server.env),
                "trust": True,
            }
            if server.cwd:
                config[name]["cwd"] = server.cwd
        elif server.transport == "streamable_http" and server.url:
            config[name] = {"httpUrl": server.url, "headers": dict(server.headers), "trust": True}
        elif server.transport == "sse" and server.url:
            config[name] = {"url": server.url, "type": "sse", "headers": dict(server.headers), "trust": True}
        else:
            logger.warning(
                "Attempted to give Gemini CLI MCP server '%s'. Failed because its %s connection is not one "
                "Gemini CLI supports, so it will run without it.",
                server.name,
                server.transport,
            )
    return config
