import logging
from typing import Any

from diffusers.pipelines.pipeline_utils import DiffusionPipeline  # type: ignore[reportMissingImports]

from diffusers_nodes_library.common.parameters.diffusion.diffusion_pipeline_parameters import (
    DiffusionPipelineParameters,
)  # type: ignore[reportMissingImports]
from diffusers_nodes_library.common.parameters.log_parameter import (  # type: ignore[reportMissingImports]
    LogParameter,  # type: ignore[reportMissingImports]
)
from diffusers_nodes_library.common.utils.huggingface_utils import model_cache
from diffusers_nodes_library.pipelines.flux.flux_loras_parameter import FluxLorasParameter
from griptape_nodes.exe_types.core_types import Parameter
from griptape_nodes.exe_types.node_types import ControlNode

logger = logging.getLogger("diffusers_nodes_library")


class DiffusionPipelineRuntimeNode(ControlNode):
    def __init__(self, **kwargs) -> None:
        self._initializing = True
        super().__init__(**kwargs)
        self.did_pipeline_change = False
        self.pipe_params = DiffusionPipelineParameters(self)
        self.pipe_params.add_input_parameters()

        self.loras_params = FluxLorasParameter(self)
        self.loras_params.add_input_parameters()

        self.log_params = LogParameter(self)
        self.log_params.add_output_parameters()
        self._initializing = False

    def before_value_set(self, parameter: Parameter, value: Any) -> Any:
        if parameter.name == "pipeline":
            current_pipeline = self.get_parameter_value("pipeline")
            self.did_pipeline_change = current_pipeline != value
        return super().before_value_set(parameter, value)

    def after_value_set(self, parameter: Parameter, value: Any) -> None:
        reset_runtime_parameters = parameter.name == "pipeline" and self.did_pipeline_change
        if reset_runtime_parameters:
            self.pipe_params.runtime_parameters.remove_input_parameters()
            self.pipe_params.runtime_parameters.remove_output_parameters()

        self.pipe_params.after_value_set(parameter, value)

        if reset_runtime_parameters:
            sorted_parameters = ["pipeline"]
            sorted_parameters.extend(
                [param.name for param in self.parameters if param.name not in ["pipeline", "loras", "logs"]]
            )
            sorted_parameters.extend(["loras", "logs"])
            self.reorder_elements(sorted_parameters)

        self.pipe_params.runtime_parameters.after_value_set(parameter, value)
        return super().after_value_set(parameter, value)

    def add_parameter(self, parameter: Parameter) -> None:
        """Add a parameter to the node.

        During initialization, parameters are added normally.
        After initialization (dynamic mode), parameters are marked as user-defined
        for serialization and duplicates are prevented.
        """
        if self._initializing:
            super().add_parameter(parameter)
            return

        # Dynamic mode: prevent duplicates and mark as user-defined
        if parameter.name not in self.parameters:
            parameter.user_defined = True
            super().add_parameter(parameter)

    def preprocess(self) -> None:
        self.pipe_params.runtime_parameters.preprocess()
        self.log_params.clear_logs()

    def _get_pipeline(self) -> DiffusionPipeline:
        diffusion_pipeline_hash = self.get_parameter_value("pipeline")
        pipeline = model_cache._pipeline_cache.get(diffusion_pipeline_hash)
        if pipeline is None:
            error_msg = f"Pipeline with config hash '{diffusion_pipeline_hash}' not found in cache"
            raise RuntimeError(error_msg)
        return pipeline

    def validate_before_node_run(self) -> list[Exception] | None:
        return self.pipe_params.runtime_parameters.validate_before_node_run()

    async def aprocess(self) -> None:
        self.preprocess()
        self.pipe_params.runtime_parameters.publish_output_image_preview_placeholder()
        pipe = self._get_pipeline()

        with (
            self.log_params.append_profile_to_logs("Configuring FLUX loras"),
            self.log_params.append_logs_to_logs(logger),
        ):
            self.loras_params.configure_loras(pipe)

        self.pipe_params.runtime_parameters.process_pipeline(pipe)
