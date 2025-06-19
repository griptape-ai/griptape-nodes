import logging
from typing import Any

import diffusers  # type: ignore[reportMissingImports]
import PIL.Image
import torch  # type: ignore[reportMissingImports]
from PIL.Image import Image
from pillow_nodes_library.utils import pil_to_image_artifact  # type: ignore[reportMissingImports]

from diffusers_nodes_library.common.parameters.huggingface_repo_parameter import (  # type: ignore[reportMissingImports]
    HuggingFaceRepoParameter,
)
from diffusers_nodes_library.common.parameters.seed_parameter import SeedParameter  # type: ignore[reportMissingImports]
from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import BaseNode

logger = logging.getLogger("diffusers_nodes_library")


class AmusedPipelineParameters:
    """Container for all parameters used by the Amused pipelines."""

    def __init__(self, node: BaseNode):
        self._node = node
        self._huggingface_repo_parameter = HuggingFaceRepoParameter(
            node,
            repo_ids=[
                "amused/amused-256",
                "amused/amused-512",
            ],
            parameter_name="model",
        )
        self._seed_parameter = SeedParameter(node)

    # ------------------------------------------------------------------
    # Parameter registration helpers
    # ------------------------------------------------------------------
    def add_input_parameters(self) -> None:
        self._huggingface_repo_parameter.add_input_parameters()

        self._node.add_parameter(
            Parameter(
                name="prompt",
                default_value="",
                input_types=["str"],
                type="str",
                tooltip="Text prompt",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="negative_prompt",
                default_value="",
                input_types=["str"],
                type="str",
                tooltip="Negative prompt (optional)",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="guidance_scale",
                default_value=10.0,
                input_types=["float"],
                type="float",
                tooltip="CFG / guidance scale",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="width",
                default_value=256,
                input_types=["int"],
                type="int",
                tooltip="Width in pixels (automatically set based on model)",
                allowed_modes=set(),
            )
        )
        self._node.add_parameter(
            Parameter(
                name="height",
                default_value=256,
                input_types=["int"],
                type="int",
                tooltip="Height in pixels (automatically set based on model)",
                allowed_modes=set(),
            )
        )
        self._node.add_parameter(
            Parameter(
                name="num_inference_steps",
                default_value=12,
                input_types=["int"],
                type="int",
                tooltip="Number of denoising steps",
            )
        )

        self._seed_parameter.add_input_parameters()

    def add_output_parameters(self) -> None:
        self._node.add_parameter(
            Parameter(
                name="output_image",
                output_type="ImageArtifact",
                tooltip="Generated image",
                allowed_modes={ParameterMode.OUTPUT},
            )
        )

    # ------------------------------------------------------------------
    # Validation / life-cycle hooks
    # ------------------------------------------------------------------
    def validate_before_node_run(self) -> list[Exception] | None:
        errors = self._huggingface_repo_parameter.validate_before_node_run()
        return errors or None

    def after_value_set(self, parameter: Parameter, value: Any) -> None:
        self._seed_parameter.after_value_set(parameter, value)

        # Auto-set width and height based on selected model
        if parameter.name == "model":
            model = str(value)
            if "256" in model:
                self._node.set_parameter_value("width", 256)
                self._node.set_parameter_value("height", 256)
            elif "512" in model:
                self._node.set_parameter_value("width", 512)
                self._node.set_parameter_value("height", 512)

    def preprocess(self) -> None:
        self._seed_parameter.preprocess()

    # ------------------------------------------------------------------
    # Convenience getters
    # ------------------------------------------------------------------
    def get_repo_revision(self) -> tuple[str, str]:
        return self._huggingface_repo_parameter.get_repo_revision()

    def get_prompt(self) -> str:
        return self._node.get_parameter_value("prompt")

    def get_negative_prompt(self) -> str:
        return self._node.get_parameter_value("negative_prompt")

    def get_guidance_scale(self) -> float:
        return float(self._node.get_parameter_value("guidance_scale"))

    def get_width(self) -> int:
        return int(self._node.get_parameter_value("width"))

    def get_height(self) -> int:
        return int(self._node.get_parameter_value("height"))

    def get_num_inference_steps(self) -> int:
        return int(self._node.get_parameter_value("num_inference_steps"))

    def get_generator(self) -> Any:
        return self._seed_parameter.get_generator()

    def get_pipe_kwargs(self) -> dict:
        return {
            "prompt": self.get_prompt(),
            "negative_prompt": self.get_negative_prompt(),
            "guidance_scale": self.get_guidance_scale(),
            "width": self.get_width(),
            "height": self.get_height(),
            "num_inference_steps": self.get_num_inference_steps(),
            "generator": self.get_generator(),
        }

    # ------------------------------------------------------------------
    # Preview helpers
    # ------------------------------------------------------------------
    def publish_output_image_preview_placeholder(self) -> None:
        width = self.get_width()
        height = self.get_height()
        preview_placeholder_image = PIL.Image.new("RGB", (width, height), color="black")
        self._node.publish_update_to_parameter("output_image", pil_to_image_artifact(preview_placeholder_image))

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

    def publish_output_image_preview_latents(self, pipe: diffusers.AmusedPipeline, latents: torch.Tensor) -> None:
        """Publish preview image from latents during inference."""
        preview_image_pil = self.latents_to_image_pil(pipe, latents)
        preview_image_artifact = pil_to_image_artifact(preview_image_pil)
        self._node.publish_update_to_parameter("output_image", preview_image_artifact)

    def publish_output_image(self, output_image_pil: Image) -> None:
        image_artifact = pil_to_image_artifact(output_image_pil)
        self._node.set_parameter_value("output_image", image_artifact)
        self._node.parameter_output_values["output_image"] = image_artifact
