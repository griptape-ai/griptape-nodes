import gc
import logging
import time
from typing import Any

import diffusers  # type: ignore[reportMissingImports]
import torch  # type: ignore[reportMissingImports]

from diffusers_nodes_library.common.parameters.log_parameter import (  # type: ignore[reportMissingImports]
    LogParameter,  # type: ignore[reportMissingImports]
)
from diffusers_nodes_library.common.utils.huggingface_utils import model_cache  # type: ignore[reportMissingImports]
from diffusers_nodes_library.pipelines.flux.flux_model_parameters import FluxModelParameters
from diffusers_nodes_library.pipelines.flux.flux_pipeline_memory_footprint import (
    optimize_flux_pipeline_memory_footprint,
)  # type: ignore[reportMissingImports]
from griptape_nodes.exe_types.core_types import Parameter
from griptape_nodes.exe_types.node_types import AsyncResult, ControlNode

logger = logging.getLogger("diffusers_nodes_library")


class FluxModel(ControlNode):
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)

        self.pipe_params = FluxModelParameters(self)
        self.pipe_params.add_input_parameters()

        self.log_params = LogParameter(self)
        self.log_params.add_output_parameters()

    def after_value_set(self, parameter: Parameter, value: Any) -> None:
        self.pipe_params.after_value_set(parameter, value)

    def validate_before_node_run(self) -> list[Exception] | None:
        errors = self.pipe_params.validate_before_node_run()
        return errors or None

    def preprocess(self) -> None:
        self.pipe_params.preprocess()

        from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
        pipe = GriptapeNodes.ModelManager().get_pipeline()
        self.log_params.append_to_logs("Checking...\n")
        if pipe is not None:
            self.log_params.append_to_logs("Clearing existing models from memory...\n")
            GriptapeNodes.ModelManager().set_pipeline(None)
            del pipe
            gc.collect()
            model_cache.from_pretrained.cache_clear()
            torch.cuda.empty_cache()

    def process(self) -> AsyncResult | None:
        yield lambda: self._process()

    def _process(self) -> AsyncResult | None:
        self.preprocess()
        self.log_params.append_to_logs("Preparing models...\n")

        with self.log_params.append_profile_to_logs("Loading model metadata"):
            base_repo_id, base_revision = self.pipe_params.get_repo_revision()
            pipe = model_cache.from_pretrained(
                diffusers.FluxPipeline,
                pretrained_model_name_or_path=base_repo_id,
                revision=base_revision,
                torch_dtype=torch.bfloat16,
                local_files_only=True,
            )

        with self.log_params.append_profile_to_logs("Loading model"), self.log_params.append_logs_to_logs(logger):
            optimize_flux_pipeline_memory_footprint(pipe)

        from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
        GriptapeNodes.ModelManager().set_pipeline(pipe)

        self.log_params.append_to_logs("Done.\n")
