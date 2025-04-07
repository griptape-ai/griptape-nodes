from griptape.drivers.prompt.dummy import DummyPromptDriver

from griptape_nodes.exe_types.core_types import Parameter
from griptape_nodes_library.drivers.base_driver import BaseDriverNode


class BasePromptDriverNode(BaseDriverNode):
    """Node for Base Prompt Driver.

    This node creates a base prompt driver and outputs its configuration.
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        driver_parameter = self.get_parameter_by_name("driver")
        if driver_parameter is not None:
            driver_parameter.name = "prompt_driver"
            driver_parameter.output_type = "PromptDriver"

        self.add_parameter(
            Parameter(
                name="model",
                input_types=["str"],
                type="str",
                output_type="str",
                default_value="",
                tooltip="Select the model you want to use from the available options.",
                # traits={Options([])},
            )
        )
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
        self.add_parameter(
            Parameter(
                name="temperature",
                input_types=["float"],
                type="float",
                output_type="float",
                default_value=0.1,
                tooltip="Temperature for sampling",
                ui_options={"slider": {"min_val": 0.0, "max_val": 1.0}, "step": 0.01},
            )
        )
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
        # Create the driver
        driver = DummyPromptDriver()

        # Set the output
        self.parameter_output_values["prompt_driver"] = driver
