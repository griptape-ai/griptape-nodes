from typing import Any

from griptape.drivers.web_search.duck_duck_go import DuckDuckGoWebSearchDriver as GtDuckDuckGoWebSearchDriver

from griptape_nodes.exe_types.core_types import Parameter
from griptape_nodes_library.config.base_driver import BaseDriver


class BaseWebSearchDriver(BaseDriver):
    """Base driver node for creating Griptape Drivers.

    This node provides a generic implementation for initializing Griptape tools with configurable parameters.

    Attributes:
        driver (dict): A dictionary representation of the created tool.
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)

        self._replace_param_by_name(
            param_name="driver",
            new_param_name="web_search_config",
            new_output_type="Web Search Driver",
            tooltip="Connect to a Web Search Tool",
        )
        self.add_parameter(
            Parameter(
                name="results_count",
                input_types=["int"],
                type="int",
                output_type="int",
                default_value=5,
                tooltip="Number of results to return from the web search.",
            )
        )
        self.add_parameter(
            Parameter(
                name="language",
                input_types=["str"],
                type="str",
                output_type="str",
                default_value="en",
                tooltip="Language for the web search results.",
            )
        )
        self.add_parameter(
            Parameter(
                name="country",
                input_types=["str"],
                type="str",
                output_type="str",
                default_value="us",
                tooltip="Country for the web search results.",
            )
        )

    def _get_common_driver_args(self, params: dict[str, Any]) -> dict[str, Any]:
        driver_args = {
            "results_count": params.get("results_count"),
            "language": params.get("language"),
            "country": params.get("country"),
        }

        return driver_args


class DuckDuckGo(BaseWebSearchDriver):
    def process(self) -> None:
        # Get the parameters from the node
        params = self.parameter_values

        # --- Get Common Driver Arguments ---
        # Use the helper method from BaseImageDriver to get common driver arguments
        common_args = self._get_common_driver_args(params)

        # Create the tool
        driver = GtDuckDuckGoWebSearchDriver(**common_args)

        # Set the output
        self.parameter_output_values["web_search_config"] = (
            driver  # TODO: https://github.com/griptape-ai/griptape-nodes/issues/874
        )
