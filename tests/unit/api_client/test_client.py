"""Tests for WebSocket client large payload warning."""

from __future__ import annotations

import json
import logging
from unittest.mock import AsyncMock

import pytest

from griptape_nodes.api_client.client import LARGE_PAYLOAD_WARNING_THRESHOLD, Client


class TestClientLargePayloadWarning:
    @pytest.fixture
    def client(self) -> Client:
        """Client with a mocked WebSocket so _send_message can run without a real connection."""
        c = Client(api_key="test_key", url="ws://localhost")
        c._websocket = AsyncMock()
        return c

    @pytest.mark.asyncio
    async def test_no_warning_for_small_payload(self, client: Client, caplog: pytest.LogCaptureFixture) -> None:
        """No warning is logged when the serialized message is under the threshold."""
        message = {"type": "test_event", "payload": {"data": "small"}, "topic": "test/topic"}

        with caplog.at_level(logging.WARNING, logger="griptape_nodes_client"):
            await client._send_message(message)

        assert not any("large" in record.message.lower() for record in caplog.records)

    @pytest.mark.asyncio
    async def test_warns_for_large_payload(self, client: Client, caplog: pytest.LogCaptureFixture) -> None:
        """A warning including the event type is logged when the message exceeds the threshold."""
        large_data = "x" * (LARGE_PAYLOAD_WARNING_THRESHOLD + 1)
        message = {"type": "test_event", "payload": {"data": large_data}, "topic": "test/topic"}

        with caplog.at_level(logging.WARNING, logger="griptape_nodes_client"):
            await client._send_message(message)

        warning_records = [r for r in caplog.records if r.levelno == logging.WARNING]
        assert len(warning_records) == 1
        assert "test_event" in warning_records[0].message

    @pytest.mark.asyncio
    async def test_message_still_sent_when_large(self, client: Client) -> None:
        """The message is still delivered over the WebSocket even when the payload is large."""
        large_data = "x" * (LARGE_PAYLOAD_WARNING_THRESHOLD + 1)
        message = {"type": "test_event", "payload": {"data": large_data}, "topic": "test/topic"}

        await client._send_message(message)

        client._websocket.send.assert_called_once_with(json.dumps(message))
