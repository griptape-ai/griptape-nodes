"""MCP (Model Context Protocol) server management events."""

from dataclasses import dataclass
from typing import Any

from griptape_nodes.retained_mode.events.base_events import (
    RequestPayload,
    ResultPayloadFailure,
    ResultPayloadSuccess,
    WorkflowAlteredMixin,
    WorkflowNotAlteredMixin,
)
from griptape_nodes.retained_mode.events.payload_registry import PayloadRegistry

# MCP Server Management Events


# Capability Discovery Events
@dataclass
@PayloadRegistry.register
class DiscoverMCPServerCapabilitiesRequest(RequestPayload):
    """Discover capabilities from a running MCP server.

    Args:
        name: The MCP server to discover capabilities from
        timeout: Maximum time to wait for server response (seconds)
    """

    name: str
    timeout: int = 30


@dataclass
@PayloadRegistry.register
class DiscoverMCPServerCapabilitiesResultSuccess(WorkflowNotAlteredMixin, ResultPayloadSuccess):
    """MCP server capabilities discovered successfully."""

    name: str
    capabilities: list[str]
    detailed_tools: list[dict[str, Any]] | None = None
    server_info: dict[str, Any] | None = None


@dataclass
@PayloadRegistry.register
class DiscoverMCPServerCapabilitiesResultFailure(WorkflowNotAlteredMixin, ResultPayloadFailure):
    """Failed to discover MCP server capabilities."""


@dataclass
@PayloadRegistry.register
class ListMCPServersRequest(RequestPayload):
    """List all configured MCP servers.

    Args:
        include_disabled: Whether to include disabled servers in the results
    """

    include_disabled: bool = False


@dataclass
@PayloadRegistry.register
class ListMCPServersResultSuccess(WorkflowNotAlteredMixin, ResultPayloadSuccess):
    """MCP servers listed successfully."""

    servers: dict[str, dict[str, Any]]


@dataclass
@PayloadRegistry.register
class ListMCPServersResultFailure(WorkflowNotAlteredMixin, ResultPayloadFailure):
    """Failed to list MCP servers."""


@dataclass
@PayloadRegistry.register
class GetMCPServerRequest(RequestPayload):
    """Get configuration for a specific MCP server.

    Args:
        name: The unique identifier for the MCP server
    """

    name: str


@dataclass
@PayloadRegistry.register
class GetMCPServerResultSuccess(WorkflowNotAlteredMixin, ResultPayloadSuccess):
    """MCP server configuration retrieved successfully."""

    server_config: dict[str, Any]


@dataclass
@PayloadRegistry.register
class GetMCPServerResultFailure(WorkflowNotAlteredMixin, ResultPayloadFailure):
    """Failed to get MCP server configuration."""


@dataclass
@PayloadRegistry.register
class CreateMCPServerRequest(RequestPayload):
    """Create a new MCP server configuration.

    Args:
        name: Unique identifier for the server
        transport: Transport type (stdio, sse, streamable_http, websocket)
        command: Command to start the server (required for stdio)
        args: Arguments to pass to the command (stdio)
        env: Environment variables for the server (stdio)
        cwd: Working directory for the server (stdio)
        encoding: Text encoding for stdio communication
        encoding_error_handler: Encoding error handler for stdio
        url: URL for HTTP-based connections (sse, streamable_http, websocket)
        headers: HTTP headers for HTTP-based connections
        timeout: HTTP timeout in seconds
        sse_read_timeout: SSE read timeout in seconds
        terminate_on_close: Whether to terminate session on close (streamable_http)
        description: Optional description of the server
        capabilities: List of server capabilities
        enabled: Whether the server is enabled by default
    """

    name: str
    transport: str = "stdio"
    enabled: bool = True

    # StdioConnection fields
    command: str | None = None
    args: list[str] | None = None
    env: dict[str, str] | None = None
    cwd: str | None = None
    encoding: str = "utf-8"
    encoding_error_handler: str = "strict"

    # HTTP-based connection fields
    url: str | None = None
    headers: dict[str, str] | None = None
    timeout: float | None = None
    sse_read_timeout: float | None = None
    terminate_on_close: bool = True

    # Common fields
    description: str | None = None
    capabilities: list[str] | None = None


@dataclass
@PayloadRegistry.register
class CreateMCPServerResultSuccess(WorkflowAlteredMixin, ResultPayloadSuccess):
    """MCP server created successfully."""

    name: str


@dataclass
@PayloadRegistry.register
class CreateMCPServerResultFailure(WorkflowAlteredMixin, ResultPayloadFailure):
    """Failed to create MCP server."""


@dataclass
@PayloadRegistry.register
class UpdateMCPServerRequest(RequestPayload):
    """Update an existing MCP server configuration.

    Args:
        name: The unique identifier for the MCP server
        new_name: Updated display name for the server
        transport: Updated transport type (stdio, sse, streamable_http, websocket)
        command: Updated command to start the server (stdio)
        args: Updated arguments to pass to the command (stdio)
        env: Updated environment variables for the server (stdio)
        cwd: Updated working directory for the server (stdio)
        encoding: Updated text encoding for stdio communication
        encoding_error_handler: Updated encoding error handler for stdio
        url: Updated URL for HTTP-based connections (sse, streamable_http, websocket)
        headers: Updated HTTP headers for HTTP-based connections
        timeout: Updated HTTP timeout in seconds
        sse_read_timeout: Updated SSE read timeout in seconds
        terminate_on_close: Updated terminate on close setting (streamable_http)
        description: Updated description of the server
        capabilities: Updated list of server capabilities
    """

    name: str
    new_name: str | None = None
    transport: str | None = None
    enabled: bool | None = None

    # StdioConnection fields
    command: str | None = None
    args: list[str] | None = None
    env: dict[str, str] | None = None
    cwd: str | None = None
    encoding: str | None = None
    encoding_error_handler: str | None = None

    # HTTP-based connection fields
    url: str | None = None
    headers: dict[str, str] | None = None
    timeout: float | None = None
    sse_read_timeout: float | None = None
    terminate_on_close: bool | None = None

    # Common fields
    description: str | None = None
    capabilities: list[str] | None = None


@dataclass
@PayloadRegistry.register
class UpdateMCPServerResultSuccess(WorkflowAlteredMixin, ResultPayloadSuccess):
    """MCP server updated successfully."""

    name: str


@dataclass
@PayloadRegistry.register
class UpdateMCPServerResultFailure(WorkflowAlteredMixin, ResultPayloadFailure):
    """Failed to update MCP server."""


@dataclass
@PayloadRegistry.register
class DeleteMCPServerRequest(RequestPayload):
    """Delete an MCP server configuration.

    Args:
        name: The unique identifier for the MCP server to delete
    """

    name: str


@dataclass
@PayloadRegistry.register
class DeleteMCPServerResultSuccess(WorkflowAlteredMixin, ResultPayloadSuccess):
    """MCP server deleted successfully."""

    name: str


@dataclass
@PayloadRegistry.register
class DeleteMCPServerResultFailure(WorkflowAlteredMixin, ResultPayloadFailure):
    """Failed to delete MCP server."""


@dataclass
@PayloadRegistry.register
class EnableMCPServerRequest(RequestPayload):
    """Enable an MCP server.

    Args:
        name: The unique identifier for the MCP server to enable
    """

    name: str


@dataclass
@PayloadRegistry.register
class EnableMCPServerResultSuccess(WorkflowAlteredMixin, ResultPayloadSuccess):
    """MCP server enabled successfully."""

    name: str


@dataclass
@PayloadRegistry.register
class EnableMCPServerResultFailure(WorkflowAlteredMixin, ResultPayloadFailure):
    """Failed to enable MCP server."""


@dataclass
@PayloadRegistry.register
class DisableMCPServerRequest(RequestPayload):
    """Disable an MCP server.

    Args:
        name: The unique identifier for the MCP server to disable
    """

    name: str


@dataclass
@PayloadRegistry.register
class DisableMCPServerResultSuccess(WorkflowAlteredMixin, ResultPayloadSuccess):
    """MCP server disabled successfully."""

    name: str


@dataclass
@PayloadRegistry.register
class DisableMCPServerResultFailure(WorkflowAlteredMixin, ResultPayloadFailure):
    """Failed to disable MCP server."""


@dataclass
@PayloadRegistry.register
class GetEnabledMCPServersRequest(RequestPayload):
    """Get all enabled MCP servers."""


@dataclass
@PayloadRegistry.register
class GetEnabledMCPServersResultSuccess(WorkflowNotAlteredMixin, ResultPayloadSuccess):
    """Enabled MCP servers retrieved successfully."""

    servers: dict[str, dict[str, Any]]


@dataclass
@PayloadRegistry.register
class GetEnabledMCPServersResultFailure(WorkflowNotAlteredMixin, ResultPayloadFailure):
    """Failed to get enabled MCP servers."""
