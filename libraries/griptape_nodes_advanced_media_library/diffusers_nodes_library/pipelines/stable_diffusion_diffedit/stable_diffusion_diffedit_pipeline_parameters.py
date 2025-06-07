import logging
from typing import Any

import diffusers  # type: ignore[reportMissingImports]
import PIL.Image
import torch  # type: ignore[reportMissingImports]
from PIL.Image import Image
from pillow_nodes_library.utils import pil_to_image_artifact  # type: ignore[reportMissingImports]

from diffusers_nodes_library.common.parameters.huggingface_repo_parameter import HuggingFaceRepoParameter
from diffusers_nodes_library.common.parameters.seed_parameter import SeedParameter
from griptape_nodes.exe_types.core_types import Parameter
from griptape_nodes.exe_types.node_types import BaseNode

logger = logging.getLogger("diffusers_nodes_library")


class StableDiffusionDiffeditPipelineParameters:
    def __init__(self, node: BaseNode):
        self._node = node
        self._huggingface_repo_parameter = HuggingFaceRepoParameter(
            node,
            repo_ids=[
                "stabilityai/stable-diffusion-2-1",
                "stabilityai/stable-diffusion-2-1-base",
                "runwayml/stable-diffusion-v1-5",
                "CompVis/stable-diffusion-v1-4",
            ],
        )
        self._seed_parameter = SeedParameter(node)

    def add_input_parameters(self) -> None:
        self._huggingface_repo_parameter.add_input_parameters()
        self._node.add_parameter(
            Parameter(
                name="image",
                input_types=["image"],
                type="image",
                tooltip="The input image to edit",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="source_prompt",
                input_types=["str"],
                type="str",
                tooltip="The source prompt describing the current image content",
                default_value="",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="target_prompt",
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
                name="mask_image",
                input_types=["image"],
                type="image",
                tooltip="Optional mask image specifying which regions to edit",
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
                name="mask_generation_guidance_scale",
                input_types=["float"],
                type="float",
                tooltip="Guidance scale for mask generation",
                default_value=7.5,
            )
        )
        self._node.add_parameter(
            Parameter(
                name="inversion_steps",
                input_types=["int"],
                type="int",
                tooltip="Number of steps for DDIM inversion",
                default_value=20,
            )
        )
        self._seed_parameter.add_input_parameters()

    def add_output_parameters(self) -> None:
        self._node.add_parameter(
            Parameter(
                name="output_image",
                input_types=[],
                type="image",
                tooltip="Generated edited image",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="output_mask",
                input_types=[],
                type="image",
                tooltip="Generated or used mask image",
            )
        )

    def after_value_set(self, parameter: Parameter, value: Any, modified_parameters_set: set[str]) -> None:
        self._seed_parameter.after_value_set(parameter, value, modified_parameters_set)

    def validate_before_node_run(self) -> list[Exception] | None:
        errors = []
        errors.extend(self._huggingface_repo_parameter.validate_before_node_run() or [])

    def preprocess(self) -> None:
        self._seed_parameter.preprocess()

    def get_repo_revision(self) -> tuple[str, str | None]:
        return self._huggingface_repo_parameter.get_repo_revision()

    def get_image(self) -> Image:
        from pillow_nodes_library.utils import image_artifact_to_pil  # type: ignore[reportMissingImports]

        image_artifact = self._node.get_parameter_value("image")
        return image_artifact_to_pil(image_artifact)

    def get_source_prompt(self) -> str:
        return self._node.get_parameter_value("source_prompt")

    def get_target_prompt(self) -> str:
        return self._node.get_parameter_value("target_prompt")

    def get_negative_prompt(self) -> str | None:
        negative_prompt = self._node.get_parameter_value("negative_prompt")
        return negative_prompt if negative_prompt else None

    def get_mask_image(self) -> Image | None:
        from pillow_nodes_library.utils import image_artifact_to_pil  # type: ignore[reportMissingImports]

        mask_artifact = self._node.get_parameter_value("mask_image")
        if mask_artifact:
            return image_artifact_to_pil(mask_artifact)
        return None

    def get_num_inference_steps(self) -> int:
        return self._node.get_parameter_value("num_inference_steps")

    def get_guidance_scale(self) -> float:
        return self._node.get_parameter_value("guidance_scale")

    def get_mask_generation_guidance_scale(self) -> float:
        return self._node.get_parameter_value("mask_generation_guidance_scale")

    def get_inversion_steps(self) -> int:
        return self._node.get_parameter_value("inversion_steps")

    def get_generator(self) -> torch.Generator:
        return self._seed_parameter.get_generator()

    def get_mask_generation_kwargs(self) -> dict[str, Any]:
        return {
            "image": self.get_image(),
            "source_prompt": self.get_source_prompt(),
            "target_prompt": self.get_target_prompt(),
            "guidance_scale": self.get_mask_generation_guidance_scale(),
            "generator": self.get_generator(),
        }

    def get_inversion_kwargs(self) -> dict[str, Any]:
        return {
            "image": self.get_image(),
            "prompt": self.get_source_prompt(),
            "guidance_scale": 1.0,
            "num_inference_steps": self.get_inversion_steps(),
            "generator": self.get_generator(),
        }

    def get_pipe_kwargs(self, mask_image: Image, latents: Any) -> dict[str, Any]:
        kwargs = {
            "prompt": self.get_target_prompt(),
            "mask_image": mask_image,
            "latents": latents,
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

    def publish_output_image_preview_latents(
        self, pipe: diffusers.StableDiffusionDiffEditPipeline, latents: Any
    ) -> None:
        try:
            with pipe.vae.disable_tiling():
                latents_scaled = 1 / pipe.vae.config.scaling_factor * latents
                image = pipe.vae.decode(latents_scaled, return_dict=False)[0]
                image = pipe.image_processor.postprocess(image, output_type="pil")[0]
                image_artifact = pil_to_image_artifact(image)
                self._node.set_parameter_value("output_image", image_artifact)
        except Exception as e:
            logger.warning("Failed to publish preview from latents: %s", e)

    def publish_output_image(self, image: Image) -> None:
        image_artifact = pil_to_image_artifact(image)
        self._node.set_parameter_value("output_image", image_artifact)

    def publish_output_mask(self, mask: Image) -> None:
        mask_artifact = pil_to_image_artifact(mask)
        self._node.set_parameter_value("output_mask", mask_artifact)
