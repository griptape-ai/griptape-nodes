import logging
import tempfile
import time
from pathlib import Path
from typing import Any

import diffusers  # type: ignore[reportMissingImports]
import torch  # type: ignore[reportMissingImports]
import transformers  # type: ignore[reportMissingImports]

from diffusers_nodes_library.common.parameters.log_parameter import (  # type: ignore[reportMissingImports]
    LogParameter,  # type: ignore[reportMissingImports]
)
from diffusers_nodes_library.common.utils.huggingface_utils import model_cache  # type: ignore[reportMissingImports]
from diffusers_nodes_library.pipelines.wan.wan_image_to_video_pipeline_memory_footprint import (
    optimize_wan_image_to_video_pipeline_memory_footprint,
)  # type: ignore[reportMissingImports]
from diffusers_nodes_library.pipelines.wan.wan_image_to_video_pipeline_parameters import (
    WanImageToVideoPipelineParameters,  # type: ignore[reportMissingImports]
)
from diffusers_nodes_library.pipelines.wan.wan_loras_parameter import (
    WanLorasParameter,  # type: ignore[reportMissingImports]
)
from griptape_nodes.exe_types.core_types import Parameter
from griptape_nodes.exe_types.node_types import AsyncResult, ControlNode

logger = logging.getLogger("diffusers_nodes_library")


class WanImageToVideoPipeline(ControlNode):
    """Griptape wrapper around diffusers.WanImageToVideoPipeline."""

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.pipe_params = WanImageToVideoPipelineParameters(self)
        self.loras_param = WanLorasParameter(self)
        self.log_params = LogParameter(self)
        self.pipe_params.add_input_parameters()
        self.loras_param.add_input_parameters()
        self.pipe_params.add_output_parameters()
        self.log_params.add_output_parameters()
        # Track last preview generation time for throttling
        self._last_preview_time = 0.0
        self._preview_throttle_seconds = 60.0

    def after_value_set(self, parameter: Parameter, value: Any) -> None:
        self.pipe_params.after_value_set(parameter, value)

    def validate_before_node_run(self) -> list[Exception] | None:
        errors = self.pipe_params.validate_before_node_run()
        return errors or None

    # ------------------------------------------------------------------
    # Lifecycle hooks
    # ------------------------------------------------------------------
    def preprocess(self) -> None:
        self.pipe_params.preprocess()

    # ------------------------------------------------------------------
    # Execution
    # ------------------------------------------------------------------
    def process(self) -> AsyncResult | None:
        yield lambda: self._process()

    def _process(self) -> AsyncResult | None:
        self.preprocess()
        self.pipe_params.publish_output_video_preview_placeholder()
        self.log_params.append_to_logs("Preparing models...\n")

        # -------------------------------------------------------------
        # Model loading
        # -------------------------------------------------------------
        with self.log_params.append_profile_to_logs("Loading model metadata"):
            repo_id, revision = self.pipe_params.get_repo_revision()

            image_encoder = model_cache.from_pretrained(
                transformers.CLIPVisionModel,  # type: ignore[reportAttributeAccessIssue]
                pretrained_model_name_or_path=repo_id,
                subfolder="image_encoder",
                torch_dtype=torch.float32,
            )

            vae = model_cache.from_pretrained(
                diffusers.AutoencoderKLWan,
                pretrained_model_name_or_path=repo_id,
                revision=revision,
                subfolder="vae",
                torch_dtype=torch.float32,
                local_files_only=True,
            )

            pipe: diffusers.WanImageToVideoPipeline = model_cache.from_pretrained(
                diffusers.WanImageToVideoPipeline,
                pretrained_model_name_or_path=repo_id,
                revision=revision,
                torch_dtype=torch.bfloat16,
                local_files_only=True,
                vae=vae,
                image_encoder=image_encoder,
            )

        with (
            self.log_params.append_profile_to_logs("Loading model"),
            self.log_params.append_logs_to_logs(logger),
        ):
            optimize_wan_image_to_video_pipeline_memory_footprint(pipe)

        with (
            self.log_params.append_profile_to_logs("Configuring wan loras"),
            self.log_params.append_logs_to_logs(logger),
        ):
            self.loras_param.configure_loras(pipe)

        # -------------------------------------------------------------
        # Inference with step callback
        # -------------------------------------------------------------
        num_inference_steps = self.pipe_params.get_num_inference_steps()

        def callback_on_step_end(
            pipe: diffusers.WanImageToVideoPipeline,
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

        self.log_params.append_to_logs(f"Starting inference step 1 of {num_inference_steps}...\n")
        frames = pipe(
            **self.pipe_params.get_pipe_kwargs(pipe),
            callback_on_step_end=callback_on_step_end,
        ).frames[0]

        # Export video & publish
        with (
            self.log_params.append_profile_to_logs("Exporting video"),
            self.log_params.append_logs_to_logs(logger=logger),
            self.log_params.append_stdout_to_logs(),
        ):
            with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as temp_file_obj:
                temp_file = Path(temp_file_obj.name)
            try:
                diffusers.utils.export_to_video(frames, str(temp_file), fps=16)
                self.pipe_params.publish_output_video(temp_file)
            finally:
                if temp_file.exists():
                    temp_file.unlink()

        self.log_params.append_to_logs("Done.\n")
