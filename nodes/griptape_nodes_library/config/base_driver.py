from abc import abstractmethod
from collections.abc import Callable
from typing import Any

from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import DataNode
from griptape_nodes.traits.options import Options


class BaseDriver(DataNode):
    """Base class for driver nodes that need to manage parameters and validate configuration.

    This class provides a foundation for driver nodes by offering utility methods
    for managing parameters, updating traits, and validating API keys.
    """

    # -----------------------------------------------------------------------------
    # Initialization
    # -----------------------------------------------------------------------------

    def __init__(self, **kwargs) -> None:
        """Initialize a BaseDriver instance.

        Args:
            kwargs (Any): Additional keyword arguments to initialize the base DataNode class.

        Example:
            driver = BaseDriver(name="ExampleDriver")
        """
        super().__init__(**kwargs)

        self.add_parameter(
            Parameter(
                name="driver",
                output_type="Any",
                default_value=None,
                tooltip="",
                allowed_modes={ParameterMode.OUTPUT},
            )
        )

    # -----------------------------------------------------------------------------
    # Abstract Methods
    # -----------------------------------------------------------------------------
    # @abstractmethod TODO: https://github.com/griptape-ai/griptape-nodes/issues/872
    def _get_common_driver_args(self, params: dict[str, Any]) -> dict[str, Any]:  # noqa: ARG002
        """Gets common driver arguments from parameters.

        Subclasses should implement this method to extract and process
        arguments that are needed to instantiate their specific driver.

        Args:
            self: The instance of the driver class.
            params: Dictionary of parameter values.

        Returns:
            A dictionary of arguments to be passed to the driver constructor.
        """
        return {}

    @abstractmethod
    def process(self) -> None:
        """Abstract method to process the node's data and set output values.

        Subclasses must override this method to define how the driver is created
        and how outputs are populated.

        Example:
            def process(self):
                driver = MyRealDriver()
                self.parameter_output_values["driver"] = driver
        """
        msg = "Subclasses must implement the 'process' method."
        raise NotImplementedError(msg)

    # -----------------------------------------------------------------------------
    # Public API Methods
    # -----------------------------------------------------------------------------

    def remove_parameter_by_name(self, name: str) -> None:
        """Removes a parameter by its name from the node.

        This method will hopefully be elevated to the base class in the future.

        Args:
            name: The name of the parameter to remove.

        """
        try:
            param = self.get_parameter_by_name(name)
            if param is not None:
                self.remove_parameter(param)
        except Exception as e:
            # Handle the case where the parameter is not found or cannot be removed
            msg = f"Error removing parameter '{name}'."
            raise ValueError(msg) from e

    def params_to_sparse_dict(
        self,
        params: dict,
        kwargs: dict,
        param_name: str,
        target_name: str | None = None,
        transform: Callable | None = None,
    ) -> dict:
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
        value = params.get(param_name)
        if value is not None:
            transformed_value = transform(value) if transform else value
            kwargs[target_name or param_name] = transformed_value
        return kwargs

    # -----------------------------------------------------------------------------
    # Internal Helper Methods
    # -----------------------------------------------------------------------------

    def _update_option_choices(self, param: str, choices: list[str], default: str) -> None:
        """Updates the model selection parameter with a new set of choices.

        This method is intended to be called by subclasses to set the available
        models for the driver. It modifies the 'model' parameter's `Options` trait
        to reflect the provided choices.

        Args:
            param: The name of the parameter representing the model selection or the Parameter object itself.
            choices: A list of model names to be set as choices.
            default: The default model name to be set. It must be one of the provided choices.
        """
        parameter = self.get_parameter_by_name(param)
        if parameter is not None:
            trait = parameter.find_element_by_id("Options")
            if trait and isinstance(trait, Options):
                trait.choices = choices

                if default in choices:
                    parameter.default_value = default
                    self.set_parameter_value(param, default)
                else:
                    msg = f"Default model '{default}' is not in the provided choices."
                    raise ValueError(msg)
        else:
            msg = f"Parameter '{param}' not found for updating model choices."
            raise ValueError(msg)

    def _remove_options_trait(self, param: str) -> None:
        """Removes the options trait from the specified parameter.

        This method is intended to be called by subclasses to remove the
        `Options` trait from a parameter, if it exists.

        Args:
            param: The name of the parameter from which to remove the `Options` trait.
        """
        parameter = self.get_parameter_by_name(param)
        if parameter is not None:
            trait = parameter.find_element_by_id("Options")
            if trait and isinstance(trait, Options):
                parameter.remove_trait(trait)
        else:
            msg = f"Parameter '{param}' not found for removing options trait."
            raise ValueError(msg)

    def _replace_param_by_name(  # noqa: PLR0913
        self,
        param_name: str,
        new_param_name: str,
        new_output_type: str | None = None,
        tooltip: str | list[dict] | None = None,
        default_value: Any = None,
        ui_options: dict | None = None,
    ) -> None:
        """Replaces a parameter in the node configuration.

        This method is used to replace a parameter with a new name and
        optionally update its tooltip and default value.

        Args:
            param_name (str): The name of the parameter to replace.
            new_param_name (str): The new name for the parameter.
            new_output_type (str, optional): The new output type for the parameter.
            tooltip (str, list[dict], optional): The new tooltip for the parameter.
            default_value (Any, optional): The new default value for the parameter.
            ui_options (dict, optional): UI options for the parameter.
        """
        param = self.get_parameter_by_name(param_name)
        if param is not None:
            param.name = new_param_name
            if tooltip is not None:
                param.tooltip = tooltip
            if default_value is not None:
                param.default_value = default_value
            if new_output_type is not None:
                param.output_type = new_output_type
            if ui_options is not None:
                param.ui_options = ui_options
        else:
            msg = f"Parameter '{param_name}' not found in node configuration."
            raise ValueError(msg)

    def _display_api_key_message(self, service_name: str, api_key_env_var: str, api_key_url: str | None) -> None:
        """Checks if the API key exists in the node configuration, displays a message if not.

        This method checks if the API key for a specific service is present
        in the node's configuration. It returns True if the key exists and
        is not empty, otherwise returns False.

        Args:
            service_name: The name of the service in the node configuration.
            api_key_env_var: The name of the key variable within the service config.
            api_key_url: An optional URL for users to visit to obtain the key,
                         included in the error message if provided.

        Returns:
            bool: True if the API key exists and is not empty, False otherwise.
        """
        message_param = self.get_parameter_by_name("message")
        if message_param is not None:
            api_key = self.get_config_value(service_name, api_key_env_var)
            msg = f"⚠️ This node requires an API key from {service_name}\nPlease visit {api_key_url} to obtain a valid key and update your settings."
            message_param.default_value = msg
            if not api_key:
                message_param._ui_options["hide"] = False
            else:
                message_param._ui_options["hide"] = True

    def _validate_api_key(
        self, service_name: str, api_key_env_var: str, api_key_url: str | None
    ) -> list[Exception] | None:
        """Validates the presence and non-emptiness of a specific API key in config.

        Checks the node's configuration for the given key within the specified
        service. Returns a list containing an error if the key is missing or empty.

        Args:
            service_name: The name of the service in the node configuration.
            api_key_env_var: The name of the key variable within the service config.
            api_key_url: An optional URL for users to visit to obtain the key,
                     included in the error message if provided.

        Returns:
            A list of exceptions (KeyError or ValueError) if validation fails,
            otherwise None.
        """
        exceptions = []

        api_key = self.get_config_value(service_name, api_key_env_var)
        if not api_key:
            msg = f"API Key ('{api_key_env_var}') for service '{service_name}' is missing."
            if api_key_url:
                msg += f" Please visit {api_key_url} to obtain a valid key and update your settings."
            else:
                msg += " Please provide a valid API key in your settings."
            exceptions.append(KeyError(msg))

        # Display a message to the user if the API key is missing or empty.
        self._display_api_key_message(
            service_name=service_name, api_key_env_var=api_key_env_var, api_key_url=api_key_url
        )

        return exceptions if exceptions else None
