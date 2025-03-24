from griptape.drivers import BaseWebSearchDriver, DuckDuckGoWebSearchDriver
from griptape.tools import WebSearchTool

from griptape_nodes.exe_types.core_types import Parameter
from griptape_nodes_library.tools.tools import gnBaseTool


class gnWebSearchTool(gnBaseTool):
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.add_parameter(Parameter(name="driver", allowed_types=["dict"], default_value={}, tooltip=""))

    def process(self) -> None:
        off_prompt = self.parameter_values.get("off_prompt", False)
        driver_dict = self.parameter_values.get("driver", {})
        if driver_dict:
            driver = BaseWebSearchDriver.from_dict(driver_dict)  # pyright: ignore[reportAttributeAccessIssue] TODO(collin): Make Web Search Drivers serializable
        else:
            driver = DuckDuckGoWebSearchDriver()

        # Create the tool
        tool = WebSearchTool(off_prompt=off_prompt, web_search_driver=driver)

        # Set the output
        self.parameter_output_values["tool"] = tool
        # print tool.from_dict()
