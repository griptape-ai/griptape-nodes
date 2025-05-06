import logging
from typing import Any

from griptape_nodes.exe_types.node_types import AsyncResult, ControlNode
from diffusers_nodes_library.utils.parameter_utils import ( # type: ignore[reportMissingImports]
    FluxPipelineParameters,  # type: ignore[reportMissingImports]
    FluxLoraParameters,  # type: ignore[reportMissingImports]
    FluxControlNetParameters__UnionOne,  # type: ignore[reportMissingImports]
    FluxControlRepoRevisionParameters,  # type: ignore[reportMissingImports]
    LogParameter,  # type: ignore[reportMissingImports]
)
from diffusers_nodes_library.utils.huggingface_utils import model_cache  # type: ignore[reportMissingImports]
from diffusers_nodes_library.utils.torch_utils import optimize_flux_pipeline_memory_footprint # type: ignore[reportMissingImports]

import diffusers   # type: ignore[reportMissingImports] 
import torch  # type: ignore[reportMissingImports]


logger = logging.getLogger("diffusers_nodes_library")


class InstantXFLUX1devControlnetUnionFluxControlNetPipeline(ControlNode):
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.category = "image"
        self.description = "Generates an image from text and an image using the flux.1 dev model"
        self.flux_params = FluxPipelineParameters(self)
        self.controlnet_revisions_params = FluxControlRepoRevisionParameters(self, "InstantX/FLUX.1-dev-Controlnet-Union")
        self.flux_control_net_params = FluxControlNetParameters__UnionOne(self)
        self.flux_lora_params = FluxLoraParameters(self)
        self.log_params = LogParameter(self)
        self.flux_params.add_input_parameters()
        self.flux_lora_params.add_input_parameters()
        self.controlnet_revisions_params.add_input_parameters()
        self.flux_control_net_params.add_input_parameters()
        self.flux_params.add_output_parameters()
        self.log_params.add_output_parameters()

    def process(self) -> AsyncResult | None:
        yield lambda: self._process()

    def _process(self) -> AsyncResult | None:
        self.flux_params.publish_output_image_preview_placeholder()
        self.log_params.append_to_logs("Preparing models...\n")
        
        with self.log_params.append_profile_to_logs("Loading flux control net model metadata"):
            controlnet_repo_id, controlnet_revision = self.controlnet_revisions_params.get_repo_revision()
            controlnet = model_cache.from_pretrained(
                diffusers.FluxControlNetModel,
                pretrained_model_name_or_path=controlnet_repo_id,
                revision=controlnet_revision,
                torch_dtype=torch.bfloat16,
                local_files_only=True,
            )

        with self.log_params.append_profile_to_logs("Loading flux model metadata"):
            base_repo_id, base_revision = self.flux_params.get_repo_revision()
            pipe = model_cache.from_pretrained(
                diffusers.FluxControlNetPipeline,
                pretrained_model_name_or_path=base_repo_id,
                revision=base_revision,
                controlnet=controlnet,
                torch_dtype=torch.bfloat16,
                local_files_only=True,
            )

        with self.log_params.append_profile_to_logs("Loading flux model"):
            with self.log_params.append_logs_to_logs(logger):
                optimize_flux_pipeline_memory_footprint(pipe)

        with self.log_params.append_profile_to_logs("Configuring flux loras"):
            self.flux_lora_params.configure_loras(pipe)

        num_inference_steps = self.flux_params.get_num_inference_steps()
        def callback_on_step_end(
            pipe: diffusers.FluxControlNetPipeline,
            i: int,
            _t: Any,
            callback_kwargs: dict,
        ) -> dict:
            if i < num_inference_steps - 1:
                self.flux_params.publish_output_image_preview_latents(pipe, callback_kwargs["latents"])
                self.log_params.append_to_logs(f"Starting inference step {i + 2} of {num_inference_steps}...\n")
            return {}
        self.log_params.append_to_logs(f"Starting inference step 1 of {num_inference_steps}...\n")
        output_image_pil = pipe(
            **self.flux_params.get_pipe_kwargs(),
            **self.flux_control_net_params.get_pipe_kwargs(),
            output_type="pil",
            callback_on_step_end=callback_on_step_end,
        ).images[0]
        self.flux_params.publish_output_image(output_image_pil)
        self.log_params.append_to_logs(f"Done.\n")

    