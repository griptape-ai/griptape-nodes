"""Tests for WebSocketConnectionCheck."""

from __future__ import annotations

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from websockets.exceptions import InvalidHandshake

from griptape_nodes.cli.commands.doctor.websocket_connection import WebSocketConnectionCheck

_MODULE = "griptape_nodes.cli.commands.doctor.websocket_connection"


class TestRun:
    def test_missing_api_key_returns_failure(self) -> None:
        """When no API key is found, run() returns a failed CheckResult."""
        check = WebSocketConnectionCheck()

        with patch.object(check, "_get_api_key", return_value=None):
            result = check.run()

        assert result.passed is False
        assert "GT_CLOUD_API_KEY" in result.message

    def test_connection_error_returns_failure(self) -> None:
        """When _test_connection raises ConnectionError, run() returns a failed CheckResult."""
        check = WebSocketConnectionCheck()
        error_message = "Connection timed out."

        with (
            patch.object(check, "_get_api_key", return_value="test-key"),
            patch.object(check, "_test_connection", new_callable=AsyncMock, side_effect=ConnectionError(error_message)),
        ):
            result = check.run()

        assert result.passed is False
        assert result.message == error_message

    def test_successful_connection_returns_pass(self) -> None:
        """When _test_connection succeeds, run() returns a passed CheckResult."""
        check = WebSocketConnectionCheck()

        with (
            patch.object(check, "_get_api_key", return_value="test-key"),
            patch.object(check, "_test_connection", new_callable=AsyncMock),
        ):
            result = check.run()

        assert result.passed is True


class TestGetApiKey:
    def test_returns_env_var_when_set(self) -> None:
        """GT_CLOUD_API_KEY from the environment is returned first."""
        check = WebSocketConnectionCheck()

        with patch(f"{_MODULE}.getenv", return_value="env-key"):
            result = check._get_api_key()

        assert result == "env-key"

    def test_falls_back_to_dotenv_when_env_var_absent(self) -> None:
        """Falls back to the .env file when the environment variable is not set."""
        check = WebSocketConnectionCheck()
        mock_dotenv = MagicMock()
        mock_dotenv.get.return_value = "dotenv-key"

        with (
            patch(f"{_MODULE}.getenv", return_value=None),
            patch(f"{_MODULE}.DotEnv", return_value=mock_dotenv),
        ):
            result = check._get_api_key()

        assert result == "dotenv-key"

    def test_returns_none_when_key_absent_everywhere(self) -> None:
        """Returns None when neither the environment variable nor .env contains the key."""
        check = WebSocketConnectionCheck()
        mock_dotenv = MagicMock()
        mock_dotenv.get.return_value = None

        with (
            patch(f"{_MODULE}.getenv", return_value=None),
            patch(f"{_MODULE}.DotEnv", return_value=mock_dotenv),
        ):
            result = check._get_api_key()

        assert result is None


class TestGetWebsocketUrl:
    def test_returns_default_url(self) -> None:
        """Returns the default Nodes API WebSocket URL when no override is set."""
        check = WebSocketConnectionCheck()

        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("GRIPTAPE_NODES_API_BASE_URL", None)
            url = check._get_websocket_url()

        assert url == "wss://api.nodes.griptape.ai/ws/engines/events?version=v2"

    def test_respects_base_url_override(self) -> None:
        """Uses GRIPTAPE_NODES_API_BASE_URL when set."""
        check = WebSocketConnectionCheck()

        def mock_getenv(key: str, default: str | None = None) -> str | None:
            if key == "GRIPTAPE_NODES_API_BASE_URL":
                return "https://custom.example.com"
            return default

        with patch(f"{_MODULE}.getenv", side_effect=mock_getenv):
            url = check._get_websocket_url()

        assert url.startswith("wss://custom.example.com")


class TestTestConnection:
    @pytest.mark.asyncio
    async def test_timeout_raises_connection_error(self) -> None:
        """A TimeoutError from the WebSocket connect is re-raised as ConnectionError."""
        check = WebSocketConnectionCheck()

        with (
            patch.object(check, "_connect_and_disconnect", new_callable=AsyncMock, side_effect=TimeoutError),
            pytest.raises(ConnectionError, match="timed out"),
        ):
            await check._test_connection("test-key")

    @pytest.mark.asyncio
    async def test_invalid_handshake_raises_connection_error(self) -> None:
        """An InvalidHandshake (e.g. 401) is re-raised as ConnectionError."""
        check = WebSocketConnectionCheck()

        with (
            patch.object(
                check, "_connect_and_disconnect", new_callable=AsyncMock, side_effect=InvalidHandshake("rejected")
            ),
            pytest.raises(ConnectionError, match="API key"),
        ):
            await check._test_connection("test-key")

    @pytest.mark.asyncio
    async def test_os_error_raises_connection_error(self) -> None:
        """An OSError (network unreachable) is re-raised as ConnectionError."""
        check = WebSocketConnectionCheck()

        with (
            patch.object(check, "_connect_and_disconnect", new_callable=AsyncMock, side_effect=OSError("refused")),
            pytest.raises(ConnectionError, match="network"),
        ):
            await check._test_connection("test-key")

    @pytest.mark.asyncio
    async def test_success_does_not_raise(self) -> None:
        """A clean connection attempt completes without raising."""
        check = WebSocketConnectionCheck()

        with patch.object(check, "_connect_and_disconnect", new_callable=AsyncMock):
            await check._test_connection("test-key")
