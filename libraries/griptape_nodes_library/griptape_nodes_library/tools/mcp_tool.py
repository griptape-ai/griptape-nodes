from griptape.tools.mcp.sessions import StdioConnection
from griptape.tools.mcp.tool import MCPTool

from griptape_nodes.exe_types.core_types import Parameter
from griptape_nodes.retained_mode.griptape_nodes import logger
from griptape_nodes_library.tools.base_tool import BaseTool


class MCPToolNode(BaseTool):
    """A tool that can be used to call MCP tools.

    TODO: (Jason) This tool is temporarily disabled, until we upgrade Griptape to Python 3.10
    as it won't currently import correctly for Agents.
    https://github.com/griptape-ai/griptape-nodes/issues/2368
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)

        self.update_tool_info(
            value="This MCP tool can be given to an agent to allow it to call MCP tools.",
            title="MCP Tool",
        )
        self.hide_parameter_by_name("off_prompt")
        self.add_parameter(
            Parameter(
                name="mcp_connection",
                input_types=["str", "json"],
                type="json",
                default_value=None,
                tooltip="The MCP connection to use",
            )
        )

    async def aprocess(self) -> None:
        logger.info("Processing MCPToolNode")
        off_prompt = self.parameter_values.get("off_prompt", False)
        mcp_connection = self.get_parameter_value("mcp_connection")

        connection: StdioConnection = mcp_connection

        # Create the tool
        tool = MCPTool(connection=connection, off_prompt=off_prompt)

        # Do this because it manually triggers post_init - but it's jucky. YMMV.
        await tool._init_activities()

        # Set the output
        self.parameter_output_values["tool"] = tool
