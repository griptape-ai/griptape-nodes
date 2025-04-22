from griptape.drivers.image_generation.griptape_cloud import GriptapeCloudImageGenerationDriver

from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.retained_mode.griptape_nodes import logger
from griptape_nodes.traits.options import Options
from griptape_nodes_library.drivers.base_driver import BaseDriver

DRIVER_DICT = {
    "config": {
        "service_key_field": [("Griptape", "GT_CLOUD_API_KEY", "api_key")],
        "driver": GriptapeCloudImageGenerationDriver,
    },
    "models": {
        "dall-e-3": {
            "params": {
                "style": {"hide": True, "options": ["natural", "vivid"], "default": "natural"},
                "quality": {"hide": True, "options": ["standard", "hd"], "default": "standard"},
                "size": {"options": ["1024x1024", "1024x1792", "1792x1024"], "default": "1024x1024"},
            }
        },
        "dall-e-2": {
            "params": {
                "style": {"hide": False, "options": ["natural", "vivid"], "default": "natural"},
                "quality": {"hide": False, "options": ["standard", "hd"], "default": "standard"},
                "size": {"options": ["256x256", "512x512", "1024x1024"], "default": "1024x1024"},
            }
        },
    },
}


class BaseImageDriver(BaseDriver):
    """Node for OpenAI Image Generation Driver.

    This node creates an OpenAI image generation driver and outputs its configuration.
    """

    def __init__(self, driver_dict=None, **kwargs) -> None:
        super().__init__(**kwargs)
        self.driver_dict = DRIVER_DICT | (driver_dict or {})
        self.setup()

    def setup(self) -> None:
        # Extract configuration values
        self.config = self.driver_dict.get("config", {})
        self.service_key_mappings = self.config.get("service_key_field", [])
        self.driver = self.config.get("driver")

        # Hard assumtion that first entry is default (yes, this is reliably ordered since 3.7)
        self.model_options = list(self.driver_dict.get("models", {}).keys())
        self.model_default = self.model_options[0]

        model_params = self.driver_dict["models"][self.model_default]["params"]
        self.style_options = model_params["style"]["options"]
        self.style_default = model_params["style"]["default"]
        self.quality_options = model_params["quality"]["options"]
        self.quality_default = model_params["quality"]["default"]
        self.size_options = model_params["size"]["options"]
        self.size_default = model_params["size"]["default"]

        self.add_parameter(
            Parameter(
                name="model",
                type="str",
                default_value=self.model_default,
                tooltip="Choose a model",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                traits={Options(choices=self.model_options)},
            )
        )

        self.add_parameter(
            Parameter(
                name="quality",
                type="str",
                default_value=self.quality_default,
                tooltip="Image Quality",
                traits={Options(choices=self.quality_options)},
            )
        )

        self.add_parameter(
            Parameter(
                name="style",
                type="str",
                default_value=self.style_default,
                tooltip="Image Style",
                traits={Options(choices=self.style_options)},
            )
        )

        self.add_parameter(
            Parameter(
                name="size",
                type="str",
                default_value=self.size_default,
                tooltip="Image Size",
                traits={Options(choices=self.size_options)},
            )
        )

        driver_parameter = self.get_parameter_by_name("driver")
        if driver_parameter is not None:
            driver_parameter.name = "image_generation_driver"
            driver_parameter.type = "Image Generation Driver"
            driver_parameter.output_type = "Image Generation Driver"

        # Apply initial model configuration
        self.update_parameters_from_model(self.model_default)

    def update_parameters_from_model(self, model: str) -> None:
        """Update all parameters based on the model configuration dictionary.

        Args:
            model: The model name to use for configuration
        """
        # Get model configuration
        model_config = self.driver_dict["models"].get(model, {}).get("params", {})

        # Update each parameter based on the configuration
        for param_name, config in model_config.items():
            param = self.get_parameter_by_name(param_name)
            if not param:
                continue

            # Process options first, collecting all UI options to apply at once
            ui_options = {}

            # Handle options/choices for traits
            if "options" in config and param.children:
                # Remove existing Options trait
                param.remove_trait(param.children[0])
                # Add new Options trait with updated choices
                param.add_trait(Options(choices=config["options"]))
                ui_options["options"] = config["options"]

            # Add hide setting to ui_options
            if "hide" in config:
                ui_options["hide"] = config["hide"]

            # Apply all UI options at once
            param.ui_options = ui_options

            # Update default value if specified
            if "default" in config:
                param.default_value = config["default"]

            # Update tooltip if specified
            if "tooltip" in config:
                param.tooltip = config["tooltip"]

    def after_value_set(self, parameter: Parameter, value=None, modified_parameters_set=None) -> None:  # noqa: ARG002
        """Update dependent parameters when a parameter value changes."""
        if parameter.name == "model":
            # Update all parameters based on the selected model
            self.update_parameters_from_model(value)

    def process(self) -> None:
        """Process the driver configuration and create the driver instance."""
        params = self.parameter_values
        current_model = params.get("model", self.model_default)
        model_params = self.driver_dict["models"][current_model]["params"]

        # Start with config entries as kwargs (excluding special keys)
        kwargs = {key: value for key, value in self.config.items() if key not in ["driver", "service_key_field"]}

        # Add credentials from the service_key_field mappings
        for service, config_key, param_name in self.service_key_mappings:
            kwargs[param_name] = self.get_config_value(service=service, value=config_key)

        # Add model-specific parameters
        kwargs["model"] = current_model
        kwargs["image_size"] = params.get("size", model_params["size"]["default"])

        # Add optional parameters if not hidden by the model
        if not model_params.get("style", {}).get("hide", False):
            kwargs["style"] = params.get("style", model_params["style"]["default"])

        if not model_params.get("quality", {}).get("hide", False):
            kwargs["quality"] = params.get("quality", model_params["quality"]["default"])

        logger.info(f"ImageDriver final kwargs = {kwargs}")
        self.parameter_output_values["image_generation_driver"] = self.driver(**kwargs)
