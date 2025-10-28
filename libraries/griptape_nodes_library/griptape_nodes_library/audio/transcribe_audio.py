from griptape.artifacts.audio_url_artifact import AudioUrlArtifact
from griptape.drivers.audio_transcription.base_audio_transcription_driver import BaseAudioTranscriptionDriver
from griptape.drivers.audio_transcription.openai import OpenAiAudioTranscriptionDriver
from griptape.loaders import AudioLoader
from griptape.structures import Structure
from griptape.tasks import AudioTranscriptionTask

from griptape_nodes.exe_types.core_types import Parameter, ParameterMessage, ParameterMode
from griptape_nodes.exe_types.node_types import AsyncResult, BaseNode, ControlNode
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
from griptape_nodes.traits.options import Options
from griptape_nodes_library.agents.griptape_nodes_agent import GriptapeNodesAgent as GtAgent
from griptape_nodes_library.utils.audio_utils import dict_to_audio_url_artifact
from griptape_nodes_library.utils.error_utils import try_throw_error

SERVICE = "OpenAI"
API_KEY_URL = "https://platform.openai.com/api-keys"
API_KEY_ENV_VAR = "OPENAI_API_KEY"
MODEL_CHOICES = ["gpt-4o-mini-transcribe", "gpt-4o-transcribe", "whisper-1"]
DEFAULT_MODEL = MODEL_CHOICES[0]


class TranscribeAudio(ControlNode):
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)

        self.add_parameter(
            Parameter(
                name="agent",
                type="Agent",
                output_type="Agent",
                tooltip="An agent that can be used to transcribe the audio.",
                default_value=None,
            )
        )
        self.add_parameter(
            Parameter(
                name="model",
                type="str",
                output_type="str",
                default_value=DEFAULT_MODEL,
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                tooltip="Choose a model, or connect an AudioTranscription Model Configuration or an Agent",
                traits={Options(choices=MODEL_CHOICES)},
                ui_options={"display_name": "audio transcription model"},
            )
        )
        self.add_parameter(
            Parameter(
                name="audio",
                input_types=["AudioArtifact", "AudioUrlArtifact"],
                type="AudioArtifact",
                output_type="AudioUrlArtifact",
                default_value=None,
                ui_options={"clickable_file_browser": True, "expander": True},
                tooltip="Audio to transcribe",
            )
        )

        self.add_parameter(
            Parameter(
                name="output",
                output_type="str",
                type="str",
                tooltip="None",
                default_value=None,
                allowed_modes={ParameterMode.OUTPUT},
                ui_options={
                    "placeholder_text": "The description of the image",
                    "multiline": True,
                    "display_name": "output",
                },
            )
        )

        pm = ParameterMessage(
            name="openai_api_key_message",
            title="OPENAI_API_KEY Required",
            variant="warning",
            value="This node requires an OPENAI_API_KEY.\n\nPlease get an API key and set the key in your Griptape Settings.",
            button_link=str(API_KEY_URL),
            button_text="Get API Key",
        )
        self.add_node_element(pm)
        self.clear_api_key_check()

    def clear_api_key_check(self) -> bool:
        # Check to see if the API key is set, if not we'll show the message
        # TODO(jason): Implement a better way to check for the API key after https://github.com/griptape-ai/griptape-nodes/issues/1309
        message_name = "openai_api_key_message"
        api_key = GriptapeNodes.SecretsManager().get_secret(API_KEY_ENV_VAR)
        if api_key:
            self.hide_message_by_name(message_name)
            return True
        self.show_message_by_name(message_name)
        return False

    def validate_before_workflow_run(self) -> list[Exception] | None:
        # TODO: https://github.com/griptape-ai/griptape-nodes/issues/871
        exceptions = []
        api_key = GriptapeNodes.SecretsManager().get_secret(API_KEY_ENV_VAR)
        self.clear_api_key_check()
        if not api_key:
            msg = f"{API_KEY_ENV_VAR} is not defined"
            exceptions.append(KeyError(msg))
            return exceptions
        return exceptions if exceptions else None

    def after_incoming_connection(
        self,
        source_node: BaseNode,
        source_parameter: Parameter,
        target_parameter: Parameter,
    ) -> None:
        if target_parameter.name == "agent":
            self.hide_parameter_by_name("model")

        if target_parameter.name == "model" and source_parameter.name == "text_to_speech_model_config":
            # Check and see if the incoming connection is from a prompt model config or an agent.
            target_parameter.type = source_parameter.type
            target_parameter.remove_trait(trait_type=target_parameter.find_elements_by_type(Options)[0])
            ui_options = target_parameter.ui_options
            ui_options["display_name"] = source_parameter.ui_options.get("display_name", source_parameter.name)
            target_parameter.ui_options = ui_options

        return super().after_incoming_connection(source_node, source_parameter, target_parameter)

    def after_incoming_connection_removed(
        self,
        source_node: BaseNode,
        source_parameter: Parameter,
        target_parameter: Parameter,
    ) -> None:
        if target_parameter.name == "agent":
            self.show_parameter_by_name("model")
        # Check and see if the incoming connection is from an agent. If so, we'll hide the model parameter
        if target_parameter.name == "model":
            target_parameter.type = "str"
            target_parameter.add_trait(Options(choices=MODEL_CHOICES))
            target_parameter.set_default_value(DEFAULT_MODEL)
            ui_options = target_parameter.ui_options
            ui_options["display_name"] = "text to speech model"
            target_parameter.ui_options = ui_options
            self.set_parameter_value("model", DEFAULT_MODEL)

        return super().after_incoming_connection_removed(source_node, source_parameter, target_parameter)

    def process(self) -> AsyncResult[Structure]:
        # Get the parameters from the node
        model_input = self.get_parameter_value("model")
        agent = None

        # If an agent is provided, we'll use and ensure it's using a PromptTask
        # If a prompt_driver is provided, we'll use that
        # If neither are provided, we'll create a new one with the selected model.
        # Otherwise, we'll just use the default model
        agent = self.get_parameter_value("agent")
        if isinstance(agent, dict):
            agent = GtAgent().from_dict(agent)
        else:
            agent = GtAgent()

        #
        # Get the audio_transcription_driver
        if isinstance(model_input, BaseAudioTranscriptionDriver):
            driver = model_input
        else:
            if model_input not in MODEL_CHOICES:
                model_input = DEFAULT_MODEL
            driver = OpenAiAudioTranscriptionDriver(
                model=model_input, api_key=GriptapeNodes.SecretsManager().get_secret(API_KEY_ENV_VAR)
            )
        audio = self.get_parameter_value("audio")
        if audio is None:
            self.parameter_output_values["output"] = "No audio provided"
            return
        if isinstance(audio, dict):
            audio_artifact = dict_to_audio_url_artifact(audio)
        else:
            audio_artifact = audio

        if isinstance(audio_artifact, AudioUrlArtifact):
            audio_artifact = AudioLoader().parse(audio_artifact.to_bytes())
        task = AudioTranscriptionTask(audio_artifact, audio_transcription_driver=driver)

        # Set the new audio transcription task
        agent.swap_task(task)

        # Run the agent
        yield lambda: agent.run([task])
        self.parameter_output_values["output"] = agent.output.value
        try_throw_error(agent.output)

        agent.insert_false_memory(
            prompt="I'm passing you some audio to transcribe. /link/to/audiofile",
            output=f"<Thought>I temporarily used an Audio Transcription tool</Thought>{agent.output.value}",
            tool="AudioTranscriptionTool",
        )

        # Reset the agent
        agent.restore_task()

        # Set the output value for the agent
        self.parameter_output_values["agent"] = agent.to_dict()
