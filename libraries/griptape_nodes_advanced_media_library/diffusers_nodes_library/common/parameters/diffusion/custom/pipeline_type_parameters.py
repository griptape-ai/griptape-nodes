import logging

from diffusers_nodes_library.common.parameters.diffusion.allegro.pipeline_type_parameters import AllegroPipelineTypeDict
from diffusers_nodes_library.common.parameters.diffusion.amused.pipeline_type_parameters import AmusedPipelineTypeDict
from diffusers_nodes_library.common.parameters.diffusion.audioldm.pipeline_type_parameters import (
    AudioldmPipelineTypeDict,
)
from diffusers_nodes_library.common.parameters.diffusion.depthcrafter.pipeline_type_parameters import (
    DepthCrafterPipelineTypeDict,
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
from griptape_nodes.exe_types.core_types import Parameter, ParameterMessage, ParameterMode
from griptape_nodes.traits.options import Options

logger = logging.getLogger("diffusers_nodes_library")


AllPipelineTypes: dict[str, type[DiffusionPipelineTypePipelineParameters]] = {
    **AllegroPipelineTypeDict,
    **AmusedPipelineTypeDict,
    **AudioldmPipelineTypeDict,
    **DepthCrafterPipelineTypeDict,
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

    def set_pipeline_type_pipeline_params(self, pipeline_type: str) -> None:
        try:
            self._pipeline_type_pipeline_params = self.pipeline_type_dict[pipeline_type](
                self._node, list_all_models=True
            )
        except KeyError as e:
            msg = f"Unsupported pipeline type: {pipeline_type}"
            logger.error(msg)
            raise ValueError(msg) from e

    def add_input_parameters(self) -> None:
        self._node.add_node_element(
            ParameterMessage(
                name="custom_pipeline_type_parameter_notice",
                title="Custom Pipelines",
                variant="info",
                value="In 'Custom' mode all compatibility guardrails are off. Ensure you are selecting compatible pipeline types and models.",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="pipeline_type",
                type="str",
                traits={Options(choices=self.pipeline_types)},
                tooltip="Type of diffusion pipeline to build",
                allowed_modes={ParameterMode.PROPERTY},
                ui_options={"show_search": True},
            )
        )

    def remove_input_parameters(self) -> None:
        self._node.remove_parameter_element_by_name("custom_pipeline_type_parameter_notice")
        self._node.remove_parameter_element_by_name("pipeline_type")
        self.pipeline_type_pipeline_params.remove_input_parameters()
