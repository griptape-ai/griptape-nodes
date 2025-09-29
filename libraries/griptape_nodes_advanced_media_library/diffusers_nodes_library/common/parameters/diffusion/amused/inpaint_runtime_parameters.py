import logging

import diffusers  # type: ignore[reportMissingImports]
import torch  # type: ignore[reportMissingImports]
from griptape.artifacts import ImageUrlArtifact
from griptape.loaders import ImageLoader
from PIL.Image import Image
from pillow_nodes_library.utils import (  # type: ignore[reportMissingImports]
    image_artifact_to_pil,
    pil_to_image_artifact,
)

from diffusers_nodes_library.common.parameters.diffusion.runtime_parameters import (
    DiffusionPipelineRuntimeParameters,
)
from griptape_nodes.exe_types.core_types import Parameter
from griptape_nodes.exe_types.node_types import BaseNode

logger = logging.getLogger("diffusers_nodes_library")


class AmusedInpaintPipelineRuntimeParameters(DiffusionPipelineRuntimeParameters):
    """Runtime parameters for AmusedInpaintPipeline."""

    def __init__(self, node: BaseNode):
        super().__init__(node)

    def _add_input_parameters(self) -> None:
        self._node.add_parameter(
            Parameter(
                name="image",
                type="ImageArtifact",
                tooltip="Input image to inpaint",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="mask_image",
                type="ImageArtifact",
                tooltip="Mask image (white areas will be inpainted)",
            )
        )
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
                default_value=10.0,
                type="float",
                tooltip="CFG / guidance scale",
            )
        )

    def _remove_input_parameters(self) -> None:
        self._node.remove_parameter_element_by_name("image")
        self._node.remove_parameter_element_by_name("mask_image")
        self._node.remove_parameter_element_by_name("prompt")
        self._node.remove_parameter_element_by_name("negative_prompt")
        self._node.remove_parameter_element_by_name("guidance_scale")

    def get_input_image(self) -> Image:
        image_artifact = self._node.get_parameter_value("image")
        if isinstance(image_artifact, ImageUrlArtifact):
            image_artifact = ImageLoader().parse(image_artifact.to_bytes())
        return image_artifact_to_pil(image_artifact).convert("RGB")

    def get_mask_image(self) -> Image:
        mask_artifact = self._node.get_parameter_value("mask_image")
        if isinstance(mask_artifact, ImageUrlArtifact):
            mask_artifact = ImageLoader().parse(mask_artifact.to_bytes())
        return image_artifact_to_pil(mask_artifact).convert("L")

    def _get_pipe_kwargs(self) -> dict:
        return {
            "image": self.get_input_image(),
            "mask_image": self.get_mask_image(),
            "prompt": self._node.get_parameter_value("prompt"),
            "negative_prompt": self._node.get_parameter_value("negative_prompt"),
            "guidance_scale": self._node.get_parameter_value("guidance_scale"),
        }

    # Override base methods to handle Amused-specific preview functionality
    def publish_output_image_preview_placeholder(self) -> None:
        input_image = self.get_input_image()
        self._node.publish_update_to_parameter("output_image", pil_to_image_artifact(input_image))

    def latents_to_image_pil(self, pipe: diffusers.AmusedInpaintPipeline, latents: torch.Tensor) -> Image:
        """Convert latents to PIL image using the pipeline's VQ-VAE decoder."""
        # Handle potential upcasting needed for float16
        needs_upcasting = pipe.vqvae.dtype == torch.float16 and pipe.vqvae.config.force_upcast

        if needs_upcasting:
            pipe.vqvae.float()

        batch_size = latents.shape[0]
        height, width = latents.shape[-2:]

        # Decode latents using VQ-VAE
        output = pipe.vqvae.decode(
            latents,
            force_not_quantize=True,
            shape=(
                batch_size,
                height,
                width,
                pipe.vqvae.config.latent_channels,
            ),
        ).sample.clip(0, 1)

        # Convert to PIL image
        intermediate_pil_image = pipe.image_processor.postprocess(output, output_type="pil")[0]
        return intermediate_pil_image
