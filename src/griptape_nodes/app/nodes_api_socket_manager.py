import json
import logging
import os
import sys
from threading import Lock
from time import sleep
from urllib.parse import urljoin

from attrs import Factory, define, field
from dotenv import get_key
from rich.align import Align
from rich.console import Console
from rich.panel import Panel
from websockets.exceptions import InvalidStatus, WebSocketException
from websockets.sync.client import ClientConnection, connect
from xdg_base_dirs import xdg_config_home

console = Console()

logger = logging.getLogger(__name__)


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
            except WebSocketException as e:
                logger.error("Error sending event to Nodes API, attempting to reconnect. %s", e)
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
        logger.debug(
            "Responded to heartbeat request with session: %s and request: %s", session_id, request.get("request_id")
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
                    message = Panel(
                        Align.center(
                            "[bold red]Nodes API key is not set, please run [code]gtn init[/code] with a valid key: [/bold red]"
                            "[code]gtn init --api-key <your key>[/code]\n"
                            "[bold red]You can generate a new key from [/bold red][bold blue][link=https://nodes.griptape.ai]https://nodes.griptape.ai[/link][/bold blue]",
                        ),
                        title="🔑 ❌ Missing Nodes API Key",
                        border_style="red",
                        padding=(1, 4),
                    )
                    console.print(message)
                    sys.exit(1)

                return connect(
                    urljoin(
                        os.getenv("GRIPTAPE_NODES_API_BASE_URL", "wss://api.nodes.griptape.ai")
                        .replace("http", "ws")
                        .replace("https", "wss"),
                        "/api/editors/ws",  # TODO: https://github.com/griptape-ai/griptape-nodes/issues/866
                    ),
                    additional_headers={"Authorization": f"Bearer {api_key}"},
                    ping_timeout=None,
                )
            except ConnectionError:
                logger.warning("Nodes API is not available, waiting 5 seconds before retrying")
                logger.debug("Error: ", exc_info=True)
                sleep(5)
            except InvalidStatus as e:
                message = Panel(
                    Align.center(
                        f"[bold red]Nodes API key is invalid ({e.response.status_code}), please re-run [code]gtn init[/code] with a valid key: [/bold red]"
                        "[code]gtn init --api-key <your key>[/code]\n"
                        "[bold red]You can generate a new key from [/bold red][bold blue][link=https://nodes.griptape.ai]https://nodes.griptape.ai[/link][/bold blue]",
                    ),
                    title="🔑 ❌ Invalid Nodes API Key",
                    border_style="red",
                    padding=(1, 4),
                )
                console.print(message)
                sys.exit(1)
            except Exception:
                logger.exception("Unexpected error while connecting to Nodes API")
                sys.exit(1)
