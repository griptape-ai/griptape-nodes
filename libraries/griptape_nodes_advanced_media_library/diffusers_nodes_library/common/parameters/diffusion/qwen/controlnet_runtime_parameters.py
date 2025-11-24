import logging
from typing import Any

from diffusers.pipelines.pipeline_utils import DiffusionPipeline  # type: ignore[reportMissingImports]
from griptape.artifacts import ImageUrlArtifact
from PIL.Image import Image
from pillow_nodes_library.utils import (  # type: ignore[reportMissingImports]
    image_artifact_to_pil,
)
from utils.image_utils import load_image_from_url_artifact

from diffusers_nodes_library.common.parameters.diffusion.qwen.common import qwen_latents_to_image_pil
from diffusers_nodes_library.common.parameters.diffusion.runtime_parameters import (
    DiffusionPipelineRuntimeParameters,
)
from griptape_nodes.exe_types.core_types import Parameter
from griptape_nodes.exe_types.node_types import BaseNode

logger = logging.getLogger("diffusers_nodes_library")


class QwenImageControlNetPipelineRuntimeParameters(DiffusionPipelineRuntimeParameters):
    def __init__(self, node: BaseNode):
        super().__init__(node)

    def _add_input_parameters(self) -> None:
        self._node.add_parameter(
            Parameter(
                name="control_image",
                input_types=["ImageArtifact", "ImageUrlArtifact"],
                type="ImageArtifact",
                tooltip="The ControlNet input condition to provide guidance to the model for generation.",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="prompt",
                default_value="",
                type="str",
                tooltip="The prompt or prompts to guide the image generation.",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="negative_prompt",
                default_value="",
                type="str",
                tooltip="The prompt or prompts not to guide the image generation.",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="controlnet_conditioning_scale",
                default_value=1.0,
                input_types=["float"],
                type="float",
                tooltip="Multiplied with the outputs of the ControlNet before they are added to the residual in the original model.",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="control_guidance_start",
                default_value=0.0,
                input_types=["float"],
                type="float",
                tooltip="The percentage of total steps at which the ControlNet starts applying.",
                ui_options={"slider": {"min_val": 0.0, "max_val": 1.0}, "step": 0.01},
            )
        )
        self._node.add_parameter(
            Parameter(
                name="control_guidance_end",
                default_value=1.0,
                input_types=["float"],
                type="float",
                tooltip="The percentage of total steps at which the ControlNet stops applying.",
                ui_options={"slider": {"min_val": 0.0, "max_val": 1.0}, "step": 0.01},
            )
        )
        # Default is not 1.0 like other qwen pipelines because of https://github.com/griptape-ai/griptape-nodes/pull/3275#discussion_r2555019559
        self._node.add_parameter(
            Parameter(
                name="true_cfg_scale",
                default_value=4.0,
                type="float",
                tooltip="True classifier-free guidance (guidance scale) is enabled when true_cfg_scale > 1 and negative_prompt is provided.",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="guidance_scale",
                default_value=3.5,
                type="float",
                tooltip="A guidance scale value for guidance distilled models. Leave empty to use true_cfg_scale instead.",
            )
        )

    def _remove_input_parameters(self) -> None:
        self._node.remove_parameter_element_by_name("prompt")
        self._node.remove_parameter_element_by_name("negative_prompt")
        self._node.remove_parameter_element_by_name("true_cfg_scale")
        self._node.remove_parameter_element_by_name("guidance_scale")
        self._node.remove_parameter_element_by_name("controlnet_conditioning_scale")
        self._node.remove_parameter_element_by_name("control_guidance_start")
        self._node.remove_parameter_element_by_name("control_guidance_end")
        self._node.remove_parameter_element_by_name("control_image")

    def _get_pipe_kwargs(self) -> dict:
        kwargs = {
            "prompt": self._node.get_parameter_value("prompt"),
            "negative_prompt": self._node.get_parameter_value("negative_prompt"),
            "true_cfg_scale": self._node.get_parameter_value("true_cfg_scale"),
            "control_image": self.get_control_image_pil(),
            "controlnet_conditioning_scale": self._node.get_parameter_value("controlnet_conditioning_scale"),
            "control_guidance_start": self._node.get_parameter_value("control_guidance_start"),
            "control_guidance_end": self._node.get_parameter_value("control_guidance_end"),
        }

        # Only add guidance_scale if it's not None (pipeline supports it optionally)
        guidance_scale = self._node.get_parameter_value("guidance_scale")
        if guidance_scale is not None:
            kwargs["guidance_scale"] = guidance_scale

        return kwargs

    def get_control_image_pil(self) -> Image:
        control_image_artifact = self._node.get_parameter_value("control_image")
        if isinstance(control_image_artifact, ImageUrlArtifact):
            control_image_artifact = load_image_from_url_artifact(control_image_artifact)
        control_image_pil = image_artifact_to_pil(control_image_artifact)
        return control_image_pil.convert("RGB")

    def latents_to_image_pil(self, pipe: DiffusionPipeline, latents: Any) -> Image:
        return qwen_latents_to_image_pil(pipe, latents, self.get_height(), self.get_width())
