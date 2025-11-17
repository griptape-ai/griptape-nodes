import logging
from typing import Any

import torch  # type: ignore[reportMissingImports]
from artifact_utils.audio_utils import dict_to_audio_url_artifact  # type: ignore[reportMissingImports]
from diffusers.pipelines.pipeline_utils import DiffusionPipeline  # type: ignore[reportMissingImports]

from diffusers_nodes_library.common.parameters.diffusion.runtime_parameters import (
    DEFAULT_NUM_INFERENCE_STEPS,
    DiffusionPipelineRuntimeParameters,
)
from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import BaseNode

logger = logging.getLogger("diffusers_nodes_library")


class Audioldm2PipelineRuntimeParameters(DiffusionPipelineRuntimeParameters):
    def __init__(self, node: BaseNode):
        super().__init__(node)

    def _add_input_parameters(self) -> None:
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
                default_value=10.0,
                type="float",
                tooltip="Length of the generated audio in seconds",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="guidance_scale",
                default_value=3.5,
                type="float",
                tooltip="Higher values follow the text prompt more closely",
            )
        )

    def add_input_parameters(self) -> None:
        self._add_input_parameters()
        # Add num_inference_steps parameter (no width/height for audio)
        self._node.add_parameter(
            Parameter(
                name="num_inference_steps",
                default_value=DEFAULT_NUM_INFERENCE_STEPS,
                type="int",
                tooltip="Number of denoising steps for generation",
            )
        )
        self._seed_parameter.add_input_parameters()

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
        self._node.remove_parameter_element_by_name("prompt")
        self._node.remove_parameter_element_by_name("negative_prompt")
        self._node.remove_parameter_element_by_name("audio_length_in_s")
        self._node.remove_parameter_element_by_name("guidance_scale")

    def remove_input_parameters(self) -> None:
        # Remove num_inference_steps (no width/height for audio)
        self._node.remove_parameter_element_by_name("num_inference_steps")
        self._seed_parameter.remove_input_parameters()
        self._remove_input_parameters()

    def remove_output_parameters(self) -> None:
        self._node.remove_parameter_element_by_name("output_audio")

    def _get_pipe_kwargs(self) -> dict:
        kwargs = {
            "prompt": self._node.get_parameter_value("prompt"),
            "audio_length_in_s": float(self._node.get_parameter_value("audio_length_in_s")),
            "guidance_scale": float(self._node.get_parameter_value("guidance_scale")),
        }

        negative_prompt = self._node.get_parameter_value("negative_prompt")
        if negative_prompt:
            kwargs["negative_prompt"] = negative_prompt

        return kwargs

    def get_pipe_kwargs(self) -> dict:
        return {
            **self._get_pipe_kwargs(),
            "num_inference_steps": int(self._node.get_parameter_value("num_inference_steps")),
            "generator": torch.Generator().manual_seed(self._seed_parameter.get_seed()),
        }

    def process_pipeline(self, pipe: DiffusionPipeline) -> None:
        num_inference_steps = int(self._node.get_parameter_value("num_inference_steps"))

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
        output_audio = pipe(  # type: ignore[reportCallIssue]
            **self.get_pipe_kwargs(),
            callback_on_step_end=callback_on_step_end,
        ).audios[0]
        self.publish_output_audio(output_audio)
        self._node.log_params.append_to_logs("Done.\n")  # type: ignore[reportAttributeAccessIssue]

    def _audio_data_to_artifact(self, audio_data: Any) -> Any:
        """Convert audio data to audio artifact."""
        import base64
        import io

        import numpy as np
        import scipy.io.wavfile  # type: ignore[reportMissingImports]

        # Convert audio array to WAV format
        buffer = io.BytesIO()
        # AudioLDM2 typically outputs at 16kHz
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
        """Convert latents to audio using AudioLDM2 pipeline VAE and vocoder."""
        try:
            # Decode latents to mel spectrogram using VAE
            latents = 1 / pipe.vae.config.scaling_factor * latents
            mel_spectrogram = pipe.vae.decode(latents).sample

            # Convert mel spectrogram to waveform using vocoder
            audio = pipe.mel_spectrogram_to_waveform(mel_spectrogram)
        except Exception as e:
            logger.warning("Failed to convert latents to audio: %s", e)
            return None
        else:
            return audio

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
        audio_artifact = self._audio_data_to_artifact(audio_data)
        self._node.set_parameter_value("output_audio", audio_artifact)
        self._node.parameter_output_values["output_audio"] = audio_artifact
