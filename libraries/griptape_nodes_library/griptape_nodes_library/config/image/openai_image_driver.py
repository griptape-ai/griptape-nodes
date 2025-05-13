from typing import Any

from griptape.drivers.image_generation.openai import (
    OpenAiImageGenerationDriver as GtOpenAiImageGenerationDriver,
)

from griptape_nodes.exe_types.core_types import Parameter
from griptape_nodes.traits.options import Options
from griptape_nodes.traits.slider import Slider
from griptape_nodes_library.config.image.base_image_driver import BaseImageDriver

# --- Constants ---

SERVICE = "OpenAI"
API_KEY_URL = "https://platform.openai.com/api-keys"
API_KEY_ENV_VAR = "OPENAI_API_KEY"
MODEL_CHOICES = ["gpt-image-1", "dall-e-3", "dall-e-2"]

# GPT_IMAGE_SPECIFICS
GPT_IMAGE_SIZES = ["1024x1024", "1536x1024", "1024x1536"]
GPT_IMAGE_QUALITY = ["low", "medium", "high"]
BACKGROUND_CHOICES = ["opaque", "transparent"]
MODERATION_CHOICES = ["low", "auto"]

# DALL_E_3_SPECIFICS
DALL_E_3_SIZES = ["1024x1024", "1024x1792", "1792x1024"]
DALL_E_3_QUALITY = ["hd", "standard"]

# DALL_E_2_SPECIFICS
DALL_E_2_SIZES = ["256x256", "512x512", "1024x1024"]

# DEFAULTS
DEFAULT_MODEL = MODEL_CHOICES[0]
DEFAULT_GPT_IMAGE_QUALITY = GPT_IMAGE_QUALITY[0]
DEFAULT_SIZE = GPT_IMAGE_SIZES[0]
DEFAULT_BACKGROUND = BACKGROUND_CHOICES[0]
DEFAULT_MODERATION = MODERATION_CHOICES[0]


class OpenAiImage(BaseImageDriver):
    """Node for OpenAI Image Generation Driver.

    This node creates an OpenAI image generation driver and outputs its configuration.
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)

        # --- Customize Inherited Parameters ---

        # Add additional parameters specific to OpenAI
        self.add_parameter(
            Parameter(
                name="style",
                type="str",
                default_value="vivid",
                tooltip="Select the style for image generation.",
                traits={Options(choices=["vivid", "natural"])},
            )
        )

        self.add_parameter(
            Parameter(
                name="quality",
                type="str",
                default_value=DEFAULT_GPT_IMAGE_QUALITY,
                tooltip="Select the quality for image generation.",
                traits={Options(choices=GPT_IMAGE_QUALITY)},
            )
        )

        self.add_parameter(
            Parameter(
                name="background",
                type="str",
                default_value=DEFAULT_BACKGROUND,
                tooltip="Select the background for image generation.",
                traits={Options(choices=BACKGROUND_CHOICES)},
            )
        )

        self.add_parameter(
            Parameter(
                name="moderation",
                type="str",
                default_value=DEFAULT_MODERATION,
                tooltip="Select the moderation level for image generation.",
                traits={Options(choices=MODERATION_CHOICES)},
            )
        )

        self.add_parameter(
            Parameter(
                name="output_format",
                type="str",
                default_value="png",
                tooltip="Select the output format for image generation.",
                traits={Options(choices=["png", "jpeg"])},
            )
        )
        self.add_parameter(
            Parameter(
                name="output_compression",
                type="int",
                default_value=80,
                tooltip="Select the output compression for image generation.",
                traits={Slider(min_val=0, max_val=100)},
                ui_options={"step": 10, "hide": True},
            )
        )

        # Update the parameters  for OpenAI specifics.
        self._update_option_choices(param="model", choices=MODEL_CHOICES, default=DEFAULT_MODEL)
        self._update_option_choices(param="image_size", choices=GPT_IMAGE_SIZES, default=DEFAULT_SIZE)

    def _set_parameter_visibility(self, names: str | list[str], *, visible: bool) -> None:
        """Sets the visibility of one or more parameters.

        Args:
            names (str or list of str): The parameter name(s) to update.
            visible (bool): Whether to show (True) or hide (False) the parameters.
        """
        if isinstance(names, str):
            names = [names]

        for name in names:
            parameter = self.get_parameter_by_name(name)
            if parameter is not None:
                parameter._ui_options["hide"] = not visible

    def hide_parameter_by_name(self, names: str | list[str]) -> None:
        """Hides one or more parameters by name."""
        self._set_parameter_visibility(names, visible=False)

    def show_parameter_by_name(self, names: str | list[str]) -> None:
        """Shows one or more parameters by name."""
        self._set_parameter_visibility(names, visible=True)

    def after_value_set(self, parameter: Parameter, value: Any, modified_parameters_set: set[str]) -> None:
        """Certain options are only available for certain models."""
        if parameter.name == "output_format":
            if value == "jpeg":
                self.show_parameter_by_name("output_compression")
            else:
                self.hide_parameter_by_name("output_compression")
            modified_parameters_set.add("output_compression")

        if parameter.name == "model":
            # If the model is gpt-image-1, update the size options accordingly
            if value == "gpt-image-1":
                self._update_option_choices(param="image_size", choices=GPT_IMAGE_SIZES, default=GPT_IMAGE_SIZES[0])
                self._update_option_choices(param="quality", choices=GPT_IMAGE_QUALITY, default=GPT_IMAGE_QUALITY[0])
                modified_parameters_set.add("image_size")

                # show gpt-image-1 specific parameters
                param_list = ["style", "quality", "background", "moderation", "output_format"]
                self.show_parameter_by_name(param_list)
                modified_parameters_set.update(param_list)

                if self.get_parameter_value("output_format") == "jpeg":
                    self.show_parameter_by_name("output_compression")
                else:
                    self.hide_parameter_by_name("output_compression")
                modified_parameters_set.add("output_compression")
            else:
                param_list = ["style", "background", "moderation", "output_compression", "output_format"]
                self.hide_parameter_by_name(param_list)

                if value == "dall-e-3":
                    self.show_parameter_by_name("quality")
                    self._update_option_choices(param="image_size", choices=DALL_E_3_SIZES, default=DALL_E_3_SIZES[0])
                    self._update_option_choices(param="quality", choices=DALL_E_3_QUALITY, default=DALL_E_3_QUALITY[0])

                # If the model is DALL-E 2, update the size options accordingly
                if value == "dall-e-2":
                    self._update_option_choices(param="image_size", choices=DALL_E_2_SIZES, default=DALL_E_2_SIZES[0])
                    self.hide_parameter_by_name("quality")

                param_list.extend(["image_size", "quality"])
                modified_parameters_set.update(param_list)

        return super().after_value_set(parameter, value, modified_parameters_set)

    def process(self) -> None:
        # Get the parameters from the node
        params = self.parameter_values

        # --- Get Common Driver Arguments ---
        # Use the helper method from BaseImageDriver to get common driver arguments
        common_args = self._get_common_driver_args(params)

        # --- Prepare Griptape Cloud Specific Arguments ---
        specific_args = {}

        # Retrieve the mandatory API key.
        specific_args["api_key"] = self.get_config_value(service=SERVICE, value=API_KEY_ENV_VAR)

        model = self.get_parameter_value("model")
        specific_args["model"] = model

        if model == "dall-e-3":
            specific_args["style"] = self.get_parameter_value("style")
            specific_args["quality"] = self.get_parameter_value("quality")
        elif model == "gpt-image-1":
            specific_args["style"] = self.get_parameter_value("style")
            specific_args["quality"] = self.get_parameter_value("quality")
            specific_args["background"] = self.get_parameter_value("background")
            specific_args["moderation"] = self.get_parameter_value("moderation")
            specific_args["output_format"] = self.get_parameter_value("output_format")
            if specific_args["output_format"] == "jpeg":
                specific_args["output_compression"] = self.get_parameter_value("output_compression")

        all_kwargs = {**common_args, **specific_args}

        self.parameter_output_values["image_model_config"] = GtOpenAiImageGenerationDriver(**all_kwargs)

    def validate_before_workflow_run(self) -> list[Exception] | None:
        """Validates that the Griptape Cloud API key is configured correctly.

        Calls the base class helper `_validate_api_key` with Griptape-specific
        configuration details.
        """
        return self._validate_api_key(
            service_name=SERVICE,
            api_key_env_var=API_KEY_ENV_VAR,
            api_key_url=API_KEY_URL,
        )
