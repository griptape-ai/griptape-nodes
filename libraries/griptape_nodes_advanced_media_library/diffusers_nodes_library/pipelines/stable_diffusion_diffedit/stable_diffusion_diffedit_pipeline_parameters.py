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

from diffusers_nodes_library.common.parameters.huggingface_repo_parameter import HuggingFaceRepoParameter
from diffusers_nodes_library.common.parameters.seed_parameter import SeedParameter
from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import BaseNode

logger = logging.getLogger("diffusers_nodes_library")


class StableDiffusionDiffeditPipelineParameters:
    def __init__(self, node: BaseNode):
        self._node = node
        self._huggingface_repo_parameter = HuggingFaceRepoParameter(
            node,
            repo_ids=[
                "stabilityai/stable-diffusion-2-1",
                "stabilityai/stable-diffusion-2",
                "CompVis/stable-diffusion-v1-4",
                "CompVis/stable-diffusion-v1-3",
                "CompVis/stable-diffusion-v1-2",
                "CompVis/stable-diffusion-v1-1",
            ],
        )
        self._seed_parameter = SeedParameter(node)

    def add_input_parameters(self) -> None:
        self._huggingface_repo_parameter.add_input_parameters()
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
                input_types=["str"],
                type="str",
                tooltip="The mask prompt describing what to edit (source content)",
                default_value="",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="prompt",
                input_types=["str"],
                type="str",
                tooltip="The target prompt describing the desired edited content",
                default_value="",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="negative_prompt",
                input_types=["str"],
                type="str",
                tooltip="The prompt to not guide the image generation",
                default_value="",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="num_inference_steps",
                input_types=["int"],
                type="int",
                tooltip="The number of denoising steps",
                default_value=50,
            )
        )
        self._node.add_parameter(
            Parameter(
                name="guidance_scale",
                input_types=["float"],
                type="float",
                tooltip="Guidance scale for generation",
                default_value=7.5,
            )
        )
        self._node.add_parameter(
            Parameter(
                name="width",
                input_types=["int"],
                type="int",
                tooltip="Width to resize + pad input image, padded resized image will be output too",
                default_value=768,
                allowed_modes=set(),
            )
        )
        self._node.add_parameter(
            Parameter(
                name="height",
                input_types=["int"],
                type="int",
                tooltip="Height to resize + pad input image, padded resized image will be output too",
                default_value=768,
                allowed_modes=set(),
            )
        )
        self._seed_parameter.add_input_parameters()

    def add_output_parameters(self) -> None:
        self._node.add_parameter(
            Parameter(
                name="mask_image",
                output_type="ImageArtifact",
                tooltip="Generated mask image showing edit regions",
                allowed_modes={ParameterMode.OUTPUT},
            )
        )
        self._node.add_parameter(
            Parameter(
                name="output_image",
                output_type="ImageUrlArtifact",
                tooltip="Generated edited image",
                allowed_modes={ParameterMode.OUTPUT},
            )
        )

    def after_value_set(self, parameter: Parameter, value: Any) -> None:
        self._seed_parameter.after_value_set(parameter, value)

    def validate_before_node_run(self) -> list[Exception] | None:
        errors = []
        errors.extend(self._huggingface_repo_parameter.validate_before_node_run() or [])
        return errors or None

    def preprocess(self) -> None:
        self._seed_parameter.preprocess()

    def get_repo_revision(self) -> tuple[str, str | None]:
        return self._huggingface_repo_parameter.get_repo_revision()

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

    def get_num_inference_steps(self) -> int:
        return int(self._node.get_parameter_value("num_inference_steps"))

    def get_guidance_scale(self) -> float:
        return float(self._node.get_parameter_value("guidance_scale"))

    def get_generator(self) -> torch.Generator:
        return self._seed_parameter.get_generator()

    def get_width(self) -> int:
        return int(self._node.get_parameter_value("width"))

    def get_height(self) -> int:
        return int(self._node.get_parameter_value("height"))

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
            generator=self.get_generator(),
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
            generator=self.get_generator(),
        ).latents

    def get_pipe_kwargs(self, pipe: Any) -> dict[str, Any]:
        """Get kwargs for the final pipeline call, including mask and image latents."""
        mask_image = self.generate_mask(pipe)
        image_latents = self.invert_image(pipe)

        kwargs = {
            "prompt": self.get_prompt(),
            "mask_image": mask_image,
            "image_latents": image_latents,
            "num_inference_steps": self.get_num_inference_steps(),
            "guidance_scale": self.get_guidance_scale(),
            "generator": self.get_generator(),
        }

        negative_prompt = self.get_negative_prompt()
        if negative_prompt:
            kwargs["negative_prompt"] = negative_prompt

        return kwargs

    def publish_output_image_preview_placeholder(self) -> None:
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

    def publish_output_image_preview_latents(self, pipe: Any, latents: Any) -> None:
        preview_image_pil = self.latents_to_image_pil(pipe, latents)
        preview_image_artifact = pil_to_image_artifact(preview_image_pil)
        self._node.publish_update_to_parameter("output_image", preview_image_artifact)

    def publish_output_image(self, image: Image) -> None:
        image_artifact = pil_to_image_artifact(image)
        self._node.set_parameter_value("output_image", image_artifact)
        self._node.parameter_output_values["output_image"] = image_artifact
