from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, ClassVar

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
from diffusers_nodes_library.common.parameters.diffusion.depthcrafter.pipeline_type_parameters import (
    DepthCrafterPipelineTypeParameters,
)
from diffusers_nodes_library.common.parameters.diffusion.flux.pipeline_type_parameters import (
    FluxPipelineTypeParameters,
)
from diffusers_nodes_library.common.parameters.diffusion.flux2.pipeline_type_parameters import (
    Flux2PipelineTypeParameters,
)
from diffusers_nodes_library.common.parameters.diffusion.ltx2.pipeline_type_parameters import (
    LTX2PipelineTypeParameters,
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
from diffusers_nodes_library.common.parameters.diffusion.z_image.pipeline_type_parameters import (
    ZImagePipelineTypeParameters,
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
    PROVIDER_MAP: ClassVar = {
        "Flux": FluxPipelineTypeParameters,
        "Flux2": Flux2PipelineTypeParameters,
        "Allegro": AllegroPipelineTypeParameters,
        "Amused": AmusedPipelineTypeParameters,
        "AudioLDM": AudioldmPipelineTypeParameters,
        "DepthCrafter": DepthCrafterPipelineTypeParameters,
        "LTX-2": LTX2PipelineTypeParameters,
        "Qwen": QwenPipelineTypeParameters,
        "Stable Diffusion": StableDiffusionPipelineTypeParameters,
        "WAN": WanPipelineTypeParameters,
        "Wuerstchen": WuerstchenPipelineTypeParameters,
        "Z-Image": ZImagePipelineTypeParameters,
        "Custom": CustomPipelineTypeParameters,
    }

    def __init__(self, node: DiffusionPipelineBuilderNode):
        self.provider_choices = list(self.PROVIDER_MAP.keys())
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
                ui_options={"placeholder_text": "Select Provider"},
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
        if provider not in self.PROVIDER_MAP:
            msg = f"Unsupported pipeline provider: {provider}"
            logger.error(msg)
            raise ValueError(msg)

        provider_class = self.PROVIDER_MAP[provider]
        self._pipeline_type_parameters = provider_class(self._node)

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
        # Save parameter properties and connections before removing parameters
        self._node.save_parameter_properties()
        saved_incoming, saved_outgoing = self._node._save_connections()

        self.pipeline_type_parameters.remove_input_parameters()
        self.set_pipeline_type_parameters(provider)
        self.pipeline_type_parameters.add_input_parameters()

        first_pipeline_type = self.pipeline_type_parameters.pipeline_types[0]
        self._node.set_parameter_value("pipeline_type", first_pipeline_type)

        # Restore connections after adding parameters
        self._node._restore_connections(saved_incoming, saved_outgoing)

        # Reorder parameters to maintain consistent layout
        self._node.reorder_parameters_by_groups()

        self._node.clear_parameter_cache()

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
