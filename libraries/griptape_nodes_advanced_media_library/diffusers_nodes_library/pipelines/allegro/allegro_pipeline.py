import logging
import tempfile
import time
from pathlib import Path
from typing import Any

import diffusers  # type: ignore[reportMissingImports]
import torch  # type: ignore[reportMissingImports]

from diffusers_nodes_library.common.parameters.log_parameter import LogParameter  # type: ignore[reportMissingImports]
from diffusers_nodes_library.common.utils.huggingface_utils import model_cache  # type: ignore[reportMissingImports]
from diffusers_nodes_library.pipelines.allegro.allegro_pipeline_memory_footprint import (  # type: ignore[reportMissingImports]
    optimize_allegro_pipeline_memory_footprint,
    print_allegro_pipeline_memory_footprint,
)
from diffusers_nodes_library.pipelines.allegro.allegro_pipeline_parameters import (  # type: ignore[reportMissingImports]
    AllegroPipelineParameters,
)
from griptape_nodes.exe_types.core_types import Parameter
from griptape_nodes.exe_types.node_types import AsyncResult, ControlNode

logger = logging.getLogger("diffusers_nodes_library")


class AllegroPipeline(ControlNode):
    """Griptape wrapper around diffusers.pipelines.allegro.AllegroPipeline."""

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.pipe_params = AllegroPipelineParameters(self)
        self.log_params = LogParameter(self)

        # Register parameters on the node.
        self.pipe_params.add_input_parameters()
        self.pipe_params.add_output_parameters()
        self.log_params.add_output_parameters()

        # Track last preview generation time for throttling
        self._last_preview_time = 0.0
        self._preview_throttle_seconds = 10.0

    # ------------------------------------------------------------------
    # Node lifecycle hooks
    # ------------------------------------------------------------------

    def after_value_set(self, parameter: Parameter, value: Any) -> None:
        self.pipe_params.after_value_set(parameter, value)

    def validate_before_node_run(self) -> list[Exception] | None:
        errors = self.pipe_params.validate_before_node_run()
        return errors or None

    def preprocess(self) -> None:
        self.pipe_params.preprocess()

    # ------------------------------------------------------------------
    # Execution
    # ------------------------------------------------------------------

    def process(self) -> AsyncResult | None:
        yield lambda: self._process()

    def _process(self) -> AsyncResult | None:
        self.preprocess()

        self.log_params.append_to_logs("Preparing models...\n")

        with self.log_params.append_profile_to_logs("Loading model"), self.log_params.append_logs_to_logs(logger):
            base_repo_id, base_revision = self.pipe_params.get_repo_revision()

            # Load VAE explicitly to avoid mixed precision issues.
            vae = model_cache.from_pretrained(
                diffusers.AutoencoderKLAllegro,
                pretrained_model_name_or_path=base_repo_id,
                revision=base_revision,
                subfolder="vae",
                torch_dtype=torch.float32,
                local_files_only=True,
            )

            # We need to enable tiling, because AutoencoderKLAllegro does not support decoding without tiling.
            vae.enable_tiling()

            pipe: diffusers.AllegroPipeline = model_cache.from_pretrained(
                diffusers.AllegroPipeline,
                pretrained_model_name_or_path=base_repo_id,
                revision=base_revision,
                vae=vae,
                torch_dtype=torch.bfloat16,
                local_files_only=True,
            )

            # Print initial memory footprint.
            print_allegro_pipeline_memory_footprint(pipe)

            # Optimize & move to device.
            optimize_allegro_pipeline_memory_footprint(pipe)

        # ------------------------------------------------------------------
        # Inference
        # ------------------------------------------------------------------

        self.log_params.append_to_logs("Starting generation...\n")

        num_inference_steps = self.pipe_params.get_num_inference_steps()

        def callback_on_step_end(
            pipe: diffusers.AllegroPipeline,
            i: int,
            _t: Any,
            callback_kwargs: dict,
        ) -> dict:
            if i < num_inference_steps - 1:
                # Throttle preview generation to once every 10 seconds
                if time.time() - self._last_preview_time >= self._preview_throttle_seconds:
                    self.pipe_params.publish_output_video_preview_latents(pipe, callback_kwargs["latents"])
                    self._last_preview_time = time.time()
                self.log_params.append_to_logs(f"Starting inference step {i + 2} of {num_inference_steps}...\n")
            return {}

        with (
            self.log_params.append_profile_to_logs("Generating video"),
            self.log_params.append_logs_to_logs(logger),
            self.log_params.append_stdout_to_logs(),
        ):
            self.log_params.append_to_logs(f"Starting inference step 1 of {num_inference_steps}...\n")
            frames = pipe(
                **self.pipe_params.get_pipe_kwargs(),
                callback_on_step_end=callback_on_step_end,
            ).frames[0]

        # ------------------------------------------------------------------
        # Export video & publish
        # ------------------------------------------------------------------

        with (
            self.log_params.append_profile_to_logs("Exporting video"),
            self.log_params.append_logs_to_logs(logger),
            self.log_params.append_stdout_to_logs(),
        ):
            with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as temp_file_obj:
                temp_file = Path(temp_file_obj.name)
            try:
                diffusers.utils.export_to_video(frames, str(temp_file), fps=15)
                self.pipe_params.publish_output_video(temp_file)
            finally:
                if temp_file.exists():
                    temp_file.unlink()

        self.log_params.append_to_logs("Done.\n")
