import logging
from typing import Any, ClassVar

from diffusers.pipelines.pipeline_utils import DiffusionPipeline  # type: ignore[reportMissingImports]

from diffusers_nodes_library.common.parameters.diffusion.pipeline_parameters import (
    DiffusionPipelineParameters,
)  # type: ignore[reportMissingImports]
from diffusers_nodes_library.common.parameters.log_parameter import (  # type: ignore[reportMissingImports]
    LogParameter,  # type: ignore[reportMissingImports]
)
from diffusers_nodes_library.common.utils.huggingface_utils import model_cache
from griptape_nodes.exe_types.core_types import Parameter
from griptape_nodes.exe_types.node_types import AsyncResult, BaseNode, ControlNode
from griptape_nodes.retained_mode.events.connection_events import (
    CreateConnectionRequest,
    IncomingConnection,
    ListConnectionsForNodeRequest,
    ListConnectionsForNodeResultSuccess,
    OutgoingConnection,
)
from griptape_nodes.retained_mode.events.parameter_events import RemoveParameterFromNodeRequest
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

logger = logging.getLogger("diffusers_nodes_library")


class DiffusionPipelineRuntimeNode(ControlNode):
    STATIC_PARAMS: ClassVar = ["pipeline"]
    START_PARAMS: ClassVar = ["pipeline"]
    END_PARAMS: ClassVar = ["logs"]

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
        self.log_params.clear_logs()

    def _get_pipeline(self) -> DiffusionPipeline:
        diffusion_pipeline_hash = self.get_parameter_value("pipeline")
        pipeline = model_cache._pipeline_cache.get(diffusion_pipeline_hash)
        if pipeline is None:
            error_msg = f"Pipeline with config hash '{diffusion_pipeline_hash}' not found in cache: {model_cache._pipeline_cache.keys()}"
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

    def remove_parameter_element_by_name(self, element_name: str) -> None:
        # HACK: `node.remove_parameter_element_by_name` does not remove connections so we need to use the retained mode request which does.  # noqa: FIX004
        # To avoid updating a ton of callers, we just override this method here.
        # TODO: Remove after https://github.com/griptape-ai/griptape-nodes/issues/2511
        if self.does_name_exist(element_name):
            GriptapeNodes.handle_request(
                RemoveParameterFromNodeRequest(parameter_name=element_name, node_name=self.name)
            )

    def process(self) -> AsyncResult:
        self.preprocess()
        self.pipe_params.runtime_parameters.publish_output_image_preview_placeholder()
        pipe = self._get_pipeline()

        yield lambda: self.pipe_params.runtime_parameters.process_pipeline(pipe)

    def _save_connections(self) -> tuple[list[IncomingConnection], list[OutgoingConnection]]:
        """Save all incoming and outgoing connections for this node, excluding pipeline parameter."""
        result = GriptapeNodes.handle_request(ListConnectionsForNodeRequest(node_name=self.name))
        if not isinstance(result, ListConnectionsForNodeResultSuccess):
            logger.error("Failed to list connections for node '%s'", self.name)
            return [], []
        # Exclude pipeline parameter since restoring it will trigger a cascade of changes
        incoming = [
            conn
            for conn in result.incoming_connections
            if conn.target_parameter_name not in DiffusionPipelineRuntimeNode.STATIC_PARAMS
        ]
        return incoming, result.outgoing_connections

    def _restore_connections(
        self, saved_incoming: list[IncomingConnection], saved_outgoing: list[OutgoingConnection]
    ) -> None:
        """Restore connections for parameters that still exist after parameter changes."""
        for conn in saved_incoming:
            if self.does_name_exist(conn.target_parameter_name):
                GriptapeNodes.handle_request(
                    CreateConnectionRequest(
                        source_node_name=conn.source_node_name,
                        source_parameter_name=conn.source_parameter_name,
                        target_node_name=self.name,
                        target_parameter_name=conn.target_parameter_name,
                    )
                )

        for conn in saved_outgoing:
            if self.does_name_exist(conn.source_parameter_name):
                GriptapeNodes.handle_request(
                    CreateConnectionRequest(
                        source_node_name=self.name,
                        source_parameter_name=conn.source_parameter_name,
                        target_node_name=conn.target_node_name,
                        target_parameter_name=conn.target_parameter_name,
                    )
                )
