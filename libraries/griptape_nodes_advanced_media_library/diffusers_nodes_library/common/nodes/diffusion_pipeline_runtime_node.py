import asyncio
import logging
from typing import Any

from diffusers.pipelines.pipeline_utils import DiffusionPipeline  # type: ignore[reportMissingImports]

from diffusers_nodes_library.common.parameters.diffusion.pipeline_parameters import (
    DiffusionPipelineParameters,
)  # type: ignore[reportMissingImports]
from diffusers_nodes_library.common.parameters.log_parameter import (  # type: ignore[reportMissingImports]
    LogParameter,  # type: ignore[reportMissingImports]
)
from diffusers_nodes_library.common.utils.huggingface_utils import model_cache
from griptape_nodes.exe_types.core_types import Parameter
from griptape_nodes.exe_types.node_types import BaseNode, ControlNode

logger = logging.getLogger("diffusers_nodes_library")


class DiffusionPipelineRuntimeNode(ControlNode):
    def __init__(self, **kwargs) -> None:
        self._initializing = True
        super().__init__(**kwargs)
        self.pipe_params = DiffusionPipelineParameters(self)
        self.pipe_params.add_input_parameters()

        self.log_params = LogParameter(self)
        self.log_params.add_output_parameters()
        self._initializing = False

    def set_parameter_value(
        self,
        param_name: str,
        value: Any,
        *,
        initial_setup: bool = False,
        emit_change: bool = True,
        skip_before_value_set: bool = False,
    ) -> None:
        parameter = self.get_parameter_by_name(param_name)
        if parameter is None:
            return

        did_pipeline_change = False
        # Handle pipeline change detection before setting the value
        if parameter.name == "pipeline":
            current_pipeline = self.get_parameter_value("pipeline")
            did_pipeline_change = current_pipeline != value

        super().set_parameter_value(
            param_name,
            value,
            initial_setup=initial_setup,
            emit_change=emit_change,
            skip_before_value_set=skip_before_value_set,
        )

        if did_pipeline_change:
            self.pipe_params.runtime_parameters.remove_input_parameters()
            self.pipe_params.runtime_parameters.remove_output_parameters()

        self.pipe_params.after_value_set(parameter, value)

        if did_pipeline_change:
            sorted_parameters = ["pipeline"]
            sorted_parameters.extend(
                [param.name for param in self.parameters if param.name not in ["pipeline", "logs"]]
            )
            sorted_parameters.extend(["logs"])
            self.reorder_elements(sorted_parameters)

        self.pipe_params.runtime_parameters.after_value_set(parameter, value)

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
        if not self.does_name_exist(parameter.name):
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

    def after_incoming_connection_removed(
        self,
        source_node: BaseNode,  # noqa: ARG002
        source_parameter: Parameter,  # noqa: ARG002
        target_parameter: Parameter,
    ) -> None:
        if target_parameter.name == "pipeline":
            self.pipe_params.runtime_parameters.remove_input_parameters()
            self.pipe_params.runtime_parameters.remove_output_parameters()

    def validate_before_node_run(self) -> list[Exception] | None:
        return self.pipe_params.runtime_parameters.validate_before_node_run()

    async def aprocess(self) -> None:
        self.preprocess()
        self.pipe_params.runtime_parameters.publish_output_image_preview_placeholder()
        pipe = self._get_pipeline()

        await asyncio.to_thread(self.pipe_params.runtime_parameters.process_pipeline, pipe)
