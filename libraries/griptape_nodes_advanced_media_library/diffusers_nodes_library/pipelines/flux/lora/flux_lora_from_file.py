import logging
from typing import Any

from griptape_nodes.exe_types.node_types import AsyncResult, ControlNode
from diffusers_nodes_library.utils.parameter_utils import ( # type: ignore[reportMissingImports]
    FluxPipelineParameters,  # type: ignore[reportMissingImports]
    FluxLoraWeightAndOutputParameters,  # type: ignore[reportMissingImports]
    FilePathParameter,  # type: ignore[reportMissingImports]
)
from griptape_nodes.exe_types.core_types import Parameter

logger = logging.getLogger("diffusers_nodes_library")


class FluxLoraFromFile(ControlNode):
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.category = "image"
        self.description = "Generates an image from text and an image using the flux.1 dev model"
        self.flux_params = FluxPipelineParameters(self)
        self.lora_file_path_params = FilePathParameter(self)
        self.lora_weight_and_output_params = FluxLoraWeightAndOutputParameters(self)
        self.lora_file_path_params.add_input_parameters()
        self.lora_weight_and_output_params.add_input_parameters()
        self.lora_weight_and_output_params.add_output_parameters()        

    def after_value_set(self, parameter: Parameter, value: Any, modified_parameters_set: set[str]) -> None:
        if parameter.name == "output_lora":
            return
        self.process()

    def process(self) -> None:
        self.lora_file_path_params.validate_parameter_values()
        lora_path = self.lora_file_path_params.get_file_path()
        lora_weight = self.lora_weight_and_output_params.get_weight()
        self.lora_weight_and_output_params.set_output_lora({ lora_path: lora_weight})