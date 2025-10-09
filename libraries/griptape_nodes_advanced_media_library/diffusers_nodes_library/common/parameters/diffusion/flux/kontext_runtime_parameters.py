import logging

from griptape.artifacts import ImageUrlArtifact
from PIL.Image import Image
from pillow_nodes_library.utils import (  # type: ignore[reportMissingImports]
    image_artifact_to_pil,
)
from utils.image_utils import load_image_from_url_artifact

from diffusers_nodes_library.common.parameters.diffusion.runtime_parameters import (
    DiffusionPipelineRuntimeParameters,
)
from griptape_nodes.exe_types.core_types import Parameter
from griptape_nodes.exe_types.node_types import BaseNode

logger = logging.getLogger("diffusers_nodes_library")


class FluxKontextPipelineRuntimeParameters(DiffusionPipelineRuntimeParameters):
    def __init__(self, node: BaseNode):
        super().__init__(node)

    def _add_input_parameters(self) -> None:
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
                name="image",
                input_types=["ImageArtifact", "ImageUrlArtifact"],
                type="ImageArtifact",
                tooltip="Image to be used as the starting point (optional).",
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

    def _get_pipe_kwargs(self) -> dict:
        kwargs = {
            "prompt": self._node.get_parameter_value("prompt"),
            "prompt_2": self._node.get_parameter_value("prompt_2"),
            "negative_prompt": self._node.get_parameter_value("negative_prompt"),
            "negative_prompt_2": self._node.get_parameter_value("negative_prompt_2"),
            "true_cfg_scale": self._node.get_parameter_value("true_cfg_scale"),
            "guidance_scale": self._node.get_parameter_value("guidance_scale"),
            "image": self.get_input_image_pil(),
        }
        if kwargs["prompt_2"] is None or kwargs["prompt_2"] == "":
            del kwargs["prompt_2"]
        if kwargs["negative_prompt_2"] is None or kwargs["negative_prompt_2"] == "":
            del kwargs["negative_prompt_2"]
        return kwargs

    def get_input_image_pil(self) -> Image | None:
        image_artifact = self._node.get_parameter_value("image")
        if image_artifact is None:
            return None
        if isinstance(image_artifact, ImageUrlArtifact):
            image_artifact = load_image_from_url_artifact(image_artifact)
        input_image_pil = image_artifact_to_pil(image_artifact)
        return input_image_pil.convert("RGB")
