import logging
from typing import Any, ClassVar

import PIL.Image
from PIL.Image import Image
from pillow_nodes_library.utils import pil_to_image_artifact  # type: ignore[reportMissingImports]

from diffusers_nodes_library.common.parameters.seed_parameter import SeedParameter
from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import BaseNode
from griptape_nodes.traits.options import Options  # type: ignore[reportMissingImports]

logger = logging.getLogger("diffusers_nodes_library")


class SD3PipelineParameters:
    """Manages all parameters for Stable Diffusion 3 pipeline."""

    # Available schedulers for SD3.5 (flow-matching compatible only)
    AVAILABLE_SCHEDULERS: ClassVar[list[str]] = [
        "FlowMatchEulerDiscreteScheduler",  # SD3.5 default - official recommendation
        "FlowMatchHeunDiscreteScheduler",  # Alternative flow-matching scheduler
        # Removed traditional diffusion schedulers - they cause warnings and poor results
    ]

    def __init__(self, node: BaseNode):
        self._node = node
        self._seed_parameter = SeedParameter(node)

    def add_input_parameters(self) -> None:
        """Add all input parameters for SD3.5 generation."""
        # Core generation parameters
        self._node.add_parameter(
            Parameter(
                name="prompt",
                default_value="",
                input_types=["str"],
                type="str",
                tooltip="Text prompt to guide image generation",
                ui_options={"multiline": True},
            )
        )

        self._node.add_parameter(
            Parameter(
                name="negative_prompt",
                default_value="",
                input_types=["str"],
                type="str",
                tooltip="Negative prompt to avoid certain elements",
                ui_options={"multiline": True},
            )
        )

        # Note: SD3.5 doesn't support img2img mode - text-to-image only

        # Image dimensions
        self._node.add_parameter(
            Parameter(
                name="width",
                default_value=1024,
                input_types=["int"],
                type="int",
                tooltip="Width of generated image",
                ui_options={"min": 256, "max": 2048, "step": 64},
            )
        )

        self._node.add_parameter(
            Parameter(
                name="height",
                default_value=1024,
                input_types=["int"],
                type="int",
                tooltip="Height of generated image",
                ui_options={"min": 256, "max": 2048, "step": 64},
            )
        )

        # Generation parameters
        self._node.add_parameter(
            Parameter(
                name="num_inference_steps",
                default_value=28,
                input_types=["int"],
                type="int",
                tooltip="Number of denoising steps",
                ui_options={"min": 1, "max": 100},
            )
        )

        self._node.add_parameter(
            Parameter(
                name="guidance_scale",
                default_value=3.5,
                input_types=["float"],
                type="float",
                tooltip="Classifier-free guidance scale",
                ui_options={"min": 0.0, "max": 20.0, "step": 0.1},
            )
        )

        # Note: strength parameter removed - SD3.5 is text-to-image only

        # Model and sampling parameters (model selection now handled by SD35ModelManager)

        self._node.add_parameter(
            Parameter(
                name="scheduler",
                default_value="FlowMatchEulerDiscreteScheduler",
                input_types=["str"],
                type="str",
                tooltip="Scheduler/sampler for denoising process",
                traits={Options(choices=self.AVAILABLE_SCHEDULERS)},
                allowed_modes={ParameterMode.PROPERTY},
            )
        )



        # Batch generation
        self._node.add_parameter(
            Parameter(
                name="num_images_per_prompt",
                default_value=1,
                input_types=["int"],
                type="int",
                tooltip="Number of images to generate per prompt",
                ui_options={"min": 1, "max": 8},
            )
        )



        # Add seed parameters
        self._seed_parameter.add_input_parameters()

    def add_output_parameters(self) -> None:
        """Add output parameters."""
        self._node.add_parameter(
            Parameter(
                name="output_image",
                output_type="ImageArtifact",
                tooltip="Generated image(s)",
                allowed_modes={ParameterMode.OUTPUT},
            )
        )

        # Note: used_seed removed - seed parameter already has output pin

    def after_value_set(self, parameter: Parameter, value: Any, modified_parameters_set: set[str]) -> None:
        """Handle parameter value changes."""
        self._seed_parameter.after_value_set(parameter, value, modified_parameters_set)

    def validate_before_node_run(self) -> list[Exception] | None:
        """Validate parameters before node execution."""
        errors = []

        # Check if prompt is provided
        prompt = self.get_prompt()
        if not prompt.strip():
            errors.append(Exception("Prompt cannot be empty"))

        # Validate dimensions
        width = self.get_width()
        height = self.get_height()
        if width % 64 != 0:
            errors.append(Exception(f"Width must be multiple of 64, got {width}"))
        if height % 64 != 0:
            errors.append(Exception(f"Height must be multiple of 64, got {height}"))

        return errors or None

    def preprocess(self) -> None:
        """Preprocess parameters before generation."""
        self._seed_parameter.preprocess()

    def get_prompt(self) -> str:
        return str(self._node.get_parameter_value("prompt"))

    def get_negative_prompt(self) -> str:
        return str(self._node.get_parameter_value("negative_prompt"))



    def get_width(self) -> int:
        return int(self._node.get_parameter_value("width"))

    def get_height(self) -> int:
        return int(self._node.get_parameter_value("height"))

    def get_num_inference_steps(self) -> int:
        return int(self._node.get_parameter_value("num_inference_steps"))

    def get_guidance_scale(self) -> float:
        return float(self._node.get_parameter_value("guidance_scale"))

    def get_num_images_per_prompt(self) -> int:
        return int(self._node.get_parameter_value("num_images_per_prompt"))

    def get_pipe_kwargs(self) -> dict:
        """Get pipeline kwargs for generation."""
        return {
            "prompt": self.get_prompt(),
            "negative_prompt": self.get_negative_prompt(),
            "width": self.get_width(),
            "height": self.get_height(),
            "num_inference_steps": self.get_num_inference_steps(),
            "guidance_scale": self.get_guidance_scale(),
            "num_images_per_prompt": self.get_num_images_per_prompt(),
            "generator": self._seed_parameter.get_generator(),
        }

    def publish_output_image_preview_placeholder(self) -> None:
        """Publish a preview placeholder image."""
        width = self.get_width()
        height = self.get_height()
        preview_placeholder_image = PIL.Image.new("RGB", (width, height), color="black")
        self._node.publish_update_to_parameter("output_image", pil_to_image_artifact(preview_placeholder_image))

    def latents_to_image_pil(self, pipe: Any, latents: Any) -> Image:
        """Convert latents to PIL image for preview."""
        # SD3 latent processing
        latents = (latents / pipe.vae.config.scaling_factor) + pipe.vae.config.shift_factor
        image = pipe.vae.decode(latents, return_dict=False)[0]
        intermediate_pil_image = pipe.image_processor.postprocess(image, output_type="pil")[0]
        return intermediate_pil_image

    def publish_output_image_preview_latents(self, pipe: Any, latents: Any) -> None:
        """Publish intermediate latents as preview image."""
        preview_image_pil = self.latents_to_image_pil(pipe, latents)
        preview_image_artifact = pil_to_image_artifact(preview_image_pil)
        self._node.publish_update_to_parameter("output_image", preview_image_artifact)

    def publish_output_image(self, output_image_pil: Image) -> None:
        """Publish a single output image."""
        output_artifact = pil_to_image_artifact(output_image_pil)
        self._node.set_parameter_value("output_image", output_artifact)
        self._node.parameter_output_values["output_image"] = output_artifact

    def publish_output_images_batch(self, output_images: list[Image]) -> None:
        """Publish multiple output images as a dictionary."""
        # TODO: Implement batch output as dict of ImageUrlArtifacts
        # For now, just publish the first image
        if output_images:
            self.publish_output_image(output_images[0])
            logger.warning(
                "Batch generation produced %d images, but only first one is returned. Batch output not yet implemented.",
                len(output_images),
            )
