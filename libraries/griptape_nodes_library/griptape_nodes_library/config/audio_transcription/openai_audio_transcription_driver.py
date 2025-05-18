from griptape.drivers.audio_transcription.openai import (
    OpenAiAudioTranscriptionDriver as GtOpenAiAudioTranscriptionDriver,
)

from griptape_nodes.exe_types.core_types import Parameter
from griptape_nodes_library.config.audio_transcription.base_audio_transcription_driver import BaseAudioTranscription

# --- Constants ---

SERVICE = "OpenAI"
API_KEY_URL = "https://platform.openai.com/api-keys"
API_KEY_ENV_VAR = "OPENAI_API_KEY"
MODEL_CHOICES = ["gpt-4o-mini-transcribe", "gpt-4o-transcribe", "whisper-1"]
DEFAULT_MODEL = MODEL_CHOICES[0]


class OpenAiAudioTranscription(BaseAudioTranscription):
    """Node for OpenAI Image Generation Driver.

    This node creates an OpenAI image generation driver and outputs its configuration.
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        # Parameter for user messages.
        self.add_parameter(
            Parameter(
                name="message",
                type="str",
                default_value="⚠️ This node requires an API key to function.",
                tooltip="",
                allowed_modes={},  # type: ignore  # noqa: PGH003
                ui_options={"is_full_width": True, "multiline": True, "hide": True},
            )
        )
        self.add_parameter(
            Parameter(
                name="testy",
                type="float",
                default_value=23423423443.2342342,
                tooltip="",
                allowed_modes={},  # type: ignore  # noqa: PGH003
            )
        )
        # Update the parameters  for OpenAI specifics.
        self._update_option_choices(param="model", choices=MODEL_CHOICES, default=DEFAULT_MODEL)
        self.clear_api_key_check(service=SERVICE, api_key_env_var=API_KEY_ENV_VAR)

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

        all_kwargs = {**common_args, **specific_args}

        self.parameter_output_values["audio_transcription_model_config"] = GtOpenAiAudioTranscriptionDriver(
            **all_kwargs
        )

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
