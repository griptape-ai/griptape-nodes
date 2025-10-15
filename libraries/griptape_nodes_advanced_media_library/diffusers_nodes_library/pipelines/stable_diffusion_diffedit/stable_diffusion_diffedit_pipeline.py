import logging
from typing import Any

import diffusers  # type: ignore[reportMissingImports]
import torch  # type: ignore[reportMissingImports]

from diffusers_nodes_library.common.parameters.log_parameter import (  # type: ignore[reportMissingImports]
    LogParameter,  # type: ignore[reportMissingImports]
)
from diffusers_nodes_library.common.utils.huggingface_utils import model_cache  # type: ignore[reportMissingImports]
from diffusers_nodes_library.pipelines.stable_diffusion_diffedit.stable_diffusion_diffedit_pipeline_memory_footprint import (
    optimize_stable_diffusion_diffedit_pipeline_memory_footprint,  # type: ignore[reportMissingImports]
)
from diffusers_nodes_library.pipelines.stable_diffusion_diffedit.stable_diffusion_diffedit_pipeline_parameters import (
    StableDiffusionDiffeditPipelineParameters,  # type: ignore[reportMissingImports]
)
from griptape_nodes.exe_types.core_types import Parameter
from griptape_nodes.exe_types.node_types import AsyncResult, ControlNode

logger = logging.getLogger("diffusers_nodes_library")


class StableDiffusionDiffeditPipeline(ControlNode):
    """Griptape wrapper around diffusers.pipelines.stable_diffusion_diffedit.StableDiffusionDiffEditPipeline."""

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.pipe_params = StableDiffusionDiffeditPipelineParameters(self)
        self.log_params = LogParameter(self)
        self.pipe_params.add_input_parameters()
        self.pipe_params.add_output_parameters()
        self.log_params.add_output_parameters()

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
        self.pipe_params.publish_output_image_preview_placeholder()
        self.log_params.append_to_logs("Preparing models...\n")

        with self.log_params.append_profile_to_logs("Loading model metadata"):
            base_repo_id, base_revision = self.pipe_params.get_repo_revision()
            pipe = model_cache.from_pretrained(
                diffusers.StableDiffusionDiffEditPipeline,
                pretrained_model_name_or_path=base_repo_id,
                revision=base_revision,
                torch_dtype=torch.float16,
                local_files_only=True,
            )

        with self.log_params.append_profile_to_logs("Loading model"), self.log_params.append_logs_to_logs(logger):
            optimize_stable_diffusion_diffedit_pipeline_memory_footprint(pipe)

        # Set up DDIM schedulers for DiffEdit
        pipe.scheduler = diffusers.DDIMScheduler.from_config(pipe.scheduler.config)
        pipe.inverse_scheduler = diffusers.DDIMInverseScheduler.from_config(pipe.scheduler.config)

        num_inference_steps = self.pipe_params.get_num_inference_steps()

        def callback(step: int, _timestep: int, latents: torch.Tensor) -> None:
            if step < num_inference_steps - 1:
                self.pipe_params.publish_output_image_preview_latents(pipe, latents)
                self.log_params.append_to_logs(f"Starting inference step {step + 2} of {num_inference_steps}...\n")

        self.log_params.append_to_logs(f"Starting inference step 1 of {num_inference_steps}...\n")
        output_image_pil = pipe(
            **self.pipe_params.get_pipe_kwargs(pipe),
            output_type="pil",
            callback=callback,
        ).images[0]
        self.pipe_params.publish_output_image(output_image_pil)
        self.log_params.append_to_logs("Done.\n")
