import logging
import tempfile
import uuid
from typing import Any

import scipy  # type: ignore[reportMissingImports]
import torch  # type: ignore[reportMissingImports]

from diffusers_nodes_library.common.artifacts.audio_url_artifact import (
    AudioUrlArtifact,  # type: ignore[reportMissingImports]
)
from diffusers_nodes_library.common.parameters.huggingface_repo_parameter import (
    HuggingFaceRepoParameter,  # type: ignore[reportMissingImports]
)
from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import ControlNode
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

logger = logging.getLogger("diffusers_nodes_library")


class AudioLDMPipelineParameters:
    def __init__(self, node: ControlNode):
        self._node = node
        self._huggingface_repo_parameter = HuggingFaceRepoParameter(node, ["cvssp/audioldm-s-full-v2"])

    def add_input_parameters(self) -> None:
        self._huggingface_repo_parameter.add_input_parameters()
        self._node.add_parameter(
            Parameter(
                name="prompt",
                default_value="",
                input_types=["str"],
                type="str",
                allowed_modes={ParameterMode.PROPERTY, ParameterMode.INPUT},
                tooltip="prompt",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="audio_length_in_s",
                default_value=5.0,
                input_types=["float"],
                type="float",
                allowed_modes={ParameterMode.PROPERTY, ParameterMode.INPUT},
                tooltip="audio_length_in_s",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="num_inference_steps",
                default_value=10,
                input_types=["int"],
                type="int",
                allowed_modes={ParameterMode.PROPERTY, ParameterMode.INPUT},
                tooltip="num_inference_steps",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="negative_prompt",
                default_value="",
                input_types=["str"],
                type="str",
                allowed_modes={ParameterMode.PROPERTY, ParameterMode.INPUT},
                tooltip="negative_prompt",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="guidance_scale",
                default_value=2.5,
                input_types=["float"],
                type="float",
                allowed_modes={ParameterMode.PROPERTY, ParameterMode.INPUT},
                tooltip="guidance_scale",
            )
        )

        self._node.add_parameter(
            Parameter(
                name="seed",
                default_value=None,
                input_types=["int", "None"],
                allowed_modes={ParameterMode.PROPERTY, ParameterMode.INPUT},
                tooltip="seed",
            )
        )

    def add_output_parameters(self) -> None:
        self._node.add_parameter(
            Parameter(
                name="output_audio",
                output_type="AudioUrlArtifact",
                type="AudioUrlArtifact",  # Hint for UI
                default_value=None,
                allowed_modes={ParameterMode.OUTPUT},
                tooltip="URL of the audio.",
            )
        )

    def get_repo_revision(self) -> tuple[str, str]:
        return self._huggingface_repo_parameter.get_repo_revision()

    def get_prompt(self) -> str:
        return self._node.get_parameter_value("prompt")

    def get_audio_length_in_s(self) -> float:
        return float(self._node.get_parameter_value("audio_length_in_s"))

    def get_num_inference_steps(self) -> int:
        return int(self._node.get_parameter_value("num_inference_steps"))

    def get_negative_prompt(self) -> str:
        return self._node.get_parameter_value("negative_prompt")

    def get_guidance_scale(self) -> float:
        return float(self._node.get_parameter_value("guidance_scale"))

    def get_generator(self) -> torch.Generator:
        seed = self._node.get_parameter_value("seed")
        generator = torch.Generator("cpu")
        if seed is not None:
            generator = generator.manual_seed(int(seed))
        return generator

    def get_pipe_kwargs(self) -> dict:
        return {
            "prompt": self.get_prompt(),
            "num_inference_steps": self.get_num_inference_steps(),
            "audio_length_in_s": self.get_audio_length_in_s(),
            "negative_prompt": self.get_negative_prompt(),
            "guidance_scale": self.get_guidance_scale(),
            "generator": self.get_generator(),
        }

    def publish_output_audio(self, audio: Any) -> None:
        self.publish_output_wav(audio)

    def publish_output_wav(self, audio: Any) -> None:
        scipy.io.wavfile.write("/Users/dylan/Downloads/out.wav", rate=16000, data=audio)
        suffix = ".wav"
        with tempfile.TemporaryFile(mode="wb+", suffix=suffix) as audio_file:
            scipy.io.wavfile.write(audio_file, rate=16000, data=audio)
            audio_file.seek(0)
            audio_bytes = audio_file.read()

        audio_filename = f"{uuid.uuid4()}{suffix}"
        audio_url = GriptapeNodes.StaticFilesManager().save_static_file(audio_bytes, audio_filename)
        audio_artifact = AudioUrlArtifact(audio_url)

        self._node.set_parameter_value("output_audio", audio_artifact)
        self._node.parameter_output_values["output_audio"] = audio_artifact
