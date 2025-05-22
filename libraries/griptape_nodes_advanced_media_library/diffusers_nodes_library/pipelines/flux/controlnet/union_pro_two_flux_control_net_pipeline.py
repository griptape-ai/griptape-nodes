import logging
from typing import Any

import diffusers  # type: ignore[reportMissingImports]
import torch  # type: ignore[reportMissingImports]

from diffusers_nodes_library.common.parameters.huggingface_repo_parameter import HuggingFaceRepoParameter
from diffusers_nodes_library.common.parameters.log_parameter import LogParameter  # type: ignore[reportMissingImports]
from diffusers_nodes_library.common.utils.huggingface_utils import model_cache  # type: ignore[reportMissingImports]
from diffusers_nodes_library.pipelines.flux.controlnet.union_two_flux_control_net_parameters import (
    UnionTwoFluxControlNetParameters,
)  # type: ignore[reportMissingImports]
from diffusers_nodes_library.pipelines.flux.flux_loras_parameter import (
    FluxLorasParameter,  # type: ignore[reportMissingImports]
)
from diffusers_nodes_library.pipelines.flux.flux_pipeline_memory_footprint import (
    optimize_flux_pipeline_memory_footprint,
)  # type: ignore[reportMissingImports]
from diffusers_nodes_library.pipelines.flux.flux_pipeline_parameters import (
    FluxPipelineParameters,  # type: ignore[reportMissingImports]
)
from griptape_nodes.exe_types.node_types import AsyncResult, ControlNode

logger = logging.getLogger("diffusers_nodes_library")


class UnionProTwoFluxControlNetPipeline(ControlNode):
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.flux_params = FluxPipelineParameters(self)
        self.controlnet_revisions_params = HuggingFaceRepoParameter(
            self, ["Shakker-Labs/FLUX.1-dev-ControlNet-Union-Pro-2.0"], "controlnet_model"
        )
        self.flux_control_net_params = UnionTwoFluxControlNetParameters(self)
        self.flux_lora_params = FluxLorasParameter(self)
        self.log_params = LogParameter(self)
        self.flux_params.add_input_parameters()
        self.flux_lora_params.add_input_parameters()
        self.controlnet_revisions_params.add_input_parameters()
        self.flux_control_net_params.add_input_parameters()
        self.flux_params.add_output_parameters()
        self.log_params.add_output_parameters()

    def validate_before_node_run(self) -> list[Exception] | None:
        errors = self.controlnet_revisions_params.validate_before_node_run()
        return errors or None

    def preprocess(self) -> None:
        self.flux_params.preprocess()

    def process(self) -> AsyncResult | None:
        yield lambda: self._process()

    def _process(self) -> AsyncResult | None:
        self.preprocess()
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

        with self.log_params.append_profile_to_logs("Loading model metadata"):
            base_repo_id, base_revision = self.flux_params.get_repo_revision()
            pipe = model_cache.from_pretrained(
                diffusers.FluxControlNetPipeline,
                pretrained_model_name_or_path=base_repo_id,
                revision=base_revision,
                controlnet=controlnet,
                torch_dtype=torch.bfloat16,
                local_files_only=True,
            )

        with self.log_params.append_profile_to_logs("Loading model"), self.log_params.append_logs_to_logs(logger):
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
        self.log_params.append_to_logs("Done.\n")
