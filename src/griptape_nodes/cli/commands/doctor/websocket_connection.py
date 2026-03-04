"""WebSocket connection health check."""

import asyncio
from os import getenv
from urllib.parse import urljoin

from dotenv.main import DotEnv
from websockets.asyncio.client import connect
from websockets.exceptions import InvalidHandshake
from xdg_base_dirs import xdg_config_home

from griptape_nodes.cli.commands.doctor.base import CheckResult, HealthCheck


class WebSocketConnectionCheck(HealthCheck):
    """Verifies a WebSocket connection to the Nodes API using the configured API key."""

    _ENV_VAR_PATH = xdg_config_home() / "griptape_nodes" / ".env"
    _CONNECTION_TIMEOUT = 10.0

    def run(self) -> CheckResult:
        api_key = self._get_api_key()
        if api_key is None:
            return CheckResult(
                name="WebSocket Connection",
                passed=False,
                message="No API key found. Set GT_CLOUD_API_KEY in your environment or .env file.",
            )

        try:
            asyncio.run(self._test_connection(api_key))
        except ConnectionError as e:
            return CheckResult(
                name="WebSocket Connection",
                passed=False,
                message=str(e),
            )

        return CheckResult(
            name="WebSocket Connection",
            passed=True,
            message="Successfully connected to Nodes API.",
        )

    def _get_api_key(self) -> str | None:
        api_key = getenv("GT_CLOUD_API_KEY")
        if api_key is not None:
            return api_key
        return DotEnv(self._ENV_VAR_PATH).get("GT_CLOUD_API_KEY")

    async def _test_connection(self, api_key: str) -> None:
        url = self._get_websocket_url()
        headers = {"Authorization": f"Bearer {api_key}"}
        try:
            await asyncio.wait_for(self._connect_and_disconnect(url, headers), timeout=self._CONNECTION_TIMEOUT)
        except TimeoutError as e:
            msg = "Connection timed out. Check your network connection and that the Nodes API is reachable."
            raise ConnectionError(msg) from e
        except InvalidHandshake as e:
            msg = f"Connection rejected by server. This usually indicates an invalid API key. Details: {e}"
            raise ConnectionError(msg) from e
        except OSError as e:
            msg = f"Could not reach Nodes API. Check your network connection. Details: {e}"
            raise ConnectionError(msg) from e

    async def _connect_and_disconnect(self, url: str, headers: dict[str, str]) -> None:
        async with connect(url, additional_headers=headers):
            pass

    def _get_websocket_url(self) -> str:
        return urljoin(
            getenv("GRIPTAPE_NODES_API_BASE_URL", "https://api.nodes.griptape.ai").replace("http", "ws"),
            "/ws/engines/events?version=v2",
        )
