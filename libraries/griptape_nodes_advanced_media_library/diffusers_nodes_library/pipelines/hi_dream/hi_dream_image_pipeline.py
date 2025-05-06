import logging
from typing import Any

import diffusers  # type: ignore[reportMissingImports]
import transformers  # type: ignore[reportMissingImports]
from diffusers_nodes_library.pipelines.hi_dream.hi_dream_image_pipeline_parameters import HiDreamImagePipelineParameters  # type: ignore[reportMissingImports]
from diffusers_nodes_library.pipelines.hi_dream.hi_dream_image_pipeline_memory_footprint import optimize_hi_dream_pipeline_memory_footprint  # type: ignore[reportMissingImports]
import torch  # type: ignore[reportMissingImports]
from pillow_nodes_library.utils import pil_to_image_artifact  # type: ignore[reportMissingImports]
from diffusers_nodes_library.utils.parameter_utils import LogParameter # type: ignore[reportMissingImports]

from diffusers_nodes_library.utils.huggingface_utils import model_cache  # type: ignore[reportMissingImports]
from griptape_nodes.exe_types.node_types import AsyncResult, ControlNode

logger = logging.getLogger("diffusers_nodes_library")


class HiDreamImagePipeline(ControlNode):
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.category = "image"
        self.description = "Generates an image from text and an image using the hi_dream model"
        self.hi_dream_params = HiDreamImagePipelineParameters(self)
        # self.hi_dream_lora_params = HiDreamImageLoraParameters(self)
        self.log_params = LogParameter(self)
        self.hi_dream_params.add_input_parameters()
        # self.hi_dream_lora_params.add_input_parameters()
        self.hi_dream_params.add_output_parameters()
        self.log_params.add_output_parameters()
        

    def process(self) -> AsyncResult | None:
        yield lambda: self._process()

    def _process(self) -> AsyncResult | None:
        self.hi_dream_params.publish_output_image_preview_placeholder()
        self.log_params.append_to_logs("Preparing models...\n")


        with self.log_params.append_profile_to_logs("Loading llama model metadata"):
            tokenizer_4 = model_cache.from_pretrained(
                transformers.PreTrainedTokenizerFast,  # type: ignore
                pretrained_model_name_or_path="meta-llama/Meta-Llama-3.1-8B-Instruct"
            )
            text_encoder_4 = model_cache.from_pretrained(
                transformers.LlamaForCausalLM, # type: ignore
                pretrained_model_name_or_path="meta-llama/Meta-Llama-3.1-8B-Instruct",
                output_hidden_states=True,
                output_attentions=True,
                torch_dtype=torch.bfloat16,
            )
   
        with self.log_params.append_profile_to_logs("Loading hi_dream model metadata"):
            base_repo_id, base_revision = self.hi_dream_params.get_repo_revision()
            pipe = model_cache.from_pretrained(
                diffusers.HiDreamImagePipeline,
                pretrained_model_name_or_path=base_repo_id,
                revision=base_revision,
                torch_dtype=torch.bfloat16,
                local_files_only=True,
                text_encoder_4=text_encoder_4,
                tokenizer_4=tokenizer_4,
            )

        with self.log_params.append_profile_to_logs("Loading hi_dream model"):
            with self.log_params.append_logs_to_logs(logger):
                optimize_hi_dream_pipeline_memory_footprint(pipe)

        # with self.log_params.append_profile_to_logs("Configuring hi_dream loras"):
        #     self.hi_dream_lora_params.configure_loras(pipe)

        num_inference_steps = self.hi_dream_params.get_num_inference_steps()
        def callback_on_step_end(
            pipe: diffusers.HiDreamImagePipeline,
            i: int,
            _t: Any,
            callback_kwargs: dict,
        ) -> dict:
            if i < num_inference_steps - 1:
                self.hi_dream_params.publish_output_image_preview_latents(pipe, callback_kwargs["latents"])
                self.log_params.append_to_logs(f"Starting inference step {i + 2} of {num_inference_steps}...\n")
            return {}
        self.log_params.append_to_logs(f"Starting inference step 1 of {num_inference_steps}...\n")
        output_image_pil = pipe(
            **self.hi_dream_params.get_pipe_kwargs(),
            output_type="pil",
            callback_on_step_end=callback_on_step_end,
        ).images[0]
        self.hi_dream_params.publish_output_image(output_image_pil)
        self.log_params.append_to_logs(f"Done.\n")
