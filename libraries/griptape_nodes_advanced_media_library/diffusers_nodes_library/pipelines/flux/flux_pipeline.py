import logging
from typing import Any

import diffusers  # type: ignore[reportMissingImports]
from diffusers_nodes_library.pipelines.flux.flux_pipeline_parameters import FluxPipelineParameters  # type: ignore[reportMissingImports]
from diffusers_nodes_library.pipelines.flux.flux_pipeline_memory_footprint import optimize_flux_pipeline_memory_footprint  # type: ignore[reportMissingImports]
import torch  # type: ignore[reportMissingImports]
from pillow_nodes_library.utils import pil_to_image_artifact  # type: ignore[reportMissingImports]
from diffusers_nodes_library.utils.parameter_utils import ( # type: ignore[reportMissingImports]
    FluxLoraParameters,  # type: ignore[reportMissingImports]
    LogParameter,  # type: ignore[reportMissingImports]
)

from diffusers_nodes_library.utils.huggingface_utils import model_cache  # type: ignore[reportMissingImports]
from griptape_nodes.exe_types.node_types import AsyncResult, ControlNode

logger = logging.getLogger("diffusers_nodes_library")


class FluxPipeline(ControlNode):
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.category = "image"
        self.description = self.__class__.__name__
        self.pipe_params = FluxPipelineParameters(self)
        self.lora_params = FluxLoraParameters(self)
        self.log_params = LogParameter(self)
        self.pipe_params.add_input_parameters()
        self.lora_params.add_input_parameters()
        self.pipe_params.add_output_parameters()
        self.log_params.add_output_parameters()
        

    def process(self) -> AsyncResult | None:
        yield lambda: self._process()

    def _process(self) -> AsyncResult | None:
        self.pipe_params.publish_output_image_preview_placeholder()
        self.log_params.append_to_logs("Preparing models...\n")
   
        with self.log_params.append_profile_to_logs("Loading model metadata"):
            base_repo_id, base_revision = self.pipe_params.get_repo_revision()
            pipe = model_cache.from_pretrained(
                diffusers.FluxPipeline,
                pretrained_model_name_or_path=base_repo_id,
                revision=base_revision,
                torch_dtype=torch.bfloat16,
                local_files_only=True,
            )

        with self.log_params.append_profile_to_logs("Loading model"):
            with self.log_params.append_logs_to_logs(logger):
                optimize_flux_pipeline_memory_footprint(pipe)

        with self.log_params.append_profile_to_logs("Configuring flux loras"):
            self.lora_params.configure_loras(pipe)

        num_inference_steps = self.pipe_params.get_num_inference_steps()
        def callback_on_step_end(
            pipe: diffusers.FluxPipeline,
            i: int,
            _t: Any,
            callback_kwargs: dict,
        ) -> dict:
            if i < num_inference_steps - 1:
                self.pipe_params.publish_output_image_preview_latents(pipe, callback_kwargs["latents"])
                self.log_params.append_to_logs(f"Starting inference step {i + 2} of {num_inference_steps}...\n")
            return {}
        self.log_params.append_to_logs(f"Starting inference step 1 of {num_inference_steps}...\n")
        output_image_pil = pipe(
            **self.pipe_params.get_pipe_kwargs(),
            output_type="pil",
            callback_on_step_end=callback_on_step_end,
        ).images[0]
        self.pipe_params.publish_output_image(output_image_pil)
        self.log_params.append_to_logs(f"Done.\n")
