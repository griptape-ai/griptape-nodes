"""Defines the OllamaPrompt node for configuring the Ollama Prompt Driver.

This module provides the `OllamaPrompt` class, which allows users
to configure and utilize the Ollama prompt service within the Griptape
Nodes framework. It inherits common prompt parameters from `BasePrompt` and
instantiates the `OllamaPromptDriver`.
"""

from typing import Any

from griptape.drivers.prompt.ollama import OllamaPromptDriver as GtOllamaPromptDriver

from griptape_nodes.exe_types.core_types import Parameter, ParameterMessage
from griptape_nodes.retained_mode.griptape_nodes import logger
from griptape_nodes_library.config.prompt.base_prompt import BasePrompt

try:
    import ollama  # pyright: ignore[reportMissingImports]

    OLLAMA_INSTALLED = True
except ImportError as e:
    OLLAMA_INSTALLED = False
    logger.warning(f"Ollama not installed: {e}")
    ollama = None  # type: ignore[assignment]


class OllamaConnectionError(Exception):
    """Exception raised when unable to connect to Ollama server or retrieve models."""


# --- Constants ---

DEFAULT_PORT = "11434"
DEFAULT_BASE_URL = "http://127.0.0.1"
DEFAULT_MODEL = "llama3.2"
REFRESH_MODELS_MESSAGE = "🔄 Refresh Models..."
# Common Ollama models - users can type their own model name as well
MODEL_CHOICES = [
    "llama4",
    "llama3.2",
    "llama3.2:1b",
    "llama3.2:3b",
    "llama3.1",
    "llama3.1:8b",
    "llama3.1:70b",
    "codellama",
    "mistral",
    "mixtral",
    "qwen2.5",
]


class OllamaPrompt(BasePrompt):
    """Node for configuring and providing an Ollama Prompt Driver.

    Inherits from `BasePrompt` to leverage common LLM parameters. This node
    customizes the available models to common Ollama models, adds Ollama-specific
    parameters like base_url and port, and does not require an API key since
    Ollama runs locally.

    The `process` method gathers the configured parameters, constructs the host URL
    from base_url and port, utilizes the `_get_common_driver_args` helper from
    `BasePrompt`, adds Ollama-specific configurations, then instantiates an
    `OllamaPromptDriver` and assigns it to the 'prompt_model_config' output parameter.
    """

    def __init__(self, **kwargs) -> None:
        """Initializes the OllamaPrompt node.

        Calls the superclass initializer, then modifies the inherited 'model'
        parameter to use common Ollama models and sets a default. It also adds
        Ollama-specific parameters for base_url and port.
        """
        super().__init__(**kwargs)

        # --- Customize Inherited Parameters ---

        # Update the 'model' parameter for Ollama specifics.
        # Try to get actual available models, fallback to static list
        available_models = self._get_available_models()
        self._update_option_choices(param="model", choices=available_models, default=available_models[0])

        # Remove parameters not typically used by Ollama
        self.remove_parameter_element_by_name("seed")
        self.remove_parameter_element_by_name("min_p")
        self.remove_parameter_element_by_name("top_k")

        # Add Ollama-specific parameters
        self.add_parameter(
            Parameter(
                name="base_url", default_value=DEFAULT_BASE_URL, type="str", tooltip="Base URL for the Ollama server"
            )
        )
        self.add_parameter(
            Parameter(name="port", default_value=DEFAULT_PORT, type="str", tooltip="Port for the Ollama server")
        )
        self.add_node_element(
            ParameterMessage(
                name="ollama_message",
                title="Ollama Prompt Models",
                value="To use the Ollama Prompt Models, you will need to have the Ollama server running.\nYou can download the Ollama server from https://ollama.com/download.",
                variant="info",
                button_link="https://ollama.com/download",
                button_text="Download Ollama",
            )
        )

    def _get_models(self, *, include_refresh: bool = True, raise_on_error: bool = True) -> list[str]:
        """Get the list of available models from the Ollama server.

        Attempts to connect to the Ollama server and retrieve the list of
        installed models. Falls back to helpful messages if the server is not available.

        Args:
            include_refresh: Whether to include the refresh option in the returned list
            raise_on_error: Whether to raise an exception on connection error (vs silent fallback)

        Returns:
            List of available model names.
        """
        try:
            # Get current connection settings (may be different from defaults)
            base_url = self.get_parameter_value("base_url") or DEFAULT_BASE_URL
            port = self.get_parameter_value("port") or DEFAULT_PORT
            host = f"{base_url}:{port}"

            # Create client with custom host if different from default
            if ollama:
                if host != f"{DEFAULT_BASE_URL}:{DEFAULT_PORT}":
                    client = ollama.Client(host=host)
                    response = client.list()
                else:
                    # Use default client
                    response = ollama.list()
            else:
                # This should never happen since we check OLLAMA_INSTALLED first
                msg = "Ollama module not available"
                raise OllamaConnectionError(msg)  # noqa: TRY301

            models = [model["model"] for model in response.get("models", [])]

            if models:
                # Sort models alphabetically for better UX
                models.sort()
                if include_refresh:
                    models.append(REFRESH_MODELS_MESSAGE)
                return models

        except Exception as e:
            if raise_on_error:
                msg = f"{self.name}: Unable to get available models from Ollama: {e}"
                logger.warning(msg)
                raise OllamaConnectionError(msg) from e
            # Silent fallback for internal use
            return []

        # No models found - show helpful message
        if include_refresh:
            no_models_message = "📝 No models found - Install models with 'ollama pull <model>'"
            return [no_models_message, REFRESH_MODELS_MESSAGE]
        return []

    def _get_available_models(self) -> list[str]:
        """Get the list of available models from the Ollama server.

        Returns:
            List of available model names with refresh option.
        """
        return self._get_models(include_refresh=True, raise_on_error=True)

    def _get_base_models(self) -> list[str]:
        """Get the list of available models from the Ollama server (without refresh option).

        Returns:
            List of available model names (without refresh option).
        """
        return self._get_models(include_refresh=False, raise_on_error=False)

    def _refresh_model_list(self) -> None:
        """Refresh the model list and update the model parameter choices.

        Queries the Ollama server for available models and updates the model
        parameter's choices and default value accordingly.
        """
        # Get fresh model list (without refresh option for counting)
        base_models = self._get_base_models()
        available_models = base_models.copy()
        available_models.append(REFRESH_MODELS_MESSAGE)

        # Update the model parameter with new choices
        model_param = self.get_parameter_by_name("model")
        if model_param:
            # Store current value to preserve user's selection if still valid
            current_value = self.get_parameter_value("model")

            # Update choices
            self._update_option_choices(param="model", choices=available_models, default=available_models[0])

            # Restore previous value if it's still available, otherwise use new default
            if current_value and current_value in base_models:  # Don't restore if it was the refresh option
                self.set_parameter_value("model", current_value)
            else:
                # Don't auto-select the helpful message - pick first real model if available
                first_real_model = next(
                    (
                        model
                        for model in available_models
                        if not model.startswith("📝") and model != "REFRESH_MODELS_MESSAGE"
                    ),
                    None,
                )
                if first_real_model:
                    self.set_parameter_value("model", first_real_model)
                else:
                    # Only helpful message and refresh option available
                    self.set_parameter_value("model", available_models[0])

    def after_value_set(self, parameter: Parameter, value: Any) -> None:
        """Handle parameter value changes.

        Refreshes model list when:
        - User selects REFRESH_MODELS_MESSAGE from the model dropdown
        - Base URL or port changes (indicating different Ollama server)
        """
        if parameter.name == "model" and value == "REFRESH_MODELS_MESSAGE":
            # User selected refresh option - refresh models and keep refresh option
            self._refresh_model_list()
            # Reset to first available model (not the refresh option)
            base_models = self._get_base_models()
            if base_models:
                self.set_parameter_value("model", base_models[0])
        elif parameter.name == "model" and value.startswith("📝"):
            # User selected the helpful message - refresh to see if models are now available
            self._refresh_model_list()

        elif parameter.name in ["base_url", "port"]:
            # Server settings changed, auto-refresh model list
            self._refresh_model_list()

        return super().after_value_set(parameter, value)

    def validate_before_node_run(self) -> list[Exception] | None:
        """Performs pre-run validation checks for the node.

        Checks if Ollama is installed and if the selected model is available.

        Returns:
            A list of Exception objects if validation fails, otherwise None.
        """
        exceptions = []

        # Check if Ollama is installed
        if not OLLAMA_INSTALLED:
            msg = f"{self.name}: Ollama is not installed. Please install ollama from https://ollama.com/download"
            exceptions.append(ValueError(msg))
            return exceptions

        # Check if the selected model is available
        try:
            selected_model = self.get_parameter_value("model")
            if not selected_model:
                msg = "No model selected"
                exceptions.append(ValueError(msg))
                return exceptions

            # Skip validation for special UI messages
            if selected_model.startswith("📝") or selected_model == REFRESH_MODELS_MESSAGE:
                return exceptions if exceptions else None

            # Get available models
            available_models = self._get_base_models()

            if not available_models:
                msg = "No models found. Install models with 'ollama pull <model>'"
                exceptions.append(ValueError(msg))
                return exceptions

            if selected_model not in available_models:
                msg = f"Selected model '{selected_model}' is not available. Available models: {', '.join(available_models)}"
                exceptions.append(ValueError(msg))

        except OllamaConnectionError as e:
            msg = f"Unable to connect to Ollama server: {e}"
            exceptions.append(e)
        except Exception as e:
            msg = f"Error validating Ollama configuration: {e}"
            exceptions.append(Exception(msg))

        return exceptions if exceptions else None

    def process(self) -> None:
        """Processes the node configuration to create an OllamaPromptDriver.

        Retrieves parameter values set on the node, constructs the host URL
        from base_url and port, gets common driver arguments, adds Ollama-specific
        configurations, instantiates the driver, and assigns it to the
        'prompt_model_config' output parameter.
        """
        # Retrieve all parameter values set on the node UI or via input connections.
        params = self.parameter_values

        # --- Get Common Driver Arguments ---
        # Use the helper method from BasePrompt to get args like temperature, stream, max_attempts, etc.
        common_args = self._get_common_driver_args(params)

        # --- Prepare Ollama Specific Arguments ---
        specific_args = {}

        # Construct the host URL from base_url and port
        base_url = self.get_parameter_value("base_url")
        port = self.get_parameter_value("port")
        specific_args["host"] = f"{base_url}:{port}"

        # Get the selected model
        specific_args["model"] = self.get_parameter_value("model")

        # Note: Ollama extra_params/options can be added here in the future
        # Currently we don't pass any additional options to Ollama

        # --- Combine Arguments and Instantiate Driver ---
        # Combine common arguments with Ollama specific arguments.
        # Specific args take precedence if there's an overlap (though unlikely here).
        all_kwargs = {**common_args, **specific_args}

        # Create the Ollama prompt driver instance.
        driver = GtOllamaPromptDriver(**all_kwargs)

        # Set the output parameter 'prompt_model_config'.
        self.parameter_output_values["prompt_model_config"] = driver
