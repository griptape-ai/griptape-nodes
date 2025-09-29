"""MCP (Model Context Protocol) server management.

Handles MCP server configurations, enabling/disabling servers, and provides
event-based interface for frontend and backend interactions.
"""

import logging

from griptape_nodes.retained_mode.events.mcp_events import (
    CreateMCPServerRequest,
    CreateMCPServerResultFailure,
    CreateMCPServerResultSuccess,
    DeleteMCPServerRequest,
    DeleteMCPServerResultFailure,
    DeleteMCPServerResultSuccess,
    DisableMCPServerRequest,
    DisableMCPServerResultFailure,
    DisableMCPServerResultSuccess,
    EnableMCPServerRequest,
    EnableMCPServerResultFailure,
    EnableMCPServerResultSuccess,
    GetEnabledMCPServersRequest,
    GetEnabledMCPServersResultFailure,
    GetEnabledMCPServersResultSuccess,
    GetMCPServerRequest,
    GetMCPServerResultFailure,
    GetMCPServerResultSuccess,
    ListMCPServersRequest,
    ListMCPServersResultFailure,
    ListMCPServersResultSuccess,
    UpdateMCPServerRequest,
    UpdateMCPServerResultFailure,
    UpdateMCPServerResultSuccess,
)
from griptape_nodes.retained_mode.managers.config_manager import ConfigManager
from griptape_nodes.retained_mode.managers.event_manager import EventManager
from griptape_nodes.retained_mode.managers.settings import MCPServerConfig

logger = logging.getLogger("griptape_nodes")


class MCPManager:
    """Manager for MCP server configurations and operations."""

    def __init__(self, event_manager: EventManager | None = None, config_manager: ConfigManager | None = None) -> None:
        """Initialize the MCPManager.

        Args:
            event_manager: The EventManager instance to use for event handling.
            config_manager: The ConfigManager instance to use for configuration management.
        """
        self.config_manager = config_manager
        if event_manager is not None:
            # Register event handlers
            event_manager.assign_manager_to_request_type(ListMCPServersRequest, self.on_list_mcp_servers_request)
            event_manager.assign_manager_to_request_type(GetMCPServerRequest, self.on_get_mcp_server_request)
            event_manager.assign_manager_to_request_type(CreateMCPServerRequest, self.on_create_mcp_server_request)
            event_manager.assign_manager_to_request_type(UpdateMCPServerRequest, self.on_update_mcp_server_request)
            event_manager.assign_manager_to_request_type(DeleteMCPServerRequest, self.on_delete_mcp_server_request)
            event_manager.assign_manager_to_request_type(EnableMCPServerRequest, self.on_enable_mcp_server_request)
            event_manager.assign_manager_to_request_type(DisableMCPServerRequest, self.on_disable_mcp_server_request)
            event_manager.assign_manager_to_request_type(
                GetEnabledMCPServersRequest, self.on_get_enabled_mcp_servers_request
            )

    def _get_mcp_servers(self) -> list[MCPServerConfig]:
        """Get the current MCP servers configuration from the config manager."""
        if self.config_manager is None:
            return []

        mcp_config_data = self.config_manager.get_config_value("mcp_servers", default=[])
        if not mcp_config_data:
            return []

        try:
            return [MCPServerConfig.model_validate(server) for server in mcp_config_data]
        except Exception as e:
            logger.error("Failed to parse MCP servers configuration: %s", e)
            return []

    def _save_mcp_servers(self, servers: list[MCPServerConfig]) -> None:
        """Save the MCP servers configuration to the config manager."""
        if self.config_manager is None:
            logger.warning("No config manager available, cannot save MCP configuration")
            return

        try:
            self.config_manager.set_config_value("mcp_servers", [server.model_dump() for server in servers])
        except Exception as e:
            logger.error("Failed to save MCP servers configuration: %s", e)

    def _update_server_fields(self, server_config: MCPServerConfig, request: UpdateMCPServerRequest) -> None:
        """Update server configuration fields from request."""
        # Map request fields to server config attributes
        field_mapping = {
            "new_name": "name",
            "transport": "transport",
            "enabled": "enabled",
            "command": "command",
            "args": "args",
            "env": "env",
            "cwd": "cwd",
            "encoding": "encoding",
            "encoding_error_handler": "encoding_error_handler",
            "url": "url",
            "headers": "headers",
            "timeout": "timeout",
            "sse_read_timeout": "sse_read_timeout",
            "terminate_on_close": "terminate_on_close",
            "description": "description",
            "capabilities": "capabilities",
        }

        # Update fields that are not None
        for request_field, config_field in field_mapping.items():
            value = getattr(request, request_field, None)
            if value is not None:
                setattr(server_config, config_field, value)

    def on_list_mcp_servers_request(
        self, request: ListMCPServersRequest
    ) -> ListMCPServersResultSuccess | ListMCPServersResultFailure:
        """Handle list MCP servers request."""
        try:
            servers = self._get_mcp_servers()

            if request.include_disabled:
                servers_dict = {server.name: server.model_dump() for server in servers}
            else:
                enabled_servers = [server for server in servers if server.enabled]
                servers_dict = {server.name: server.model_dump() for server in enabled_servers}

            return ListMCPServersResultSuccess(
                servers=servers_dict, result_details=f"Successfully listed {len(servers_dict)} MCP servers"
            )
        except Exception as e:
            logger.error("Failed to list MCP servers: %s", e)
            return ListMCPServersResultFailure(result_details=f"Failed to list MCP servers: {e}")

    def on_get_mcp_server_request(
        self, request: GetMCPServerRequest
    ) -> GetMCPServerResultSuccess | GetMCPServerResultFailure:
        """Handle get MCP server request."""
        try:
            servers = self._get_mcp_servers()

            # Find server by server_id
            server_config = None
            for server in servers:
                if server.name == request.name:
                    server_config = server
                    break

            if server_config is None:
                return GetMCPServerResultFailure(
                    result_details=f"Failed to get MCP server '{request.name}' - not found"
                )

            return GetMCPServerResultSuccess(
                server_config=server_config.model_dump(),
                result_details=f"Successfully retrieved MCP server '{request.name}'",
            )
        except Exception as e:
            logger.error("Failed to get MCP server '%s': %s", request.name, e)
            return GetMCPServerResultFailure(result_details=f"Failed to get MCP server '{request.name}': {e}")

    def on_create_mcp_server_request(
        self, request: CreateMCPServerRequest
    ) -> CreateMCPServerResultSuccess | CreateMCPServerResultFailure:
        """Handle create MCP server request."""
        try:
            servers = self._get_mcp_servers()

            # Check if server already exists
            for server in servers:
                if server.name == request.name:
                    return CreateMCPServerResultFailure(
                        result_details=f"Failed to create MCP server '{request.name}' - already exists"
                    )

            # Create new server configuration
            server_config = MCPServerConfig(
                name=request.name,
                enabled=request.enabled,
                transport=request.transport,
                # StdioConnection fields
                command=request.command,
                args=request.args or [],
                env=request.env or {},
                cwd=request.cwd,
                encoding=request.encoding,
                encoding_error_handler=request.encoding_error_handler,
                # HTTP-based connection fields
                url=request.url,
                headers=request.headers,
                timeout=request.timeout,
                sse_read_timeout=request.sse_read_timeout,
                terminate_on_close=request.terminate_on_close,
                # Common fields
                description=request.description,
                capabilities=request.capabilities or [],
            )

            servers.append(server_config)
            self._save_mcp_servers(servers)

            return CreateMCPServerResultSuccess(
                name=request.name, result_details=f"Successfully created MCP server '{request.name}'"
            )
        except Exception as e:
            logger.error("Failed to create MCP server '%s': %s", request.name, e)
            return CreateMCPServerResultFailure(result_details=f"Failed to create MCP server '{request.name}': {e}")

    def on_update_mcp_server_request(
        self, request: UpdateMCPServerRequest
    ) -> UpdateMCPServerResultSuccess | UpdateMCPServerResultFailure:
        """Handle update MCP server request."""
        try:
            servers = self._get_mcp_servers()

            # Find server by server_id
            server_config = None
            for server in servers:
                if server.name == request.name:
                    server_config = server
                    break

            if server_config is None:
                return UpdateMCPServerResultFailure(
                    result_details=f"Failed to update MCP server '{request.name}' - not found"
                )

            # Update only provided fields
            self._update_server_fields(server_config, request)

            self._save_mcp_servers(servers)

            return UpdateMCPServerResultSuccess(
                name=request.name, result_details=f"Successfully updated MCP server '{request.name}'"
            )
        except Exception as e:
            logger.error("Failed to update MCP server '%s': %s", request.name, e)
            return UpdateMCPServerResultFailure(result_details=f"Failed to update MCP server '{request.name}': {e}")

    def on_delete_mcp_server_request(
        self, request: DeleteMCPServerRequest
    ) -> DeleteMCPServerResultSuccess | DeleteMCPServerResultFailure:
        """Handle delete MCP server request."""
        try:
            servers = self._get_mcp_servers()

            # Find and remove server by server_id
            server_found = False
            for i, server in enumerate(servers):
                if server.name == request.name:
                    servers.pop(i)
                    server_found = True
                    break

            if not server_found:
                return DeleteMCPServerResultFailure(
                    result_details=f"Failed to delete MCP server '{request.name}' - not found"
                )

            self._save_mcp_servers(servers)

            return DeleteMCPServerResultSuccess(
                name=request.name, result_details=f"Successfully deleted MCP server '{request.name}'"
            )
        except Exception as e:
            logger.error("Failed to delete MCP server '%s': %s", request.name, e)
            return DeleteMCPServerResultFailure(result_details=f"Failed to delete MCP server '{request.name}': {e}")

    def on_enable_mcp_server_request(
        self, request: EnableMCPServerRequest
    ) -> EnableMCPServerResultSuccess | EnableMCPServerResultFailure:
        """Handle enable MCP server request."""
        try:
            servers = self._get_mcp_servers()

            # Find server by server_id
            server_config = None
            for server in servers:
                if server.name == request.name:
                    server_config = server
                    break

            if server_config is None:
                return EnableMCPServerResultFailure(
                    result_details=f"Failed to enable MCP server '{request.name}' - not found"
                )

            server_config.enabled = True
            self._save_mcp_servers(servers)

            return EnableMCPServerResultSuccess(
                name=request.name, result_details=f"Successfully enabled MCP server '{request.name}'"
            )
        except Exception as e:
            logger.error("Failed to enable MCP server '%s': %s", request.name, e)
            return EnableMCPServerResultFailure(result_details=f"Failed to enable MCP server '{request.name}': {e}")

    def on_disable_mcp_server_request(
        self, request: DisableMCPServerRequest
    ) -> DisableMCPServerResultSuccess | DisableMCPServerResultFailure:
        """Handle disable MCP server request."""
        try:
            servers = self._get_mcp_servers()

            # Find server by server_id
            server_config = None
            for server in servers:
                if server.name == request.name:
                    server_config = server
                    break

            if server_config is None:
                return DisableMCPServerResultFailure(
                    result_details=f"Failed to disable MCP server '{request.name}' - not found"
                )

            server_config.enabled = False
            self._save_mcp_servers(servers)

            return DisableMCPServerResultSuccess(
                name=request.name, result_details=f"Successfully disabled MCP server '{request.name}'"
            )
        except Exception as e:
            logger.error("Failed to disable MCP server '%s': %s", request.name, e)
            return DisableMCPServerResultFailure(result_details=f"Failed to disable MCP server '{request.name}': {e}")

    def on_get_enabled_mcp_servers_request(
        self,
        request: GetEnabledMCPServersRequest,  # noqa: ARG002
    ) -> GetEnabledMCPServersResultSuccess | GetEnabledMCPServersResultFailure:
        """Handle get enabled MCP servers request."""
        try:
            servers = self._get_mcp_servers()
            enabled_servers = [server for server in servers if server.enabled]
            servers_dict = {server.name: server.model_dump() for server in enabled_servers}

            return GetEnabledMCPServersResultSuccess(
                servers=servers_dict, result_details=f"Successfully retrieved {len(servers_dict)} enabled MCP servers"
            )
        except Exception as e:
            logger.error("Failed to get enabled MCP servers: %s", e)
            return GetEnabledMCPServersResultFailure(result_details=f"Failed to get enabled MCP servers: {e}")
