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
from diffusers_nodes_library.pipelines.kandinsky2_2.kandinsky2_2_pipeline_memory_footprint import (
    optimize_kandinsky2_2_pipeline_memory_footprint,  # type: ignore[reportMissingImports]
    print_kandinsky2_2_pipeline_memory_footprint,  # type: ignore[reportMissingImports]
)
from diffusers_nodes_library.pipelines.kandinsky2_2.kandinsky2_2_pipeline_parameters import (
    Kandinsky22PipelineParameters,  # type: ignore[reportMissingImports]
)
from griptape_nodes.exe_types.core_types import Parameter
from griptape_nodes.exe_types.node_types import AsyncResult, ControlNode

logger = logging.getLogger("diffusers_nodes_library")


class Kandinsky22Pipeline(ControlNode):
    """Griptape wrapper around diffusers.KandinskyV22Pipeline."""

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.pipe_params = Kandinsky22PipelineParameters(self)
        self.log_params = LogParameter(self)

        self.pipe_params.add_input_parameters()
        self.pipe_params.add_output_parameters()
        self.log_params.add_output_parameters()

    # ------------------------------------------------------------------
    # Lifecycle hooks
    # ------------------------------------------------------------------
    def after_value_set(self, parameter: Parameter, value: Any, modified_parameters_set: set[str]) -> None:
        self.pipe_params.after_value_set(parameter, value, modified_parameters_set)

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
        self.pipe_params.publish_output_image_preview_placeholder()
        self.log_params.append_to_logs("Preparing models...\n")

        # -------------------------------------------------------------
        # Model loading - Kandinsky 2.2 requires separate prior + decoder stages
        # -------------------------------------------------------------
        with self.log_params.append_profile_to_logs("Loading model metadata"):
            repo_id, revision = self.pipe_params.get_repo_revision()

            # Load the prior pipeline for text-to-image embeddings
            prior_pipe: diffusers.KandinskyV22PriorPipeline = model_cache.from_pretrained(
                diffusers.KandinskyV22PriorPipeline,
                pretrained_model_name_or_path="kandinsky-community/kandinsky-2-2-prior",
                torch_dtype=torch.float16,
                local_files_only=True,
            )

            # Load the main pipeline for image generation
            pipe: diffusers.KandinskyV22Pipeline = model_cache.from_pretrained(
                diffusers.KandinskyV22Pipeline,
                pretrained_model_name_or_path=repo_id,
                revision=revision,
                torch_dtype=torch.float16,
                local_files_only=True,
            )

        with (
            self.log_params.append_profile_to_logs("Loading model"),
            self.log_params.append_logs_to_logs(logger),
        ):
            optimize_kandinsky2_2_pipeline_memory_footprint(pipe)
            optimize_kandinsky2_2_pipeline_memory_footprint(prior_pipe)

        # -------------------------------------------------------------
        # Inference - Two-stage process
        # -------------------------------------------------------------
        num_inference_steps = self.pipe_params.get_num_inference_steps()

        # Stage 1: Generate image embeddings from text
        self.log_params.append_to_logs("Generating image embeddings from text...\n")
        image_embeds, negative_image_embeds = prior_pipe(
            prompt=self.pipe_params.get_prompt(),
            negative_prompt=self.pipe_params.get_negative_prompt(),
            generator=self.pipe_params.get_generator(),
        ).to_tuple()

        def callback_on_step_end(
            pipe: diffusers.KandinskyV22Pipeline,
            step: int,
            _timestep: int,
            callback_kwargs: dict,
        ) -> dict:
            if step < num_inference_steps - 1:
                self.pipe_params.publish_output_image_preview_latents(pipe, callback_kwargs["latents"])
                self.log_params.append_to_logs(f"Starting inference step {step + 2} of {num_inference_steps}...\n")
            return {}

        # Stage 2: Generate image from embeddings
        self.log_params.append_to_logs(f"Starting inference step 1 of {num_inference_steps}...\n")
        output_image_pil = pipe(
            image_embeds=image_embeds,
            negative_image_embeds=negative_image_embeds,
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
        logger.info("Kandinsky 2.2 memory footprint after inference:")
        print_kandinsky2_2_pipeline_memory_footprint(pipe)
