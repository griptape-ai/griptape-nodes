import logging

from diffusers_nodes_library.common.parameters.diffusion.allegro.pipeline_type_parameters import AllegroPipelineTypeDict
from diffusers_nodes_library.common.parameters.diffusion.amused.pipeline_type_parameters import AmusedPipelineTypeDict
from diffusers_nodes_library.common.parameters.diffusion.audioldm.pipeline_type_parameters import (
    AudioldmPipelineTypeDict,
)
from diffusers_nodes_library.common.parameters.diffusion.diffusion_pipeline_type_parameters import (
    DiffusionPipelineTypeParameters,
)
from diffusers_nodes_library.common.parameters.diffusion.flux.pipeline_type_parameters import FluxPipelineTypeDict
from diffusers_nodes_library.common.parameters.diffusion.pipeline_type_parameters import (
    DiffusionPipelineTypePipelineParameters,
)
from diffusers_nodes_library.common.parameters.diffusion.qwen.pipeline_type_parameters import QwenPipelineTypeDict
from diffusers_nodes_library.common.parameters.diffusion.stable_diffusion.pipeline_type_parameters import (
    StableDiffusionPipelineTypeDict,
)
from diffusers_nodes_library.common.parameters.diffusion.wan.pipeline_type_parameters import WanPipelineTypeDict
from diffusers_nodes_library.common.parameters.diffusion.wuerstchen.pipeline_type_parameters import (
    WuerstchenPipelineTypeDict,
)
from griptape_nodes.exe_types.core_types import ParameterMessage

logger = logging.getLogger("diffusers_nodes_library")


AllPipelineTypes: dict[str, type[DiffusionPipelineTypePipelineParameters]] = {
    **AllegroPipelineTypeDict,
    **AmusedPipelineTypeDict,
    **AudioldmPipelineTypeDict,
    **FluxPipelineTypeDict,
    **QwenPipelineTypeDict,
    **StableDiffusionPipelineTypeDict,
    **WanPipelineTypeDict,
    **WuerstchenPipelineTypeDict,
}


class CustomPipelineTypeParameters(DiffusionPipelineTypeParameters):
    @property
    def pipeline_type_dict(self) -> dict[str, type[DiffusionPipelineTypePipelineParameters]]:
        return AllPipelineTypes
    
    def add_input_parameters(self) -> None:
        self._node.add_node_element(
            ParameterMessage(
                name="custom_pipeline_type_parameter_notice",
                title="Custom Pipelines",
                variant="info",
                value="In 'Custom' mode all guardrails are off. Ensure you are selecting compatible pipeline types and models.",
            )
        )
        super().add_input_parameters()

    def remove_input_parameters(self) -> None:
        self._node.remove_parameter_element_by_name("custom_pipeline_type_parameter_notice")
        return super().remove_input_parameters()
