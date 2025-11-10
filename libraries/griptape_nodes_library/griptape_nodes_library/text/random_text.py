import random
import re
import secrets
import string
from typing import Any

from griptape.artifacts import BaseArtifact
from griptape.drivers.prompt.griptape_cloud import GriptapeCloudPromptDriver

from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import DataNode
from griptape_nodes.exe_types.param_components.seed_parameter import SeedParameter
from griptape_nodes.retained_mode.events.execution_events import ResolveNodeRequest
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
from griptape_nodes.traits.options import Options
from griptape_nodes_library.agents.griptape_nodes_agent import GriptapeNodesAgent as GtAgent

API_KEY_ENV_VAR = "GT_CLOUD_API_KEY"
SERVICE = "Griptape"
MODEL = "gpt-4.1-nano"

# Common English words for random selection
COMMON_WORDS = [
    "the",
    "be",
    "to",
    "of",
    "and",
    "a",
    "in",
    "that",
    "have",
    "I",
    "it",
    "for",
    "not",
    "on",
    "with",
    "he",
    "as",
    "you",
    "do",
    "at",
    "this",
    "but",
    "his",
    "by",
    "from",
    "they",
    "we",
    "say",
    "her",
    "she",
    "or",
    "an",
    "will",
    "my",
    "one",
    "all",
    "would",
    "there",
    "their",
    "what",
    "so",
    "up",
    "out",
    "if",
    "about",
    "who",
    "get",
    "which",
    "go",
    "me",
    "when",
    "make",
    "can",
    "like",
    "time",
    "no",
    "just",
    "him",
    "know",
    "take",
    "people",
    "into",
    "year",
    "your",
    "good",
    "some",
    "could",
    "them",
    "see",
    "other",
    "than",
    "then",
    "now",
    "look",
    "only",
    "come",
    "its",
    "over",
    "think",
    "also",
    "back",
    "after",
    "use",
    "two",
    "how",
    "our",
    "work",
    "first",
    "well",
    "way",
    "even",
    "new",
    "want",
    "because",
    "any",
    "these",
    "give",
    "day",
    "most",
    "us",
    "is",
    "are",
    "was",
    "were",
    "been",
    "being",
    "have",
    "has",
    "had",
    "do",
    "does",
    "did",
    "will",
    "would",
    "shall",
    "should",
    "may",
    "might",
    "must",
    "can",
    "could",
    "am",
    "is",
    "are",
    "was",
    "were",
    "be",
    "being",
    "been",
    "have",
    "has",
    "had",
    "do",
    "does",
    "did",
    "will",
    "would",
    "shall",
    "should",
    "may",
    "might",
    "must",
    "can",
    "could",
]


class RandomText(DataNode):
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)

        # Add input text parameter
        self.add_parameter(
            Parameter(
                name="input_text",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                default_value="",
                input_types=["str"],
                ui_options={"multiline": True},
                tooltip="The multiline text to select random content from. If empty, random content will be generated.",
            )
        )

        # Initialize SeedParameter component
        self._seed_parameter = SeedParameter(self)
        self._seed_parameter.add_input_parameters()

        # Add selection type option
        selection_type_param = Parameter(
            name="selection_type",
            allowed_modes={ParameterMode.PROPERTY},
            type="str",
            default_value="word",
            tooltip="The type of text unit to randomly select.",
        )
        selection_type_param.add_trait(Options(choices=["character", "word", "sentence", "paragraph"]))
        self.add_parameter(selection_type_param)

        # Add output parameter
        self.add_parameter(
            Parameter(
                name="output",
                allowed_modes={ParameterMode.OUTPUT},
                output_type="str",
                ui_options={"multiline": True, "placeholder_text": "Randomly selected text."},
                default_value="",
                tooltip="The randomly selected text unit.",
            )
        )

        # Initialize the agent
        self.agent = None
        self._initialize_agent()

    def _initialize_agent(self) -> None:
        """Initialize the Griptape Agent for text generation."""
        api_key = GriptapeNodes.SecretsManager().get_secret(API_KEY_ENV_VAR)
        if not api_key:
            msg = f"{API_KEY_ENV_VAR} is not defined"
            raise KeyError(msg)

        prompt_driver = GriptapeCloudPromptDriver(model=MODEL, api_key=api_key, stream=True)
        self.agent = GtAgent(prompt_driver=prompt_driver)

    def _generate_with_agent(self, selection_type: str, seed: int | None) -> str:
        """Generate random content using the Griptape Agent."""
        if not self.agent:
            self._initialize_agent()

        # Create appropriate prompt based on selection type
        if selection_type == "sentence":
            prompt = f"Generate a random, grammatically correct sentence. Use seed {seed} for reproducibility. Return only the sentence and nothing else."
            self.parameter_output_values["output"] = "[Generating sentence]"
        elif selection_type == "paragraph":
            prompt = f"Generate a random, coherent paragraph of 2-4 sentences. Use seed {seed} for reproducibility. Return only the paragraph and nothing else."
            self.parameter_output_values["output"] = "[Generating sentence]"
        else:
            # For character and word, fall back to simple random generation
            return self._generate_simple_content(selection_type)

        # Run the agent
        if self.agent:
            result = self.agent.run(prompt)
            if isinstance(result, BaseArtifact):
                return result.output.value
            return str(result.output.value)
        return ""

    def _generate_simple_content(self, selection_type: str) -> str:
        """Generate simple random content for characters and words."""
        if selection_type == "character":
            return secrets.choice(string.ascii_letters + string.digits + string.punctuation)
        # word
        return secrets.choice(COMMON_WORDS)

    def _get_random_selection(self) -> str:
        """Get a random selection from the input text based on the selection type."""
        # Get input parameters
        input_text = self.parameter_values.get("input_text", "")
        seed = self._seed_parameter.get_seed()
        selection_type = self.parameter_values.get("selection_type", "word")

        # Set the random seed
        random.seed(seed)

        try:
            # If input text is empty, generate random content
            if not input_text.strip():
                return self._generate_with_agent(selection_type, seed)

            # Split text based on selection type
            if selection_type == "character":
                items = list(input_text)
            elif selection_type == "word":
                items = input_text.split()
            elif selection_type == "sentence":
                # Split on sentence endings followed by space or newline
                items = [s.strip() for s in re.split(r"[.!?]+[\s\n]+", input_text) if s.strip()]
            else:  # paragraph
                items = [p.strip() for p in input_text.split("\n\n") if p.strip()]

            # Return empty string if no items found
            if not items:
                return self._generate_with_agent(selection_type, seed)

            # Select random item
            return random.choice(items)  # noqa: S311

        except Exception:
            return self._generate_with_agent(selection_type, seed)

    def preprocess(self) -> None:
        self._seed_parameter.preprocess()

    def after_value_set(
        self,
        parameter: Parameter,
        value: Any,
    ) -> None:
        # Handle seed parameter component
        self._seed_parameter.after_value_set(parameter, value)

        if parameter.name != "output":
            # Get current values
            input_text = self.parameter_values.get("input_text", "")
            selection_type = self.parameter_values.get("selection_type", "word")

            # Only trigger node execution if we need to generate content with the agent
            if (
                not input_text.strip()
                and selection_type in ["sentence", "paragraph"]
                and parameter.name in ["selection_type", "seed", "randomize_seed"]
            ):
                # Trigger node execution
                request = ResolveNodeRequest(node_name=self.name)
                GriptapeNodes.handle_request(request)
            else:
                result = self._get_random_selection()
                self.parameter_output_values["output"] = result
                self.set_parameter_value("output", result)
        return super().after_value_set(parameter, value)

    def process(self) -> None:
        # Get random selection
        result = self._get_random_selection()

        # Set the output
        self.parameter_output_values["output"] = result
        self.set_parameter_value("output", result)
