import logging
from typing import Any

from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import BaseNode
from griptape_nodes.traits.options import Options

logger = logging.getLogger("diffusers_nodes_library")


class HuggingFacePipelineParameter:
    def __init__(self, node: BaseNode):
        self._node = node

    def get_hf_pipeline_parameters(self) -> dict[str, Any]:
        return {
            "memory_optimization_strategy": self._node.get_parameter_value("memory_optimization_strategy"),
            "attention_slicing": self._node.get_parameter_value("attention_slicing"),
            "vae_slicing": self._node.get_parameter_value("vae_slicing"),
            "transformer_layerwise_casting": self._node.get_parameter_value("transformer_layerwise_casting"),
            "cpu_offload_strategy": self._node.get_parameter_value("cpu_offload_strategy"),
            "quantization_mode": self._node.get_parameter_value("quantization_mode"),
        }

    def add_input_parameters(self) -> None:
        memory_optimization_strategy_choices = ["Automatic", "Manual"]
        self._node.add_parameter(
            Parameter(
                name="memory_optimization_strategy",
                default_value=memory_optimization_strategy_choices[0],
                type="str",
                traits={
                    Options(
                        choices=memory_optimization_strategy_choices,
                    )
                },
                tooltip="Memory Optimization Strategy",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="attention_slicing",
                type="bool",
                output_type="bool",
                tooltip="Enable attention slicing to reduce memory usage.",
                default_value=False,
            )
        )
        self._node.add_parameter(
            Parameter(
                name="vae_slicing",
                type="bool",
                output_type="bool",
                tooltip="Enable VAE slicing to reduce memory usage.",
                default_value=False,
            )
        )
        self._node.add_parameter(
            Parameter(
                name="transformer_layerwise_casting",
                type="bool",
                output_type="bool",
                tooltip="Enable transformer layerwise casting to reduce memory usage.",
                default_value=False,
            )
        )
        cpu_offload_strategy_choices = ["None", "Model", "Sequential"]
        self._node.add_parameter(
            Parameter(
                name="cpu_offload_strategy",
                default_value=cpu_offload_strategy_choices[0],
                type="str",
                traits={
                    Options(
                        choices=cpu_offload_strategy_choices,
                    )
                },
                tooltip="CPU Offload Strategy",
            )
        )
        quantization_mode_choices = ["None", "fp8", "int8", "int4"]
        self._node.add_parameter(
            Parameter(
                name="quantization_mode",
                type="str",
                default_value=quantization_mode_choices[0],
                allowed_modes={ParameterMode.PROPERTY},
                tooltip="Quantization strategy: none/fp8/int8/int4",
                traits={Options(choices=quantization_mode_choices)},
            )
        )
