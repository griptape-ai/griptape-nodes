"""High-level runner that wraps `pydantic_ai.Agent` for the chat sidebar.

This module is the single point of contact between the request-handling layer
(``AgentManager``) and the Pydantic AI harness. It exposes one async entry
point :meth:`PydanticAgentRunner.run` that:

  * builds (or reuses) a Pydantic AI ``Agent`` configured with the Griptape
    Cloud model and any MCP servers the caller passed,
  * loads message history for the requested thread from the storage driver,
  * runs the conversation while emitting Griptape Nodes ``AgentStreamEvent``
    tokens through the supplied sink so the chat sidebar UI streams as before,
  * logs every model request, tool call, and tool result so we can debug the
    "agent stopped after planning" failure mode end-to-end,
  * persists the new message history back through the storage driver.

The runner stays framework-agnostic on purpose: it doesn't know about
``RunAgentRequest`` or the global event manager, so it's easy to test and
swap.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from pydantic_ai import Agent
from pydantic_ai.exceptions import UsageLimitExceeded
from pydantic_ai.messages import (
    FinalResultEvent,
    FunctionToolCallEvent,
    FunctionToolResultEvent,
    PartDeltaEvent,
    PartStartEvent,
    RetryPromptPart,
    TextPart,
    TextPartDelta,
    ThinkingPart,
    ThinkingPartDelta,
    ToolCallPart,
)

from griptape_nodes.agents.pydantic_ai.image_tools import (
    IMAGE_TOOL_NAME,
    ImageGenerationToolset,
    ImageGenerationToolsetConfig,
    register_image_tools,
)
from griptape_nodes.agents.pydantic_ai.model import build_griptape_cloud_model
from griptape_nodes.agents.pydantic_ai.repo_context import load_repo_context

if TYPE_CHECKING:
    from collections.abc import AsyncIterable, Awaitable, Callable, Sequence
    from pathlib import Path

    from pydantic_ai._run_context import RunContext
    from pydantic_ai.messages import UserContent
    from pydantic_ai.toolsets import AbstractToolset
    from pydantic_ai.usage import UsageLimits

    from griptape_nodes.drivers.thread_storage.base_thread_storage_driver import BaseThreadStorageDriver
    from griptape_nodes.retained_mode.managers.static_files_manager import StaticFilesManager


logger = logging.getLogger("griptape_nodes")


TokenSink = "Callable[[str], Awaitable[None] | None]"
"""Callback that receives streamed text tokens for relay to clients."""

EventSink = "Callable[[RunEvent], Awaitable[None] | None]"
"""Callback that receives structured run events for relay to clients."""


# Cap how much of any string we'll write to the log so a giant tool argument
# or file payload doesn't drown the console.
_LOG_PREVIEW_BYTES = 240


@dataclass
class RunEvent:
    """Base class for structured events emitted during a runner ``run`` call."""


@dataclass
class TextDelta(RunEvent):
    """Incremental text token from the model's final response."""

    delta: str


@dataclass
class ToolCall(RunEvent):
    """The model has committed to a tool call."""

    tool_call_id: str
    tool_name: str
    args: str


@dataclass
class ToolResult(RunEvent):
    """A tool call has returned a value (or a retry prompt for an error)."""

    tool_call_id: str
    tool_name: str
    content: str
    is_error: bool = False


@dataclass
class ThinkingDelta(RunEvent):
    """Incremental reasoning text from the model."""

    delta: str


@dataclass
class AgentRunResult:
    """The return value of :meth:`PydanticAgentRunner.run`.

    Attributes:
        thread_id: The thread that was used (created if the caller passed None).
        output: The final assistant text response.
        message_count: Total messages in the thread after this run.
        image_urls: URLs of images produced by the ``generate_image`` tool
            during this run, in call order. Empty when no image was generated.
    """

    thread_id: str
    output: str
    message_count: int
    image_urls: list[str] = field(default_factory=list)


@dataclass
class PydanticAgentRunner:
    """Runs Pydantic AI agents and persists message history through a thread store."""

    model_name: str
    api_key: str
    workspace_root: Path
    storage: BaseThreadStorageDriver
    instructions: str | None = None
    base_url: str | None = None
    mcp_servers: list[AbstractToolset[Any]] = field(default_factory=list)
    image_config: ImageGenerationToolsetConfig | None = None
    static_files_manager: StaticFilesManager | None = None
    auto_load_repo_context: bool = True
    usage_limits: UsageLimits | None = None

    _agent: Agent[Any, str] = field(init=False)
    _image_toolset: ImageGenerationToolset | None = field(init=False, default=None)

    def __post_init__(self) -> None:
        toolsets: list[Any] = list(self.mcp_servers)
        instructions = self._build_instructions()
        self._agent = Agent(
            build_griptape_cloud_model(self.model_name, api_key=self.api_key, base_url=self.base_url),
            instructions=instructions,
            toolsets=toolsets or None,
        )
        if self.image_config is not None:
            if self.static_files_manager is None:
                msg = "image_config requires a static_files_manager to persist generated images."
                raise ValueError(msg)
            self._image_toolset = register_image_tools(self._agent, self.image_config, self.static_files_manager)
        logger.info(
            "PydanticAgentRunner ready: model=%s workspace=%s mcp_servers=%d "
            "image_tool=%s auto_repo_context=%s usage_limits=%s",
            self.model_name,
            self.workspace_root,
            len(self.mcp_servers),
            self._image_toolset is not None,
            self.auto_load_repo_context,
            self.usage_limits,
        )

    def _build_instructions(self) -> str | None:
        """Compose the instruction string from the user's input plus repo context."""
        parts: list[str] = []
        if self.instructions:
            parts.append(self.instructions)
        if self.auto_load_repo_context:
            repo_context = load_repo_context(self.workspace_root)
            if repo_context:
                parts.append(repo_context)
        return "\n\n".join(parts) or None

    @property
    def agent(self) -> Agent[Any, str]:
        return self._agent

    @property
    def image_toolset(self) -> ImageGenerationToolset | None:
        return self._image_toolset

    async def run(
        self,
        prompt: str | Sequence[UserContent],
        *,
        thread_id: str | None = None,
        token_sink: Callable[[str], Awaitable[None] | None] | None = None,
        event_sink: Callable[[RunEvent], Awaitable[None] | None] | None = None,
    ) -> AgentRunResult:
        """Run the agent against ``prompt``, streaming events and saving history.

        Args:
            prompt: The user prompt for this turn. Either plain text or a
                sequence of Pydantic AI user-content parts (e.g. text plus
                inlined ``BinaryContent`` images) for multimodal input.
            thread_id: Existing thread id, or ``None`` to start a fresh one.
            token_sink: Callback invoked with each text-delta token as it
                arrives from the model. Convenience hook for text-only
                consumers; use ``event_sink`` for the structured stream.
            event_sink: Callback invoked for every structured run event
                (text deltas, tool calls, tool results, thinking deltas).
                Use this to drive rich UI surfaces.

        Returns:
            An :class:`AgentRunResult` describing the new state of the thread.
        """
        if thread_id is None or not self.storage.thread_exists(thread_id):
            thread_id, _ = self.storage.create_thread()

        history = self.storage.load_history(thread_id)
        run_id = thread_id[:8]

        logger.info(
            "[run %s] start: model=%s history_len=%d prompt=%r",
            run_id,
            self.model_name,
            len(history),
            _prompt_preview(prompt),
        )
        started = time.monotonic()

        text_buffer: list[str] = []
        # Log counters - every event funnels through `_event_handler` which
        # bumps these in lockstep with what the model is actually doing.
        counters = _RunCounters(run_id=run_id)

        async def event_handler(_ctx: RunContext[Any], events: AsyncIterable[Any]) -> None:
            await counters.consume(events, token_sink, event_sink, text_buffer)

        try:
            agent_result = await self._agent.run(
                prompt,
                message_history=history,
                usage_limits=self.usage_limits,
                event_stream_handler=event_handler,
            )
        except UsageLimitExceeded as exc:
            logger.warning(
                "[run %s] usage limit exceeded: %s. Aborting run; no history saved for this turn.",
                run_id,
                exc,
            )
            raise

        new_messages = agent_result.all_messages()
        usage = agent_result.usage

        elapsed = time.monotonic() - started
        text = "".join(text_buffer)
        logger.info(
            "[run %s] done in %.2fs: requests=%d tool_calls=%d "
            "input_tokens=%d output_tokens=%d new_messages=%d output=%r",
            run_id,
            elapsed,
            usage.requests,
            counters.tool_calls,
            usage.input_tokens,
            usage.output_tokens,
            len(new_messages),
            _preview(text),
        )
        if not text and counters.tool_calls == 0:
            logger.warning(
                "[run %s] empty assistant turn: model returned no text and no tool calls.",
                run_id,
            )
        elif not text:
            logger.warning(
                "[run %s] assistant produced no final text after %d tool calls. "
                "The chat sidebar may render this turn as silent.",
                run_id,
                counters.tool_calls,
            )

        self.storage.save_history(thread_id, list(new_messages))
        return AgentRunResult(
            thread_id=thread_id,
            output=text,
            message_count=len(new_messages),
            image_urls=list(counters.image_urls),
        )


@dataclass
class _RunCounters:
    """Aggregate per-run counters fed by the event-stream handler."""

    run_id: str
    text_parts: int = 0
    tool_calls: int = 0
    final_result_emitted: bool = False
    image_urls: list[str] = field(default_factory=list)

    async def consume(
        self,
        events: AsyncIterable[Any],
        token_sink: Callable[[str], Awaitable[None] | None] | None,
        event_sink: Callable[[RunEvent], Awaitable[None] | None] | None,
        text_buffer: list[str],
    ) -> None:
        async for event in events:
            await self._on_event(event, token_sink, event_sink, text_buffer)

    async def _on_event(
        self,
        event: Any,
        token_sink: Callable[[str], Awaitable[None] | None] | None,
        event_sink: Callable[[RunEvent], Awaitable[None] | None] | None,
        text_buffer: list[str],
    ) -> None:
        if isinstance(event, PartStartEvent):
            await self._on_part_start(event, token_sink, event_sink, text_buffer)
        elif isinstance(event, PartDeltaEvent):
            await self._on_part_delta(event, token_sink, event_sink, text_buffer)
        elif isinstance(event, FunctionToolCallEvent):
            self.tool_calls += 1
            args_str = _args_str(event.part.args)
            logger.info(
                "[run %s] tool call #%d -> %s(%s) id=%s",
                self.run_id,
                self.tool_calls,
                event.part.tool_name,
                _preview(args_str),
                event.part.tool_call_id,
            )
            await _push_event(
                event_sink,
                ToolCall(
                    tool_call_id=event.part.tool_call_id,
                    tool_name=event.part.tool_name,
                    args=_args_json(event.part.args),
                ),
            )
        elif isinstance(event, FunctionToolResultEvent):
            part = getattr(event, "part", None) or getattr(event, "result", None)
            content = getattr(part, "content", None)
            tool_name = getattr(part, "tool_name", "?")
            is_error = isinstance(part, RetryPromptPart)
            content_str = _stringify(content)
            if tool_name == IMAGE_TOOL_NAME and not is_error and content_str:
                self.image_urls.append(content_str)
            logger.info(
                "[run %s] tool result <- %s id=%s preview=%r is_error=%s",
                self.run_id,
                tool_name,
                event.tool_call_id,
                _preview(content_str),
                is_error,
            )
            await _push_event(
                event_sink,
                ToolResult(
                    tool_call_id=event.tool_call_id,
                    tool_name=tool_name,
                    content=_truncate(content_str, _RESULT_TRANSPORT_BYTES),
                    is_error=is_error,
                ),
            )
        elif isinstance(event, FinalResultEvent):
            self.final_result_emitted = True
            logger.info(
                "[run %s] final result event: tool_name=%s tool_call_id=%s",
                self.run_id,
                event.tool_name,
                event.tool_call_id,
            )

    async def _on_part_start(
        self,
        event: PartStartEvent,
        token_sink: Callable[[str], Awaitable[None] | None] | None,
        event_sink: Callable[[RunEvent], Awaitable[None] | None] | None,
        text_buffer: list[str],
    ) -> None:
        if isinstance(event.part, TextPart):
            self.text_parts += 1
            logger.info("[run %s] text part #%d started", self.run_id, self.text_parts)
            if event.part.content:
                text_buffer.append(event.part.content)
                await _push_token(token_sink, event.part.content)
                await _push_event(event_sink, TextDelta(delta=event.part.content))
        elif isinstance(event.part, ThinkingPart):
            if event.part.content:
                await _push_event(event_sink, ThinkingDelta(delta=event.part.content))
        elif isinstance(event.part, ToolCallPart):
            logger.info(
                "[run %s] tool-call part started: %s id=%s",
                self.run_id,
                event.part.tool_name,
                event.part.tool_call_id,
            )

    @staticmethod
    async def _on_part_delta(
        event: PartDeltaEvent,
        token_sink: Callable[[str], Awaitable[None] | None] | None,
        event_sink: Callable[[RunEvent], Awaitable[None] | None] | None,
        text_buffer: list[str],
    ) -> None:
        if isinstance(event.delta, TextPartDelta):
            chunk = event.delta.content_delta
            if not chunk:
                return
            text_buffer.append(chunk)
            await _push_token(token_sink, chunk)
            await _push_event(event_sink, TextDelta(delta=chunk))
        elif isinstance(event.delta, ThinkingPartDelta):
            chunk = event.delta.content_delta
            if not chunk:
                return
            await _push_event(event_sink, ThinkingDelta(delta=chunk))


async def _push_token(
    token_sink: Callable[[str], Awaitable[None] | None] | None,
    token: str,
) -> None:
    if token_sink is None:
        return
    result = token_sink(token)
    if hasattr(result, "__await__"):
        await result  # type: ignore[func-returns-value]


async def _push_event(
    event_sink: Callable[[RunEvent], Awaitable[None] | None] | None,
    event: RunEvent,
) -> None:
    if event_sink is None:
        return
    result = event_sink(event)
    if hasattr(result, "__await__"):
        await result  # type: ignore[func-returns-value]


def _preview(value: str) -> str:
    if len(value) <= _LOG_PREVIEW_BYTES:
        return value
    return value[:_LOG_PREVIEW_BYTES] + "..."


def _prompt_preview(prompt: str | Sequence[UserContent]) -> str:
    """Render a log-safe preview of a prompt that may carry binary content.

    Text parts are previewed inline; non-text parts (images, audio, etc.) are
    rendered as a ``<TypeName>`` marker so a binary payload never hits the log.
    """
    if isinstance(prompt, str):
        return _preview(prompt)
    parts = [_preview(item) if isinstance(item, str) else f"<{type(item).__name__}>" for item in prompt]
    return " ".join(parts)


def _stringify(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, default=str)
    except (TypeError, ValueError):
        return str(value)


def _args_str(args: Any) -> str:
    if args is None:
        return "<empty: None>"
    if isinstance(args, str):
        if not args:
            return "<empty: ''>"
        return args
    if isinstance(args, dict):
        if not args:
            return "<empty: {}>"
        # Keys only: argument values are often huge file payloads.
        return "{" + ", ".join(f"{k}=..." for k in args) + "}"
    return str(args)


# Cap on how much arg JSON we ship to clients. Larger than the log preview so
# UI surfaces show meaningful detail, smaller than "unbounded" so a giant file
# payload doesn't bloat the WebSocket frame.
_ARGS_TRANSPORT_BYTES = 4096
_RESULT_TRANSPORT_BYTES = 16384


def _truncate(value: str, limit: int) -> str:
    if len(value) <= limit:
        return value
    return value[:limit] + "..."


def _args_json(args: Any) -> str:
    """Return a JSON-ish string of ``args`` suitable for transport to the UI.

    Unlike :func:`_args_str` which redacts dict values for log readability,
    this preserves the full structure so callers can render real tool-call
    detail. The result is truncated at :data:`_ARGS_TRANSPORT_BYTES` to bound
    the on-the-wire size.
    """
    if args is None:
        return "{}"
    if isinstance(args, str):
        text = args or "{}"
    else:
        try:
            text = json.dumps(args, default=str)
        except (TypeError, ValueError):
            text = str(args)
    if len(text) <= _ARGS_TRANSPORT_BYTES:
        return text
    return text[:_ARGS_TRANSPORT_BYTES] + "..."
