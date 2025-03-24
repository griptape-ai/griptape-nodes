from griptape.drivers.audio_transcription.openai import OpenAiAudioTranscriptionDriver
from griptape.tools.audio_transcription.tool import AudioTranscriptionTool

from griptape_nodes_library.tools.tools import gnBaseTool


class gnAudioTranscriptionTool(gnBaseTool):
    def process(self) -> None:
        self.parameter_values.get("off_prompt", True)
        driver = self.parameter_values.get("driver", None)

        # Set default driver if none provided
        if not driver:
            driver = OpenAiAudioTranscriptionDriver(model="whisper-1")

        # Create the tool with parameters
        tool = AudioTranscriptionTool(audio_transcription_driver=driver)

        # Set the output
        self.parameter_output_values["tool"] = tool
