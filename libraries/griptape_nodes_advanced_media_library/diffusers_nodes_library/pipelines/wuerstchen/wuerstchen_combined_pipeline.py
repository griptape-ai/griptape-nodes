import logging
from typing import Any

import diffusers  # type: ignore[reportMissingImports]
import torch  # type: ignore[reportMissingImports]
import transformers  # type: ignore[reportMissingImports]

from diffusers_nodes_library.common.parameters.log_parameter import (  # type: ignore[reportMissingImports]
    LogParameter,  # type: ignore[reportMissingImports]
)
from diffusers_nodes_library.common.utils.huggingface_utils import model_cache  # type: ignore[reportMissingImports]
from diffusers_nodes_library.pipelines.wuerstchen.wuerstchen_combined_pipeline_memory_footprint import (
    optimize_wuerstchen_combined_pipeline_memory_footprint,
    print_wuerstchen_combined_pipeline_memory_footprint,
)  # type: ignore[reportMissingImports]
from diffusers_nodes_library.pipelines.wuerstchen.wuerstchen_combined_pipeline_parameters import (
    WuerstchenCombinedPipelineParameters,  # type: ignore[reportMissingImports]
)
from griptape_nodes.exe_types.core_types import Parameter
from griptape_nodes.exe_types.node_types import AsyncResult, ControlNode

logger = logging.getLogger("diffusers_nodes_library")


class WuerstchenCombinedPipeline(ControlNode):
    """Griptape wrapper around diffusers.WuerstchenCombinedPipeline."""

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.pipe_params = WuerstchenCombinedPipelineParameters(self)
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
            prior_repo_id, prior_revision = self.pipe_params.get_prior_repo_revision()
            prior_tokenizer = model_cache.from_pretrained(
                transformers.CLIPTokenizerFast,
                pretrained_model_name_or_path=prior_repo_id,
                revision=prior_revision,
                subfolder="tokenizer",
                torch_dtype=torch.bfloat16,
                local_files_only=True,
            )
            prior_text_encoder = model_cache.from_pretrained(
                transformers.CLIPTextModel,
                pretrained_model_name_or_path=prior_repo_id,
                revision=prior_revision,
                subfolder="text_encoder",
                torch_dtype=torch.bfloat16,
                local_files_only=True,
            )
            prior_prior = model_cache.from_pretrained(
                diffusers.pipelines.wuerstchen.WuerstchenPrior,
                pretrained_model_name_or_path=prior_repo_id,
                revision=prior_revision,
                subfolder="prior",
                torch_dtype=torch.bfloat16,
                local_files_only=True,
            )
            prior_scheduler = model_cache.from_pretrained(
                diffusers.DDPMWuerstchenScheduler,
                pretrained_model_name_or_path=prior_repo_id,
                revision=prior_revision,
                subfolder="scheduler",
                torch_dtype=torch.bfloat16,
                local_files_only=True,
            )

            decoder_repo_id, decoder_revision = self.pipe_params.get_decoder_repo_revision()
            decoder_tokenizer = model_cache.from_pretrained(
                transformers.CLIPTokenizerFast,
                pretrained_model_name_or_path=decoder_repo_id,
                revision=decoder_revision,
                subfolder="tokenizer",
                torch_dtype=torch.bfloat16,
                local_files_only=True,
            )
            decoder_text_encoder = model_cache.from_pretrained(
                transformers.CLIPTextModel,
                pretrained_model_name_or_path=decoder_repo_id,
                revision=decoder_revision,
                subfolder="text_encoder",
                torch_dtype=torch.bfloat16,
                local_files_only=True,
            )
            decoder_decoder = model_cache.from_pretrained(
                diffusers.pipelines.wuerstchen.WuerstchenDiffNeXt,
                pretrained_model_name_or_path=decoder_repo_id,
                revision=decoder_revision,
                subfolder="decoder",
                torch_dtype=torch.bfloat16,
                local_files_only=True,
            )
            decoder_scheduler = model_cache.from_pretrained(
                diffusers.DDPMWuerstchenScheduler,
                pretrained_model_name_or_path=decoder_repo_id,
                revision=decoder_revision,
                subfolder="scheduler",
                torch_dtype=torch.bfloat16,
                local_files_only=True,
            )
            decoder_vqgan = model_cache.from_pretrained(
                diffusers.pipelines.wuerstchen.PaellaVQModel,
                pretrained_model_name_or_path=decoder_repo_id,
                revision=decoder_revision,
                subfolder="vqgan",
                torch_dtype=torch.bfloat16,
                local_files_only=True,
            )

            pipe = diffusers.WuerstchenCombinedPipeline(
                prior_tokenizer=prior_tokenizer,
                prior_text_encoder=prior_text_encoder,
                prior_prior=prior_prior,
                prior_scheduler=prior_scheduler,
                tokenizer=decoder_tokenizer,
                text_encoder=decoder_text_encoder,
                decoder=decoder_decoder,
                scheduler=decoder_scheduler,
                vqgan=decoder_vqgan,
            )

        with (
            self.log_params.append_profile_to_logs("Loading model"),
            self.log_params.append_logs_to_logs(logger),
        ):
            optimize_wuerstchen_combined_pipeline_memory_footprint(pipe)

        num_inference_steps = self.pipe_params.get_num_inference_steps()

        def callback_on_step_end(
            pipe: diffusers.WuerstchenCombinedPipeline,
            i: int,
            _t: Any,
            callback_kwargs: dict,
        ) -> dict:
            if i < num_inference_steps - 1:
                self.pipe_params.publish_output_image_preview_latents(pipe, callback_kwargs.get("latents"))
                self.log_params.append_to_logs(f"Starting inference step {i + 2} of {num_inference_steps}...\n")
            return {}

        self.log_params.append_to_logs(f"Starting inference step 1 of {num_inference_steps}...\n")
        output_image_pil = pipe(
            **self.pipe_params.get_pipe_kwargs(),
            output_type="pil",
            callback_on_step_end=callback_on_step_end,
        ).images[0]
        self.pipe_params.publish_output_image(output_image_pil)
        self.log_params.append_to_logs("Done.\n")

        # Optionally dump a final memory report
        logger.info("WuerstchenCombined memory footprint after inference:")
        print_wuerstchen_combined_pipeline_memory_footprint(pipe)
