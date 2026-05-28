"""Tests for the Griptape Cloud SSE -> Pydantic AI stream-event translation."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import TYPE_CHECKING

import pytest
from pydantic_ai.messages import (
    PartDeltaEvent,
    PartStartEvent,
    TextPart,
    TextPartDelta,
    ToolCallPart,
    ToolCallPartDelta,
)
from pydantic_ai.models import ModelRequestParameters

from griptape_nodes.agents.pydantic_ai.griptape_cloud_model import GriptapeCloudStreamedResponse

if TYPE_CHECKING:
    from collections.abc import AsyncIterator


@dataclass
class _FakeResponse:
    lines: list[str]

    async def aiter_lines(self) -> AsyncIterator[str]:
        for line in self.lines:
            yield line

    async def aclose(self) -> None:
        return


def _sse(payload: dict) -> str:
    return f"data: {json.dumps(payload)}"


@pytest.mark.asyncio
class TestGriptapeCloudStreamedResponse:
    async def test_text_deltas_merge_into_one_text_part(self) -> None:
        lines = [
            _sse({"type": "DeltaMessage", "content": {"type": "TextDeltaMessageContent", "index": 0, "text": "He"}}),
            _sse({"type": "DeltaMessage", "content": {"type": "TextDeltaMessageContent", "index": 0, "text": "llo"}}),
        ]
        stream = GriptapeCloudStreamedResponse(
            model_request_parameters=ModelRequestParameters(),
            _response=_FakeResponse(lines),
            _model_name="test",
        )
        events = [e async for e in stream._get_event_iterator()]
        assert len(events) == 2  # noqa: PLR2004
        assert isinstance(events[0], PartStartEvent)
        assert isinstance(events[0].part, TextPart)
        assert events[0].part.content == "He"
        assert isinstance(events[1], PartDeltaEvent)
        assert isinstance(events[1].delta, TextPartDelta)
        assert events[1].delta.content_delta == "llo"

    async def test_tool_call_deltas_merge_partial_input_under_first_tag(self) -> None:
        # Mirrors what Griptape Cloud actually sends: the first chunk carries
        # tag/name/path; later chunks only carry partial_input slices and
        # share the same `index`.
        lines = [
            _sse(
                {
                    "type": "DeltaMessage",
                    "content": {
                        "type": "ActionCallDeltaMessageContent",
                        "index": 0,
                        "tag": "call_1",
                        "name": "Tool",
                        "path": "add",
                        "partial_input": "",
                    },
                },
            ),
            _sse(
                {
                    "type": "DeltaMessage",
                    "content": {
                        "type": "ActionCallDeltaMessageContent",
                        "index": 0,
                        "tag": None,
                        "name": None,
                        "path": None,
                        "partial_input": '{"a": 1, ',
                    },
                },
            ),
            _sse(
                {
                    "type": "DeltaMessage",
                    "content": {
                        "type": "ActionCallDeltaMessageContent",
                        "index": 0,
                        "tag": None,
                        "name": None,
                        "path": None,
                        "partial_input": '"b": 2}',
                    },
                },
            ),
        ]
        stream = GriptapeCloudStreamedResponse(
            model_request_parameters=ModelRequestParameters(),
            _response=_FakeResponse(lines),
            _model_name="test",
        )
        events = [e async for e in stream._get_event_iterator()]
        # First event upgrades the delta into a ToolCallPart once the name lands.
        first = next((e for e in events if isinstance(e, PartStartEvent) and isinstance(e.part, ToolCallPart)), None)
        assert first is not None
        assert isinstance(first.part, ToolCallPart)
        assert first.part.tool_name == "add"
        assert first.part.tool_call_id == "call_1"

        # Subsequent chunks land as deltas with the JSON arg slices.
        deltas = [e for e in events if isinstance(e, PartDeltaEvent) and isinstance(e.delta, ToolCallPartDelta)]
        joined = "".join(str(d.delta.args_delta) for d in deltas if isinstance(d.delta, ToolCallPartDelta))
        assert joined == '{"a": 1, "b": 2}'

    async def test_usage_accumulates(self) -> None:
        lines = [
            _sse({"type": "DeltaMessage", "usage": {"input_tokens": 10, "output_tokens": 5}, "content": None}),
            _sse({"type": "DeltaMessage", "usage": {"input_tokens": 0, "output_tokens": 3}, "content": None}),
        ]
        stream = GriptapeCloudStreamedResponse(
            model_request_parameters=ModelRequestParameters(),
            _response=_FakeResponse(lines),
            _model_name="test",
        )
        async for _ in stream._get_event_iterator():
            pass
        assert stream._usage.input_tokens == 10  # noqa: PLR2004
        assert stream._usage.output_tokens == 8  # noqa: PLR2004

    async def test_error_payload_raises(self) -> None:
        lines = [_sse({"error": "model is on fire"})]
        stream = GriptapeCloudStreamedResponse(
            model_request_parameters=ModelRequestParameters(),
            _response=_FakeResponse(lines),
            _model_name="test",
        )
        with pytest.raises(RuntimeError, match="model is on fire"):
            async for _ in stream._get_event_iterator():
                pass
