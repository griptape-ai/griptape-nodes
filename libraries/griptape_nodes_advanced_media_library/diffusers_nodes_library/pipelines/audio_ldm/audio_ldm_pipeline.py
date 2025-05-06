import logging
from typing import Any

import diffusers  # type: ignore[reportMissingImports]
import torch  # type: ignore[reportMissingImports]

from diffusers_nodes_library.common.parameters.log_parameter import LogParameter  # type: ignore[reportMissingImports]
from diffusers_nodes_library.common.utils.huggingface_utils import model_cache  # type: ignore[reportMissingImports]
from diffusers_nodes_library.pipelines.audio_ldm.audio_ldm_memory_footprint import (
    optimize_audio_ldm_pipeline_memory_footprint,
)
from diffusers_nodes_library.pipelines.audio_ldm.audio_ldm_pipeline_parameters import (
    AudioLDMPipelineParameters,  # type: ignore[reportMissingImports]
)
from griptape_nodes.exe_types.node_types import AsyncResult, ControlNode

logger = logging.getLogger("diffusers_nodes_library")


class AudioLDMPipeline(ControlNode):
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.category = "audio"
        self.description = self.__class__.__name__
        self.pipe_params = AudioLDMPipelineParameters(self)
        self.log_params = LogParameter(self)
        self.pipe_params.add_input_parameters()
        self.pipe_params.add_output_parameters()
        self.log_params.add_output_parameters()

    def process(self) -> AsyncResult | None:
        yield lambda: self._process()

    def _process(self) -> AsyncResult | None:
        # self.pipe_params.publish_output_video_preview_placeholder() ?
        self.log_params.append_to_logs("Preparing models...\n")

        with self.log_params.append_profile_to_logs("Loading model metadata"):
            repo_id, revision = self.pipe_params.get_repo_revision()
            pipe = model_cache.from_pretrained(
                diffusers.AudioLDMPipeline,
                pretrained_model_name_or_path=repo_id,
                revision=revision,
                torch_dtype=torch.float16,
                local_files_only=True,
            )

        with self.log_params.append_profile_to_logs("Loading model"), self.log_params.append_logs_to_logs(logger):
            # Without vae tiling --  NotImplementedError: "Decoding without tiling has not been implemented yet"
            pipe.enable_vae_tiling()
            optimize_audio_ldm_pipeline_memory_footprint(pipe)

        num_inference_steps = self.pipe_params.get_num_inference_steps()

        def callback(i: int, _t: Any, latents: torch.Tensor) -> dict:  # noqa: ARG001
            if i < num_inference_steps - 1:
                # Publish output preview here
                self.log_params.append_to_logs(f"Starting inference step {i + 2} of {num_inference_steps}...\n")
            return {}

        self.log_params.append_to_logs(f"Starting inference step 1 of {num_inference_steps}...\n")
        audio = pipe(
            **self.pipe_params.get_pipe_kwargs(),
            callback=callback,
        ).audios[0]

        self.log_params.append_to_logs(f"Starting inference step 1 of {num_inference_steps}...\n")
        self.pipe_params.publish_output_audio(audio)

        self.log_params.append_to_logs("Done.\n")
