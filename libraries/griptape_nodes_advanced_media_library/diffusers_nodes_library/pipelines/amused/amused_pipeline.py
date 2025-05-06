import logging
from typing import Any

import diffusers  # type: ignore[reportMissingImports]
import torch  # type: ignore[reportMissingImports]

from diffusers_nodes_library.common.parameters.log_parameter import LogParameter  # type: ignore[reportMissingImports]
from diffusers_nodes_library.common.utils.huggingface_utils import model_cache  # type: ignore[reportMissingImports]
from diffusers_nodes_library.pipelines.amused.amused_memory_footprint import optimize_amused_pipeline_memory_footprint
from diffusers_nodes_library.pipelines.amused.amused_pipeline_parameters import (
    AmusedPipelineParameters,  # type: ignore[reportMissingImports]
)
from griptape_nodes.exe_types.node_types import AsyncResult, ControlNode

logger = logging.getLogger("diffusers_nodes_library")


class AmusedPipeline(ControlNode):
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.category = "image"
        self.description = self.__class__.__name__
        self.pipe_params = AmusedPipelineParameters(self)
        self.log_params = LogParameter(self)
        self.pipe_params.add_input_parameters()
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
                diffusers.AmusedPipeline,
                pretrained_model_name_or_path=base_repo_id,
                revision=base_revision,
                torch_dtype=torch.bfloat16,
                local_files_only=True,
            )

        with self.log_params.append_profile_to_logs("Loading model"), self.log_params.append_logs_to_logs(logger):
            optimize_amused_pipeline_memory_footprint(pipe)

        num_inference_steps = self.pipe_params.get_num_inference_steps()

        def callback(i: int, _t: Any, latents: torch.Tensor) -> None:
            if i < num_inference_steps - 1:
                self.pipe_params.publish_output_image_preview_latents(pipe, latents)
                self.log_params.append_to_logs(f"Starting inference step {i + 2} of {num_inference_steps}...\n")

        self.log_params.append_to_logs(f"Starting inference step 1 of {num_inference_steps}...\n")
        output_image_pil = pipe(
            **self.pipe_params.get_pipe_kwargs(),
            output_type="pil",
            callback=callback,
        ).images[0]
        self.pipe_params.publish_output_image(output_image_pil)
        self.log_params.append_to_logs("Done.\n")
