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
                name="driver",
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
        self.parameter_output_values["driver"] = driver.to_dict()  # pyright: ignore[reportAttributeAccessIssue] TODO(collin): Make Web Search Drivers serializable
