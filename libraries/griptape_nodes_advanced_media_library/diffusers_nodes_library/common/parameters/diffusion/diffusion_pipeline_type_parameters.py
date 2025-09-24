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
                default_value=self.pipeline_types[0],
                type="str",
                traits={Options(choices=self.pipeline_types)},
                tooltip="Type of diffusion pipeline to build",
            )
        )
        self.set_pipeline_type_pipeline_params(self._node.get_parameter_value("pipeline_type"))
        self.pipeline_type_pipeline_params.add_input_parameters()

    def remove_input_parameters(self) -> None:
        self._node.remove_parameter_element_by_name("pipeline_type")
        self.pipeline_type_pipeline_params.remove_input_parameters()

    def after_value_set(self, parameter: Parameter, value: Any) -> None:
        reset_pipeline_type_pipeline_params = parameter.name == "pipeline_type"
        if reset_pipeline_type_pipeline_params:
            self.pipeline_type_pipeline_params.remove_input_parameters()
            self.set_pipeline_type_pipeline_params(value)
            self.pipeline_type_pipeline_params.add_input_parameters()

            sorted_parameters = ["provider", "pipeline_type"]
            sorted_parameters.extend(
                [
                    param.name
                    for param in self._node.parameters
                    if param.name
                    not in [
                        "provider",
                        "pipeline_type",
                        *HuggingFacePipelineParameter.get_hf_pipeline_parameter_names(),
                        "pipeline",
                        "logs",
                    ]
                ]
            )
            sorted_parameters.extend(
                [*HuggingFacePipelineParameter.get_hf_pipeline_parameter_names(), "pipeline", "logs"]
            )
            self._node.reorder_elements(sorted_parameters)

    @property
    @abstractmethod
    def pipeline_type_pipeline_params(self) -> DiffusionPipelineTypePipelineParameters:
        raise NotImplementedError

    def get_config_kwargs(self) -> dict:
        return self.pipeline_type_pipeline_params.get_config_kwargs()
