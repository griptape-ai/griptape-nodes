import logging
from typing import Any

from diffusers_nodes_library.common.parameters.diffusion.allegro.allegro_pipeline_type_parameters import (
    AllegroPipelineTypeParameters,
)
from diffusers_nodes_library.common.parameters.diffusion.amused.amused_pipeline_type_parameters import (
    AmusedPipelineTypeParameters,
)
from diffusers_nodes_library.common.parameters.diffusion.audioldm.audioldm_pipeline_type_parameters import (
    AudioldmPipelineTypeParameters,
)
from diffusers_nodes_library.common.parameters.diffusion.diffusion_pipeline_type_parameters import (
    DiffusionPipelineTypeParameters,
)
from diffusers_nodes_library.common.parameters.diffusion.flux.flux_pipeline_type_parameters import (
    FluxPipelineTypeParameters,
)
from diffusers_nodes_library.common.parameters.diffusion.stable_diffusion.stable_diffusion_pipeline_type_parameters import (
    StableDiffusionPipelineTypeParameters,
)
from diffusers_nodes_library.common.parameters.diffusion.wan.wan_pipeline_type_parameters import (
    WanPipelineTypeParameters,
)
from diffusers_nodes_library.common.parameters.diffusion.wuerstchen.wuerstchen_pipeline_type_parameters import (
    WuerstchenPipelineTypeParameters,
)
from diffusers_nodes_library.common.parameters.huggingface_pipeline_parameter import HuggingFacePipelineParameter
from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import BaseNode
from griptape_nodes.traits.options import Options

logger = logging.getLogger("diffusers_nodes_library")


class DiffusionPipelineBuilderParameters:
    def __init__(self, node: BaseNode):
        self.provider_choices = ["Flux", "Allegro", "Amused", "AudioLDM", "Stable Diffusion", "WAN", "Wuerstchen"]
        self._node = node
        self._pipeline_type_parameters: DiffusionPipelineTypeParameters
        self.set_pipeline_type_parameters(self.provider_choices[0])

    def add_input_parameters(self) -> None:
        self._node.add_parameter(
            Parameter(
                name="provider",
                default_value=self.provider_choices[0],
                type="str",
                traits={Options(choices=self.provider_choices)},
                tooltip="AI model provider",
            )
        )
        self._pipeline_type_parameters.add_input_parameters()

    def add_output_parameters(self) -> None:
        self._node.add_parameter(
            Parameter(
                name="pipeline",
                output_type="Pipeline Config",
                default_value=None,
                tooltip="Built and cached pipeline configuration",
                allowed_modes={ParameterMode.OUTPUT},
                ui_options={"display_name": "pipeline"},
                # This will be a complex object that cannot serialize and could contain private keys; it needs to be assigned at runtime.
                serializable=False,
            )
        )

    def set_pipeline_type_parameters(self, provider: str) -> None:
        match provider:
            case "Flux":
                self._pipeline_type_parameters = FluxPipelineTypeParameters(self._node)
            case "Allegro":
                self._pipeline_type_parameters = AllegroPipelineTypeParameters(self._node)
            case "Amused":
                self._pipeline_type_parameters = AmusedPipelineTypeParameters(self._node)
            case "AudioLDM":
                self._pipeline_type_parameters = AudioldmPipelineTypeParameters(self._node)
            case "Stable Diffusion":
                self._pipeline_type_parameters = StableDiffusionPipelineTypeParameters(self._node)
            case "WAN":
                self._pipeline_type_parameters = WanPipelineTypeParameters(self._node)
            case "Wuerstchen":
                self._pipeline_type_parameters = WuerstchenPipelineTypeParameters(self._node)
            case _:
                msg = f"Unsupported pipeline provider: {provider}"
                logger.error(msg)
                raise ValueError(msg)

    def after_value_set(self, parameter: Parameter, value: Any) -> None:
        reset_provider = parameter.name == "provider"
        if reset_provider:
            self.pipeline_type_parameters.remove_input_parameters()
            self.set_pipeline_type_parameters(value)
            self._node.set_parameter_value("pipeline_type", self.pipeline_type_parameters.pipeline_types[0])
            self.pipeline_type_parameters.add_input_parameters()

            sorted_parameters = ["provider"]
            sorted_parameters.extend(
                [
                    param.name
                    for param in self._node.parameters
                    if param.name
                    not in [
                        "provider",
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
        self.pipeline_type_parameters.after_value_set(parameter, value)

    @property
    def pipeline_type_parameters(self) -> DiffusionPipelineTypeParameters:
        if self._pipeline_type_parameters is None:
            msg = "Pipeline type parameters not initialized. Ensure provider parameter is set."
            logger.error(msg)
            raise ValueError(msg)
        return self._pipeline_type_parameters

    def get_provider(self) -> str:
        return self._node.get_parameter_value("provider")

    def get_config_kwargs(self) -> dict:
        return {
            **self.pipeline_type_parameters.get_config_kwargs(),
            "provider": self.get_provider(),
        }
