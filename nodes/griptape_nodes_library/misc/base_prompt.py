"""Defines the BasePrompt node, an abstract base class for prompt driver configuration nodes.

This module provides the `BasePrompt` class, which serves as a foundation
for creating specific prompt driver configuration nodes within the Griptape
Nodes framework. It inherits from `BaseDriver` and defines common parameters
used by most prompt drivers (like temperature, model, etc.). Subclasses
should inherit from `BasePrompt` and override the `process` method to instantiate
and configure a specific Griptape prompt driver.
"""

from griptape.drivers.prompt.dummy import DummyPromptDriver

from griptape_nodes.exe_types.core_types import Parameter
from griptape_nodes.traits.options import Options
from griptape_nodes_library.drivers.base_driver import BaseDriver


class BasePrompt(BaseDriver):
    """Abstract base node for configuring Griptape Prompt Drivers.

    Inherits from `BaseDriver` and provides a standard set of parameters common
    to many Large Language Model (LLM) prompt drivers, such as temperature,
    model selection, and token limits.

    It renames the inherited 'driver' output parameter to 'prompt model config'
    to clearly indicate its purpose in the context of prompt configuration.

    Subclasses should:
    1. Inherit from this class.
    2. Potentially override or modify the `model` parameter's `Options` trait
       to list specific models supported by their driver.
    3. Override the `process` method to instantiate the specific Griptape
       prompt driver (e.g., `OpenAiChatPromptDriver`, `AnthropicPromptDriver`)
       using the parameter values defined here.

    Note: The `process` method in this base class creates a `DummyPromptDriver`
    primarily to establish the output socket type. It does not utilize the
    configuration parameters defined herein. Direct use of `BasePrompt` is
    generally not intended.
    """

    def __init__(self, **kwargs) -> None:
        """Initializes the BasePrompt node.

        Sets up the node by calling the superclass initializer, renaming the
        inherited 'driver' output parameter to 'prompt model config', and
        adding standard parameters common across various prompt drivers.
        """
        super().__init__(**kwargs)

        # Rename the inherited output parameter for clarity in this context.
        # The base 'BaseDriver' likely outputs a generic 'driver', but here we
        # specifically output a 'Prompt Model Config' (which is a driver).
        driver_parameter = self.get_parameter_by_name("driver")
        if driver_parameter is not None:
            driver_parameter.name = "prompt model config"
            driver_parameter.output_type = "Prompt Model Config"

        # --- Common Prompt Driver Parameters ---
        # These parameters represent settings frequently used by LLM prompt drivers.
        # Subclasses will typically use these values when instantiating their specific driver.

        # Parameter for model selection. Subclasses should populate the 'choices'.
        self.add_parameter(
            Parameter(
                name="model",
                input_types=["str"],
                type="str",
                output_type="str",
                default_value="",
                tooltip="Select the model you want to use from the available options.",
                traits={Options(choices=[])},
            )
        )

        # Parameter controlling randomness/creativity in generation.
        self.add_parameter(
            Parameter(
                name="temperature",
                input_types=["float"],
                type="float",
                output_type="float",
                default_value=0.1,
                tooltip="Temperature for creativity. Higher values will be more creative.",
                ui_options={"slider": {"min_val": 0.0, "max_val": 1.0}, "step": 0.01},
            )
        )
        # Parameter for retry logic upon driver failure.
        self.add_parameter(
            Parameter(
                name="max_attempts_on_fail",
                input_types=["int"],
                type="int",
                output_type="int",
                default_value=2,
                tooltip="Maximum attempts on failure",
                ui_options={"slider": {"min_val": 1, "max_val": 100}},
            )
        )

        # Parameter for reproducibility (if supported by the driver).
        self.add_parameter(
            Parameter(
                name="seed",
                input_types=["int"],
                type="int",
                output_type="int",
                default_value=10342349342,
                tooltip="Seed for random number generation",
            )
        )

        # Parameter for nucleus sampling (alternative/complement to temperature).
        self.add_parameter(
            Parameter(
                name="min_p",
                input_types=["float"],
                type="float",
                output_type="float",
                default_value=0.1,
                tooltip="Minimum probability for sampling. Lower values will be more random.",
                ui_options={"slider": {"min_val": 0.0, "max_val": 1.0}, "step": 0.01},
            )
        )

        # Parameter for limiting the sampling pool (top-k sampling).
        self.add_parameter(
            Parameter(
                name="top_k",
                input_types=["int"],
                type="int",
                output_type="int",
                default_value=50,
                tooltip="Limits the number of tokens considered for each step of the generation. Prevents the model from focusing too narrowly on the top choices.",
            )
        )

        # Parameter to enable/disable model-specific tool use capabilities.
        self.add_parameter(
            Parameter(
                name="use_native_tools",
                input_types=["bool"],
                type="bool",
                output_type="bool",
                default_value=True,
                tooltip="Use native tools for the LLM.",
            )
        )

        # Parameter to limit the length of the generated response.
        self.add_parameter(
            Parameter(
                name="max_tokens",
                input_types=["int"],
                type="int",
                output_type="int",
                default_value=-1,
                tooltip="Maximum tokens to generate. If <=0, it will use the default based on the tokenizer.",
            )
        )

        # Parameter to enable/disable streaming output from the driver.
        self.add_parameter(
            Parameter(
                name="stream",
                input_types=["bool"],
                type="bool",
                output_type="bool",
                default_value=True,
                tooltip="",
            )
        )

    def process(self) -> None:
        """Processes the node to generate the output prompt model configuration.

        In this base class, this method creates a `DummyPromptDriver` instance
        and assigns it to the 'prompt model config' output parameter. This primarily
        serves to define the output socket type for the node graph and provide a
        non-functional default if the node is used directly (which is discouraged).

        Subclasses MUST override this method to:
        1. Retrieve parameter values using `self.get_parameter_value(<param_name>)`.
        2. Instantiate their specific Griptape prompt driver (e.g., `OpenAiChatPromptDriver`)
           using these retrieved values.
        3. Assign the created driver instance to the 'prompt model config' output parameter:
           `self.parameter_output_values["prompt model config"] = specific_driver`
        """
        # Create a placeholder driver for the base class output type definition.
        # This ensures the output socket has the correct type ('Prompt Model Config')
        # even though this base node doesn't configure a real driver.
        driver = DummyPromptDriver()

        # Set the output parameter with the placeholder driver.
        self.parameter_output_values["prompt model config"] = driver
