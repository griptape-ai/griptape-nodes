import logging

import diffusers  # type: ignore[reportMissingImports]
import PIL.Image
import torch  # type: ignore[reportMissingImports]
from PIL.Image import Image
from pillow_nodes_library.utils import pil_to_image_artifact  # type: ignore[reportMissingImports]
from utils.directory_utils import check_cleanup_intermediates_directory, get_intermediates_directory_path

from diffusers_nodes_library.common.parameters.diffusion.runtime_parameters import (
    DiffusionPipelineRuntimeParameters,
)
from griptape_nodes.exe_types.core_types import Parameter
from griptape_nodes.exe_types.node_types import BaseNode

logger = logging.getLogger("diffusers_nodes_library")


class AmusedPipelineRuntimeParameters(DiffusionPipelineRuntimeParameters):
    """Runtime parameters for Amused pipeline."""

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
                default_value=10.0,
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

    # Override base methods to handle Amused-specific preview functionality
    def publish_output_image_preview_placeholder(self) -> None:
        width = self.get_width()
        height = self.get_height()
        preview_placeholder_image = PIL.Image.new("RGB", (width, height), color="black")

        # Check to ensure there's enough space in the intermediates directory
        # if that setting is enabled.
        check_cleanup_intermediates_directory()
        self._node.publish_update_to_parameter(
            "output_image",
            pil_to_image_artifact(preview_placeholder_image, directory_path=get_intermediates_directory_path()),
        )

    def latents_to_image_pil(self, pipe: diffusers.AmusedPipeline, latents: torch.Tensor) -> Image:
        """Convert latents to PIL image using the pipeline's VQ-VAE decoder."""
        # Handle potential upcasting needed for float16
        needs_upcasting = pipe.vqvae.dtype == torch.float16 and pipe.vqvae.config.force_upcast

        if needs_upcasting:
            pipe.vqvae.float()

        batch_size = latents.shape[0]
        # Use actual latent dimensions from tensor shape
        latent_height, latent_width = latents.shape[-2:]

        # Decode latents using VQ-VAE
        output = pipe.vqvae.decode(
            latents,
            force_not_quantize=True,
            shape=(
                batch_size,
                latent_height,
                latent_width,
                pipe.vqvae.config.latent_channels,
            ),
        ).sample.clip(0, 1)

        # Convert to PIL image
        intermediate_pil_image = pipe.image_processor.postprocess(output, output_type="pil")[0]
        return intermediate_pil_image
