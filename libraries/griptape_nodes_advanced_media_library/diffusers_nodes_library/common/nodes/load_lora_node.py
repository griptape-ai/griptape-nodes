import logging

from diffusers_nodes_library.common.parameters.file_path_parameter import FilePathParameter
from diffusers_nodes_library.pipelines.flux.lora.flux_lora_parameters import (  # type: ignore[reportMissingImports]
    FluxLoraParameters,  # type: ignore[reportMissingImports]
)
from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import ControlNode

logger = logging.getLogger("diffusers_nodes_library")


class LoadLora(ControlNode):
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.lora_file_path_params = FilePathParameter(
            self,
            file_types=[".safetensors", ".sft", ".pt", ".bin", ".json", ".lora"],
            tooltip="Absolute path to a local LoRA file",
        )
        self.lora_weight_and_output_params = FluxLoraParameters(self)
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
                tooltip="A phrase that shall be included in the prompt to ensure triggering the lora",
                hide=True,
            )
        )

    def process(self) -> None:
        self.lora_file_path_params.validate_parameter_values()
        lora_path = str(self.lora_file_path_params.get_file_path())
        lora_weight = self.lora_weight_and_output_params.get_weight()
        self.lora_weight_and_output_params.set_output_lora({lora_path: lora_weight})
