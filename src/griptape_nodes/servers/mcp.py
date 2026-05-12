import asyncio
import contextlib
import json
import logging
import os
import socket
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

from griptape_nodes.api_client import Client, RequestClient
from griptape_nodes.retained_mode.events.base_events import RequestPayload
from griptape_nodes.retained_mode.events.connection_events import (
    CreateConnectionRequest,
    DeleteConnectionRequest,
    ListConnectionsForNodeRequest,
)
from griptape_nodes.retained_mode.events.context_events import (
    GetWorkflowContextRequest,
    SetWorkflowContextRequest,
)
from griptape_nodes.retained_mode.events.execution_events import (
    ExecuteNodeRequest,
    ResolveNodeRequest,
    StartFlowFromNodeRequest,
    StartFlowRequest,
)
from griptape_nodes.retained_mode.events.flow_events import (
    CreateFlowRequest,
    DeleteFlowRequest,
    ListFlowsInCurrentContextRequest,
    ListNodesInFlowRequest,
)
from griptape_nodes.retained_mode.events.library_events import (
    ListCategoriesInLibraryRequest,
    ListNodeTypesInLibraryRequest,
    ListRegisteredLibrariesRequest,
    RegisterSandboxNodeFromSourceRequest,
)
from griptape_nodes.retained_mode.events.node_events import (
    CreateNodeRequest,
    DeleteNodeRequest,
    GetNodeMetadataRequest,
    GetNodeResolutionStateRequest,
    ListParametersOnNodeRequest,
    ResetNodeToDefaultsRequest,
    SetLockNodeStateRequest,
    SetNodeMetadataRequest,
)
from griptape_nodes.retained_mode.events.object_events import (
    ClearAllObjectStateRequest,
    RenameObjectRequest,
)
from griptape_nodes.retained_mode.events.parameter_events import (
    GetConnectionsForParameterRequest,
    GetParameterDetailsRequest,
    GetParameterValueRequest,
    SetParameterValueRequest,
)
from griptape_nodes.retained_mode.events.workflow_events import (
    ListAllWorkflowsRequest,
    RunWorkflowWithCurrentStateRequest,
)
from griptape_nodes.retained_mode.managers.config_manager import ConfigManager
from griptape_nodes.retained_mode.managers.secrets_manager import SecretsManager

SUPPORTED_REQUEST_EVENTS: dict[str, type[RequestPayload]] = {
    # Workflows
    "RunWorkflowWithCurrentStateRequest": RunWorkflowWithCurrentStateRequest,
    "ListAllWorkflowsRequest": ListAllWorkflowsRequest,
    # Workflow context
    "SetWorkflowContextRequest": SetWorkflowContextRequest,
    "GetWorkflowContextRequest": GetWorkflowContextRequest,
    # Libraries
    "ListRegisteredLibrariesRequest": ListRegisteredLibrariesRequest,
    "ListNodeTypesInLibraryRequest": ListNodeTypesInLibraryRequest,
    "ListCategoriesInLibraryRequest": ListCategoriesInLibraryRequest,
    "RegisterSandboxNodeFromSourceRequest": RegisterSandboxNodeFromSourceRequest,
    # Execution
    "ResolveNodeRequest": ResolveNodeRequest,
    "ExecuteNodeRequest": ExecuteNodeRequest,
    "StartFlowRequest": StartFlowRequest,
    "StartFlowFromNodeRequest": StartFlowFromNodeRequest,
    # Flows
    "CreateFlowRequest": CreateFlowRequest,
    "DeleteFlowRequest": DeleteFlowRequest,
    "ListFlowsInCurrentContextRequest": ListFlowsInCurrentContextRequest,
    # Nodes
    "CreateNodeRequest": CreateNodeRequest,
    "DeleteNodeRequest": DeleteNodeRequest,
    "ListNodesInFlowRequest": ListNodesInFlowRequest,
    "GetNodeResolutionStateRequest": GetNodeResolutionStateRequest,
    "GetNodeMetadataRequest": GetNodeMetadataRequest,
    "SetNodeMetadataRequest": SetNodeMetadataRequest,
    "ResetNodeToDefaultsRequest": ResetNodeToDefaultsRequest,
    "SetLockNodeStateRequest": SetLockNodeStateRequest,
    # Objects
    "RenameObjectRequest": RenameObjectRequest,
    "ClearAllObjectStateRequest": ClearAllObjectStateRequest,
    # Connections
    "CreateConnectionRequest": CreateConnectionRequest,
    "DeleteConnectionRequest": DeleteConnectionRequest,
    "ListConnectionsForNodeRequest": ListConnectionsForNodeRequest,
    # Parameters
    "ListParametersOnNodeRequest": ListParametersOnNodeRequest,
    "GetParameterValueRequest": GetParameterValueRequest,
    "SetParameterValueRequest": SetParameterValueRequest,
    "GetParameterDetailsRequest": GetParameterDetailsRequest,
    "GetConnectionsForParameterRequest": GetConnectionsForParameterRequest,
}

GTN_MCP_SERVER_HOST = os.getenv("GTN_MCP_SERVER_HOST", "localhost")
# Port of the MCP server (where uvicorn binds). 0 means the OS assigns a free port automatically.
GTN_MCP_SERVER_PORT = int(os.getenv("GTN_MCP_SERVER_PORT", "0"))
GTN_MCP_SERVER_LOG_LEVEL = os.getenv("GTN_MCP_SERVER_LOG_LEVEL", "ERROR").lower()

config_manager = ConfigManager()
secrets_manager = SecretsManager(config_manager)

mcp_server_logger = logging.getLogger("griptape_nodes_mcp_server")
mcp_server_logger.addHandler(RichHandler(show_time=True, show_path=False, markup=True, rich_tracebacks=True))
mcp_server_logger.setLevel(logging.INFO)


def _summarize_result_details(result_details: object) -> str | list[dict] | None:
    """Collapse the engine's nested result_details payload into something terse.

    The engine emits `result_details` as a dict wrapping a list of ResultDetail entries,
    e.g. ``{"result_details": [{"level": 10, "message": "..."}, ...]}``. For the MCP
    surface we only really need the messages, joined on newlines. Anything we do not
    recognize is returned as-is so we never hide information we did not intend to hide.
    """
    if result_details is None:
        return None
    if isinstance(result_details, str):
        return result_details
    if isinstance(result_details, dict):
        inner = result_details.get("result_details")
        if isinstance(inner, list):
            messages = [entry.get("message", "") for entry in inner if isinstance(entry, dict)]
            joined = "\n".join(message for message in messages if message)
            if joined:
                return joined
            return inner
    return result_details  # type: ignore[return-value]


def _trim_response(result: dict) -> dict:
    """Strip envelope noise from an engine response before we hand it back to the MCP client.

    The raw response wraps the real payload in engine/session/routing metadata and an echoed
    request. Agents only need to know whether the call succeeded and the payload fields the
    handler produced, so we surface a success discriminator, a terse `details` string, and the
    rest of the inner `result` object.
    """
    inner = dict(result.get("result") or {})
    result_type = result.get("result_type", "")
    details = _summarize_result_details(inner.pop("result_details", None))

    trimmed: dict = {"ok": result_type.endswith("Success")}
    if details is not None:
        trimmed["details"] = details
    trimmed.update(inner)
    return trimmed


def start_mcp_server(api_key: str, sock: socket.socket) -> None:
    """Synchronous version of main entry point for the Griptape Nodes MCP server.

    The socket should already be bound to the desired address and port before calling
    this function. Using a pre-bound socket avoids race conditions when discovering
    the actual port assigned by the OS.
    """
    mcp_server_logger.debug("Starting MCP GTN server...")

    app = Server("mcp-gtn")

    # Manager reference to be set in lifespan
    manager: RequestClient | None = None

    @app.list_tools()
    async def list_tools() -> list[Tool]:
        return [
            Tool(name=event.__name__, description=event.__doc__, inputSchema=TypeAdapter(event).json_schema())
            for (name, event) in SUPPORTED_REQUEST_EVENTS.items()
        ]

    @app.call_tool()
    async def call_tool(name: str, arguments: dict) -> list[TextContent]:
        if manager is None:
            msg = "Request manager not initialized"
            raise RuntimeError(msg)

        if name not in SUPPORTED_REQUEST_EVENTS:
            msg = f"Unsupported tool: {name}"
            raise ValueError(msg)

        request_payload = SUPPORTED_REQUEST_EVENTS[name](**arguments)

        result = await manager.request(
            request_payload.__class__.__name__, dict(request_payload.__dict__), timeout_ms=30000
        )
        mcp_server_logger.debug("Got result: %s", result)

        return [TextContent(type="text", text=json.dumps(_trim_response(result)))]

    # Create the session manager with our app and event store
    session_manager = StreamableHTTPSessionManager(
        app=app,
    )

    @contextlib.asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        """Context manager for managing session manager and WebSocket client lifecycle."""
        nonlocal manager

        async with Client(api_key=api_key) as ws_client, RequestClient(client=ws_client) as req_manager:
            manager = req_manager
            mcp_server_logger.debug("Request manager initialized")

            async with session_manager.run():
                mcp_server_logger.debug("GTN MCP server started with StreamableHTTP session manager!")
                try:
                    yield
                finally:
                    mcp_server_logger.debug("GTN MCP server shutting down...")
                    manager = None

    mcp_server_app = FastAPI(lifespan=lifespan)

    # ASGI handler for streamable HTTP connections
    async def handle_streamable_http(scope: Scope, receive: Receive, send: Send) -> None:
        await session_manager.handle_request(scope, receive, send)

    mcp_server_app.mount("/mcp", app=handle_streamable_http)

    try:
        config = uvicorn.Config(mcp_server_app, log_config=None, log_level=GTN_MCP_SERVER_LOG_LEVEL)
        server = uvicorn.Server(config)
        asyncio.run(server.serve(sockets=[sock]))
    except Exception as e:
        mcp_server_logger.error("MCP server failed: %s", e)
        raise
