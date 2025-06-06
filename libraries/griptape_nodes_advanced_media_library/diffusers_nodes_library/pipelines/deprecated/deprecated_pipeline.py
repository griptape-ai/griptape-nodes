import logging
from typing import Any

import diffusers  # type: ignore[reportMissingImports]
import torch  # type: ignore[reportMissingImports]

from diffusers_nodes_library.common.parameters.log_parameter import (  # type: ignore[reportMissingImports]
    LogParameter,  # type: ignore[reportMissingImports]
)
from diffusers_nodes_library.common.utils.huggingface_utils import model_cache  # type: ignore[reportMissingImports]
from diffusers_nodes_library.pipelines.deprecated.deprecated_pipeline_memory_footprint import (  # type: ignore[reportMissingImports]
    optimize_deprecated_pipeline_memory_footprint,
    print_deprecated_pipeline_memory_footprint,
)
from diffusers_nodes_library.pipelines.deprecated.deprecated_pipeline_parameters import (  # type: ignore[reportMissingImports]
    DeprecatedPipelineParameters,
)
from griptape_nodes.exe_types.core_types import Parameter
from griptape_nodes.exe_types.node_types import AsyncResult, ControlNode

logger = logging.getLogger("diffusers_nodes_library")


class DeprecatedPipeline(ControlNode):
    """Griptape wrapper around deprecated diffusers pipelines."""

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.pipe_params = DeprecatedPipelineParameters(self)
        self.log_params = LogParameter(self)
        self.pipe_params.add_input_parameters()
        self.pipe_params.add_output_parameters()
        self.log_params.add_output_parameters()

    def after_value_set(self, parameter: Parameter, value: Any, modified_parameters_set: set[str]) -> None:
        self.pipe_params.after_value_set(parameter, value, modified_parameters_set)

    def validate_before_node_run(self) -> list[Exception] | None:
        errors = self.pipe_params.validate_before_node_run()
        return errors or None

    def preprocess(self) -> None:
        self.pipe_params.preprocess()

    def process(self) -> AsyncResult | None:
        yield lambda: self._process()

    def _process(self) -> AsyncResult | None:
        self.preprocess()
        self.pipe_params.publish_output_preview_placeholder()
        self.log_params.append_to_logs("Preparing models...\n")

        with self.log_params.append_profile_to_logs("Loading model metadata"):
            base_repo_id, base_revision = self.pipe_params.get_repo_revision()
            pipeline_class = self.pipe_params.get_pipeline_class()
            pipe = model_cache.from_pretrained(
                pipeline_class,
                pretrained_model_name_or_path=base_repo_id,
                revision=base_revision,
                torch_dtype=torch.float32,
                local_files_only=True,
            )

        with self.log_params.append_profile_to_logs("Loading model"), self.log_params.append_logs_to_logs(logger):
            optimize_deprecated_pipeline_memory_footprint(pipe)

        with self.log_params.append_profile_to_logs("Running inference"):
            output = pipe(**self.pipe_params.get_pipe_kwargs())
            
        self.pipe_params.publish_output(output)
        self.log_params.append_to_logs("Done.\n")