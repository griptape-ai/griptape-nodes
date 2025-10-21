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


class FluxFillPipelineRuntimeParameters(DiffusionPipelineRuntimeParameters):
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
                name="input_image",
                input_types=["ImageArtifact", "ImageUrlArtifact"],
                type="ImageArtifact",
                tooltip="Image to be used as the starting point.",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="mask_image",
                input_types=["ImageArtifact", "ImageUrlArtifact"],
                type="ImageArtifact",
                tooltip="Image representing an image batch to mask image.",
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

    def _remove_input_parameters(self) -> None:
        self._node.remove_parameter_element_by_name("input_image")
        self._node.remove_parameter_element_by_name("mask_image")
        self._node.remove_parameter_element_by_name("prompt")
        self._node.remove_parameter_element_by_name("prompt_2")
        self._node.remove_parameter_element_by_name("guidance_scale")

    def _get_pipe_kwargs(self) -> dict:
        kwargs = {
            "prompt": self._node.get_parameter_value("prompt"),
            "prompt_2": self._node.get_parameter_value("prompt_2"),
            "guidance_scale": self._node.get_parameter_value("guidance_scale"),
            "image": self.get_input_image_pil(),
            "mask_image": self.get_mask_image_pil(),
        }
        if kwargs["prompt_2"] is None or kwargs["prompt_2"] == "":
            del kwargs["prompt_2"]
        return kwargs

    def validate_before_node_run(self) -> list[Exception] | None:
        input_image_pil = self.get_input_image_pil()
        mask_image_pil = self.get_mask_image_pil()
        if input_image_pil.size != mask_image_pil.size:
            msg = (
                "The input image and mask image must have the same size. "
                f"Input image size: {input_image_pil.size}, "
                f"Mask image size: {mask_image_pil.size}"
            )
            raise RuntimeError(msg)
        if input_image_pil.width != self.get_width() or input_image_pil.height != self.get_height():
            msg = (
                "The input image size must match the width and height parameters. "
                f"Input image size: {input_image_pil.size}, "
                f"Width: {self.get_width()}, Height: {self.get_height()}"
            )
            raise RuntimeError(msg)

    def get_input_image_pil(self) -> Image:
        input_image_artifact = self._node.get_parameter_value("input_image")
        if isinstance(input_image_artifact, ImageUrlArtifact):
            input_image_artifact = load_image_from_url_artifact(input_image_artifact)
        input_image_pil = image_artifact_to_pil(input_image_artifact)
        return input_image_pil.convert("RGB")

    def get_mask_image_pil(self) -> Image:
        mask_image_artifact = self._node.get_parameter_value("mask_image")
        if isinstance(mask_image_artifact, ImageUrlArtifact):
            mask_image_artifact = load_image_from_url_artifact(mask_image_artifact)
        mask_image_pil = image_artifact_to_pil(mask_image_artifact)
        return mask_image_pil.convert("L")
