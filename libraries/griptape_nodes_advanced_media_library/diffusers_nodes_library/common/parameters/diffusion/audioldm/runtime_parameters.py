import logging
from typing import Any

from artifact_utils.audio_utils import dict_to_audio_url_artifact  # type: ignore[reportMissingImports]
from diffusers.pipelines.pipeline_utils import DiffusionPipeline  # type: ignore[reportMissingImports]

from diffusers_nodes_library.common.parameters.diffusion.runtime_parameters import (
    DiffusionPipelineRuntimeParameters,
)
from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import BaseNode
from griptape_nodes.exe_types.param_components.huggingface.huggingface_repo_parameter import (
    HuggingFaceRepoParameter,  # type: ignore[reportMissingImports]
)

logger = logging.getLogger("diffusers_nodes_library")


class AudioldmPipelineRuntimeParameters(DiffusionPipelineRuntimeParameters):
    def __init__(self, node: BaseNode, *, list_all_models: bool = False):
        super().__init__(node)
        self._huggingface_repo_parameter = HuggingFaceRepoParameter(
            node,
            repo_ids=[
                "cvssp/audioldm-s-full-v2",
                "cvssp/audioldm-s-full",
                "cvssp/audioldm-m-full",
                "cvssp/audioldm-l-full",
            ],
            list_all_models=list_all_models,
        )

    def _add_input_parameters(self) -> None:
        self._huggingface_repo_parameter.add_input_parameters()
        self._node.add_parameter(
            Parameter(
                name="prompt",
                default_value="",
                type="str",
                tooltip="Text prompt describing the audio to generate",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="negative_prompt",
                default_value="",
                type="str",
                tooltip="Optional negative prompt to guide what not to generate",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="audio_length_in_s",
                default_value=5.0,
                type="float",
                tooltip="Length of the generated audio in seconds",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="guidance_scale",
                default_value=2.5,
                type="float",
                tooltip="Higher values follow the text prompt more closely",
            )
        )

    def add_output_parameters(self) -> None:
        self._node.add_parameter(
            Parameter(
                name="output_audio",
                output_type="AudioUrlArtifact",
                tooltip="The generated audio",
                allowed_modes={ParameterMode.OUTPUT},
            )
        )

    def _remove_input_parameters(self) -> None:
        self._huggingface_repo_parameter.remove_input_parameters()
        self._node.remove_parameter_element_by_name("prompt")
        self._node.remove_parameter_element_by_name("negative_prompt")
        self._node.remove_parameter_element_by_name("audio_length_in_s")
        self._node.remove_parameter_element_by_name("guidance_scale")

    def remove_output_parameters(self) -> None:
        self._node.remove_parameter_element_by_name("output_audio")

    def validate_before_node_run(self) -> list[Exception] | None:
        errors = self._huggingface_repo_parameter.validate_before_node_run()
        return errors or None

    def after_value_set(self, parameter: Parameter, value: Any) -> None:
        super().after_value_set(parameter, value)

    def preprocess(self) -> None:
        super().preprocess()

    def get_repo_revision(self) -> tuple[str, str]:
        return self._huggingface_repo_parameter.get_repo_revision()

    def get_prompt(self) -> str:
        return self._node.get_parameter_value("prompt")

    def get_negative_prompt(self) -> str:
        return self._node.get_parameter_value("negative_prompt")

    def get_audio_length_in_s(self) -> float:
        return float(self._node.get_parameter_value("audio_length_in_s"))

    def get_guidance_scale(self) -> float:
        return float(self._node.get_parameter_value("guidance_scale"))

    def _get_pipe_kwargs(self) -> dict:
        kwargs = {
            "prompt": self.get_prompt(),
            "audio_length_in_s": self.get_audio_length_in_s(),
            "guidance_scale": self.get_guidance_scale(),
        }

        negative_prompt = self.get_negative_prompt()
        if negative_prompt:
            kwargs["negative_prompt"] = negative_prompt

        return kwargs

    def process_pipeline(self, pipe: DiffusionPipeline) -> None:
        """Override to handle audio generation instead of image generation."""
        num_inference_steps = self.get_num_inference_steps()

        def callback_on_step_end(
            pipe: DiffusionPipeline,
            i: int,
            _t: Any,
            callback_kwargs: dict,
        ) -> dict:
            # Check for cancellation request
            if self._node.is_cancellation_requested:
                pipe._interrupt = True
                self._node.log_params.append_to_logs("Cancellation requested, stopping after this step...\n")  # type: ignore[reportAttributeAccessIssue]
                return callback_kwargs

            if i < num_inference_steps - 1:
                self.publish_output_audio_preview(pipe, callback_kwargs["latents"])
                self._node.log_params.append_to_logs(f"Starting inference step {i + 2} of {num_inference_steps}...\n")  # type: ignore[reportAttributeAccessIssue]
                self._node.progress_bar_component.increment()  # type: ignore[reportAttributeAccessIssue]
            return {}

        self._node.log_params.append_to_logs(f"Starting inference step 1 of {num_inference_steps}...\n")  # type: ignore[reportAttributeAccessIssue]
        self._node.progress_bar_component.initialize(num_inference_steps)  # type: ignore[reportAttributeAccessIssue]
        self._node.progress_bar_component.increment()  # type: ignore[reportAttributeAccessIssue]
        result = pipe(  # type: ignore[reportCallIssue]
            **self.get_pipe_kwargs(),
            callback_on_step_end=callback_on_step_end,
        )

        # AudioLDM returns audio data directly
        audio_data = result.audios[0] if hasattr(result, "audios") else result
        self.publish_output_audio(audio_data)
        self._node.log_params.append_to_logs("Done.\n")  # type: ignore[reportAttributeAccessIssue]

    def _audio_data_to_artifact(self, audio_data: Any) -> Any:
        """Convert audio data to audio artifact."""
        import base64
        import io

        import numpy as np
        import scipy.io.wavfile  # type: ignore[reportMissingImports]

        # Convert audio array to WAV format
        buffer = io.BytesIO()
        # AudioLDM typically outputs at 16kHz
        sample_rate = 16000

        # Ensure audio is in the right format for scipy
        if isinstance(audio_data, list):
            audio_data = audio_data[0]  # Take first audio if batch

        # Normalize and convert to int16
        audio_data = np.array(audio_data)
        if audio_data.dtype != np.int16:
            # Normalize to [-1, 1] then scale to int16 range
            audio_data = audio_data / np.max(np.abs(audio_data))
            audio_data = (audio_data * 32767).astype(np.int16)

        scipy.io.wavfile.write(buffer, sample_rate, audio_data)
        buffer.seek(0)

        # Convert to base64
        audio_bytes = buffer.getvalue()
        audio_b64 = base64.b64encode(audio_bytes).decode()

        # Create audio artifact
        audio_dict = {"type": "audio/wav", "value": f"data:audio/wav;base64,{audio_b64}"}
        return dict_to_audio_url_artifact(audio_dict, "wav")

    def latents_to_audio(self, pipe: Any, latents: Any) -> Any:
        """Convert latents to audio using AudioLDM pipeline VAE and vocoder."""
        try:
            # Decode latents to mel spectrogram using VAE
            latents = 1 / pipe.vae.config.scaling_factor * latents
            mel_spectrogram = pipe.vae.decode(latents).sample

            # Convert mel spectrogram to waveform using vocoder
            mel_spec_dim_4 = 4
            if mel_spectrogram.dim() == mel_spec_dim_4:
                mel_spectrogram = mel_spectrogram.squeeze(1)

            waveform = pipe.vocoder(mel_spectrogram)
            waveform = waveform.cpu().float()
        except Exception as e:
            logger.warning("Failed to convert latents to audio: %s", e)
            return None
        else:
            return waveform

    def publish_output_audio_preview(self, pipe: Any, latents: Any) -> None:
        """Publish a preview audio from latents during generation."""
        try:
            audio_data = self.latents_to_audio(pipe, latents)
            if audio_data is not None:
                audio_artifact = self._audio_data_to_artifact(audio_data)
                self._node.publish_update_to_parameter("output_audio", audio_artifact)
        except Exception as e:
            logger.warning("Failed to generate audio preview from latents: %s", e)

    def publish_output_audio(self, audio_data: Any) -> None:
        """Publish the final generated audio."""
        audio_artifact = self._audio_data_to_artifact(audio_data)
        self._node.set_parameter_value("output_audio", audio_artifact)
        self._node.parameter_output_values["output_audio"] = audio_artifact
