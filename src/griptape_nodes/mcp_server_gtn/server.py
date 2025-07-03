import asyncio
import logging
import contextlib
import logging
from collections.abc import AsyncIterator

from mcp.server.lowlevel import Server
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from starlette.applications import Starlette
from starlette.routing import Mount
from starlette.types import Receive, Scope, Send

from mcp.types import (
    TextContent,
    Tool,
)
from pydantic import TypeAdapter

from griptape_nodes.retained_mode.events.base_events import RequestPayload, ResultPayload
from griptape_nodes.retained_mode.events.node_events import CreateNodeRequest
from griptape_nodes.mcp_server_gtn.ws_request_manager import AsyncRequestManager, WebSocketConnectionManager


logger = logging.getLogger("griptape_nodes")

SUPPORTED_REQUEST_EVENTS: dict[str, type[RequestPayload]] = {
    "CreateNodeRequest": CreateNodeRequest,
}

def main() -> int:
    logger.info("Starting MCP GTN server...")

    connection_manager = WebSocketConnectionManager()
    request_manager = AsyncRequestManager(connection_manager)

    app = Server("mcp-gtn")

    @app.list_tools()
    async def list_tools() -> list[Tool]:
        foo = [Tool(name=event.__name__, description=event.__doc__, inputSchema=TypeAdapter(event).json_schema()) for (name, event) in SUPPORTED_REQUEST_EVENTS.items()]
        logger.info(f"Listing tools: {foo}")
        return foo

    @app.call_tool()
    async def call_tool(name: str, arguments: dict) -> list[TextContent]:
        if name not in SUPPORTED_REQUEST_EVENTS:
            raise ValueError(f"Unsupported tool: {name}")
        
        request_payload = SUPPORTED_REQUEST_EVENTS[name](**arguments)
        # Add session ID to the request

        try:
            await request_manager.connect(token="gt-Hu0tXsSHSijSBIGr37v1abSJlBUR3JpcHRhcGU6KatAFMuKI4rwN1Np12tqCitlzQ")
            result = await request_manager.create_request_event(
                request_payload.__class__.__name__, 
                request_payload.__dict__, 
                timeout_ms=5000
            )
            logger.info(f"Got result: {result}")

            if isinstance(result, ResultPayload):
                return [TextContent(text=str(result))]
            else:
                raise ValueError("Unexpected result type")

        except asyncio.TimeoutError as e:
            logger.error("Request timed out")
            raise e
        except Exception as e:
            logger.exception(f"Request failed: {str(e)}")
            raise e

    # Create the session manager with our app and event store
    session_manager = StreamableHTTPSessionManager(
        app=app,
    )

    # ASGI handler for streamable HTTP connections
    async def handle_streamable_http(
        scope: Scope, receive: Receive, send: Send
    ) -> None:
        await session_manager.handle_request(scope, receive, send)

    @contextlib.asynccontextmanager
    async def lifespan(app: Starlette) -> AsyncIterator[None]:
        """Context manager for managing session manager lifecycle."""
        async with session_manager.run():
            logger.info("Application started with StreamableHTTP session manager!")
            try:
                yield
            finally:
                logger.info("Application shutting down...")

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