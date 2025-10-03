import logging
from typing import Any

from griptape.artifacts import ImageUrlArtifact
from PIL.Image import Image
from pillow_nodes_library.utils import (  # type: ignore[reportMissingImports]
    image_artifact_to_pil,
)
from utils.image_utils import load_image_from_url_artifact

from diffusers_nodes_library.common.nodes.diffusion_pipeline_builder_node import UNION_PRO_2_CONFIG_HASH_POSTFIX
from diffusers_nodes_library.common.parameters.diffusion.runtime_parameters import (
    DiffusionPipelineRuntimeParameters,
)
from griptape_nodes.exe_types.core_types import Parameter
from griptape_nodes.exe_types.node_types import BaseNode
from griptape_nodes.traits.options import Options

logger = logging.getLogger("diffusers_nodes_library")

CONTROL_MODES = {
    "canny": 0,
    "tile": 1,
    "depth": 2,
    "blur": 3,
    "gray": 5,
}


class FluxControlNetPipelineRuntimeParameters(DiffusionPipelineRuntimeParameters):
    def __init__(self, node: BaseNode):
        super().__init__(node)

    def _add_input_parameters(self) -> None:
        self._node.add_parameter(
            Parameter(
                name="control_image",
                input_types=["ImageArtifact", "ImageUrlArtifact"],
                type="ImageArtifact",
                tooltip="The ControlNet input condition to provide guidance to the unet for generation.",
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
                name="prompt_2",
                type="str",
                tooltip="The prompt or prompts to be sent to tokenizer_2 and text_encoder_2. If not defined, prompt is will be used instead",
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
                name="negative_prompt_2",
                type="str",
                tooltip="The prompt or prompts not to guide the image generation to be sent to tokenizer_2 and text_encoder_2. If not defined, negative_prompt is used in all the text-encoders.",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="controlnet_conditioning_scale",
                default_value=0.7,
                input_types=["float"],
                type="float",
                tooltip="Multiplied with the outputs of the ControlNet before they are added to the residual in the original unet.",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="control_guidance_end",
                default_value=0.8,
                input_types=["float"],
                type="float",
                tooltip="The percentage of total steps at which the ControlNet stops applying.",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="control_mode",
                default_value=next(iter(CONTROL_MODES.keys())),
                input_types=["str"],
                type="str",
                traits={
                    Options(
                        choices=list(CONTROL_MODES.keys()),
                    )
                },
                tooltip="The control mode.",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="true_cfg_scale",
                default_value=1.0,
                type="float",
                tooltip="True classifier-free guidance (guidance scale) is enabled when true_cfg_scale > 1 and negative_prompt is provided.",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="guidance_scale",
                default_value=3.5,
                type="float",
                tooltip="Higher guidance_scale encourages a model to generate images more aligned with prompt at the expense of lower image quality.",
            )
        )

        self._node.hide_parameter_by_name("prompt_2")
        self._node.hide_parameter_by_name("negative_prompt_2")

    def _remove_input_parameters(self) -> None:
        self._node.remove_parameter_element_by_name("prompt")
        self._node.remove_parameter_element_by_name("prompt_2")
        self._node.remove_parameter_element_by_name("negative_prompt")
        self._node.remove_parameter_element_by_name("negative_prompt_2")
        self._node.remove_parameter_element_by_name("true_cfg_scale")
        self._node.remove_parameter_element_by_name("guidance_scale")
        self._node.remove_parameter_element_by_name("controlnet_conditioning_scale")
        self._node.remove_parameter_element_by_name("control_guidance_end")
        self._node.remove_parameter_element_by_name("control_mode")
        self._node.remove_parameter_element_by_name("control_image")

    def after_value_set(self, parameter: Parameter, value: Any) -> None:
        super().after_value_set(parameter, value)
        if parameter.name == "pipeline":
            # Convert hex postfix to int
            config_bits_postfix = int(value.split("-")[-1], 16)
            # If UNION_PRO_2_CONFIG_HASH_POSTFIX bit is set, hide control_mode parameter
            if config_bits_postfix & UNION_PRO_2_CONFIG_HASH_POSTFIX:
                self._node.hide_parameter_by_name("control_mode")
            else:
                self._node.show_parameter_by_name("control_mode")

    def _get_pipe_kwargs(self) -> dict:
        kwargs = {
            "prompt": self._node.get_parameter_value("prompt"),
            "prompt_2": self._node.get_parameter_value("prompt_2"),
            "negative_prompt": self._node.get_parameter_value("negative_prompt"),
            "negative_prompt_2": self._node.get_parameter_value("negative_prompt_2"),
            "true_cfg_scale": self._node.get_parameter_value("true_cfg_scale"),
            "guidance_scale": self._node.get_parameter_value("guidance_scale"),
            "control_image": self.get_control_image_pil(),
            "controlnet_conditioning_scale": self._node.get_parameter_value("controlnet_conditioning_scale"),
            "control_guidance_end": self._node.get_parameter_value("control_guidance_end"),
            "control_mode": CONTROL_MODES[self._node.get_parameter_value("control_mode")],
        }
        if kwargs["prompt_2"] is None or kwargs["prompt_2"] == "":
            del kwargs["prompt_2"]
        if kwargs["negative_prompt_2"] is None or kwargs["negative_prompt_2"] == "":
            del kwargs["negative_prompt_2"]
        return kwargs

    def get_control_image_pil(self) -> Image:
        control_image_artifact = self._node.get_parameter_value("control_image")
        if isinstance(control_image_artifact, ImageUrlArtifact):
            control_image_artifact = load_image_from_url_artifact(control_image_artifact)
        control_image_pil = image_artifact_to_pil(control_image_artifact)
        return control_image_pil.convert("RGB")
