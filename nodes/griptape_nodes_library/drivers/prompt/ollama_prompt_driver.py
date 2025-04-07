from griptape.drivers.prompt.ollama import OllamaPromptDriver

from griptape_nodes.exe_types.node_types import Parameter
from griptape_nodes_library.drivers.prompt.base_prompt_driver import BasePromptDriverNode
from traits.options import Options

DEFAULT_PORT = "11434"
DEFAULT_BASE_URL = "http://127.0.0.1"
DEFAULT_MODEL = "llama3.2"


class OllamaPromptDriverNode(BasePromptDriverNode):
    """Node for Ollama Prompt Driver.

    This node creates an Ollama prompt driver and outputs its configuration.
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)

        # Set any defaults
        model_parameter = self.get_parameter_by_name("model")
        self.get_model_list()
        if model_parameter is not None:
            model_parameter.default_value = self.models[0]
            model_parameter.input_types = ["str"]
            model_parameter.add_trait(Options(self.models))

        self.add_parameter(Parameter(name="base_url", default_value=DEFAULT_BASE_URL, type="str", tooltip=""))
        self.add_parameter(Parameter(name="port", default_value=DEFAULT_PORT, type="str", tooltip=""))

    def get_model_list(self) -> None:
        import ollama

        self.models = [model["model"] for model in ollama.list()["models"]]

    def process(self) -> None:
        # Get the parameters from the node
        params = self.parameter_values

        kwargs = {}
        kwargs["model"] = params.get("model", self.models[0])
        base_url = params.get("base_url", DEFAULT_BASE_URL)
        port = params.get("port", DEFAULT_PORT)
        kwargs["host"] = f"{base_url}:{port}"
        kwargs["temperature"] = params.get("temperature", None)
        kwargs["max_attempts"] = params.get("max_attempts_on_fail", None)
        kwargs["use_native_tools"] = params.get("use_native_tools", False)
        kwargs["max_tokens"] = params.get("max_tokens", None)

        kwargs["extra_params"] = {
            "options": {
                "min_p": params.get("min_p", None),
                "top_k": params.get("top_k", None),
            },
        }

        # Create the driver
        driver = OllamaPromptDriver(**kwargs)

        # Set the output
        self.parameter_output_values["prompt_driver"] = driver
