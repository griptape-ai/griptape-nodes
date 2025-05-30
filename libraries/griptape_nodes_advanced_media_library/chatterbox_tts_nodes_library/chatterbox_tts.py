import logging
from pathlib import Path
import tempfile
import uuid
import warnings

with warnings.catch_warnings():
    warnings.simplefilter("ignore")  # Silence noisy but harmless warnings from controlnet_aux
    import controlnet_aux  # type: ignore[reportMissingImports]

from griptape.loaders import AudioLoader  # type: ignore[reportMissingImports]
from griptape.artifacts import AudioArtifact
from griptape_nodes_library.audio.audio_url_artifact import AudioUrlArtifact  # type: ignore[reportMissingImports]
import huggingface_hub
import PIL.Image
import torch  # type: ignore[reportMissingImports]
from diffusers_nodes_library.common.parameters.huggingface_repo_parameter import (
    HuggingFaceRepoParameter,  # type: ignore[reportMissingImports]
)
from griptape.artifacts import ImageUrlArtifact
from griptape.loaders import ImageLoader
from PIL.Image import Image
from pillow_nodes_library.utils import (  # type: ignore[reportMissingImports]
    image_artifact_to_pil,  # type: ignore[reportMissingImports]
    pil_to_image_artifact,  # type: ignore[reportMissingImports]
)

from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import AsyncResult, ControlNode

import torchaudio as ta  # type: ignore[reportMissingImports]
import chatterbox.tts  # type: ignore[reportMissingImports]

logger = logging.getLogger("diffusers_nodes_library")


def wav_to_audio_url_artifact(audio_wav: Path) -> AudioUrlArtifact:
    """Converts Pillow Image to Griptape ImageArtifact."""
    from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

    url = GriptapeNodes.StaticFilesManager().save_static_file(audio_wav.read_bytes(), f"{uuid.uuid4()}.wav")
    return AudioUrlArtifact(url)

class ChatterboxTTS(ControlNode):
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.add_parameter(
            Parameter(
                name="text",
                input_types=["str"],
                type="str",
                tooltip="text",
            )
        )
        self.add_parameter(
            Parameter(
                name="voice_audio",
                input_types=["AudioArtifact", "AudioUrlArtifact"],
                type="AudioArtifact",
                output_type="AudioUrlArtifact",
                default_value=None,
                ui_options={"clickable_file_browser": True, "expander": True},
                tooltip="Voice sample",
            )
        )
        self.add_parameter(
            Parameter(
                name="exaggeration",
                input_types=["float"],
                type="float",
                default_value=0.5,
                tooltip="Exaggeration factor for the voice",
                ui_options={"slider": {"min_val": 0.0, "max_val": 3.0}, "step": 0.01},
            )
        )
        self.add_parameter(
            Parameter(
                name="cfg_weight",
                input_types=["float"],
                type="float",
                default_value=0.5,
                tooltip="",
                ui_options={"slider": {"min_val": 0.0, "max_val": 5.0}, "step": 0.01},
            )
        )
        self.add_parameter(
            Parameter(
                name="temperature",
                input_types=["float"],
                type="float",
                default_value=0.8,
                tooltip="",
                ui_options={"slider": {"min_val": 0.0, "max_val": 1.0}, "step": 0.01},
            )
        )

        self.add_parameter(
            Parameter(
                name="output_audio",
                output_type="AudioUrlArtifact",
                tooltip="The output audio",
                allowed_modes={ParameterMode.OUTPUT},
            )
        )

    def get_text(self) -> str:
        return self.get_parameter_value("text") or ""
    
    def get_exaggeration(self) -> float:
        return float(self.get_parameter_value("exaggeration"))
    
    def get_cfg_weight(self) -> float:
        return float(self.get_parameter_value("cfg_weight"))
    
    def get_temperature(self) -> float:
        return float(self.get_parameter_value("temperature"))
    
    def get_voice_audio(self) -> AudioArtifact | None:
        voice_audio_artifact = self.get_parameter_value("voice_audio")
        if voice_audio_artifact is None:
            logger.exception("No input audio specified")
            return None

        if isinstance(voice_audio_artifact, AudioUrlArtifact):
            voice_audio_artifact = AudioLoader().parse(voice_audio_artifact.to_bytes())
        
        return voice_audio_artifact

    def get_chatterbox_tts(self) -> chatterbox.tts.ChatterboxTTS:
        chatterbox_tts = chatterbox.tts.ChatterboxTTS.from_pretrained(device="mps")

        # device = "mps"
        # chatterbox_tts.ve.to(device).eval()
        # chatterbox_tts.t3.to(device).eval()
        # chatterbox_tts.s3gen.to(device).eval()
        # chatterbox_tts.conds.to(device).eval()

        return chatterbox_tts
            
    
    def publish_output_audio(self, audio_artifact: AudioArtifact) -> None:
        self.parameter_output_values["output_audio"] = audio_artifact

    def process(self) -> AsyncResult | None:
        yield lambda: self._process()

    def _process(self) -> AsyncResult | None:
        with tempfile.TemporaryDirectory() as temp_dir:
            voice_audio = self.get_voice_audio()
            if voice_audio is not None:
                temp_voice_path = Path(temp_dir) / "voice.wav"
                print(f"{voice_audio.format=}")
                print(f"Saving voice audio to {temp_voice_path}")

                # Let's hope this is always a wav file
                temp_voice_path.write_bytes(voice_audio.to_bytes())
            else:
                temp_voice_path = None

            chatterbox_tts = self.get_chatterbox_tts()
            audio_wav = chatterbox_tts.generate(
                self.get_text(),
                audio_prompt_path=temp_voice_path,
                exaggeration=self.get_exaggeration(),
                cfg_weight=self.get_cfg_weight(),
                temperature=self.get_temperature(),
            )
        
            temp_output_audio_path = Path(temp_dir) / "audio.wav"
            ta.save(str(temp_output_audio_path), audio_wav, chatterbox_tts.sr)
            output_audio_url_artifact = wav_to_audio_url_artifact(temp_output_audio_path)
            self.publish_output_audio(output_audio_url_artifact)
