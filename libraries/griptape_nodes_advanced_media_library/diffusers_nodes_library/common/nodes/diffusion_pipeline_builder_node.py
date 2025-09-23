import asyncio
import hashlib
import json
import logging
from typing import Any

import diffusers  # type: ignore[reportMissingImports]
import torch  # type: ignore[reportMissingImports]

from diffusers_nodes_library.common.parameters.log_parameter import LogParameter
from diffusers_nodes_library.common.parameters.diffusion.diffusion_pipeline_builder_parameters import DiffusionPipelineBuilderParameters
from diffusers_nodes_library.common.utils.huggingface_utils import model_cache
from diffusers_nodes_library.common.utils.pipeline_utils import optimize_diffusion_pipeline
from diffusers_nodes_library.common.parameters.huggingface_pipeline_parameter import HuggingFacePipelineParameter
from griptape_nodes.exe_types.core_types import Parameter
from griptape_nodes.exe_types.node_types import ControlNode

logger = logging.getLogger("diffusers_nodes_library")


class DiffusionPipelineBuilderNode(ControlNode):
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.params = DiffusionPipelineBuilderParameters(self)
        self.params.add_input_parameters()

        self.huggingface_pipeline_params = HuggingFacePipelineParameter(self)
        self.huggingface_pipeline_params.add_input_parameters()

        self.params.add_output_parameters()

        self.log_params = LogParameter(self)
        self.log_params.add_output_parameters()

        self.set_config_hash()

    def set_config_hash(self) -> None:
        config_hash = self._config_hash
        self.log_params.append_to_logs(f"Pipeline configuration hash: {config_hash}\n")
        self.set_parameter_value("pipeline", config_hash)
        self.parameter_output_values["pipeline"] = config_hash

    @property
    def optimization_kwargs(self) -> dict[str, Any]:
        """Get optimization settings for the pipeline."""
        return self.huggingface_pipeline_params.get_hf_pipeline_parameters()

    @property
    def _config_hash(self) -> str:
        """Generate a hash for the current configuration to use as cache key."""
        config_data = {
            **self.params.get_config_kwargs(),
            "torch_dtype": "bfloat16",  # Currently hardcoded
        }

        opt_kwargs = self.huggingface_pipeline_params.get_hf_pipeline_parameters()
        for key, value in opt_kwargs.items():
            config_data[f"opt_{key}"] = value

        return (
            self.params.pipeline_type_parameters.pipeline_type_pipeline_params.pipeline_class.__name__
            + "-"
            + hashlib.sha256(json.dumps(config_data, sort_keys=True).encode()).hexdigest()
        )

    def after_value_set(self, parameter: Parameter, value: Any) -> None:
        if parameter.name != "pipeline":
            self.set_config_hash()
        self.params.after_value_set(parameter, value)
        self.huggingface_pipeline_params.after_value_set(parameter, value)
        return super().after_value_set(parameter, value)

    def validate_before_node_run(self) -> list[Exception] | None:
        return self.params.pipeline_type_parameters.pipeline_type_pipeline_params.validate_before_node_run()

    def preprocess(self) -> None:
        self.log_params.clear_logs()

    async def aprocess(self) -> None:
        self.preprocess()
        self.log_params.append_to_logs("Building pipeline...\n")

        def builder() -> Any:
            return self._build_pipeline()

        with self.log_params.append_profile_to_logs("Pipeline building/caching"):
            await asyncio.to_thread(model_cache.get_or_build_pipeline, self.get_parameter_value("pipeline"), builder)

        self.log_params.append_to_logs("Pipeline building complete.\n")

    def _build_pipeline(self) -> Any:
        """Build the actual pipeline instance."""
        self.log_params.append_to_logs("Creating new pipeline instance...\n")

        with self.log_params.append_profile_to_logs("Loading pipeline"):
            pipe = self.params.pipeline_type_parameters.pipeline_type_pipeline_params.build_pipeline()

        with self.log_params.append_profile_to_logs("Applying optimizations"):
            optimization_kwargs = self.huggingface_pipeline_params.get_hf_pipeline_parameters()
            optimize_diffusion_pipeline(pipe=pipe, **optimization_kwargs)

        self.log_params.append_to_logs("Pipeline creation complete.\n")
        return pipe
