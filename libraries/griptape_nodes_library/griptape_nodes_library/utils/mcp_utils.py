"""MCP (Model Context Protocol) utility functions for Griptape Nodes."""

from typing import Any

from griptape.tools import MCPTool

from griptape_nodes.retained_mode.events.mcp_events import (
    GetEnabledMCPServersRequest,
    GetEnabledMCPServersResultSuccess,
)
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes, logger


def get_available_mcp_servers() -> list[str]:
    """Get list of available MCP server IDs for the dropdown."""
    servers = []
    try:
        app = GriptapeNodes()
        mcp_manager = app.MCPManager()

        # Get enabled MCP servers
        enabled_request = GetEnabledMCPServersRequest()
        enabled_result = mcp_manager.on_get_enabled_mcp_servers_request(enabled_request)

        if hasattr(enabled_result, "servers"):
            servers.extend(enabled_result.servers.keys())

        # Note: griptape-nodes-local removed from MCPTaskNode due to circular dependency issues
        # It's still available for the agent, but not for MCPTaskNode

    except Exception as e:
        logger.warning(f"Failed to get MCP servers: {e}")
        # Return empty list if no servers available (no griptape-nodes-local for MCPTaskNode)
    return servers


def validate_mcp_server(mcp_server_name: str) -> tuple[bool, str | None]:
    """Validate that an MCP server exists and is enabled.

    Returns:
        tuple: (is_valid, error_message)
    """
    if not mcp_server_name:
        return False, "No MCP server selected. Please select an MCP server from the dropdown."

    app = GriptapeNodes()
    mcp_manager = app.MCPManager()

    # Get enabled MCP servers
    enabled_request = GetEnabledMCPServersRequest()
    enabled_result = mcp_manager.on_get_enabled_mcp_servers_request(enabled_request)

    if not isinstance(enabled_result, GetEnabledMCPServersResultSuccess):
        return False, f"Failed to get enabled MCP servers: {enabled_result}"

    if mcp_server_name not in enabled_result.servers:
        return False, f"MCP server '{mcp_server_name}' not found or not enabled."

    return True, None


def get_server_config(mcp_server_name: str) -> dict[str, Any] | None:
    """Get MCP server configuration."""
    app = GriptapeNodes()
    mcp_manager = app.MCPManager()
    enabled_request = GetEnabledMCPServersRequest()
    enabled_result = mcp_manager.on_get_enabled_mcp_servers_request(enabled_request)

    if not isinstance(enabled_result, GetEnabledMCPServersResultSuccess):
        logger.error(f"Failed to get enabled MCP servers: {enabled_result}")
        return None

    if mcp_server_name not in enabled_result.servers:
        logger.error(f"MCP server '{mcp_server_name}' not found or not enabled")
        return None

    # enabled_result.servers contains dict[str, Any] from model_dump() calls in MCP manager
    return enabled_result.servers[mcp_server_name]  # type: ignore[return-value]


def create_mcp_tool(mcp_server_name: str, server_config: dict[str, Any]) -> MCPTool:
    """Create MCP tool from server configuration.

    Args:
        mcp_server_name: Name of the MCP server
        server_config: Server configuration dictionary

    Returns:
        MCPTool: Initialized MCP tool
    """
    # Create MCP connection from server config
    connection = create_connection_from_config(server_config)

    # Create tool with unique name
    clean_name = "".join(c for c in mcp_server_name if c.isalnum())
    tool_name = f"mcp{clean_name.title()}"

    # Create and initialize the tool
    tool = MCPTool(connection=connection, name=tool_name)  # type: ignore[arg-type]

    return tool


def create_connection_from_config(server_config: dict[str, Any]) -> dict[str, Any]:
    """Create a connection dictionary from server configuration based on transport type."""
    # Field mappings for each transport type
    transport_field_mappings = {
        "stdio": ["command", "args", "env", "cwd", "encoding", "encoding_error_handler"],
        "sse": ["url", "headers", "timeout", "sse_read_timeout"],
        "streamable_http": ["url", "headers", "timeout", "sse_read_timeout", "terminate_on_close"],
        "websocket": ["url"],
    }

    transport = server_config.get("transport", "stdio")

    # Start with transport
    connection = {"transport": transport}

    # Map relevant fields based on transport type
    fields_to_map = transport_field_mappings.get(transport, transport_field_mappings["stdio"])
    for field in fields_to_map:
        if field in server_config and server_config[field] is not None:
            connection[field] = server_config[field]

    return connection
