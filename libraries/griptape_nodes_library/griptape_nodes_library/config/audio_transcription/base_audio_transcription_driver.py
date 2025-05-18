from griptape.drivers.audio_transcription.dummy import DummyAudioTranscriptionDriver

from griptape_nodes.exe_types.core_types import Parameter
from griptape_nodes.traits.options import Options
from griptape_nodes_library.config.base_driver import BaseDriver


class BaseAudioTranscription(BaseDriver):
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)

        # Update the inherited driver parameter to specify it's for image generation
        driver_parameter = self.get_parameter_by_name("driver")
        if driver_parameter is not None:
            driver_parameter.name = "audio_transcription_model_config"
            driver_parameter.output_type = "Audio Transcription Model Config"
            driver_parameter._ui_options = {"display_name": "audio transcription model config"}

        # --- Common Prompt Driver Parameters ---
        # These parameters represent settings frequently used by Audio Transcription drivers.
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

    def process(self) -> None:
        # Create a placeholder driver for the base class output type definition.
        # This ensures the output socket has the correct type ('Image Generation Driver')
        # even though this base node doesn't configure a real driver.
        driver = DummyAudioTranscriptionDriver()

        # Set the output parameter with the placeholder driver.
        self.parameter_output_values["audio_transcription_model_config"] = driver
