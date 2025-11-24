import logging
from typing import Any, ClassVar

from diffusers.pipelines.pipeline_utils import DiffusionPipeline  # type: ignore[reportMissingImports]

from diffusers_nodes_library.common.mixins.parameter_connection_preservation_mixin import (
    ParameterConnectionPreservationMixin,
)
from diffusers_nodes_library.common.parameters.diffusion.pipeline_parameters import (
    DiffusionPipelineParameters,
)
from diffusers_nodes_library.common.utils.huggingface_utils import model_cache
from diffusers_nodes_library.common.utils.pipeline_utils import cleanup_memory_caches
from griptape_nodes.exe_types.core_types import Parameter
from griptape_nodes.exe_types.node_types import AsyncResult, BaseNode, ControlNode
from griptape_nodes.exe_types.param_components.log_parameter import LogParameter
from griptape_nodes.exe_types.param_components.progress_bar_component import ProgressBarComponent
from griptape_nodes.retained_mode.events.parameter_events import RemoveParameterFromNodeRequest
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

logger = logging.getLogger("diffusers_nodes_library")


class DiffusionPipelineRuntimeNode(ParameterConnectionPreservationMixin, ControlNode):
    STATIC_PARAMS: ClassVar = ["pipeline"]
    START_PARAMS: ClassVar = ["pipeline"]
    END_PARAMS: ClassVar = ["progress", "logs"]

    def __init__(self, **kwargs) -> None:
        self._initializing = True
        super().__init__(**kwargs)
        self.pipe_params = DiffusionPipelineParameters(self)
        self.pipe_params.add_input_parameters()

        self.progress_bar_component = ProgressBarComponent(self)
        self.progress_bar_component.add_property_parameters()

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

        saved_incoming = []
        saved_outgoing = []
        if did_pipeline_change:
            saved_incoming, saved_outgoing = self._save_connections()
            self.pipe_params.runtime_parameters.remove_input_parameters()
            self.pipe_params.runtime_parameters.remove_output_parameters()

        self.pipe_params.after_value_set(parameter, value)

        if did_pipeline_change:
            start_params = DiffusionPipelineRuntimeNode.START_PARAMS
            end_params = DiffusionPipelineRuntimeNode.END_PARAMS
            excluded_params = {*start_params, *end_params}

            middle_elements = [
                element.name for element in self.root_ui_element._children if element.name not in excluded_params
            ]
            sorted_parameters = [*start_params, *middle_elements, *end_params]

            self.reorder_elements(sorted_parameters)

        self.pipe_params.runtime_parameters.after_value_set(parameter, value)

        if did_pipeline_change:
            self._restore_connections(saved_incoming, saved_outgoing)

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
        self.progress_bar_component.reset()
        self.log_params.clear_logs()

    def _get_pipeline(self) -> DiffusionPipeline:
        diffusion_pipeline_hash = self.get_parameter_value("pipeline")
        pipeline = model_cache.get_pipeline(diffusion_pipeline_hash)
        if pipeline is None:
            # Attempt to rebuild the pipeline from the connected builder node if not in the cache, this should only happen in exceptional cases: https://github.com/griptape-ai/griptape-nodes/issues/2578
            try:
                connections = GriptapeNodes.FlowManager().get_connections()
                node_connections = connections.incoming_index.get(self.name)
                pipeline_connection_id = node_connections.get("pipeline") if node_connections else None
                pipeline_connection = (
                    connections.connections.get(pipeline_connection_id[0]) if pipeline_connection_id else None
                )
                builder_node = pipeline_connection.source_node if pipeline_connection else None
                return model_cache.get_or_build_pipeline(diffusion_pipeline_hash, builder_node._build_pipeline)  # type: ignore[reportAttributeAccessIssue, reportOptionalMemberAccess]
            except Exception as e:
                logger.error("Error while attempting to rebuild pipeline from builder node: %s", e)
                error_msg = f"Pipeline with config hash '{diffusion_pipeline_hash}' not found in cache and could not be rebuilt: {model_cache._pipeline_cache.keys()}"
                raise RuntimeError(error_msg) from e
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

    def remove_parameter_element_by_name(self, element_name: str) -> None:
        # HACK: `node.remove_parameter_element_by_name` does not remove connections so we need to use the retained mode request which does.  # noqa: FIX004
        # To avoid updating a ton of callers, we just override this method here.
        # TODO: Remove after https://github.com/griptape-ai/griptape-nodes/issues/2511
        if self.get_element_by_name_and_type(element_name):
            GriptapeNodes.handle_request(
                RemoveParameterFromNodeRequest(parameter_name=element_name, node_name=self.name)
            )

    def process(self) -> AsyncResult:
        self.preprocess()
        self.pipe_params.runtime_parameters.publish_output_image_preview_placeholder()
        pipe = self._get_pipeline()

        def work() -> Any:
            try:
                return self.pipe_params.runtime_parameters.process_pipeline(pipe)
            except Exception:
                logger.exception("%s: Diffusion Pipeline execution failed", self.name)
                # Aggressive cleanup on failure
                cleanup_memory_caches()
                raise

        yield work
