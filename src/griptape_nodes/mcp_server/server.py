import contextlib
import json
import logging
import os
from collections.abc import AsyncIterator

import uvicorn
from fastapi import FastAPI
from mcp.server.lowlevel import Server
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from mcp.types import (
    TextContent,
    Tool,
)
from pydantic import TypeAdapter
from rich.logging import RichHandler
from starlette.types import Receive, Scope, Send

from griptape_nodes.mcp_server.ws_request_manager import AsyncRequestManager, WebSocketConnectionManager
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

GTN_MCP_SERVER_HOST = os.getenv("GTN_MCP_SERVER_HOST", "localhost")
GTN_MCP_SERVER_PORT = int(os.getenv("GTN_MCP_SERVER_PORT", "9927"))
GTN_MCP_SERVER_LOG_LEVEL = os.getenv("GTN_MCP_SERVER_LOG_LEVEL", "ERROR").lower()

config_manager = ConfigManager()
secrets_manager = SecretsManager(config_manager)

mcp_server_logger = logging.getLogger("griptape_nodes_mcp_server")
mcp_server_logger.addHandler(RichHandler(show_time=True, show_path=False, markup=True, rich_tracebacks=True))
mcp_server_logger.setLevel(logging.INFO)


def main(api_key: str) -> None:
    """Main entry point for the Griptape Nodes MCP server."""
    mcp_server_logger.debug("Starting MCP GTN server...")
    # Give these a session ID
    connection_manager = WebSocketConnectionManager()
    request_manager = AsyncRequestManager(connection_manager, api_key)

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

        await request_manager.connect()
        result = await request_manager.create_request_event(
            request_payload.__class__.__name__, request_payload.__dict__, timeout_ms=5000
        )
        mcp_server_logger.debug("Got result: %s", result)

        return [TextContent(type="text", text=json.dumps(result))]

    # Create the session manager with our app and event store
    session_manager = StreamableHTTPSessionManager(
        app=app,
    )

    @contextlib.asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        """Context manager for managing session manager lifecycle."""
        async with session_manager.run():
            mcp_server_logger.debug("GTN MCP server started with StreamableHTTP session manager!")
            try:
                yield
            finally:
                mcp_server_logger.debug("GTN MCP server shutting down...")

    # Create an ASGI application using the transport
    mcp_server_app = FastAPI(lifespan=lifespan)

    # ASGI handler for streamable HTTP connections
    async def handle_streamable_http(scope: Scope, receive: Receive, send: Send) -> None:
        await session_manager.handle_request(scope, receive, send)

    mcp_server_app.mount("/mcp", app=handle_streamable_http)

    uvicorn.run(
        mcp_server_app,
        host=GTN_MCP_SERVER_HOST,
        port=GTN_MCP_SERVER_PORT,
        log_config=None,
        log_level=GTN_MCP_SERVER_LOG_LEVEL,
    )
