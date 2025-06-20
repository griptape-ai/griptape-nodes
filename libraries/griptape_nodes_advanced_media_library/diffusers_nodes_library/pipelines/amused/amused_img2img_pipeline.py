import logging
from typing import Any

import diffusers  # type: ignore[reportMissingImports]
import torch  # type: ignore[reportMissingImports]

from diffusers_nodes_library.common.parameters.log_parameter import LogParameter  # type: ignore[reportMissingImports]
from diffusers_nodes_library.common.utils.huggingface_utils import model_cache  # type: ignore[reportMissingImports]
from diffusers_nodes_library.pipelines.amused.amused_img2img_pipeline_parameters import (  # type: ignore[reportMissingImports]
    AmusedImg2ImgPipelineParameters,
)
from diffusers_nodes_library.pipelines.amused.amused_pipeline_memory_footprint import (  # type: ignore[reportMissingImports]
    optimize_amused_pipeline_memory_footprint,
    print_amused_pipeline_memory_footprint,
)
from griptape_nodes.exe_types.core_types import Parameter
from griptape_nodes.exe_types.node_types import AsyncResult, ControlNode

logger = logging.getLogger("diffusers_nodes_library")


class AmusedImg2ImgPipeline(ControlNode):
    """Griptape wrapper around diffusers.AmusedImg2ImgPipeline."""

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.pipe_params = AmusedImg2ImgPipelineParameters(self)
        self.log_params = LogParameter(self)

        self.pipe_params.add_input_parameters()
        self.pipe_params.add_output_parameters()
        self.log_params.add_output_parameters()

    # ------------------------------------------------------------------
    # Lifecycle hooks
    # ------------------------------------------------------------------
    def after_value_set(self, parameter: Parameter, value: Any) -> None:
        self.pipe_params.after_value_set(parameter, value)

    def validate_before_node_run(self) -> list[Exception] | None:
        return self.pipe_params.validate_before_node_run()

    def preprocess(self) -> None:
        self.pipe_params.preprocess()

    # ------------------------------------------------------------------
    # Execution
    # ------------------------------------------------------------------
    def process(self) -> AsyncResult | None:
        yield lambda: self._process()

    def _process(self) -> AsyncResult | None:
        self.preprocess()
        self.pipe_params.publish_output_image_preview_placeholder()
        self.log_params.append_to_logs("Preparing models...\n")

        # -------------------------------------------------------------
        # Model loading
        # -------------------------------------------------------------
        with self.log_params.append_profile_to_logs("Loading model metadata"):
            repo_id, revision = self.pipe_params.get_repo_revision()
            pipe: diffusers.AmusedImg2ImgPipeline = model_cache.from_pretrained(
                diffusers.AmusedImg2ImgPipeline,
                pretrained_model_name_or_path=repo_id,
                revision=revision,
                torch_dtype="auto",
                local_files_only=True,
            )

        with (
            self.log_params.append_profile_to_logs("Optimising model"),
            self.log_params.append_logs_to_logs(logger),
        ):
            optimize_amused_pipeline_memory_footprint(pipe)

        # -------------------------------------------------------------
        # Inference
        # -------------------------------------------------------------
        num_inference_steps = self.pipe_params.get_num_inference_steps()

        def callback(step: int, _timestep: int, _latents: torch.Tensor) -> None:
            if step < num_inference_steps - 1:
                # TODO: https://github.com/griptape-ai/griptape-nodes/issues/1467
                # self.pipe_params.publish_output_image_preview_latents(pipe, latents)  # noqa: ERA001
                self.log_params.append_to_logs(f"Starting inference step {step + 2} of {num_inference_steps}...\n")

        self.log_params.append_to_logs(f"Starting inference step 1 of {num_inference_steps}...\n")

        output_image_pil = pipe(
            **self.pipe_params.get_pipe_kwargs(),
            output_type="pil",
            callback=callback,
            callback_steps=1,
        ).images[0]

        self.pipe_params.publish_output_image(output_image_pil)
        self.log_params.append_to_logs("Done.\n")

        # Optionally dump a final memory report
        logger.info("AmusedImg2Img memory footprint after inference:")
        print_amused_pipeline_memory_footprint(pipe)
