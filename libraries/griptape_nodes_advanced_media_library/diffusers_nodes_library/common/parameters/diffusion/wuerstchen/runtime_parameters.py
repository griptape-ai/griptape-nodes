import logging

from diffusers_nodes_library.common.parameters.diffusion.runtime_parameters import (
    DiffusionPipelineRuntimeParameters,
)
from griptape_nodes.exe_types.core_types import Parameter
from griptape_nodes.exe_types.node_types import BaseNode

logger = logging.getLogger("diffusers_nodes_library")


class WuerstchenCombinedPipelineRuntimeParameters(DiffusionPipelineRuntimeParameters):
    def __init__(self, node: BaseNode):
        super().__init__(node)

    def _add_input_parameters(self) -> None:
        self._node.add_parameter(
            Parameter(
                name="prompt",
                type="str",
                tooltip="Text description of the image to generate",
                default_value="A beautiful landscape with mountains and a lake",
            )
        )

        self._node.add_parameter(
            Parameter(
                name="negative_prompt",
                type="str",
                tooltip="What not to include in the image",
                default_value="",
            )
        )

        self._node.add_parameter(
            Parameter(
                name="prior_num_inference_steps",
                type="int",
                tooltip="Number of denoising steps for the prior stage",
                default_value=60,
            )
        )

        self._node.add_parameter(
            Parameter(
                name="prior_guidance_scale",
                type="float",
                tooltip="Text guidance strength for the prior stage",
                default_value=4.0,
            )
        )

        self._node.add_parameter(
            Parameter(
                name="decoder_guidance_scale",
                type="float",
                tooltip="Text guidance strength for the decoder stage",
                default_value=0.0,
            )
        )

    def _remove_input_parameters(self) -> None:
        self._node.remove_parameter_element_by_name("prompt")
        self._node.remove_parameter_element_by_name("negative_prompt")
        self._node.remove_parameter_element_by_name("prior_num_inference_steps")
        self._node.remove_parameter_element_by_name("prior_guidance_scale")
        self._node.remove_parameter_element_by_name("decoder_guidance_scale")

    def _get_pipe_kwargs(self) -> dict:
        prompt = self._node.get_parameter_value("prompt")
        negative_prompt = self._node.get_parameter_value("negative_prompt")

        kwargs = {
            "prompt": prompt,
            "prior_num_inference_steps": int(self._node.get_parameter_value("prior_num_inference_steps")),
            "prior_guidance_scale": float(self._node.get_parameter_value("prior_guidance_scale")),
            "decoder_guidance_scale": float(self._node.get_parameter_value("decoder_guidance_scale")),
        }

        if negative_prompt:
            kwargs["negative_prompt"] = negative_prompt

        return kwargs

    def validate_before_node_run(self) -> list[Exception] | None:
        errors = []

        # Validate dimensions are multiples of 128
        height = self.get_height()
        width = self.get_width()

        if height % 128 != 0:
            errors.append(ValueError("Height must be a multiple of 128"))
        if width % 128 != 0:
            errors.append(ValueError("Width must be a multiple of 128"))

        # Validate positive values
        if height <= 0:
            errors.append(ValueError("Height must be positive"))
        if width <= 0:
            errors.append(ValueError("Width must be positive"))

        prior_num_inference_steps = int(self._node.get_parameter_value("prior_num_inference_steps"))
        if prior_num_inference_steps <= 0:
            errors.append(ValueError("prior_num_inference_steps must be positive"))

        num_inference_steps = self.get_num_inference_steps()
        if num_inference_steps <= 0:
            errors.append(ValueError("num_inference_steps must be positive"))

        return errors or None
