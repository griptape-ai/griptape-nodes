import logging
from abc import ABC, abstractmethod
from typing import Any

from diffusers_nodes_library.common.parameters.diffusion.diffusion_pipeline_type_pipeline_parameters import (
    DiffusionPipelineTypePipelineParameters,
)
from diffusers_nodes_library.common.parameters.huggingface_pipeline_parameter import HuggingFacePipelineParameter
from griptape_nodes.exe_types.core_types import Parameter
from griptape_nodes.exe_types.node_types import BaseNode
from griptape_nodes.traits.options import Options

logger = logging.getLogger("diffusers_nodes_library")


class DiffusionPipelineTypeParameters(ABC):
    def __init__(self, node: BaseNode):
        self._node: BaseNode = node
        self.did_pipeline_type_change = False
        self.set_pipeline_type_pipeline_params(self.pipeline_types[0])

    @property
    @abstractmethod
    def pipeline_types(self) -> list[str]:
        raise NotImplementedError

    @abstractmethod
    def set_pipeline_type_pipeline_params(self, pipeline_type: str) -> None:
        raise NotImplementedError

    def add_input_parameters(self) -> None:
        self._node.add_parameter(
            Parameter(
                name="pipeline_type",
                type="str",
                traits={Options(choices=self.pipeline_types)},
                tooltip="Type of diffusion pipeline to build",
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
        self.set_pipeline_type_pipeline_params(pipeline_type)
        self.pipeline_type_pipeline_params.remove_input_parameters()
        self.pipeline_type_pipeline_params.add_input_parameters()

        # Get all current element names
        all_element_names = [element.name for element in self._node.root_ui_element.children]

        # Start with required positioning
        sorted_parameters = ["provider", "pipeline_type"]

        # Add all other parameters that aren't already positioned or at the end
        hf_param_names = HuggingFacePipelineParameter.get_hf_pipeline_parameter_names()
        end_params = {*hf_param_names, "pipeline", "logs"}
        positioned_params = {"provider", "pipeline_type"}

        sorted_parameters.extend(
            [
                param_name
                for param_name in all_element_names
                if param_name not in positioned_params and param_name not in end_params
            ]
        )

        # Add end parameters
        sorted_parameters.extend([*hf_param_names, "pipeline", "logs"])

        self._node.reorder_elements(sorted_parameters)

    @property
    @abstractmethod
    def pipeline_type_pipeline_params(self) -> DiffusionPipelineTypePipelineParameters:
        raise NotImplementedError

    def get_config_kwargs(self) -> dict:
        return self.pipeline_type_pipeline_params.get_config_kwargs()
