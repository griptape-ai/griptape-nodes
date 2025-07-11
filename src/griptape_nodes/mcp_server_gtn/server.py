import contextlib
import json
import logging
from collections.abc import AsyncIterator

from mcp.server.lowlevel import Server
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from mcp.types import (
    TextContent,
    Tool,
)
from pydantic import TypeAdapter
from rich.logging import RichHandler
from starlette.applications import Starlette
from starlette.routing import Mount
from starlette.types import Receive, Scope, Send

from griptape_nodes.mcp_server_gtn.ws_request_manager import AsyncRequestManager, WebSocketConnectionManager
from griptape_nodes.retained_mode.events.base_events import RequestPayload
from griptape_nodes.retained_mode.events.connection_events import (
    CreateConnectionRequest,
    DeleteConnectionRequest,
    ListConnectionsForNodeRequest,
)
from griptape_nodes.retained_mode.events.flow_events import ListNodesInFlowRequest
from griptape_nodes.retained_mode.events.node_events import (
    CreateNodeRequest,
    DeleteNodeRequest,
    GetNodeMetadataRequest,
    GetNodeResolutionStateRequest,
    ListParametersOnNodeRequest,
    SetNodeMetadataRequest,
)
from griptape_nodes.retained_mode.events.parameter_events import (
    GetParameterValueRequest,
    SetParameterValueRequest,
)
from griptape_nodes.retained_mode.managers.config_manager import ConfigManager
from griptape_nodes.retained_mode.managers.secrets_manager import SecretsManager

SUPPORTED_REQUEST_EVENTS: dict[str, type[RequestPayload]] = {
    # Nodes
    "CreateNodeRequest": CreateNodeRequest,
    "DeleteNodeRequest": DeleteNodeRequest,
    "ListNodesInFlowRequest": ListNodesInFlowRequest,
    "GetNodeResolutionStateRequest": GetNodeResolutionStateRequest,
    "GetNodeMetadataRequest": GetNodeMetadataRequest,
    "SetNodeMetadataRequest": SetNodeMetadataRequest,
    # Connections
    "CreateConnectionRequest": CreateConnectionRequest,
    "DeleteConnectionRequest": DeleteConnectionRequest,
    "ListConnectionsForNodeRequest": ListConnectionsForNodeRequest,
    # Parameters
    "ListParametersOnNodeRequest": ListParametersOnNodeRequest,
    "GetParameterValueRequest": GetParameterValueRequest,
    "SetParameterValueRequest": SetParameterValueRequest,
}

API_KEY_ENV_VAR = "GT_CLOUD_API_KEY"

config_manager = ConfigManager()
secrets_manager = SecretsManager(config_manager)


def main() -> int:
    """Main entry point for the Griptape Nodes MCP server."""
    mcp_server_logger = logging.getLogger("griptape_nodes_mcp_server")
    mcp_server_logger.addHandler(RichHandler(show_time=True, show_path=False, markup=True, rich_tracebacks=True))
    mcp_server_logger.setLevel(logging.INFO)
    mcp_server_logger.info("Starting MCP GTN server...")

    api_key = secrets_manager.get_secret(API_KEY_ENV_VAR)
    if not api_key:
        msg = f"Secret '{API_KEY_ENV_VAR}' not found"
        raise ValueError(msg)

    # Give these a session ID
    connection_manager = WebSocketConnectionManager()
    request_manager = AsyncRequestManager(connection_manager)

    app = Server("mcp-gtn")

    @app.list_tools()
    async def list_tools() -> list[Tool]:
        return [
            Tool(name=event.__name__, description=event.__doc__, inputSchema=TypeAdapter(event).json_schema())
            for (name, event) in SUPPORTED_REQUEST_EVENTS.items()
        ]

    @app.call_tool()
    async def call_tool(name: str, arguments: dict) -> list[TextContent]:
        if name not in SUPPORTED_REQUEST_EVENTS:
            msg = f"Unsupported tool: {name}"
            raise ValueError(msg)

        request_payload = SUPPORTED_REQUEST_EVENTS[name](**arguments)

        await request_manager.connect(token=api_key)
        result = await request_manager.create_request_event(
            request_payload.__class__.__name__, request_payload.__dict__, timeout_ms=5000
        )
        mcp_server_logger.debug("Got result: %s", result)

        return [TextContent(type="text", text=json.dumps(result))]

    # Create the session manager with our app and event store
    session_manager = StreamableHTTPSessionManager(
        app=app,
    )

    # ASGI handler for streamable HTTP connections
    async def handle_streamable_http(scope: Scope, receive: Receive, send: Send) -> None:
        await session_manager.handle_request(scope, receive, send)

    @contextlib.asynccontextmanager
    async def lifespan(_: Starlette) -> AsyncIterator[None]:
        """Context manager for managing session manager lifecycle."""
        async with session_manager.run():
            mcp_server_logger.info("Application started with StreamableHTTP session manager!")
            try:
                yield
            finally:
                mcp_server_logger.info("Application shutting down...")

    # Create an ASGI application using the transport
    starlette_app = Starlette(
        debug=True,
        routes=[
            Mount("/mcp", app=handle_streamable_http),
        ],
        lifespan=lifespan,
    )

    import uvicorn

    uvicorn.run(starlette_app, host="127.0.0.1", port=9927)

    return 0
