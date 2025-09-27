import logging

from diffusers_nodes_library.common.parameters.diffusion.runtime_parameters import (
    DiffusionPipelineRuntimeParameters,
)
from griptape_nodes.exe_types.core_types import Parameter
from griptape_nodes.exe_types.node_types import BaseNode

logger = logging.getLogger("diffusers_nodes_library")


class StableDiffusion3PipelineRuntimeParameters(DiffusionPipelineRuntimeParameters):
    def __init__(self, node: BaseNode):
        super().__init__(node)

    def _add_input_parameters(self) -> None:
        self._node.add_parameter(
            Parameter(
                name="prompt",
                default_value="",
                type="str",
                tooltip="Text prompt",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="negative_prompt",
                default_value="",
                type="str",
                tooltip="Negative prompt (optional)",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="guidance_scale",
                default_value=7.0,
                type="float",
                tooltip="CFG / guidance scale",
            )
        )

    def _remove_input_parameters(self) -> None:
        self._node.remove_parameter_element_by_name("prompt")
        self._node.remove_parameter_element_by_name("negative_prompt")
        self._node.remove_parameter_element_by_name("guidance_scale")

    def _get_pipe_kwargs(self) -> dict:
        return {
            "prompt": self._node.get_parameter_value("prompt"),
            "negative_prompt": self._node.get_parameter_value("negative_prompt"),
            "guidance_scale": self._node.get_parameter_value("guidance_scale"),
        }
