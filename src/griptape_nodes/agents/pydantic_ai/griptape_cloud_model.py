"""Pydantic AI :class:`Model` adapter for Griptape Cloud chat-messages."""

from __future__ import annotations

import json
import logging
import os
import tempfile
import uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from pydantic_ai.messages import (
    FinishReason,
    ModelResponse,
    ModelResponseStreamEvent,
    ToolCallPart,
)
from pydantic_ai.models import Model, ModelRequestParameters, StreamedResponse, check_allow_model_requests
from pydantic_ai.usage import RequestUsage

from griptape_nodes.agents.pydantic_ai._translation import (
    griptape_message_to_response_parts,
    messages_to_griptape,
    tools_to_griptape,
)
from griptape_nodes.agents.pydantic_ai.griptape_cloud_provider import GriptapeCloudProvider

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from pydantic_ai.messages import ModelMessage
    from pydantic_ai.profiles import ModelProfileSpec
    from pydantic_ai.settings import ModelSettings


logger = logging.getLogger("griptape_nodes")


CHAT_MESSAGES_PATH = "/api/chat/messages/"
CHAT_MESSAGES_STREAM_PATH = "/api/chat/messages/stream/"
HTTP_BAD_REQUEST = 400


class GriptapeCloudModel(Model):
    """Routes Pydantic AI agent requests through Griptape Cloud's chat-messages API.

    Griptape Cloud picks the underlying provider (OpenAI, Anthropic, Bedrock,
    Google, etc.) based on the `driver_configuration.model` we send. Native
    tool calls and structured output flow through Griptape's own message format,
    so this adapter speaks no provider SDK directly — only HTTP.
    """

    def __init__(  # noqa: PLR0913
        self,
        model_name: str,
        *,
        provider: GriptapeCloudProvider | None = None,
        api_key: str | None = None,
        base_url: str | None = None,
        settings: ModelSettings | None = None,
        profile: ModelProfileSpec | None = None,
    ) -> None:
        super().__init__(settings=settings, profile=profile)
        self._model_name = model_name
        self._gtc_provider: GriptapeCloudProvider = provider or GriptapeCloudProvider(
            api_key=api_key, base_url=base_url
        )
        self._provider = self._gtc_provider
        self._tool_schemas_logged = False
        self._payload_dumped = False

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def system(self) -> str:
        return "griptape-cloud"

    @property
    def base_url(self) -> str | None:
        return self._gtc_provider.base_url

    async def request(
        self,
        messages: list[ModelMessage],
        model_settings: ModelSettings | None,
        model_request_parameters: ModelRequestParameters,
    ) -> ModelResponse:
        check_allow_model_requests()
        model_settings, model_request_parameters = self.prepare_request(model_settings, model_request_parameters)
        messages = self.prepare_messages(messages)

        payload = self._build_payload(messages, model_settings, model_request_parameters, stream=False)
        response = await self._gtc_provider.client.post(
            self._url(CHAT_MESSAGES_PATH),
            headers=self._gtc_provider.auth_headers,
            json=payload,
        )
        _raise_for_griptape_cloud_error(response)
        return self._build_model_response(response.json())

    @asynccontextmanager
    async def request_stream(
        self,
        messages: list[ModelMessage],
        model_settings: ModelSettings | None,
        model_request_parameters: ModelRequestParameters,
        run_context: Any | None = None,  # noqa: ARG002
    ) -> AsyncIterator[StreamedResponse]:
        check_allow_model_requests()
        model_settings, model_request_parameters = self.prepare_request(model_settings, model_request_parameters)
        messages = self.prepare_messages(messages)

        payload = self._build_payload(messages, model_settings, model_request_parameters, stream=True)
        async with self._gtc_provider.client.stream(
            "POST",
            self._url(CHAT_MESSAGES_STREAM_PATH),
            headers=self._gtc_provider.auth_headers,
            json=payload,
        ) as response:
            if response.status_code >= HTTP_BAD_REQUEST:
                body = (await response.aread()).decode(errors="replace")
                msg = (
                    f"Griptape Cloud chat-messages stream failed: {response.status_code} {response.reason_phrase}. "
                    f"Body: {body}"
                )
                raise RuntimeError(msg)
            stream = GriptapeCloudStreamedResponse(
                model_request_parameters=model_request_parameters,
                _response=response,
                _model_name=self._model_name,
                _provider_name=self._gtc_provider.name,
                _provider_url=self._gtc_provider.base_url,
            )
            yield stream

    def _build_payload(
        self,
        messages: list[ModelMessage],
        model_settings: ModelSettings | None,
        model_request_parameters: ModelRequestParameters,
        *,
        stream: bool,
    ) -> dict[str, Any]:
        settings = model_settings or {}
        tool_defs = [
            *model_request_parameters.function_tools,
            *model_request_parameters.output_tools,
        ]
        self._maybe_log_tool_schemas(tool_defs)

        driver_configuration: dict[str, Any] = {
            "model": self._model_name,
            "stream": stream,
        }
        if tool_defs:
            driver_configuration["use_native_tools"] = True
        if (max_tokens := settings.get("max_tokens")) is not None:
            driver_configuration["max_tokens"] = max_tokens
        if (temperature := settings.get("temperature")) is not None:
            driver_configuration["temperature"] = temperature
        if (extra := settings.get("extra_body")) is not None:
            driver_configuration["extra_params"] = extra

        payload: dict[str, Any] = {
            "messages": messages_to_griptape(
                messages,
                instruction_parts=self._get_instruction_parts(messages, model_request_parameters),
            ),
            "tools": tools_to_griptape(tool_defs),
            "driver_configuration": driver_configuration,
        }
        if (output_object := model_request_parameters.output_object) is not None:
            payload["output_schema"] = output_object.json_schema
        self._maybe_dump_payload(payload)
        return payload

    def _build_model_response(self, body: dict[str, Any]) -> ModelResponse:
        usage_dict = body.get("usage") or {}
        usage = RequestUsage(
            input_tokens=int(usage_dict.get("input_tokens") or 0),
            output_tokens=int(usage_dict.get("output_tokens") or 0),
        )

        parts: list[Any] = list(griptape_message_to_response_parts(body))
        finish_reason: FinishReason | None = "tool_call" if any(isinstance(p, ToolCallPart) for p in parts) else "stop"

        return ModelResponse(
            parts=parts,
            usage=usage,
            model_name=self._model_name,
            provider_name=self._provider.name,
            provider_url=self._provider.base_url,
            finish_reason=finish_reason,
        )

    def _url(self, path: str) -> str:
        return f"{self._gtc_provider.base_url.rstrip('/')}{path}"

    def _maybe_dump_payload(self, payload: dict[str, Any]) -> None:
        """On the first request, dump the full POST body to a temp file when GTN_DUMP_GTC_PAYLOAD is set.

        Used to debug "the model called the tool with empty args" failures by capturing the exact
        JSON body the agent sends to Griptape Cloud's chat-messages endpoint. Disabled by default;
        set the env var to any non-empty value to enable.
        """
        if self._payload_dumped:
            return
        if not os.environ.get("GTN_DUMP_GTC_PAYLOAD"):
            return
        self._payload_dumped = True
        path = Path(tempfile.gettempdir()) / f"gtc_payload_{uuid.uuid4().hex}.json"
        try:
            path.write_text(json.dumps(payload, indent=2, default=str))
        except OSError as exc:
            logger.warning("Failed to dump GTC payload to %s: %s", path, exc)
            return
        logger.info("Dumped GTC chat-messages payload to %s", path)

    def _maybe_log_tool_schemas(self, tool_defs: list[Any]) -> None:
        """On the first request, log the JSON schema of every tool we're sending.

        This surfaces what the model actually sees, which is the only reliable way
        to debug "the model called the tool with empty args" failures: the model's
        view is determined by the schema we hand it, not by our Python source.
        Logged once per :class:`GriptapeCloudModel` instance to keep the console
        readable.
        """
        if self._tool_schemas_logged:
            return
        self._tool_schemas_logged = True
        if not tool_defs:
            return
        for td in tool_defs:
            try:
                schema = json.dumps(td.parameters_json_schema, indent=2, default=str)
            except (TypeError, ValueError):
                schema = repr(td.parameters_json_schema)
            logger.info(
                "Tool schema [%s]: %s\n%s",
                td.name,
                (td.description or "").splitlines()[0] if td.description else "<no description>",
                schema,
            )


def _raise_for_griptape_cloud_error(response: Any) -> None:
    """Raise with the response body in the message so cloud-side errors are visible."""
    if response.status_code < HTTP_BAD_REQUEST:
        return
    body = response.text
    msg = f"Griptape Cloud chat-messages request failed: {response.status_code} {response.reason_phrase}. Body: {body}"
    raise RuntimeError(msg)


@dataclass
class GriptapeCloudStreamedResponse(StreamedResponse):
    """Translates Griptape Cloud SSE deltas into Pydantic AI stream events."""

    _response: Any = None
    _model_name: str = ""
    _provider_name: str | None = None
    _provider_url: str | None = None
    _timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def provider_name(self) -> str | None:
        return self._provider_name

    @property
    def provider_url(self) -> str | None:
        return self._provider_url

    @property
    def timestamp(self) -> datetime:
        return self._timestamp

    async def close_stream(self) -> None:
        if self._response is not None:
            await self._response.aclose()

    async def _get_event_iterator(self) -> AsyncIterator[ModelResponseStreamEvent]:
        # Track the tool_call_id Griptape sends on the first chunk of each
        # tool-call sequence: subsequent partial_input chunks reuse the same
        # `index` but null out tag/name/path. We hand a stable vendor id to
        # the parts manager so adjacent deltas merge into one ToolCallPart.
        tool_call_ids: dict[int, str] = {}
        async for line in self._response.aiter_lines():
            if not line.startswith("data:"):
                continue
            payload_str = line.removeprefix("data:").strip()
            if not payload_str:
                continue
            try:
                delta = json.loads(payload_str)
            except json.JSONDecodeError:
                logger.warning("Skipping malformed Griptape Cloud SSE line: %s", payload_str)
                continue
            if "error" in delta:
                msg = f"Griptape Cloud stream error: {delta['error']}"
                raise RuntimeError(msg)
            for event in self._consume_delta(delta, tool_call_ids):
                yield event

    def _consume_delta(self, delta: dict[str, Any], tool_call_ids: dict[int, str]) -> list[ModelResponseStreamEvent]:
        events: list[ModelResponseStreamEvent] = []

        if (usage := delta.get("usage")) is not None:
            input_tokens = usage.get("input_tokens")
            output_tokens = usage.get("output_tokens")
            if input_tokens or output_tokens:
                self._usage += RequestUsage(
                    input_tokens=int(input_tokens or 0),
                    output_tokens=int(output_tokens or 0),
                )

        content = delta.get("content")
        if not content:
            return events

        kind = content.get("type")
        index = int(content.get("index", 0))
        if kind == "TextDeltaMessageContent":
            text = content.get("text") or ""
            if not text:
                return events
            events.extend(
                self._parts_manager.handle_text_delta(
                    vendor_part_id=f"text-{index}",
                    content=text,
                )
            )
        elif kind == "ActionCallDeltaMessageContent":
            tag = content.get("tag")
            if tag is not None:
                tool_call_ids[index] = tag
            tool_call_id = tool_call_ids.get(index)
            event = self._parts_manager.handle_tool_call_delta(
                vendor_part_id=f"tool-{index}",
                tool_name=content.get("path"),
                args=content.get("partial_input"),
                tool_call_id=tool_call_id,
            )
            if event is not None:
                events.append(event)
        return events
