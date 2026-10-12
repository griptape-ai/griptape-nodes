"""Per-run approval state for chat-agent tool calls that spend credits or run work.

A gated call ends the run with Pydantic AI's ``DeferredToolRequests`` instead of
executing, and the caller resumes the thread later with ``DeferredToolResults``.

Which calls are gated is decided per toolset (see ``mcp_servers`` and
``image_tools``), but every gate reads the same :class:`ToolApprovalDeps` off
``ctx.deps``. The state has to arrive per run: the engine's MCP toolset is baked
into a cached agent and user MCP toolsets are cached across runs, so anything
captured at construction would go stale the moment the user grants or clears a
permission.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from pydantic_ai.messages import ModelRequest, ModelResponse, RetryPromptPart, ToolReturnPart

if TYPE_CHECKING:
    from collections.abc import Sequence

    from pydantic_ai.messages import ModelMessage, ToolCallPart


TOOL_DENIED_BY_USER_MESSAGE = (
    "The user declined to run this. Do not retry it or work around it with a different tool. "
    "Answer in text, or ask the user before trying again."
)
"""What the model reads in place of a tool result the user denied."""

TOOL_DENIED_BY_NEW_MESSAGE = "The user sent a new message instead of answering this approval request."
"""What the model reads for a pending call the user skipped by sending another message."""


@dataclass(frozen=True)
class ToolApprovalDeps:
    """Approval state for one agent run, passed as the run's ``deps``.

    Attributes:
        enabled: Whether gated tools must ask before running. ``False`` runs every
            tool without pausing.
        granted: Grant keys the user approved for the whole conversation. A gated
            call runs without asking when all of its grant keys are in here.
    """

    enabled: bool = False
    granted: frozenset[str] = field(default_factory=frozenset)


def needs_approval(deps: ToolApprovalDeps, grant_keys: Sequence[str]) -> bool:
    """Whether a call with these grant keys must wait for the user.

    An empty ``grant_keys`` means the call has nothing that needs approving.
    """
    if not deps.enabled:
        return False
    if not grant_keys:
        return False
    return not deps.granted.issuperset(grant_keys)


def pending_tool_calls(history: Sequence[ModelMessage]) -> list[ToolCallPart]:
    """Return the tool calls a paused turn is still waiting on, in call order.

    A turn that paused for approval ends in the ``ModelResponse`` carrying the
    calls, optionally followed by a ``ModelRequest`` holding the results of the
    calls in that response that ran without asking. The pending calls are the
    ones with no result. Any other shape, including a trailing request with a
    user prompt in it, has nothing pending.
    """
    if not history:
        return []

    last = history[-1]
    answered: set[str] = set()
    if isinstance(last, ModelResponse):
        response = last
    elif isinstance(last, ModelRequest):
        if len(history) < 2:  # noqa: PLR2004
            return []
        previous = history[-2]
        if not isinstance(previous, ModelResponse):
            return []
        if not all(isinstance(part, (ToolReturnPart, RetryPromptPart)) for part in last.parts):
            return []
        response = previous
        answered = {part.tool_call_id for part in last.parts if isinstance(part, (ToolReturnPart, RetryPromptPart))}
    else:
        return []

    return [call for call in response.tool_calls if call.tool_call_id not in answered]
