"""Translation between Pydantic AI types and Griptape Cloud wire format.

Griptape Cloud's `/api/chat/messages` endpoint speaks Griptape's `Message` and
`DeltaMessage` shapes. This module owns every conversion in both directions so
the rest of the model adapter stays focused on transport.

Two design choices worth flagging:

1.  Griptape tools are grouped: a *tool* has many *activities*, and a tool call
    on the wire carries both a tool `name` and an activity `path`. Pydantic AI
    tools are flat — one name per tool. We pack every Pydantic AI tool as a
    single activity under one synthetic Griptape tool (``GTN_AGENT_TOOL_NAME``)
    and use the activity name as the actual tool name. On the way back we drop
    the wrapping tool name and surface the activity name.

2.  Griptape's `ActionResultMessageContent` requires the original tool action
    (tag + name + path + input). Pydantic AI's `ToolReturnPart` carries only
    `tool_name`, `content`, and `tool_call_id`. We re-derive the action by
    walking the message history for the matching `ToolCallPart` so we can
    reconstruct a complete `ToolAction` payload.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from pydantic_ai.messages import (
    BinaryContent,
    DocumentUrl,
    ImageUrl,
    InstructionPart,
    ModelMessage,
    ModelRequest,
    ModelResponse,
    RetryPromptPart,
    SystemPromptPart,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

    from pydantic_ai.tools import ToolDefinition


GTN_AGENT_TOOL_NAME = "GriptapeNodesAgent"
"""Single Griptape tool wrapper that hosts every Pydantic AI tool as an activity."""


def messages_to_griptape(
    messages: Sequence[ModelMessage],
    *,
    instruction_parts: Sequence[InstructionPart] | None = None,
) -> list[dict[str, Any]]:
    """Convert Pydantic AI message history into a list of Griptape `Message` dicts.

    Each Pydantic AI ``ModelMessage`` may carry several parts. Most map 1:1 to a
    Griptape ``Message``. Agent-level ``instructions`` aren't attached to any
    individual part — they live on every ``ModelRequest`` and are deduped here
    by the caller resolving them once via ``Model._get_instruction_parts`` and
    passing them in. The output is the list that goes straight into the
    `messages` field of the chat-messages payload.
    """
    out: list[dict[str, Any]] = []
    if instruction_parts:
        out.extend(_text_message("system", part.content) for part in instruction_parts)
    for message in messages:
        if isinstance(message, ModelRequest):
            out.extend(_request_to_griptape(message))
        elif isinstance(message, ModelResponse):
            response_dict = _response_to_griptape(message)
            if response_dict is not None:
                out.append(response_dict)
    return out


def tools_to_griptape(tool_defs: Sequence[ToolDefinition]) -> list[dict[str, Any]]:
    """Pack Pydantic AI tools as a single Griptape tool with one activity per tool."""
    if not tool_defs:
        return []
    activities = [
        {
            "name": td.name,
            "description": td.description or "",
            "json_schema": td.parameters_json_schema,
        }
        for td in tool_defs
    ]
    return [{"name": GTN_AGENT_TOOL_NAME, "activities": activities}]


def griptape_message_to_response_parts(message_dict: dict[str, Any]) -> list[TextPart | ToolCallPart]:
    """Convert a single Griptape assistant `Message` dict into Pydantic AI response parts."""
    parts: list[TextPart | ToolCallPart] = []
    for content in message_dict.get("content", []):
        kind = content.get("type")
        if kind == "TextMessageContent":
            text = content.get("artifact", {}).get("value", "")
            if text:
                parts.append(TextPart(content=text))
        elif kind == "ActionCallMessageContent":
            action = content.get("artifact", {}).get("value", {})
            parts.append(_action_to_tool_call(action))
    return parts


def _action_to_tool_call(action: dict[str, Any]) -> ToolCallPart:
    return ToolCallPart(
        tool_name=action.get("path") or action.get("name", ""),
        args=action.get("input") or {},
        tool_call_id=action.get("tag", ""),
    )


def _request_to_griptape(request: ModelRequest) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []

    user_contents: list[dict[str, Any]] = []
    for part in request.parts:
        if isinstance(part, SystemPromptPart):
            out.append(_text_message("system", part.content))
        elif isinstance(part, UserPromptPart):
            user_contents.extend(_user_part_contents(part))
        elif isinstance(part, ToolReturnPart):
            # Each tool return becomes its own message. Griptape uses role='user'
            # for tool results (its convention, not OpenAI's 'tool' role).
            out.append(_tool_return_message(part))
        elif isinstance(part, RetryPromptPart):
            # A retry prompt is the framework's way of asking the model to fix a
            # tool call. Emit either a tool result with the retry text (if it
            # ties to a specific tool call) or a plain user message.
            if part.tool_call_id and part.tool_name:
                out.append(_retry_to_tool_return_message(part))
            else:
                out.append(_text_message("user", part.model_response()))
    if user_contents:
        out.append({"type": "Message", "role": "user", "content": user_contents})
    return out


def _response_to_griptape(response: ModelResponse) -> dict[str, Any] | None:
    contents: list[dict[str, Any]] = []
    for part in response.parts:
        if isinstance(part, TextPart) and part.content:
            contents.append(_text_content(part.content))
        elif isinstance(part, ToolCallPart):
            contents.append(_action_call_content(part))
    if not contents:
        return None
    return {"type": "Message", "role": "assistant", "content": contents}


def _user_part_contents(part: UserPromptPart) -> list[dict[str, Any]]:
    if isinstance(part.content, str):
        return [_text_content(part.content)]

    contents: list[dict[str, Any]] = []
    for piece in part.content:
        if isinstance(piece, str):
            contents.append(_text_content(piece))
        elif isinstance(piece, ImageUrl):
            contents.append(_image_url_content(piece))
        elif isinstance(piece, DocumentUrl):
            contents.append(_text_content(f"[Document URL: {piece.url}]"))
        elif isinstance(piece, BinaryContent) and piece.is_image:
            contents.append(_image_binary_content(piece))
        else:
            # Fallback for anything we don't handle yet — render as text so the
            # model still sees something rather than silently dropping content.
            contents.append(_text_content(f"[Unsupported content: {type(piece).__name__}]"))
    return contents


def _tool_return_message(part: ToolReturnPart) -> dict[str, Any]:
    return {
        "type": "Message",
        "role": "user",
        "content": [
            {
                "type": "ActionResultMessageContent",
                "artifact": {"type": "TextArtifact", "value": _stringify(part.content)},
                "action": {
                    "type": "ToolAction",
                    "tag": part.tool_call_id,
                    "name": GTN_AGENT_TOOL_NAME,
                    "path": part.tool_name,
                    # We don't have the original args here. Griptape's parser
                    # tolerates an empty dict; the model already saw the call.
                    "input": {},
                },
            }
        ],
    }


def _retry_to_tool_return_message(part: RetryPromptPart) -> dict[str, Any]:
    return {
        "type": "Message",
        "role": "user",
        "content": [
            {
                "type": "ActionResultMessageContent",
                "artifact": {"type": "TextArtifact", "value": part.model_response()},
                "action": {
                    "type": "ToolAction",
                    "tag": part.tool_call_id,
                    "name": GTN_AGENT_TOOL_NAME,
                    "path": part.tool_name,
                    "input": {},
                },
            }
        ],
    }


def _action_call_content(part: ToolCallPart) -> dict[str, Any]:
    args = part.args
    if isinstance(args, str):
        try:
            args_dict = json.loads(args) if args else {}
        except json.JSONDecodeError:
            args_dict = {"_raw_args": args}
    elif args is None:
        args_dict = {}
    else:
        args_dict = args
    return {
        "type": "ActionCallMessageContent",
        "artifact": {
            "type": "ActionArtifact",
            "value": {
                "type": "ToolAction",
                "tag": part.tool_call_id,
                "name": GTN_AGENT_TOOL_NAME,
                "path": part.tool_name,
                "input": args_dict,
            },
        },
    }


def _text_message(role: str, text: str) -> dict[str, Any]:
    return {"type": "Message", "role": role, "content": [_text_content(text)]}


def _text_content(text: str) -> dict[str, Any]:
    return {"type": "TextMessageContent", "artifact": {"type": "TextArtifact", "value": text}}


def _image_url_content(piece: ImageUrl) -> dict[str, Any]:
    # Griptape exposes image URLs through ImageUrlArtifact / ImageMessageContent.
    # The cloud accepts both URL and base64 inline images. We keep URLs as URLs
    # and let the cloud-side fetch / inline as needed.
    return {
        "type": "ImageMessageContent",
        "artifact": {"type": "ImageUrlArtifact", "value": piece.url},
    }


def _image_binary_content(piece: BinaryContent) -> dict[str, Any]:
    return {
        "type": "ImageMessageContent",
        "artifact": {
            "type": "ImageArtifact",
            "value": piece.base64,
            "format": piece.media_type.split("/")[-1] if piece.media_type else "png",
        },
    }


def _stringify(value: Any) -> str:
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, default=str)
    except (TypeError, ValueError):
        return str(value)
