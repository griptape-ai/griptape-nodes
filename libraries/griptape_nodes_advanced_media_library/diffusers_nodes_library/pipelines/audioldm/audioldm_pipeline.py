import logging
import time
from typing import Any

import diffusers  # type: ignore[reportMissingImports]
import torch  # type: ignore[reportMissingImports]

from diffusers_nodes_library.common.parameters.log_parameter import (  # type: ignore[reportMissingImports]
    LogParameter,  # type: ignore[reportMissingImports]
)
from diffusers_nodes_library.common.utils.huggingface_utils import model_cache  # type: ignore[reportMissingImports]
from diffusers_nodes_library.pipelines.audioldm.audioldm_pipeline_memory_footprint import (
    optimize_audio_ldm_pipeline_memory_footprint,
)  # type: ignore[reportMissingImports]
from diffusers_nodes_library.pipelines.audioldm.audioldm_pipeline_parameters import (
    AudioldmPipelineParameters,  # type: ignore[reportMissingImports]
)
from griptape_nodes.exe_types.core_types import Parameter
from griptape_nodes.exe_types.node_types import AsyncResult, ControlNode

logger = logging.getLogger("diffusers_nodes_library")


class AudioldmPipeline(ControlNode):
    """Griptape wrapper around diffusers.pipelines.audioldm.AudioLDMPipeline."""

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.pipe_params = AudioldmPipelineParameters(self)
        self.log_params = LogParameter(self)
        self.pipe_params.add_input_parameters()
        self.pipe_params.add_output_parameters()
        self.log_params.add_output_parameters()
        # Track last preview generation time for throttling
        self._last_preview_time = 0.0
        self._preview_throttle_seconds = 30.0

    def after_value_set(self, parameter: Parameter, value: Any) -> None:
        self.pipe_params.after_value_set(parameter, value)

    def validate_before_node_run(self) -> list[Exception] | None:
        errors = self.pipe_params.validate_before_node_run()
        return errors or None

    def preprocess(self) -> None:
        self.pipe_params.preprocess()

    def process(self) -> AsyncResult | None:
        yield lambda: self._process()

    def _process(self) -> AsyncResult | None:
        self.preprocess()
        self.log_params.append_to_logs("Preparing AudioLDM models...\n")

        with self.log_params.append_profile_to_logs("Loading model metadata"):
            base_repo_id, base_revision = self.pipe_params.get_repo_revision()
            pipe = model_cache.from_pretrained(
                diffusers.AudioLDMPipeline,
                pretrained_model_name_or_path=base_repo_id,
                revision=base_revision,
                torch_dtype=torch.float16,
                local_files_only=True,
            )

        with self.log_params.append_profile_to_logs("Loading model"), self.log_params.append_logs_to_logs(logger):
            optimize_audio_ldm_pipeline_memory_footprint(pipe)

        num_inference_steps = self.pipe_params.get_num_inference_steps()
        audio_length = self.pipe_params.get_audio_length_in_s()

        def callback(
            step_idx: int,
            _t: Any,
            latents: Any,
        ) -> None:
            # Throttle preview generation to once every 30 seconds
            if time.time() - self._last_preview_time >= self._preview_throttle_seconds:
                self.pipe_params.publish_output_audio_preview(pipe, latents)
                self._last_preview_time = time.time()

            if step_idx < num_inference_steps - 1:
                self.log_params.append_to_logs(f"Starting inference step {step_idx + 2} of {num_inference_steps}...\n")

        self.log_params.append_to_logs(
            f"Generating {audio_length}s audio with {num_inference_steps} inference steps...\n"
        )
        self.log_params.append_to_logs(f"Starting inference step 1 of {num_inference_steps}...\n")

        result = pipe(
            **self.pipe_params.get_pipe_kwargs(),
            callback=callback,
            callback_steps=1,
        )

        output_audio = result.audios[0]
        self.pipe_params.publish_output_audio(output_audio)
        self.log_params.append_to_logs("Audio generation complete.\n")
