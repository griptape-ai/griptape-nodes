from griptape.drivers.embedding.ollama import OllamaEmbeddingDriver as GtOllamaEmbeddingDriver

from griptape_nodes.exe_types.core_types import Parameter
from griptape_nodes_library.drivers.embedding.base_embedding_driver import BaseEmbeddingDriver

OLLAMA_BASE_URL_ENV_VAR = "ollama_base_url"
DEFAULT_BASE_URL = "http://127.0.0.1"
DEFAULT_MODEL = "all-minilm"
DEFAULT_PORT = "11434"
SERVICE = "Ollama"


class OllamaEmbeddingDriver(BaseEmbeddingDriver):
    """Node for Ollama Embedding Driver.

    This node creates an Ollama embedding driver and outputs its configuration.
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)

        # Add parameters specific to Ollama embedding driver
        self.add_parameter(
            Parameter(
                name="base_url",
                input_types=["str"],
                type="str",
                output_type="str",
                default_value=DEFAULT_BASE_URL,
                tooltip="The base URL of the Ollama server",
            )
        )
        self.add_parameter(
            Parameter(
                name="port",
                input_types=["str"],
                type="str",
                output_type="str",
                default_value=DEFAULT_PORT,
                tooltip="The port of the Ollama server",
            )
        )
        self.add_parameter(
            Parameter(
                name="embedding_model",
                input_types=["str"],
                type="str",
                output_type="str",
                default_value="",
                tooltip="The embedding model to use",
            )
        )

    def process(self) -> None:
        # Get the parameters from the node
        params = self.parameter_values

        # Initialize kwargs for driver creation
        kwargs = {}
        kwargs["model"] = params.get("embedding_model", DEFAULT_MODEL)

        # Set up the host URL by combining base_url and port
        base_url = params.get("base_url", DEFAULT_BASE_URL)
        if not base_url or base_url == "":
            base_url = self.get_config_value(service=SERVICE, value=OLLAMA_BASE_URL_ENV_VAR)

        port = params.get("port", DEFAULT_PORT)
        if base_url and port:
            kwargs["host"] = f"{base_url}:{port}"

        self.parameter_output_values["embedding_driver"] = GtOllamaEmbeddingDriver(**kwargs)
