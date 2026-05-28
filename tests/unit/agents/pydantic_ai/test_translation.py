"""Unit tests for the Pydantic AI <-> Griptape Cloud message/tool translation layer."""

from __future__ import annotations

from griptape.common import BaseMessage
from pydantic_ai.messages import (
    ModelRequest,
    ModelResponse,
    SystemPromptPart,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)
from pydantic_ai.tools import ToolDefinition

from griptape_nodes.agents.pydantic_ai._translation import (
    GTN_AGENT_TOOL_NAME,
    griptape_message_to_response_parts,
    messages_to_griptape,
    tools_to_griptape,
)


class TestMessagesToGriptape:
    def test_system_and_user_request(self) -> None:
        messages = [
            ModelRequest(parts=[SystemPromptPart(content="Be helpful.")]),
            ModelRequest(parts=[UserPromptPart(content="Hi there.")]),
        ]
        result = messages_to_griptape(messages)
        assert [m["role"] for m in result] == ["system", "user"]
        assert result[0]["content"][0]["artifact"]["value"] == "Be helpful."
        assert result[1]["content"][0]["artifact"]["value"] == "Hi there."

    def test_request_instructions_become_leading_system_message(self) -> None:
        from pydantic_ai.messages import InstructionPart

        messages = [
            ModelRequest(parts=[UserPromptPart(content="Hello")], instructions="You are a robot."),
        ]
        result = messages_to_griptape(
            messages,
            instruction_parts=[InstructionPart(content="You are a robot.")],
        )
        assert result[0]["role"] == "system"
        assert result[0]["content"][0]["artifact"]["value"] == "You are a robot."
        assert result[1]["role"] == "user"

    def test_instructions_emitted_only_once_across_multiple_requests(self) -> None:
        from pydantic_ai.messages import InstructionPart, ToolCallPart, ToolReturnPart

        messages = [
            ModelRequest(parts=[UserPromptPart(content="Hi")], instructions="Be brief."),
            ModelResponse(parts=[ToolCallPart(tool_name="t", args={}, tool_call_id="c1")]),
            ModelRequest(
                parts=[ToolReturnPart(tool_name="t", content="ok", tool_call_id="c1")],
                instructions="Be brief.",
            ),
        ]
        result = messages_to_griptape(
            messages,
            instruction_parts=[InstructionPart(content="Be brief.")],
        )
        roles = [m["role"] for m in result]
        # exactly one leading system message; no system between assistant and tool return.
        assert roles == ["system", "user", "assistant", "user"]

    def test_assistant_response_with_text_and_tool_call(self) -> None:
        messages = [
            ModelResponse(
                parts=[
                    TextPart(content="Calling..."),
                    ToolCallPart(tool_name="add", args={"a": 1, "b": 2}, tool_call_id="call_1"),
                ]
            ),
        ]
        result = messages_to_griptape(messages)
        assert len(result) == 1
        assert result[0]["role"] == "assistant"
        kinds = [c["type"] for c in result[0]["content"]]
        assert kinds == ["TextMessageContent", "ActionCallMessageContent"]
        action = result[0]["content"][1]["artifact"]["value"]
        assert action == {
            "type": "ToolAction",
            "tag": "call_1",
            "name": GTN_AGENT_TOOL_NAME,
            "path": "add",
            "input": {"a": 1, "b": 2},
        }

    def test_tool_return_lands_as_user_action_result(self) -> None:
        messages = [
            ModelRequest(
                parts=[
                    ToolReturnPart(tool_name="add", content="3", tool_call_id="call_1"),
                ]
            ),
        ]
        result = messages_to_griptape(messages)
        assert result[0]["role"] == "user"
        content = result[0]["content"][0]
        assert content["type"] == "ActionResultMessageContent"
        assert content["artifact"]["value"] == "3"
        assert content["action"]["tag"] == "call_1"
        assert content["action"]["path"] == "add"

    def test_string_args_round_trip_through_json(self) -> None:
        messages = [
            ModelResponse(
                parts=[ToolCallPart(tool_name="echo", args='{"x": 1}', tool_call_id="call_2")],
            ),
        ]
        result = messages_to_griptape(messages)
        assert result[0]["content"][0]["artifact"]["value"]["input"] == {"x": 1}

    def test_invalid_string_args_are_preserved_under_raw_key(self) -> None:
        messages = [
            ModelResponse(
                parts=[ToolCallPart(tool_name="echo", args="not json", tool_call_id="call_3")],
            ),
        ]
        result = messages_to_griptape(messages)
        assert result[0]["content"][0]["artifact"]["value"]["input"] == {"_raw_args": "not json"}

    def test_response_with_only_empty_parts_is_dropped(self) -> None:
        messages = [ModelResponse(parts=[TextPart(content="")])]
        assert messages_to_griptape(messages) == []

    def test_round_trip_through_griptape_base_message(self) -> None:
        """Translator output must be parseable by Griptape's `BaseMessage.from_dict`.

        The cloud endpoint feeds every message through `BaseMessage.from_dict`, so any
        shape we emit has to deserialize cleanly there.
        """
        messages = [
            ModelRequest(
                parts=[SystemPromptPart(content="Be terse."), UserPromptPart(content="Hi")],
            ),
            ModelResponse(
                parts=[
                    TextPart(content="ok"),
                    ToolCallPart(tool_name="add", args={"a": 1}, tool_call_id="call_1"),
                ]
            ),
            ModelRequest(parts=[ToolReturnPart(tool_name="add", content="1", tool_call_id="call_1")]),
        ]
        for msg_dict in messages_to_griptape(messages):
            BaseMessage.from_dict(msg_dict)


class TestToolsToGriptape:
    def test_empty_tool_list(self) -> None:
        assert tools_to_griptape([]) == []

    def test_tools_pack_under_single_griptape_tool_with_one_activity_each(self) -> None:
        tools = [
            ToolDefinition(name="read_file", description="Read", parameters_json_schema={"type": "object"}),
            ToolDefinition(name="write_file", description="Write", parameters_json_schema={"type": "object"}),
        ]
        result = tools_to_griptape(tools)
        assert len(result) == 1
        assert result[0]["name"] == GTN_AGENT_TOOL_NAME
        activity_names = [a["name"] for a in result[0]["activities"]]
        assert activity_names == ["read_file", "write_file"]


class TestGriptapeMessageToResponseParts:
    def test_text_message_becomes_text_part(self) -> None:
        message = {
            "type": "Message",
            "role": "assistant",
            "content": [
                {"type": "TextMessageContent", "artifact": {"type": "TextArtifact", "value": "hi"}},
            ],
        }
        parts = griptape_message_to_response_parts(message)
        assert len(parts) == 1
        assert isinstance(parts[0], TextPart)
        assert parts[0].content == "hi"

    def test_action_call_becomes_tool_call_part(self) -> None:
        message = {
            "type": "Message",
            "role": "assistant",
            "content": [
                {
                    "type": "ActionCallMessageContent",
                    "artifact": {
                        "type": "ActionArtifact",
                        "value": {
                            "type": "ToolAction",
                            "tag": "call_42",
                            "name": GTN_AGENT_TOOL_NAME,
                            "path": "add",
                            "input": {"a": 1, "b": 2},
                        },
                    },
                },
            ],
        }
        parts = griptape_message_to_response_parts(message)
        assert isinstance(parts[0], ToolCallPart)
        assert parts[0].tool_name == "add"
        assert parts[0].args == {"a": 1, "b": 2}
        assert parts[0].tool_call_id == "call_42"

    def test_empty_text_is_skipped(self) -> None:
        message = {
            "type": "Message",
            "role": "assistant",
            "content": [{"type": "TextMessageContent", "artifact": {"type": "TextArtifact", "value": ""}}],
        }
        assert griptape_message_to_response_parts(message) == []
