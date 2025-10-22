from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from diffusers_nodes_library.common.parameters.diffusion.allegro.pipeline_type_parameters import (
    AllegroPipelineTypeParameters,
)
from diffusers_nodes_library.common.parameters.diffusion.amused.pipeline_type_parameters import (
    AmusedPipelineTypeParameters,
)
from diffusers_nodes_library.common.parameters.diffusion.audioldm.pipeline_type_parameters import (
    AudioldmPipelineTypeParameters,
)
from diffusers_nodes_library.common.parameters.diffusion.custom.pipeline_type_parameters import (
    CustomPipelineTypeParameters,
)
from diffusers_nodes_library.common.parameters.diffusion.flux.pipeline_type_parameters import (
    FluxPipelineTypeParameters,
)
from diffusers_nodes_library.common.parameters.diffusion.qwen.pipeline_type_parameters import (
    QwenPipelineTypeParameters,
)
from diffusers_nodes_library.common.parameters.diffusion.stable_diffusion.pipeline_type_parameters import (
    StableDiffusionPipelineTypeParameters,
)
from diffusers_nodes_library.common.parameters.diffusion.wan.pipeline_type_parameters import (
    WanPipelineTypeParameters,
)
from diffusers_nodes_library.common.parameters.diffusion.wuerstchen.pipeline_type_parameters import (
    WuerstchenPipelineTypeParameters,
)
from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.traits.options import Options

if TYPE_CHECKING:
    from diffusers_nodes_library.common.nodes.diffusion_pipeline_builder_node import DiffusionPipelineBuilderNode
    from diffusers_nodes_library.common.parameters.diffusion.diffusion_pipeline_type_parameters import (
        DiffusionPipelineTypeParameters,
    )

logger = logging.getLogger("diffusers_nodes_library")


class DiffusionPipelineBuilderParameters:
    def __init__(self, node: DiffusionPipelineBuilderNode):
        self.provider_choices = [
            "Flux",
            "Allegro",
            "Amused",
            "AudioLDM",
            "Qwen",
            "Stable Diffusion",
            "WAN",
            "Wuerstchen",
            "Custom",
        ]
        self._node = node
        self._pipeline_type_parameters: DiffusionPipelineTypeParameters
        self.did_provider_change = False
        self.set_pipeline_type_parameters(self.provider_choices[0])

    def add_input_parameters(self) -> None:
        self._node.add_parameter(
            Parameter(
                name="provider",
                type="str",
                traits={Options(choices=self.provider_choices)},
                tooltip="AI model provider",
                allowed_modes={ParameterMode.PROPERTY},
            )
        )

    def add_output_parameters(self) -> None:
        self._node.add_parameter(
            Parameter(
                name="pipeline",
                output_type="Pipeline Config",
                default_value=None,
                tooltip="Built and cached pipeline configuration",
                allowed_modes={ParameterMode.OUTPUT},
                ui_options={"display_name": "pipeline"},
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
            case "Qwen":
                self._pipeline_type_parameters = QwenPipelineTypeParameters(self._node)
            case "Stable Diffusion":
                self._pipeline_type_parameters = StableDiffusionPipelineTypeParameters(self._node)
            case "WAN":
                self._pipeline_type_parameters = WanPipelineTypeParameters(self._node)
            case "Wuerstchen":
                self._pipeline_type_parameters = WuerstchenPipelineTypeParameters(self._node)
            case "Custom":
                self._pipeline_type_parameters = CustomPipelineTypeParameters(self._node)
            case _:
                msg = f"Unsupported pipeline provider: {provider}"
                logger.error(msg)
                raise ValueError(msg)

    def before_value_set(self, parameter: Parameter, value: Any) -> None:
        if parameter.name == "provider":
            current_provider = self._node.get_parameter_value("provider")
            self.did_provider_change = current_provider != value
        self.pipeline_type_parameters.before_value_set(parameter, value)

    def after_value_set(self, parameter: Parameter, value: Any) -> None:
        if parameter.name == "provider" and self.did_provider_change:
            self.regenerate_pipeline_type_parameters_for_provider(value)
        self.pipeline_type_parameters.after_value_set(parameter, value)

    def regenerate_pipeline_type_parameters_for_provider(self, provider: str) -> None:
        from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

        self._node.cache_param_attrs()

        # Remove old parameters (automatically caches param names via remove_parameter_element_by_name)
        self.pipeline_type_parameters.remove_input_parameters()

        # Switch to new provider and add its parameters
        self.set_pipeline_type_parameters(provider)
        self.pipeline_type_parameters.add_input_parameters()

        # Get desired parameter names from what actually exists on the node now
        desired_param_names = {param.name for param in self._node.parameters}
        cached_param_names = self._node.get_cached_param_names()

        # Determine which parameters to preserve (exist in both old and new)
        params_to_preserve = cached_param_names & desired_param_names

        # Update Connection objects to reference new Parameter instances
        connections = GriptapeNodes.FlowManager().get_connections()
        connections.update_parameter_references_after_replacement(self._node, params_to_preserve)

        # Set the pipeline_type parameter to the first available type
        first_pipeline_type = self.pipeline_type_parameters.pipeline_types[0]
        self._node.set_parameter_value("pipeline_type", first_pipeline_type)

        self._node.clear_param_attrs_cache()
        self._node.clear_param_names_cache()

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
