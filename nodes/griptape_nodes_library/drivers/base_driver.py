from griptape.drivers.prompt.dummy import DummyPromptDriver

from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import DataNode
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes


class BaseDriverNode(DataNode):
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.config = GriptapeNodes.ConfigManager()

        self.add_parameter(
            Parameter(
                name="driver",
                output_type="Any",
                default_value=None,
                tooltip="The created driver",
            )
        )

    def getenv(self, service: str, value: str) -> str:
        api_key = self.config.get_config_value(f"env.{service}.{value}")
        return api_key

    def params_to_sparse_dict(self, params, kwargs, param_name, target_name=None, transform=None) -> dict:
        """Add a parameter to kwargs if it exists in params, with optional transformation.

        Args:
            params (dict): Dictionary containing parameters
            kwargs (dict): Dictionary to add parameter to if it exists
            param_name (str): Name of the parameter to look for in params
            target_name (str, optional): Name to use in kwargs. If None, uses param_name
            transform (callable, optional): Function to transform the value

        Returns:
            dict: The updated kwargs dictionary
        """
        value = params.get(param_name, None)
        if value is not None:
            transformed_value = transform(value) if transform else value
            kwargs[target_name or param_name] = transformed_value
        return kwargs

    def process(self) -> None:
        # Create the driver
        driver = DummyPromptDriver()

        # Set the output
        self.parameter_output_values["driver"] = driver
