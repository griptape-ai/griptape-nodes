import logging
from typing import Any

from artifact_utils.audio_utils import dict_to_audio_url_artifact  # type: ignore[reportMissingImports]

from diffusers_nodes_library.common.parameters.huggingface_repo_parameter import (
    HuggingFaceRepoParameter,  # type: ignore[reportMissingImports]
)
from diffusers_nodes_library.common.parameters.seed_parameter import SeedParameter  # type: ignore[reportMissingImports]
from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import BaseNode

logger = logging.getLogger("diffusers_nodes_library")


class AudioldmPipelineParameters:
    def __init__(self, node: BaseNode):
        self._node = node
        self._huggingface_repo_parameter = HuggingFaceRepoParameter(
            node,
            repo_ids=[
                "cvssp/audioldm-s-full-v2",
                "cvssp/audioldm-s-full",
                "cvssp/audioldm-m-full",
                "cvssp/audioldm-l-full",
            ],
        )
        self._seed_parameter = SeedParameter(node)

    def add_input_parameters(self) -> None:
        self._huggingface_repo_parameter.add_input_parameters()
        self._node.add_parameter(
            Parameter(
                name="prompt",
                default_value="",
                input_types=["str"],
                type="str",
                tooltip="Text prompt describing the audio to generate",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="negative_prompt",
                default_value="",
                input_types=["str"],
                type="str",
                tooltip="Optional negative prompt to guide what not to generate",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="audio_length_in_s",
                default_value=5.0,
                input_types=["float"],
                type="float",
                tooltip="Length of the generated audio in seconds",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="num_inference_steps",
                default_value=10,
                input_types=["int"],
                type="int",
                tooltip="Number of denoising steps for generation",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="guidance_scale",
                default_value=2.5,
                input_types=["float"],
                type="float",
                tooltip="Higher values follow the text prompt more closely",
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

    def validate_before_node_run(self) -> list[Exception] | None:
        errors = self._huggingface_repo_parameter.validate_before_node_run()
        return errors or None

    def after_value_set(self, parameter: Parameter, value: Any) -> None:
        self._seed_parameter.after_value_set(parameter, value)

    def preprocess(self) -> None:
        self._seed_parameter.preprocess()

    def get_repo_revision(self) -> tuple[str, str]:
        return self._huggingface_repo_parameter.get_repo_revision()

    def get_prompt(self) -> str:
        return self._node.get_parameter_value("prompt")

    def get_negative_prompt(self) -> str:
        return self._node.get_parameter_value("negative_prompt")

    def get_audio_length_in_s(self) -> float:
        return float(self._node.get_parameter_value("audio_length_in_s"))

    def get_num_inference_steps(self) -> int:
        return int(self._node.get_parameter_value("num_inference_steps"))

    def get_guidance_scale(self) -> float:
        return float(self._node.get_parameter_value("guidance_scale"))

    def get_pipe_kwargs(self) -> dict:
        kwargs = {
            "prompt": self.get_prompt(),
            "audio_length_in_s": self.get_audio_length_in_s(),
            "num_inference_steps": self.get_num_inference_steps(),
            "guidance_scale": self.get_guidance_scale(),
            "generator": self._seed_parameter.get_generator(),
        }

        negative_prompt = self.get_negative_prompt()
        if negative_prompt:
            kwargs["negative_prompt"] = negative_prompt

        return kwargs

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
        audio_artifact = self._audio_data_to_artifact(audio_data)
        self._node.parameter_output_values["output_audio"] = audio_artifact
