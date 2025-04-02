import json
import os
import sys
from threading import Lock
from time import sleep
from urllib.parse import urljoin

from rich.align import Align
from rich.console import Console
from rich.panel import Panel
from attrs import Factory, define, field
from dotenv import get_key
from websockets.exceptions import WebSocketException, InvalidStatus
from websockets.sync.client import ClientConnection, connect
from xdg_base_dirs import xdg_config_home

from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

console = Console()
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
        body = {"type": args[0], "payload": json.loads(args[1]) if len(args) > 1 else {}}
        sent = False
        while not sent:
            try:
                self.socket.send(json.dumps(body))
                sent = True
            except WebSocketException:
                logger.warning("Error sending event to Nodes API, attempting to reconnect.")
                self.socket = self._connect()

    def heartbeat(self, *, session_id: str | None, request: dict) -> None:
        self.emit(
            "success_result",
            json.dumps(
                {
                    "request": request,
                    "result": {},
                    "request_type": "Heartbeat",
                    "event_type": "EventResultSuccess",
                    "result_type": "HeartbeatSuccess",
                    **({"session_id": session_id} if session_id is not None else {}),
                }
            ),
        )

    def run(self, *args, **kwargs) -> None:
        pass

    def start_background_task(self, *args, **kwargs) -> None:
        pass

    def _connect(self) -> ClientConnection:
        while True:
            try:
                api_key = get_key(xdg_config_home() / "griptape_nodes" / ".env", "GT_CLOUD_API_KEY")
                if api_key is None:
                    msg = "GT_CLOUD_API_KEY is not set, please visit https://nodes.griptape.ai to get a key, and then run `griptape-nodes init` to set it up."
                    raise ValueError(msg) from None

                return connect(
                    urljoin(
                        os.getenv("GRIPTAPE_NODES_API_BASE_URL", "wss://api.nodes.griptape.ai")
                        .replace("http", "ws")
                        .replace("https", "wss"),
                        "/api/editors/ws",  # TODO(matt): this is the destination path for events. reevaluate if we do bi-directional communication
                    ),
                    additional_headers={"Authorization": f"Bearer {api_key}"},
                    ping_timeout=None,
                )
            except ConnectionError:
                logger.warning("Nodes API is not available, waiting 5 seconds before retrying")
                logger.debug("Error: ", exc_info=True)
                sleep(5)
            except InvalidStatus as e:
                if e.response.status_code in {401, 403}:
                    message = Panel(
                        Align.center(
                            "[bold red]Nodes API key is invalid, please re-run `gtn` with a valid key: [/bold red]"
                            "[code]gtn --api-key <your key>[/code]\n"
                            "[bold red]You can generate a new key from [/bold red][bold blue][link=https://nodes.griptape.ai]https://nodes.griptape.ai[/link][/bold blue]",
                        ),
                        title="🔑 ❌ Invalid Nodes API Key",
                        border_style="red",
                        padding=(1, 4),
                    )
                    console.print(message)
                    sys.exit(1)
