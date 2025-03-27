import json
import logging
import os
import threading
from time import sleep
from urllib.parse import urljoin

from attrs import Factory, define, field
from websockets import ConnectionClosedError
from websockets.sync.client import ClientConnection, connect

from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
from griptape_nodes.api.routes.api import process_event

logger = GriptapeNodes.get_logger()


@define(kw_only=True)
class NodesApiSocketManager:
    """Drop-in replacement for SocketIO that sends events to the Nodes API via websocket."""

    socket: ClientConnection = field(
        default=Factory(
            lambda self: self._connect_to_socket(), takes_self=True
        ),
    )
    nodes_app_url: str = field(default=os.getenv("GRIPTAPE_NODES_APP_URL", "https://nodes.griptape.ai"))

    def emit(self, *args, **kwargs) -> None:  # noqa: ARG002 # drop-in replacement workaround
        body = {"type": args[0], "payload": json.loads(args[1])}
        self.socket.send(json.dumps(body))

    def run(self, *args, **kwargs) -> None:
        pass

    def start_background_task(self, *args, **kwargs) -> None:  # noqa: ARG002 # drop-in replacement workaround
        threading.Thread(target=self._listen_for_events, daemon=True).start()

    def _connect_to_socket(self) -> ClientConnection:
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
                    .get_config_value('griptape.api_keys.Nodes.GRIPTAPE_NODES_API_KEY')
                }"
            },
        )

    def _listen_for_events(self) -> None:
        while True:
            try:
                event_str = self.socket.recv()
                event_str = event_str.decode("utf-8") if isinstance(event_str, bytes) else event_str
                if event_str == "START":
                    logger.info("[bold green]Engine is ready to receive events![/bold green]")
                    logger.info(
                        "[bold green]Please visit [link=%s]%s[/link] in your browser.[/bold green]",
                        self.nodes_app_url,
                        self.nodes_app_url,
                    )
                    continue

                process_event(json.loads(event_str)["payload"])
            except ConnectionClosedError as e:
                logger.error(f"Connection closed, attempting to reconnect")
                sleep(5)
                while True:
                    try:
                        self.socket = self._connect_to_socket()
                    except Exception as e:
                        logger.error(f"Failed to reconnect, attempting again in 5 seconds")
