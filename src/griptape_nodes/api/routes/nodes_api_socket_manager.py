import json
import os
from threading import Lock
from time import sleep
from urllib.parse import urljoin

from attrs import Factory, define, field
from websockets.exceptions import WebSocketException
from websockets.sync.client import ClientConnection, connect

from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

logger = GriptapeNodes.get_instance().LogManager().get_logger(event_handler=False)


@define(kw_only=True)
class NodesApiSocketManager:
    """Drop-in replacement for SocketIO that sends events to the Nodes API via websocket."""

    socket: ClientConnection = field(
        default=Factory(
            lambda self: self._connect(),
            takes_self=True,
        ),
    )
    lock: Lock = field(factory=Lock)

    def emit(self, *args, **kwargs) -> None:  # noqa: ARG002 # drop-in replacement workaround
        body = {"type": args[0], "payload": json.loads(args[1])}
        sent = False
        while not sent:
            try:
                self.socket.send(json.dumps(body))
                sent = True
            except WebSocketException:
                logger.warning("Error sending event to Nodes API, attempting to reconnect.")
                self.socket = self._connect()

    def run(self, *args, **kwargs) -> None:
        pass

    def start_background_task(self, *args, **kwargs) -> None:
        pass

    def _connect(self) -> ClientConnection:
        while True:
            try:
                return connect(
                    urljoin(
                        os.getenv("GRIPTAPE_NODES_API_BASE_URL", "wss://api.nodes.griptape.ai")
                        .replace("http", "ws")
                        .replace("https", "wss"),
                        "/api/editors/ws",  # TODO(matt): this is the destination path for events. reevaluate if we do bi-directional communication
                    ),
                    additional_headers={
                        "Authorization": f"Bearer {
                            GriptapeNodes.get_instance()
                            .ConfigManager()
                            .get_config_value('env.Griptape.GT_CLOUD_API_KEY')
                        }"
                    },
                    ping_timeout=None,
                )
            except ConnectionError:
                logger.warning("Nodes API is not available, waiting 5 seconds before retrying")
                sleep(5)
