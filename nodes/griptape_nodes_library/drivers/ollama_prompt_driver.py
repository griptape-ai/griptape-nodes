from griptape.drivers.prompt.ollama import OllamaPromptDriver

from griptape_nodes_library.drivers.base_prompt_driver import BasePromptDriverNode

DEFAULT_PORT = "11434"
DEFAULT_BASE_URL = "http://127.0.0.1"
DEFAULT_MODEL = "llama3.2"


class OllamaPromptDriverNode(BasePromptDriverNode):
    """Node for Ollama Prompt Driver.

    This node creates an Ollama prompt driver and outputs its configuration.
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)

    def process(self) -> None:
        # Get the parameters from the node
        kwargs = {}
        kwargs["model"] = self.valid_or_fallback("model", DEFAULT_MODEL)
        kwargs["temperature"] = self.valid_or_fallback("temperature", None)
        kwargs["max_attempts"] = self.valid_or_fallback("max_attempts_on_fail", None)
        kwargs["use_native_tools"] = self.valid_or_fallback("use_native_tools", False)
        kwargs["max_tokens"] = self.valid_or_fallback("max_tokens", None)

        kwargs["extra_params"] = {
            "options": {
                "min_p": self.valid_or_fallback("min_p", None),
                "top_k": self.valid_or_fallback("top_k", None),
            },
        }

        # Create the driver
        driver = OllamaPromptDriver(**kwargs)

        # Set the output
        self.parameter_output_values["driver"] = driver
