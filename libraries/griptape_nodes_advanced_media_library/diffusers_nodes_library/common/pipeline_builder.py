import asyncio
import logging
from typing import Any

import diffusers  # type: ignore[reportMissingImports]
import torch  # type: ignore[reportMissingImports]

from diffusers_nodes_library.common.parameters.log_parameter import LogParameter
from diffusers_nodes_library.common.pipeline_builder_parameters import PipelineBuilderParameters
from diffusers_nodes_library.common.utils.huggingface_utils import model_cache
from diffusers_nodes_library.pipelines.flux.flux_loras_parameter import FluxLorasParameter
from diffusers_nodes_library.common.utils.pipeline_utils import optimize_diffusion_pipeline
from griptape_nodes.exe_types.core_types import Parameter
from griptape_nodes.exe_types.node_types import ControlNode

logger = logging.getLogger("diffusers_nodes_library")


class PipelineBuilder(ControlNode):
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.params = PipelineBuilderParameters(self)
        self.loras_params = FluxLorasParameter(self)
        self.log_params = LogParameter(self)

        self.params.add_input_parameters()
        self.loras_params.add_input_parameters()
        self.params.add_output_parameters()
        self.log_params.add_output_parameters()
        self.set_config_hash()

    def set_config_hash(self) -> None:
        config_hash = self.params.config_hash
        self.log_params.append_to_logs(f"Pipeline configuration hash: {config_hash}\n")
        self.set_parameter_value("pipeline", config_hash)
        self.parameter_output_values["pipeline"] = config_hash

    def after_value_set(self, parameter: Parameter, value: Any) -> None:
        if parameter.name != "pipeline":
            self.set_config_hash()
            
        self.params.after_value_set(parameter, value)
        return super().after_value_set(parameter, value)

    def validate_before_node_run(self) -> list[Exception] | None:
        errors = self.params.validate_configuration()
        return errors or None

    def preprocess(self) -> None:
        self.log_params.clear_logs()

    async def aprocess(self) -> None:
        self.preprocess()
        self.log_params.append_to_logs("Building pipeline...\n")

        # Build pipeline with caching (offload to thread)
        def builder() -> Any:
            return self._build_pipeline()

        with self.log_params.append_profile_to_logs("Pipeline building/caching"):
            await asyncio.to_thread(model_cache.get_or_build_pipeline, self.get_parameter_value("pipeline"), builder)

        self.log_params.append_to_logs("Pipeline building complete.\n")

    def _build_pipeline(self) -> Any:
        """Build the actual pipeline instance."""
        self.log_params.append_to_logs("Creating new pipeline instance...\n")

        # Get pipeline configuration
        pipeline_class = self.params.pipeline_class
        base_repo_id, base_revision = self.params.repo_revision

        # Load base model
        with self.log_params.append_profile_to_logs("Loading base model"):
            base_kwargs = {
                "pretrained_model_name_or_path": base_repo_id,
                "revision": base_revision,
                "torch_dtype": torch.bfloat16,
                "local_files_only": True,
            }

            # Handle ControlNet pipelines
            if self.params.should_show_controlnet_params:
                controlnet_repo_revision = self.params.controlnet_repo_revision
                if controlnet_repo_revision:
                    controlnet_repo, controlnet_revision = controlnet_repo_revision
                    self.log_params.append_to_logs(f"Loading ControlNet model: {controlnet_repo}\n")

                    with self.log_params.append_profile_to_logs("Loading ControlNet model"):
                        controlnet = model_cache.from_pretrained(
                            diffusers.FluxControlNetModel,
                            pretrained_model_name_or_path=controlnet_repo,
                            revision=controlnet_revision,
                            torch_dtype=torch.bfloat16,
                            local_files_only=True,
                        )
                    base_kwargs["controlnet"] = controlnet

            pipe = model_cache.from_pretrained(pipeline_class, **base_kwargs)

        # Apply optimizations
        with self.log_params.append_profile_to_logs("Applying optimizations"):
            optimization_kwargs = self.params.optimization_kwargs
            optimize_diffusion_pipeline(pipe=pipe, **optimization_kwargs)

        # Configure LoRAs
        with self.log_params.append_profile_to_logs("Configuring LoRAs"):
            self.loras_params.configure_loras(pipe)

        self.log_params.append_to_logs("Pipeline creation complete.\n")
        return pipe
