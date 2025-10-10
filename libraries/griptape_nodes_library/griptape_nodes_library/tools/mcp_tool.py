from griptape_nodes.exe_types.core_types import Parameter
from griptape_nodes.retained_mode.griptape_nodes import logger
from griptape_nodes.traits.button import Button, ButtonDetailsMessagePayload
from griptape_nodes.traits.options import Options
from griptape_nodes_library.tools.base_tool import BaseTool
from griptape_nodes_library.utils.mcp_utils import (
    create_mcp_tool,
    get_available_mcp_servers,
    get_server_config,
)


class MCPToolNode(BaseTool):
    """A tool that can be used to call MCP tools.

    TODO: (Jason) This tool is temporarily disabled, until we figure out how to
    properly serialize connections for the MCPTool.
    https://github.com/griptape-ai/griptape-nodes/issues/2368
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)

        self.update_tool_info(
            value="This MCP tool can be given to an agent to allow it to use MCP servers.",
            title="MCP Tool",
        )
        self.hide_parameter_by_name("off_prompt")
        # Get available MCP servers for the dropdown
        mcp_servers = get_available_mcp_servers()
        default_mcp_server = mcp_servers[0] if mcp_servers else None
        self.add_parameter(
            Parameter(
                name="mcp_server_name",
                input_types=["str"],
                type="str",
                default_value=default_mcp_server,
                tooltip="Select an MCP server to use",
                traits={
                    Options(choices=mcp_servers),
                    Button(
                        full_width=False,
                        icon="refresh-cw",
                        size="icon",
                        variant="secondary",
                        on_click=self._reload_mcp_servers,
                    ),
                },
                ui_options={"placeholder_text": "Select MCP server..."},
            )
        )
        self.move_element_to_position("tool", position="last")

    def _reload_mcp_servers(self, button: Button, button_details: ButtonDetailsMessagePayload) -> None:  # noqa: ARG002
        """Reload MCP servers when the refresh button is clicked."""
        try:
            # Get fresh list of MCP servers
            mcp_servers = get_available_mcp_servers()

            # Update the parameter's choices using the proper method
            if mcp_servers:
                current_value = self.get_parameter_value("mcp_server_name")
                if current_value in mcp_servers:
                    default_value = current_value
                else:
                    default_value = mcp_servers[0]

                # Use _update_option_choices to properly update both trait and UI options
                self._update_option_choices("mcp_server_name", mcp_servers, default_value)
                msg = f"{self.name}: Refreshed MCP servers: {len(mcp_servers)} servers available"
                logger.info(f"Refreshed MCP servers: {len(mcp_servers)} servers available")
            else:
                # No servers available - use proper method
                self._update_option_choices("mcp_server_name", ["No MCP servers available"], "No MCP servers available")
                msg = f"{self.name}: No MCP servers available"
                logger.info(msg)

        except Exception as e:
            msg = f"{self.name}: Failed to reload MCP servers: {e}"
            logger.error(msg)

    async def aprocess(self) -> None:
        logger.info("Processing MCPToolNode")
        mcp_server_name = self.get_parameter_value("mcp_server_name")
        # Get MCP server configuration
        server_config = get_server_config(mcp_server_name)
        if server_config is None:
            error_details = f"MCP server '{mcp_server_name}' not found or not enabled"
            logger.error(f"{self.name}: {error_details}")
            return

        # Create MCP tool using utility function
        tool = create_mcp_tool(mcp_server_name, server_config)

        # Set the output
        self.parameter_output_values["tool"] = tool
