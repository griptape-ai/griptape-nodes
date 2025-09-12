import logging

from diffusers_nodes_library.common.parameters.file_path_parameter import FilePathParameter
from diffusers_nodes_library.pipelines.wan.lora.wan_lora_parameters import (  # type: ignore[reportMissingImports]
    WanLoraParameters,  # type: ignore[reportMissingImports],  # type: ignore[reportMissingImports]
)
from diffusers_nodes_library.pipelines.wan.wan_pipeline_parameters import (
    WanPipelineParameters,  # type: ignore[reportMissingImports]
)
from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import ControlNode

logger = logging.getLogger("diffusers_nodes_library")


class WanLoraFromFile(ControlNode):
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.wan_params = WanPipelineParameters(self)
        self.lora_file_path_params = FilePathParameter(self)
        self.lora_weight_and_output_params = WanLoraParameters(self)
        self.lora_file_path_params.add_input_parameters()
        self.lora_weight_and_output_params.add_input_parameters()
        self.lora_weight_and_output_params.add_output_parameters()
        self.add_parameter(
            Parameter(
                name="trigger_phrase",
                default_value="",
                type="str",
                output_type="str",
                allowed_modes={ParameterMode.PROPERTY, ParameterMode.OUTPUT},
                tooltip="a phrase that must be included in the prompt in order to trigger the lora",
            )
        )

    def process(self) -> None:
        self.lora_file_path_params.validate_parameter_values()
        lora_path = str(self.lora_file_path_params.get_file_path())
        lora_weight = self.lora_weight_and_output_params.get_weight()
        self.lora_weight_and_output_params.set_output_lora({lora_path: lora_weight})
