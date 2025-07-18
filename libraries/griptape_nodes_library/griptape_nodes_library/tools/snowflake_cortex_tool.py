from griptape.tools.snowflake_cortex.tool import SnowflakeCortexTool

from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes_library.tools.base_tool import BaseTool


class SnowflakeCortex(BaseTool):
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.update_tool_info(
            value="The Snowflake Cortex tool can invoke Snowflake Cortex Agents.",
            title="Snowflake Cortex Tool",
        )

        self.add_parameter(
            Parameter(
                name="Agent_Model",
                type="str",
                tooltip="Snowflake Cortex Agent model to use. ex: \"claude-3-5-sonnet\"",
                allowed_modes={ParameterMode.PROPERTY},
                default_value="claude-3-5-sonnet",
            )
        )
        self.add_parameter(
            Parameter(
                name="Search_Limit",
                type="int",
                tooltip="Maximum number of Cortex Search results to return.",
                allowed_modes={ParameterMode.PROPERTY},
                default_value=10,
            )
        )
        self.add_parameter(
            Parameter(
                name="Search_Service",
                type="str",
                tooltip="Snowflake Cortex Search service name. ex: \"sales_intelligence.data.sales_conversation_search\"",
                allowed_modes={ParameterMode.PROPERTY},
            )
        )
        self.add_parameter(
            Parameter(
                name="Analyst_Semantic_Model_File",
                type="str",
                tooltip="Snowflake Analyst semantic model file. ex: \"@sales_intelligence.data.models/sales_metrics_model.yaml\"",
                allowed_modes={ParameterMode.PROPERTY},
            )
        )

        self.move_element_to_position("tool", position="last")
        self.hide_parameter_by_name("off_prompt")

    def process(self) -> None:
        off_prompt = self.get_parameter_value("off_prompt")

        tool = SnowflakeCortexTool(
            off_prompt=off_prompt,
            account=self.get_config_value(service="Snowflake", value="SNOWFLAKE_ACCOUNT"),
            user=self.get_config_value(service="Snowflake", value="SNOWFLAKE_USER"),
            password=self.get_config_value(service="Snowflake", value="SNOWFLAKE_PASSWORD"),
            role=self.get_config_value(service="Snowflake", value="SNOWFLAKE_ROLE"),
            agent_model=self.get_parameter_value("Agent_Model"),
            search_limit=self.get_parameter_value("Search_Limit"),
            search_service=self.get_parameter_value("Search_Service"),
            analyst_semantic_model_file=self.get_parameter_value("Analyst_Semantic_Model_File"),
        )
        self.parameter_output_values["tool"] = tool
