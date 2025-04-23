from griptape.drivers.web_search.duck_duck_go import DuckDuckGoWebSearchDriver as GtDuckDuckGoWebSearchDriver

from griptape_nodes.exe_types.core_types import Parameter
from griptape_nodes.exe_types.node_types import DataNode


class BaseWebSearchDriver(DataNode):
    """Base driver node for creating Griptape Drivers.

    This node provides a generic implementation for initializing Griptape tools with configurable parameters.

    Attributes:
        driver (dict): A dictionary representation of the created tool.
    """

    def __init__(self, name: str, metadata: dict | None = None) -> None:
        super().__init__(name, metadata)

        self.add_parameter(
            Parameter(
                name="web_search_driver",
                input_types=["Web Search Driver"],
                type="Web Search Driver",
                output_type="Web Search Driver",
                default_value=None,
                tooltip="",
            )
        )


class DuckDuckGo(BaseWebSearchDriver):
    def process(self) -> None:
        # Create the tool
        driver = GtDuckDuckGoWebSearchDriver()

        # Set the output
        self.parameter_output_values["web_search_driver"] = (
            driver  # TODO(osipa): Replace this when drivers are serializable
        )
