import logging
from typing import Any

from diffusers.pipelines.pipeline_utils import DiffusionPipeline

from diffusers_nodes_library.common.parameters.log_parameter import (  # type: ignore[reportMissingImports]
    LogParameter,  # type: ignore[reportMissingImports]
)
from diffusers_nodes_library.common.parameters.diffusion.diffusion_pipeline_parameters import DiffusionPipelineParameters  # type: ignore[reportMissingImports]
from diffusers_nodes_library.common.utils.huggingface_utils import model_cache
from diffusers_nodes_library.pipelines.flux.flux_loras_parameter import FluxLorasParameter
from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import ControlNode

logger = logging.getLogger("diffusers_nodes_library")


class DiffusionPipelineNode(ControlNode):
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.pipe_params = DiffusionPipelineParameters(self)
        self.pipe_params.add_input_parameters()
        
        self.loras_params = FluxLorasParameter(self)
        self.loras_params.add_input_parameters()

        self.log_params = LogParameter(self)
        self.log_params.add_output_parameters()

    def after_value_set(self, parameter: Parameter, value: Any) -> None:
        reset_runtime_parameters = parameter.name == "diffusion_pipeline"
        if reset_runtime_parameters:
            if hasattr(self.pipe_params, '_runtime_parameters') and self.pipe_params._runtime_parameters is not None:
                self.pipe_params.runtime_parameters.remove_input_parameters()
                self.pipe_params.runtime_parameters.remove_output_parameters()

        self.pipe_params.after_value_set(parameter, value)

        if reset_runtime_parameters:
            sorted_parameters = ["diffusion_pipeline"]
            for parameter in self.parameters:
                if parameter.name not in {"diffusion_pipeline", "loras", "logs"}:
                    sorted_parameters.append(parameter.name)
            sorted_parameters.extend(["loras", "logs"])
            self.reorder_elements(sorted_parameters)

        if hasattr(self.pipe_params, '_runtime_parameters') and self.pipe_params._runtime_parameters is not None:
            self.pipe_params.runtime_parameters.after_value_set(parameter, value)

    def preprocess(self) -> None:
        self.pipe_params.runtime_parameters.preprocess()
        self.log_params.clear_logs()

    async def aprocess(self) -> None:
        self.preprocess()
        self.pipe_params.runtime_parameters.publish_output_image_preview_placeholder()

        with (
            self.log_params.append_profile_to_logs("Configuring FLUX loras"),
            self.log_params.append_logs_to_logs(logger),
        ):
            self.loras_params.configure_loras(self.pipe_params.pipeline)

        num_inference_steps = self.pipe_params.runtime_parameters.get_num_inference_steps()

        def callback_on_step_end(
            pipe: DiffusionPipeline,
            i: int,
            _t: Any,
            callback_kwargs: dict,
        ) -> dict:
            if i < num_inference_steps - 1:
                self.pipe_params.runtime_parameters.publish_output_image_preview_latents(self.pipe_params.pipeline, callback_kwargs["latents"])
                self.log_params.append_to_logs(f"Starting inference step {i + 2} of {num_inference_steps}...\n")
            return {}

        self.log_params.append_to_logs(f"Starting inference step 1 of {num_inference_steps}...\n")
        output_image_pil = self.pipe_params.pipeline(  # type: ignore[reportCallIssue]
            **self.pipe_params.runtime_parameters.get_pipe_kwargs(),
            output_type="pil",
            callback_on_step_end=callback_on_step_end,
        ).images[0]
        self.pipe_params.runtime_parameters.publish_output_image(output_image_pil)
        self.log_params.append_to_logs("Done.\n")
