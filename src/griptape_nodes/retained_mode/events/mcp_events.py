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
        server_id: The MCP server to discover capabilities from
        timeout: Maximum time to wait for server response (seconds)
    """

    server_id: str
    timeout: int = 30


@dataclass
@PayloadRegistry.register
class DiscoverMCPServerCapabilitiesResultSuccess(WorkflowNotAlteredMixin, ResultPayloadSuccess):
    """MCP server capabilities discovered successfully."""
    
    server_id: str
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
        server_id: The unique identifier for the MCP server
    """

    server_id: str


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
        server_id: Unique identifier for the server
        name: Display name for the server
        command: Command to start the server
        args: Arguments to pass to the command
        env: Environment variables for the server
        description: Optional description of the server
        capabilities: List of server capabilities
        enabled: Whether the server is enabled by default
    """

    server_id: str
    name: str
    command: str
    args: list[str] = None
    env: dict[str, str] = None
    description: str | None = None
    capabilities: list[str] = None
    enabled: bool = True


@dataclass
@PayloadRegistry.register
class CreateMCPServerResultSuccess(WorkflowAlteredMixin, ResultPayloadSuccess):
    """MCP server created successfully."""

    server_id: str


@dataclass
@PayloadRegistry.register
class CreateMCPServerResultFailure(WorkflowAlteredMixin, ResultPayloadFailure):
    """Failed to create MCP server."""


@dataclass
@PayloadRegistry.register
class UpdateMCPServerRequest(RequestPayload):
    """Update an existing MCP server configuration.

    Args:
        server_id: The unique identifier for the MCP server
        name: Updated display name for the server
        command: Updated command to start the server
        args: Updated arguments to pass to the command
        env: Updated environment variables for the server
        description: Updated description of the server
        capabilities: Updated list of server capabilities
    """

    server_id: str
    name: str | None = None
    command: str | None = None
    args: list[str] | None = None
    env: dict[str, str] | None = None
    description: str | None = None
    capabilities: list[str] | None = None


@dataclass
@PayloadRegistry.register
class UpdateMCPServerResultSuccess(WorkflowAlteredMixin, ResultPayloadSuccess):
    """MCP server updated successfully."""

    server_id: str


@dataclass
@PayloadRegistry.register
class UpdateMCPServerResultFailure(WorkflowAlteredMixin, ResultPayloadFailure):
    """Failed to update MCP server."""


@dataclass
@PayloadRegistry.register
class DeleteMCPServerRequest(RequestPayload):
    """Delete an MCP server configuration.

    Args:
        server_id: The unique identifier for the MCP server to delete
    """

    server_id: str


@dataclass
@PayloadRegistry.register
class DeleteMCPServerResultSuccess(WorkflowAlteredMixin, ResultPayloadSuccess):
    """MCP server deleted successfully."""

    server_id: str


@dataclass
@PayloadRegistry.register
class DeleteMCPServerResultFailure(WorkflowAlteredMixin, ResultPayloadFailure):
    """Failed to delete MCP server."""


@dataclass
@PayloadRegistry.register
class EnableMCPServerRequest(RequestPayload):
    """Enable an MCP server.

    Args:
        server_id: The unique identifier for the MCP server to enable
    """

    server_id: str


@dataclass
@PayloadRegistry.register
class EnableMCPServerResultSuccess(WorkflowAlteredMixin, ResultPayloadSuccess):
    """MCP server enabled successfully."""

    server_id: str


@dataclass
@PayloadRegistry.register
class EnableMCPServerResultFailure(WorkflowAlteredMixin, ResultPayloadFailure):
    """Failed to enable MCP server."""


@dataclass
@PayloadRegistry.register
class DisableMCPServerRequest(RequestPayload):
    """Disable an MCP server.

    Args:
        server_id: The unique identifier for the MCP server to disable
    """

    server_id: str


@dataclass
@PayloadRegistry.register
class DisableMCPServerResultSuccess(WorkflowAlteredMixin, ResultPayloadSuccess):
    """MCP server disabled successfully."""

    server_id: str


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
