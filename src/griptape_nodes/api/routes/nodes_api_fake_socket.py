import json
import os

import httpx
from urllib.parse import urljoin

from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes


class NodesApiFakeSocket:
    """Drop-in replacement for SocketIO that sends events to the Nodes API."""

    def emit(self, *args, **kwargs) -> None:  # noqa: ARG002 # drop-in replacement workaround
        service = "Nodes"
        value = "GRIPTAPE_NODES_API_KEY"
        api_token = (
            GriptapeNodes.get_instance().ConfigManager().get_config_value(f"griptape.api_keys.{service}.{value}")
        )
        body = {"type": args[0], "payload": json.loads(args[1])}
        response = httpx.post(
            urljoin(os.getenv("GRIPTAPE_NODES_API_BASE_URL", "https://api.nodes.griptape.ai"), "/api/editors/request"),
            json=body,
            headers={"Authorization": f"Bearer {api_token}"},
            timeout=120,
        )
        response.raise_for_status()

    def run(self, *args, **kwargs) -> None:
        pass

    def start_background_task(self, *args, **kwargs) -> None:
        pass
