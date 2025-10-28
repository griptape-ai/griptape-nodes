import logging
from typing import Any

import PIL.Image
import torch  # type: ignore[reportMissingImports]
from griptape.artifacts import ImageUrlArtifact
from griptape.loaders import ImageLoader
from PIL.Image import Image
from pillow_nodes_library.utils import (
    image_artifact_to_pil,  # type: ignore[reportMissingImports]
    pil_to_image_artifact,  # type: ignore[reportMissingImports]
)

from diffusers_nodes_library.common.parameters.diffusion.runtime_parameters import (
    DiffusionPipelineRuntimeParameters,
)
from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import BaseNode

logger = logging.getLogger("diffusers_nodes_library")


class StableDiffusionDiffEditPipelineRuntimeParameters(DiffusionPipelineRuntimeParameters):
    def __init__(self, node: BaseNode):
        super().__init__(node)

    def _add_input_parameters(self) -> None:
        self._node.add_parameter(
            Parameter(
                name="image",
                input_types=["ImageArtifact", "ImageUrlArtifact"],
                type="ImageArtifact",
                tooltip="The input image to edit",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="mask_prompt",
                type="str",
                tooltip="The mask prompt describing what to edit (source content)",
                default_value="",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="prompt",
                type="str",
                tooltip="The target prompt describing the desired edited content",
                default_value="",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="negative_prompt",
                type="str",
                tooltip="The prompt to not guide the image generation",
                default_value="",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="guidance_scale",
                type="float",
                tooltip="Guidance scale for generation",
                default_value=7.5,
            )
        )

    def add_output_parameters(self) -> None:
        super().add_output_parameters()
        self._node.add_parameter(
            Parameter(
                name="mask_image",
                output_type="ImageArtifact",
                tooltip="Generated mask image showing edit regions",
                allowed_modes={ParameterMode.OUTPUT},
            )
        )

    def _remove_input_parameters(self) -> None:
        self._node.remove_parameter_element_by_name("image")
        self._node.remove_parameter_element_by_name("mask_prompt")
        self._node.remove_parameter_element_by_name("prompt")
        self._node.remove_parameter_element_by_name("negative_prompt")
        self._node.remove_parameter_element_by_name("guidance_scale")

    def remove_output_parameters(self) -> None:
        super().remove_output_parameters()
        self._node.remove_parameter_element_by_name("mask_image")

    def get_width(self) -> int:
        # Override to use resized image dimensions
        return 768

    def get_height(self) -> int:
        # Override to use resized image dimensions
        return 768

    def get_image(self) -> Image:
        image_artifact = self._node.get_parameter_value("image")
        if isinstance(image_artifact, ImageUrlArtifact):
            image_artifact = ImageLoader().parse(image_artifact.to_bytes())
        image = image_artifact_to_pil(image_artifact)
        return self._resize_and_pad_image(image, self.get_width(), self.get_height())

    def get_mask_prompt(self) -> str:
        return self._node.get_parameter_value("mask_prompt")

    def get_prompt(self) -> str:
        return self._node.get_parameter_value("prompt")

    def get_negative_prompt(self) -> str | None:
        negative_prompt = self._node.get_parameter_value("negative_prompt")
        return negative_prompt if negative_prompt else None

    def get_guidance_scale(self) -> float:
        return float(self._node.get_parameter_value("guidance_scale"))

    def _resize_and_pad_image(self, image: Image, target_width: int, target_height: int) -> Image:
        """Resize image proportionally to fit target dimensions and pad with black."""
        # Calculate scale to fit image within target dimensions
        scale = min(target_width / image.width, target_height / image.height)
        new_width = int(image.width * scale)
        new_height = int(image.height * scale)

        # Resize image
        resized_image = image.resize((new_width, new_height), PIL.Image.Resampling.LANCZOS)

        # Create black canvas and paste resized image centered
        canvas = PIL.Image.new("RGB", (target_width, target_height), (0, 0, 0))
        x_offset = (target_width - new_width) // 2
        y_offset = (target_height - new_height) // 2
        canvas.paste(resized_image, (x_offset, y_offset))

        return canvas

    def generate_mask(self, pipe: Any) -> Image:
        """Generate mask using the pipeline."""
        mask_array = pipe.generate_mask(
            image=self.get_image(),
            source_prompt=self.get_prompt(),
            target_prompt=self.get_mask_prompt(),
            guidance_scale=self.get_guidance_scale(),
            generator=torch.Generator().manual_seed(self._seed_parameter.get_seed()),
            output_type="np",
        )

        # Convert numpy array to PIL Image
        # Handle different array shapes and squeeze unnecessary dimensions
        mask_array = mask_array.squeeze()
        rgb_channels = 3
        if len(mask_array.shape) == rgb_channels and mask_array.shape[2] == 1:
            mask_array = mask_array[:, :, 0]
        mask_image = PIL.Image.fromarray((mask_array * 255).astype("uint8"), mode="L")

        # Publish the generated mask immediately
        mask_artifact = pil_to_image_artifact(mask_image)
        self._node.publish_update_to_parameter("mask_image", mask_artifact)
        self._node.set_parameter_value("mask_image", mask_artifact)
        self._node.parameter_output_values["mask_image"] = mask_artifact

        return mask_image

    def invert_image(self, pipe: Any) -> Any:
        """Perform DDIM inversion to get image latents."""
        return pipe.invert(
            image=self.get_image(),
            prompt=self.get_mask_prompt(),
            guidance_scale=1.0,
            num_inference_steps=self.get_num_inference_steps(),
            generator=torch.Generator().manual_seed(self._seed_parameter.get_seed()),
        ).latents

    def _get_pipe_kwargs(self) -> dict[str, Any]:
        """Get DiffEdit-specific kwargs for the pipeline call."""
        # DiffEdit requires special processing - generate mask and get image latents
        # This is a simplified version - the full implementation would need to handle
        # the pipeline object passed to process_pipeline method
        kwargs = {
            "prompt": self.get_prompt(),
            "guidance_scale": self.get_guidance_scale(),
        }

        negative_prompt = self.get_negative_prompt()
        if negative_prompt:
            kwargs["negative_prompt"] = negative_prompt

        return kwargs

    def process_pipeline(self, pipe: Any) -> None:
        """Custom processing for DiffEdit pipeline."""
        # First generate the mask
        mask_image = self.generate_mask(pipe)

        # Then perform DDIM inversion
        image_latents = self.invert_image(pipe)

        # Finally generate the edited image
        num_inference_steps = self.get_num_inference_steps()

        def callback_on_step_end(
            pipe: Any,
            i: int,
            _t: Any,
            callback_kwargs: dict,
        ) -> dict:
            # Check for cancellation request
            if self._node.is_cancellation_requested:
                pipe._interrupt = True
                self._node.log_params.append_to_logs("Cancellation requested, stopping after this step...\n")  # type: ignore[reportAttributeAccessIssue]
                return callback_kwargs

            if i < num_inference_steps - 1:
                self.publish_output_image_preview_latents(pipe, callback_kwargs["latents"])
                self._node.log_params.append_to_logs(f"Starting inference step {i + 2} of {num_inference_steps}...\n")  # type: ignore[reportAttributeAccessIssue]
                self._node.progress_bar_component.increment()  # type: ignore[reportAttributeAccessIssue]
            return {}

        self._node.log_params.append_to_logs(f"Starting inference step 1 of {num_inference_steps}...\n")  # type: ignore[reportAttributeAccessIssue]
        self._node.progress_bar_component.initialize(num_inference_steps)  # type: ignore[reportAttributeAccessIssue]
        self._node.progress_bar_component.increment()  # type: ignore[reportAttributeAccessIssue]
        # Get the final pipeline kwargs including mask and latents
        pipe_kwargs = {
            "prompt": self.get_prompt(),
            "mask_image": mask_image,
            "image_latents": image_latents,
            "num_inference_steps": num_inference_steps,
            "guidance_scale": self.get_guidance_scale(),
            "generator": torch.Generator().manual_seed(self._seed_parameter.get_seed()),
        }

        negative_prompt = self.get_negative_prompt()
        if negative_prompt:
            pipe_kwargs["negative_prompt"] = negative_prompt

        output_image_pil = pipe(  # type: ignore[reportCallIssue]
            **pipe_kwargs,
            output_type="pil",
            callback_on_step_end=callback_on_step_end,
        ).images[0]

        self.publish_output_image(output_image_pil)
        self._node.log_params.append_to_logs("Done.\n")  # type: ignore[reportAttributeAccessIssue]

    def publish_output_image_preview_placeholder(self) -> None:
        """Override to use the input image dimensions for placeholder."""
        input_image = self.get_image()
        width, height = input_image.size
        placeholder_image = PIL.Image.new("RGB", (width, height), (128, 128, 128))
        placeholder_artifact = pil_to_image_artifact(placeholder_image)
        self._node.set_parameter_value("output_image", placeholder_artifact)

    def latents_to_image_pil(self, pipe: Any, latents: Any) -> Image:
        """Convert latents to PIL Image using the VAE."""
        latents_scaled = 1 / pipe.vae.config.scaling_factor * latents
        image = pipe.vae.decode(latents_scaled, return_dict=False)[0]
        intermediate_pil_image = pipe.image_processor.postprocess(image, output_type="pil")[0]
        return intermediate_pil_image

    def publish_output_image(self, image: Image) -> None:
        """Publish the final output image."""
        image_artifact = pil_to_image_artifact(image)
        self._node.set_parameter_value("output_image", image_artifact)
        self._node.parameter_output_values["output_image"] = image_artifact
