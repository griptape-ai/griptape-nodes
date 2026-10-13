from __future__ import annotations

import logging
import os
import shutil
import tempfile
import time
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar

from pydantic_ai.messages import BinaryContent
from pydantic_ai.tools import ToolDenied

from griptape_nodes.agents.cli.process import run_jsonl_process
from griptape_nodes.agents.cli.transcript import TranscriptBuilder, denied_tool_return, render_catch_up, user_turn
from griptape_nodes.agents.cli.windows_shims import launch_command
from griptape_nodes.agents.harness import (
    RESULT_TRANSPORT_BYTES,
    AgentRunResult,
    RunEvent,
    TextDelta,
    ToolCall,
    ToolResult,
    args_json,
    push_event,
    truncate,
)
from griptape_nodes.agents.pydantic_ai.mcp_servers import GTN_SERVER_NAME
from griptape_nodes.agents.pydantic_ai.tool_approval import pending_tool_calls
from griptape_nodes.drivers.thread_storage.base_thread_storage_driver import HarnessSession

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from pydantic_ai.messages import ModelMessage, ToolReturnPart, UserContent

    from griptape_nodes.agents.harness import AgentTurn
    from griptape_nodes.drivers.thread_storage.base_thread_storage_driver import BaseThreadStorageDriver

logger = logging.getLogger("griptape_nodes")

# Where CLIs commonly install, beyond PATH. An engine started by the desktop app
# inherits a minimal PATH that misses the user's shell setup.
_EXTRA_SEARCH_DIRS = (
    "~/.local/bin",
    "~/.claude/local",
    "~/.npm-global/bin",
    "~/.bun/bin",
    "~/.volta/bin",
    "~/.local/share/mise/shims",
    "~/.asdf/shims",
    "/opt/homebrew/bin",
    "/usr/local/bin",
)


class CliHarnessError(RuntimeError):
    """A CLI harness turn failed. The message is meant for the user."""


@dataclass(frozen=True)
class CliMCPServer:
    """``env`` and ``headers`` may contain secrets; never log them."""

    name: str
    transport: str
    url: str | None = None
    headers: Mapping[str, str] = field(default_factory=dict)
    command: str | None = None
    args: Sequence[str] = ()
    env: Mapping[str, str] = field(default_factory=dict)
    cwd: str | None = None

    @classmethod
    def from_config(cls, name: str, config: Mapping[str, Any]) -> CliMCPServer:
        return cls(
            name=name,
            transport=str(config.get("transport") or "stdio"),
            url=config.get("url") or None,
            headers=dict(config.get("headers") or {}),
            command=config.get("command") or None,
            args=[str(arg) for arg in config.get("args") or []],
            env={str(key): str(value) for key, value in (config.get("env") or {}).items()},
            cwd=config.get("cwd") or None,
        )


@dataclass(frozen=True)
class PromptImage:
    data: bytes
    media_type: str
    path: Path


@dataclass(frozen=True)
class CliTurnContext:
    """Invocation context for one turn.

    Attributes:
        prompt_text: Includes messages the CLI has not seen and, when it has no
            system prompt option, the instructions.
        instructions: Empty when already included in ``prompt_text``.
        mcp_servers: The engine's MCP server, then the turn's.
        max_turns: Maximum agent steps, or ``None`` for the CLI's limit.
        scratch_dir: Removed after the turn.
    """

    prompt_text: str
    images: Sequence[PromptImage]
    instructions: str
    resume_session_id: str | None
    new_session_id: str
    mcp_servers: Sequence[CliMCPServer]
    model: str | None
    max_turns: int | None
    workspace_root: Path
    scratch_dir: Path


@dataclass(frozen=True)
class CliInvocation:
    """``env`` augments the engine's environment; a ``None`` value removes a variable."""

    args: Sequence[str]
    stdin: bytes | None = None
    env: Mapping[str, str | None] = field(default_factory=dict)


@dataclass(frozen=True)
class SessionStarted:
    session_id: str


@dataclass(frozen=True)
class TurnEnded:
    """``truncated`` covers output and turn limits, not CLI failures."""

    truncated: bool = False
    error: str | None = None


CliEvent = RunEvent | SessionStarted | TurnEnded


class CliStreamParser(ABC):
    """One parser per CLI process; state may span records."""

    @abstractmethod
    def feed(self, record: dict[str, Any]) -> list[CliEvent]:
        """Emit events in record order, with engine ``<server>_<tool>`` names.

        Leave arguments and results untruncated; the harness truncates transport copies.
        """


@dataclass
class _TurnOutcome:
    transcript: TranscriptBuilder
    events_seen: int = 0
    session_id: str | None = None
    ended: TurnEnded | None = None
    text: list[str] = field(default_factory=list)
    cancelled: bool = False
    returncode: int | None = None
    stderr_tail: str = ""


@dataclass
class CliHarness(ABC):
    harness_id: ClassVar[str]

    display_name: ClassVar[str]

    executable: ClassVar[str]

    install_hint: ClassVar[str]

    supports_system_prompt: ClassVar[bool] = True
    """Whether the CLI takes extra system prompt text. Otherwise it goes in the prompt."""

    suggested_models: ClassVar[tuple[str, ...]] = ()
    """Model names offered when the user picks a model. The CLI may accept others."""

    workspace_root: Path
    storage: BaseThreadStorageDriver
    engine_mcp_url: str
    instructions: str | None = None
    model: str | None = None
    command: str | None = None
    max_turns: int | None = None
    """Maximum agent steps per turn, where the CLI supports a limit."""

    @property
    def supports_tool_approval(self) -> bool:
        return False

    def mcp_tool_name(self, server: str, tool: str) -> str:
        return f"mcp__{server}__{tool}"

    def normalize_tool_name(self, name: str) -> str:
        """Use Pydantic AI's MCP names so tool cards and provider switches stay consistent.

        Built-in CLI tools keep their own names.
        """
        prefix = "mcp__"
        if not name.startswith(prefix):
            return name
        server, separator, tool = name.removeprefix(prefix).partition("__")
        if not separator:
            return name
        return f"{server}_{tool}"

    @abstractmethod
    def build_invocation(self, context: CliTurnContext) -> CliInvocation:
        """Return the command line that runs one turn."""

    @abstractmethod
    def new_parser(self) -> CliStreamParser:
        """Return a parser for one process's output."""

    def environment(self) -> dict[str, str]:
        return dict(os.environ)

    async def run_turn(self, turn: AgentTurn) -> AgentRunResult:
        if not self.storage.thread_exists(turn.thread_id):
            msg = f"Attempted to run {self.display_name} in conversation {turn.thread_id}. Failed because the conversation does not exist."
            raise CliHarnessError(msg)
        if turn.prompt is None:
            msg = (
                f"Attempted to continue the conversation with {self.display_name}. Failed because "
                f"{self.display_name} runs its tools without asking, so there is no approval to answer. "
                "Send a new message instead."
            )
            raise CliHarnessError(msg)

        history = self.storage.load_history(turn.thread_id)
        denied = self._declined_calls(history, turn)
        session = self.storage.get_harness_session(turn.thread_id, self.harness_id)
        executable = self._resolve_executable()
        if not self.workspace_root.is_dir():
            msg = (
                f"Attempted to start {self.display_name} in the workspace '{self.workspace_root}'. "
                "Failed because that folder does not exist. Choose an existing workspace folder in Settings."
            )
            raise CliHarnessError(msg)

        started = time.monotonic()
        with tempfile.TemporaryDirectory(prefix=f"gtn-{self.harness_id}-") as scratch:
            scratch_dir = Path(scratch)
            images = _write_images(turn.prompt, scratch_dir)
            outcome = await self._run_process(
                executable, turn, history, session, images=images, scratch_dir=scratch_dir
            )
            if _should_retry_without_session(outcome, session):
                # CLIs may delete saved sessions.
                logger.warning(
                    "%s could not resume session %s for conversation %s; starting a new session.",
                    self.display_name,
                    session.session_id if session else None,
                    turn.thread_id,
                )
                session = None
                outcome = await self._run_process(
                    executable, turn, history, None, images=images, scratch_dir=scratch_dir
                )

        logger.debug(
            "%s turn for conversation %s finished in %.2fs: events=%d session=%s returncode=%s cancelled=%s",
            self.display_name,
            turn.thread_id,
            time.monotonic() - started,
            outcome.events_seen,
            outcome.session_id,
            outcome.returncode,
            outcome.cancelled,
        )
        session_id = outcome.session_id or (session.session_id if session else None)
        output = "".join(outcome.text)

        if outcome.cancelled:
            # A cancelled CLI session can hold partial turns absent from thread history.
            if session_id is not None:
                self._remember_session(turn.thread_id, session_id, len(history))
            return AgentRunResult(thread_id=turn.thread_id, output=output, message_count=len(history), cancelled=True)

        self._raise_for_failure(outcome)

        persisted_prompt = turn.persist_prompt if turn.persist_prompt is not None else turn.prompt
        messages = [*history, user_turn(persisted_prompt, denied=denied), *outcome.transcript.messages()]
        self.storage.save_history(turn.thread_id, messages)
        if session_id is not None:
            self._remember_session(turn.thread_id, session_id, len(messages))
        truncated = outcome.ended is not None and outcome.ended.truncated
        return AgentRunResult(thread_id=turn.thread_id, output=output, message_count=len(messages), truncated=truncated)

    def _declined_calls(self, history: Sequence[ModelMessage], turn: AgentTurn) -> list[ToolReturnPart]:
        """A CLI cannot run another harness's pending calls."""
        waiting = pending_tool_calls(history)
        if not waiting:
            return []
        approvals = turn.deferred_tool_results.approvals if turn.deferred_tool_results is not None else {}
        denied: list[ToolReturnPart] = []
        for call in waiting:
            answer = approvals.get(call.tool_call_id)
            if isinstance(answer, ToolDenied):
                denied.append(denied_tool_return(call.tool_name, call.tool_call_id, answer.message))
            elif answer is False:
                denied.append(denied_tool_return(call.tool_name, call.tool_call_id, ToolDenied().message))
            else:
                msg = (
                    f"Attempted to run '{call.tool_name}' with {self.display_name}. Failed because another "
                    f"provider asked for it, and {self.display_name} can't run it. Switch back to that "
                    "provider to approve it, or send a new message to decline it."
                )
                raise CliHarnessError(msg)
        return denied

    async def _run_process(  # noqa: PLR0913
        self,
        executable: str,
        turn: AgentTurn,
        history: Sequence[ModelMessage],
        session: HarnessSession | None,
        *,
        images: Sequence[PromptImage],
        scratch_dir: Path,
    ) -> _TurnOutcome:
        context = self._turn_context(turn, history, session, images=images, scratch_dir=scratch_dir)
        invocation = self.build_invocation(context)
        env = self.environment()
        for key, value in invocation.env.items():
            if value is None:
                env.pop(key, None)
            else:
                env[key] = value

        parser = self.new_parser()
        outcome = _TurnOutcome(transcript=TranscriptBuilder(provider_name=self.harness_id, model_name=self.model))

        async def on_record(record: dict[str, Any]) -> None:
            for event in parser.feed(record):
                await self._handle_event(event, outcome, turn)

        logger.debug(
            "Starting %s for conversation %s: resume=%s mcp_servers=%s",
            self.display_name,
            turn.thread_id,
            context.resume_session_id,
            [server.name for server in context.mcp_servers],
        )
        try:
            exit_info = await run_jsonl_process(
                [*launch_command(executable), *invocation.args],
                cwd=self.workspace_root,
                env=env,
                stdin=invocation.stdin,
                on_record=on_record,
                cancel_event=turn.cancel_event,
            )
        except FileNotFoundError as e:
            raise CliHarnessError(self._missing_executable_message()) from e
        except PermissionError as e:
            msg = f"Attempted to start {self.display_name} from '{executable}'. Failed because it could not be run: {e}"
            raise CliHarnessError(msg) from e
        outcome.cancelled = exit_info.cancelled
        outcome.returncode = exit_info.returncode
        outcome.stderr_tail = exit_info.stderr_tail
        return outcome

    async def _handle_event(self, event: CliEvent, outcome: _TurnOutcome, turn: AgentTurn) -> None:
        if isinstance(event, SessionStarted):
            outcome.session_id = event.session_id
            return
        if isinstance(event, TurnEnded):
            outcome.ended = event
            return
        outcome.events_seen += 1
        outcome.transcript.add(event)
        if isinstance(event, TextDelta):
            outcome.text.append(event.delta)
            await push_event(turn.event_sink, event)
        elif isinstance(event, ToolCall):
            await push_event(
                turn.event_sink,
                ToolCall(tool_call_id=event.tool_call_id, tool_name=event.tool_name, args=args_json(event.args)),
            )
        elif isinstance(event, ToolResult):
            await push_event(
                turn.event_sink,
                ToolResult(
                    tool_call_id=event.tool_call_id,
                    tool_name=event.tool_name,
                    content=truncate(event.content, RESULT_TRANSPORT_BYTES),
                    is_error=event.is_error,
                ),
            )
        else:
            await push_event(turn.event_sink, event)

    def _turn_context(
        self,
        turn: AgentTurn,
        history: Sequence[ModelMessage],
        session: HarnessSession | None,
        *,
        images: Sequence[PromptImage],
        scratch_dir: Path,
    ) -> CliTurnContext:
        if session is not None and session.message_count <= len(history):
            unseen = history[session.message_count :]
            resume_session_id: str | None = session.session_id
        else:
            unseen = history
            resume_session_id = None

        instructions = "\n\n".join(part for part in (self.instructions, turn.instructions) if part)
        prompt_text = render_catch_up(unseen) + _prompt_text(turn.prompt or "")
        if not self.supports_system_prompt:
            # The CLI keeps the instructions in its session, so only a new session needs them.
            if resume_session_id is None and instructions:
                prompt_text = f"<instructions>\n{instructions}\n</instructions>\n\n{prompt_text}"
            instructions = ""

        engine_server = CliMCPServer(name=GTN_SERVER_NAME, transport="streamable_http", url=self.engine_mcp_url)
        user_servers = [CliMCPServer.from_config(server.name, server.config) for server in turn.mcp_servers]
        return CliTurnContext(
            prompt_text=prompt_text,
            images=images,
            instructions=instructions,
            resume_session_id=resume_session_id,
            new_session_id=str(uuid.uuid4()),
            mcp_servers=[engine_server, *user_servers],
            model=self.model or None,
            max_turns=self.max_turns,
            workspace_root=self.workspace_root,
            scratch_dir=scratch_dir,
        )

    def _raise_for_failure(self, outcome: _TurnOutcome) -> None:
        if outcome.ended is not None and outcome.ended.error:
            msg = f"{self.display_name} stopped with an error: {outcome.ended.error}"
            raise CliHarnessError(msg)
        if outcome.returncode not in (0, None) or outcome.ended is None:
            detail = outcome.stderr_tail.strip() or "it printed no error."
            msg = (
                f"Attempted to run {self.display_name}. Failed because it exited with code "
                f"{outcome.returncode} before finishing the reply: {detail}"
            )
            raise CliHarnessError(msg)

    def _remember_session(self, thread_id: str, session_id: str, message_count: int) -> None:
        self.storage.set_harness_session(
            thread_id, self.harness_id, HarnessSession(session_id=session_id, message_count=message_count)
        )

    def _resolve_executable(self) -> str:
        if self.command:
            resolved = shutil.which(str(Path(self.command).expanduser()))
            if resolved is None:
                msg = (
                    f"Attempted to start {self.display_name} from '{self.command}'. Failed because that "
                    "command was not found. Check the path set for it in the agent settings."
                )
                raise CliHarnessError(msg)
            return resolved
        search_path = os.pathsep.join(
            [os.environ.get("PATH", ""), *(str(Path(directory).expanduser()) for directory in _EXTRA_SEARCH_DIRS)]
        )
        resolved = shutil.which(self.executable, path=search_path)
        if resolved is None:
            raise CliHarnessError(self._missing_executable_message())
        return resolved

    def _missing_executable_message(self) -> str:
        return (
            f"Attempted to start {self.display_name}. Failed because the `{self.executable}` command was not "
            f"found on this computer. {self.install_hint}"
        )


def _should_retry_without_session(outcome: _TurnOutcome, session: HarnessSession | None) -> bool:
    if session is None or outcome.cancelled or outcome.events_seen:
        return False
    return outcome.ended is None or bool(outcome.ended.error)


def _prompt_text(prompt: str | Sequence[UserContent]) -> str:
    if isinstance(prompt, str):
        return prompt
    return "\n".join(item for item in prompt if isinstance(item, str))


def _write_images(prompt: str | Sequence[UserContent], scratch_dir: Path) -> list[PromptImage]:
    if isinstance(prompt, str):
        return []
    images: list[PromptImage] = []
    for index, item in enumerate(prompt):
        if not isinstance(item, BinaryContent) or not item.is_image:
            continue
        path = scratch_dir / f"attachment-{index}.{item.format}"
        path.write_bytes(item.data)
        images.append(PromptImage(data=item.data, media_type=item.media_type, path=path))
    return images
