from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any, ClassVar

from diffusers_nodes_library.common.parameters.huggingface_pipeline_parameter import HuggingFacePipelineParameter
from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.traits.options import Options

if TYPE_CHECKING:
    from diffusers_nodes_library.common.nodes.diffusion_pipeline_builder_node import DiffusionPipelineBuilderNode
    from diffusers_nodes_library.common.parameters.diffusion.pipeline_type_parameters import (
        DiffusionPipelineTypePipelineParameters,
    )

logger = logging.getLogger("diffusers_nodes_library")


class DiffusionPipelineTypeParameters(ABC):
    START_PARAMS: ClassVar = ["pipeline", "provider", "pipeline_type"]
    END_PARAMS: ClassVar = ["loras", "logs"]

    def __init__(self, node: DiffusionPipelineBuilderNode):
        self._node = node
        self.did_pipeline_type_change = False
        self._pipeline_type_pipeline_params: DiffusionPipelineTypePipelineParameters
        self.set_pipeline_type_pipeline_params(self.pipeline_types[0])

    @property
    @abstractmethod
    def pipeline_type_dict(self) -> dict[str, type[DiffusionPipelineTypePipelineParameters]]:
        raise NotImplementedError

    @property
    def pipeline_types(self) -> list[str]:
        return list(self.pipeline_type_dict.keys())

    def set_pipeline_type_pipeline_params(self, pipeline_type: str) -> None:
        try:
            self._pipeline_type_pipeline_params = self.pipeline_type_dict[pipeline_type](self._node)
        except KeyError as e:
            msg = f"Unsupported pipeline type: {pipeline_type}"
            logger.error(msg)
            raise ValueError(msg) from e

    @property
    def pipeline_type_pipeline_params(self) -> DiffusionPipelineTypePipelineParameters:
        if self._pipeline_type_pipeline_params is None:
            msg = "Pipeline type builder parameters not initialized. Ensure provider parameter is set."
            logger.error(msg)
            raise ValueError(msg)
        return self._pipeline_type_pipeline_params

    def add_input_parameters(self) -> None:
        self._node.add_parameter(
            Parameter(
                name="pipeline_type",
                type="str",
                traits={Options(choices=self.pipeline_types)},
                tooltip="Type of diffusion pipeline to build",
                allowed_modes={ParameterMode.PROPERTY},
            )
        )

    def remove_input_parameters(self) -> None:
        self._node.remove_parameter_element_by_name("pipeline_type")
        self.pipeline_type_pipeline_params.remove_input_parameters()

    def before_value_set(self, parameter: Parameter, value: Any) -> None:
        if parameter.name == "pipeline_type":
            current_pipeline_type = self._node.get_parameter_value("pipeline_type")
            self.did_pipeline_type_change = current_pipeline_type != value

    def after_value_set(self, parameter: Parameter, value: Any) -> None:
        if parameter.name == "pipeline_type" and self.did_pipeline_type_change:
            self.regenerate_elements_for_pipeline_type(value)

    def regenerate_elements_for_pipeline_type(self, pipeline_type: str) -> None:
        self._node.save_parameter_properties()

        self.pipeline_type_pipeline_params.remove_input_parameters()
        self.set_pipeline_type_pipeline_params(pipeline_type)
        self.pipeline_type_pipeline_params.add_input_parameters()

        # Get all current element names
        all_element_names = [element.name for element in self._node.root_ui_element.children]

        # Build parameter groupings
        hf_param_names = HuggingFacePipelineParameter.get_hf_pipeline_parameter_names()
        start_params = DiffusionPipelineTypeParameters.START_PARAMS
        end_params = [*hf_param_names, *DiffusionPipelineTypeParameters.END_PARAMS]
        excluded_params = {*start_params, *end_params}

        # Assemble final order: start -> middle -> end
        middle_params = [name for name in all_element_names if name not in excluded_params]
        sorted_parameters = [*start_params, *middle_params, *end_params]

        self._node.reorder_elements(sorted_parameters)

        self._node.clear_parameter_cache()

    def get_config_kwargs(self) -> dict:
        return self.pipeline_type_pipeline_params.get_config_kwargs()
