import logging
from typing import Any

import diffusers  # type: ignore[reportMissingImports]
import torch  # type: ignore[reportMissingImports]

from diffusers_nodes_library.common.parameters.log_parameter import (
    LogParameter,  # type: ignore[reportMissingImports]
)
from diffusers_nodes_library.common.utils.huggingface_utils import (
    model_cache,  # type: ignore[reportMissingImports]
)
from diffusers_nodes_library.pipelines.kandinsky.kandinsky_pipeline_parameters import (
    KandinskyPipelineParameters,  # type: ignore[reportMissingImports]
)
from diffusers_nodes_library.pipelines.kandinsky.kandinsky_pipeline_memory_footprint import (
    optimize_kandinsky_pipeline_memory_footprint,  # type: ignore[reportMissingImports]
)
from diffusers_nodes_library.pipelines.kandinsky.kandinsky_pipeline_memory_footprint import (
    print_kandinsky_pipeline_memory_footprint,  # type: ignore[reportMissingImports]
)
from griptape_nodes.exe_types.core_types import Parameter
from griptape_nodes.exe_types.node_types import AsyncResult, ControlNode

logger = logging.getLogger("diffusers_nodes_library")


class KandinskyPipeline(ControlNode):
    """Griptape wrapper around diffusers.KandinskyPipeline."""

    def __init__(self, **kwargs) -> None:  # noqa: D401
        super().__init__(**kwargs)
        self.pipe_params = KandinskyPipelineParameters(self)
        self.log_params = LogParameter(self)

        self.pipe_params.add_input_parameters()
        self.pipe_params.add_output_parameters()
        self.log_params.add_output_parameters()

    # ------------------------------------------------------------------
    # Lifecycle hooks
    # ------------------------------------------------------------------
    def after_value_set(
        self, parameter: Parameter, value: Any, modified_parameters_set: set[str]
    ) -> None:
        self.pipe_params.after_value_set(parameter, value, modified_parameters_set)

    def validate_before_node_run(self) -> list[Exception] | None:  # noqa: D401
        errors = self.pipe_params.validate_before_node_run()
        return errors or None

    def preprocess(self) -> None:
        self.pipe_params.preprocess()

    # ------------------------------------------------------------------
    # Execution
    # ------------------------------------------------------------------
    def process(self) -> AsyncResult | None:  # noqa: D401
        yield lambda: self._process()

    def _process(self) -> AsyncResult | None:  # noqa: C901
        self.preprocess()
        self.pipe_params.publish_output_image_preview_placeholder()
        self.log_params.append_to_logs("Preparing models...\n")

        # -------------------------------------------------------------
        # Model loading - Kandinsky requires separate prior + decoder stages
        # -------------------------------------------------------------
        with self.log_params.append_profile_to_logs("Loading model metadata"):
            repo_id, revision = self.pipe_params.get_repo_revision()
            
            # Load the prior pipeline for text-to-image embeddings
            prior_pipe: diffusers.KandinskyPriorPipeline = model_cache.from_pretrained(
                diffusers.KandinskyPriorPipeline,
                pretrained_model_name_or_path=repo_id,
                revision=revision,
                torch_dtype=torch.float16,
                local_files_only=True,
            )
            
            # Load the main pipeline for image generation
            pipe: diffusers.KandinskyPipeline = model_cache.from_pretrained(
                diffusers.KandinskyPipeline,
                pretrained_model_name_or_path=repo_id,
                revision=revision,
                torch_dtype=torch.float16,
                local_files_only=True,
            )

        with (
            self.log_params.append_profile_to_logs("Loading model"),
            self.log_params.append_logs_to_logs(logger),
        ):
            optimize_kandinsky_pipeline_memory_footprint(pipe)
            optimize_kandinsky_pipeline_memory_footprint(prior_pipe)

        # -------------------------------------------------------------
        # Inference - Two-stage process
        # -------------------------------------------------------------
        num_inference_steps = self.pipe_params.get_num_inference_steps()
        
        # Stage 1: Generate image embeddings from text
        self.log_params.append_to_logs("Generating image embeddings from text...\n")
        image_embeds = prior_pipe(
            prompt=self.pipe_params.get_prompt(),
            negative_prompt=self.pipe_params.get_negative_prompt(),
            generator=self.pipe_params.get_generator(),
        ).image_embeds

        def callback_on_step_end(
            step: int,
            _timestep: int,
            callback_kwargs: dict,
        ) -> dict:  # noqa: D401
            if step < num_inference_steps - 1:
                self.log_params.append_to_logs(
                    f"Starting inference step {step + 2} of {num_inference_steps}...\n"
                )
            return {}

        # Stage 2: Generate image from embeddings
        self.log_params.append_to_logs(f"Starting inference step 1 of {num_inference_steps}...\n")
        output_image_pil = pipe(
            image_embeds=image_embeds,
            width=self.pipe_params.get_width(),
            height=self.pipe_params.get_height(),
            num_inference_steps=num_inference_steps,
            generator=self.pipe_params.get_generator(),
            output_type="pil",
            callback_on_step_end=callback_on_step_end,
        ).images[0]

        self.pipe_params.publish_output_image(output_image_pil)
        self.log_params.append_to_logs("Done.\n")

        # Optionally dump a final memory report
        logger.info("Kandinsky memory footprint after inference:")
        print_kandinsky_pipeline_memory_footprint(pipe)