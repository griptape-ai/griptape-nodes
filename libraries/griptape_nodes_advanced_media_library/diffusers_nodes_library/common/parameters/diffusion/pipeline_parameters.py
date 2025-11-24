import logging
from typing import Any

from diffusers_nodes_library.common.parameters.diffusion.allegro.runtime_parameters import (
    AllegroPipelineRuntimeParameters,
)
from diffusers_nodes_library.common.parameters.diffusion.amused.img2img_runtime_parameters import (
    AmusedImg2ImgPipelineRuntimeParameters,
)
from diffusers_nodes_library.common.parameters.diffusion.amused.inpaint_runtime_parameters import (
    AmusedInpaintPipelineRuntimeParameters,
)
from diffusers_nodes_library.common.parameters.diffusion.amused.runtime_parameters import (
    AmusedPipelineRuntimeParameters,
)
from diffusers_nodes_library.common.parameters.diffusion.audioldm.runtime_parameters import (
    AudioldmPipelineRuntimeParameters,
)
from diffusers_nodes_library.common.parameters.diffusion.audioldm2.runtime_parameters import (
    Audioldm2PipelineRuntimeParameters,
)
from diffusers_nodes_library.common.parameters.diffusion.depthcrafter.depthcrafter_runtime_parameters import (
    DepthCrafterPipelineRuntimeParameters,
)
from diffusers_nodes_library.common.parameters.diffusion.flux.controlnet_runtime_parameters import (
    FluxControlNetPipelineRuntimeParameters,
)
from diffusers_nodes_library.common.parameters.diffusion.flux.fill_runtime_parameters import (
    FluxFillPipelineRuntimeParameters,
)
from diffusers_nodes_library.common.parameters.diffusion.flux.img2img_runtime_parameters import (
    FluxImg2ImgPipelineRuntimeParameters,
)
from diffusers_nodes_library.common.parameters.diffusion.flux.kontext_runtime_parameters import (
    FluxKontextPipelineRuntimeParameters,
)
from diffusers_nodes_library.common.parameters.diffusion.flux.runtime_parameters import (
    FluxPipelineRuntimeParameters,
)
from diffusers_nodes_library.common.parameters.diffusion.flux.upscale_runtime_parameters import (
    FluxUpscalePipelineRuntimeParameters,
)
from diffusers_nodes_library.common.parameters.diffusion.qwen.controlnet_runtime_parameters import (
    QwenImageControlNetPipelineRuntimeParameters,
)
from diffusers_nodes_library.common.parameters.diffusion.qwen.edit_plus_runtime_parameters import (
    QwenImageEditPlusPipelineRuntimeParameters,
)
from diffusers_nodes_library.common.parameters.diffusion.qwen.edit_runtime_parameters import (
    QwenEditPipelineRuntimeParameters,
)
from diffusers_nodes_library.common.parameters.diffusion.qwen.img2img_runtime_parameters import (
    QwenImg2ImgPipelineRuntimeParameters,
)
from diffusers_nodes_library.common.parameters.diffusion.qwen.runtime_parameters import (
    QwenPipelineRuntimeParameters,
)
from diffusers_nodes_library.common.parameters.diffusion.qwen.upscale_runtime_parameters import (
    QwenUpscalePipelineRuntimeParameters,
)
from diffusers_nodes_library.common.parameters.diffusion.runtime_parameters import (
    DiffusionPipelineRuntimeParameters,
)
from diffusers_nodes_library.common.parameters.diffusion.stable_diffusion.runtime_parameters import (
    StableDiffusionPipelineRuntimeParameters,
)
from diffusers_nodes_library.common.parameters.diffusion.stable_diffusion_3.runtime_parameters import (
    StableDiffusion3PipelineRuntimeParameters,
)
from diffusers_nodes_library.common.parameters.diffusion.stable_diffusion_ae.runtime_parameters import (
    StableDiffusionAttendAndExcitePipelineRuntimeParameters,
)
from diffusers_nodes_library.common.parameters.diffusion.stable_diffusion_diffedit.runtime_parameters import (
    StableDiffusionDiffEditPipelineRuntimeParameters,
)
from diffusers_nodes_library.common.parameters.diffusion.wan.img2vid_runtime_parameters import (
    WanImageToVideoPipelineRuntimeParameters,
)
from diffusers_nodes_library.common.parameters.diffusion.wan.runtime_parameters import (
    WanPipelineRuntimeParameters,
)
from diffusers_nodes_library.common.parameters.diffusion.wan.vace_runtime_parameters import (
    WanVacePipelineRuntimeParameters,
)
from diffusers_nodes_library.common.parameters.diffusion.wan.vid2vid_runtime_parameters import (
    WanVideoToVideoPipelineRuntimeParameters,
)
from diffusers_nodes_library.common.parameters.diffusion.wuerstchen.runtime_parameters import (
    WuerstchenCombinedPipelineRuntimeParameters,
)
from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import BaseNode

logger = logging.getLogger("diffusers_nodes_library")


class DiffusionPipelineParameters:
    def __init__(self, node: BaseNode):
        self._node: BaseNode = node
        self._runtime_parameters: DiffusionPipelineRuntimeParameters
        self.set_runtime_parameters("FluxPipeline")

    def add_input_parameters(self) -> None:
        self._node.add_parameter(
            Parameter(
                name="pipeline",
                type="Pipeline Config",
                tooltip="🤗 Diffusion Pipeline",
                allowed_modes={ParameterMode.INPUT},
            )
        )

    def set_runtime_parameters(self, pipeline_class: str) -> None:  # noqa: C901 PLR0912 PLR0915
        match pipeline_class:
            case "FluxPipeline":
                self._runtime_parameters = FluxPipelineRuntimeParameters(self._node)
            case "FluxFillPipeline":
                self._runtime_parameters = FluxFillPipelineRuntimeParameters(self._node)
            case "FluxControlNetPipeline":
                self._runtime_parameters = FluxControlNetPipelineRuntimeParameters(self._node)
            case "FluxKontextPipeline":
                self._runtime_parameters = FluxKontextPipelineRuntimeParameters(self._node)
            case "FluxImg2ImgPipeline":
                self._runtime_parameters = FluxImg2ImgPipelineRuntimeParameters(self._node)
            case "FluxUpscalePipeline":
                self._runtime_parameters = FluxUpscalePipelineRuntimeParameters(self._node)
            case "AllegroPipeline":
                self._runtime_parameters = AllegroPipelineRuntimeParameters(self._node)
            case "AmusedPipeline":
                self._runtime_parameters = AmusedPipelineRuntimeParameters(self._node)
            case "AmusedImg2ImgPipeline":
                self._runtime_parameters = AmusedImg2ImgPipelineRuntimeParameters(self._node)
            case "AmusedInpaintPipeline":
                self._runtime_parameters = AmusedInpaintPipelineRuntimeParameters(self._node)
            case "AudioLDMPipeline":
                self._runtime_parameters = AudioldmPipelineRuntimeParameters(self._node)
            case "AudioLDM2Pipeline":
                self._runtime_parameters = Audioldm2PipelineRuntimeParameters(self._node)
            case "DepthCrafterVideoDiffusionPipeline":
                self._runtime_parameters = DepthCrafterPipelineRuntimeParameters(self._node)
            case "QwenImagePipeline":
                self._runtime_parameters = QwenPipelineRuntimeParameters(self._node)
            case "QwenImageImg2ImgPipeline":
                self._runtime_parameters = QwenImg2ImgPipelineRuntimeParameters(self._node)
            case "QwenImageEditPipeline":
                self._runtime_parameters = QwenEditPipelineRuntimeParameters(self._node)
            case "QwenImageEditPlusPipeline":
                self._runtime_parameters = QwenImageEditPlusPipelineRuntimeParameters(self._node)
            case "QwenImageUpscalePipeline":
                self._runtime_parameters = QwenUpscalePipelineRuntimeParameters(self._node)
            case "QwenImageControlNetPipeline":
                self._runtime_parameters = QwenImageControlNetPipelineRuntimeParameters(self._node)
            case "StableDiffusionPipeline":
                self._runtime_parameters = StableDiffusionPipelineRuntimeParameters(self._node)
            case "StableDiffusion3Pipeline":
                self._runtime_parameters = StableDiffusion3PipelineRuntimeParameters(self._node)
            case "StableDiffusionAttendAndExcitePipeline":
                self._runtime_parameters = StableDiffusionAttendAndExcitePipelineRuntimeParameters(self._node)
            case "StableDiffusionDiffEditPipeline":
                self._runtime_parameters = StableDiffusionDiffEditPipelineRuntimeParameters(self._node)
            case "WanPipeline":
                self._runtime_parameters = WanPipelineRuntimeParameters(self._node)
            case "WanVacePipeline":
                self._runtime_parameters = WanVacePipelineRuntimeParameters(self._node)
            case "WanImageToVideoPipeline":
                self._runtime_parameters = WanImageToVideoPipelineRuntimeParameters(self._node)
            case "WanVideoToVideoPipeline":
                self._runtime_parameters = WanVideoToVideoPipelineRuntimeParameters(self._node)
            case "WuerstchenCombinedPipeline":
                self._runtime_parameters = WuerstchenCombinedPipelineRuntimeParameters(self._node)
            case _:
                msg = f"Unsupported pipeline class: {pipeline_class}"
                logger.error(msg)
                raise ValueError(msg)

    def after_value_set(self, parameter: Parameter, value: Any) -> None:
        if parameter.name != "pipeline":
            return

        if value is None:
            logger.warning("Value was None, ignoring...")
            return

        pipeline_class = value.split("-", 1)[0]
        self.set_runtime_parameters(pipeline_class)

        self.runtime_parameters.add_input_parameters()
        self.runtime_parameters.add_output_parameters()

    @property
    def runtime_parameters(self) -> DiffusionPipelineRuntimeParameters:
        if self._runtime_parameters is None:
            msg = "Runtime parameters not initialized. Ensure pipeline parameter is set."
            logger.error(msg)
            raise ValueError(msg)
        return self._runtime_parameters
