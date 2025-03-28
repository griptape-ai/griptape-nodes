import json
import os
from urllib.parse import urljoin

from attrs import Factory, define, field
from websockets.sync.client import ClientConnection, connect

from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes


@define(kw_only=True)
class NodesApiSocketManager:
    """Drop-in replacement for SocketIO that sends events to the Nodes API via websocket."""

    socket: ClientConnection = field(
        default=Factory(
            lambda: connect(
                urljoin(
                    os.getenv("GRIPTAPE_NODES_API_BASE_URL", "wss://api.nodes.griptape.ai")
                    .replace("http", "ws")
                    .replace("https", "wss"),
                    "/api/editors/ws",  # TODO(matt): this is the destination path for events. reevaluate if we do bi-directional communication
                ),
                additional_headers={
                    "Authorization": f"Bearer {
                        GriptapeNodes.get_instance().ConfigManager().get_config_value('env.Griptape.GT_CLOUD_API_KEY')
                    }"
                },
            ),
        ),
    )

    def emit(self, *args, **kwargs) -> None:  # noqa: ARG002 # drop-in replacement workaround
        body = {"type": args[0], "payload": json.loads(args[1])}
        self.socket.send(json.dumps(body))

    def run(self, *args, **kwargs) -> None:
        pass

    def start_background_task(self, *args, **kwargs) -> None:
        pass
