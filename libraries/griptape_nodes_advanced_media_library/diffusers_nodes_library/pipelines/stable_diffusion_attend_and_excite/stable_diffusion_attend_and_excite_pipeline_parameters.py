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


class StableDiffusionAttendAndExcitePipelineParameters:
    def __init__(self, node: BaseNode):
        self._node = node
        self._huggingface_repo_parameter = HuggingFaceRepoParameter(
            node,
            repo_ids=[
                "stabilityai/stable-diffusion-2-1-base",
                "stabilityai/stable-diffusion-2-1",
                "runwayml/stable-diffusion-v1-5",
                "CompVis/stable-diffusion-v1-4",
            ],
        )
        self._seed_parameter = SeedParameter(node)

    def add_input_parameters(self) -> None:
        self._huggingface_repo_parameter.add_input_parameters()
        self._node.add_parameter(
            Parameter(
                name="prompt",
                input_types=["str"],
                type="str",
                tooltip="The prompt to guide image generation",
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
                name="height",
                input_types=["int"],
                type="int",
                tooltip="Height of generated image",
                default_value=512,
            )
        )
        self._node.add_parameter(
            Parameter(
                name="width",
                input_types=["int"],
                type="int",
                tooltip="Width of generated image",
                default_value=512,
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
                name="token_indices",
                input_types=["list"],
                type="list",
                tooltip="Token indices to apply attention control to",
                default_value=[],
            )
        )
        self._node.add_parameter(
            Parameter(
                name="attention_store_steps",
                input_types=["int"],
                type="int",
                tooltip="Number of steps to store attention maps",
                default_value=10,
            )
        )
        self._node.add_parameter(
            Parameter(
                name="attention_res",
                input_types=["int"],
                type="int",
                tooltip="Attention resolution",
                default_value=16,
            )
        )
        self._seed_parameter.add_input_parameters()

    def add_output_parameters(self) -> None:
        self._node.add_parameter(
            Parameter(
                name="output_image",
                input_types=[],
                type="image",
                tooltip="Generated image",
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

    def get_prompt(self) -> str:
        return self._node.get_parameter_value("prompt")

    def get_negative_prompt(self) -> str | None:
        negative_prompt = self._node.get_parameter_value("negative_prompt")
        return negative_prompt if negative_prompt else None

    def get_height(self) -> int:
        return self._node.get_parameter_value("height")

    def get_width(self) -> int:
        return self._node.get_parameter_value("width")

    def get_num_inference_steps(self) -> int:
        return self._node.get_parameter_value("num_inference_steps")

    def get_guidance_scale(self) -> float:
        return self._node.get_parameter_value("guidance_scale")

    def get_token_indices(self) -> list[int]:
        return self._node.get_parameter_value("token_indices")

    def get_attention_store_steps(self) -> int:
        return self._node.get_parameter_value("attention_store_steps")

    def get_attention_res(self) -> int:
        return self._node.get_parameter_value("attention_res")

    def get_generator(self) -> torch.Generator:
        return self._seed_parameter.get_generator()

    def get_pipe_kwargs(self) -> dict[str, Any]:
        kwargs = {
            "prompt": self.get_prompt(),
            "height": self.get_height(),
            "width": self.get_width(),
            "num_inference_steps": self.get_num_inference_steps(),
            "guidance_scale": self.get_guidance_scale(),
            "generator": self.get_generator(),
            "token_indices": self.get_token_indices(),
            "attention_store_steps": self.get_attention_store_steps(),
            "attention_res": self.get_attention_res(),
        }

        negative_prompt = self.get_negative_prompt()
        if negative_prompt:
            kwargs["negative_prompt"] = negative_prompt

        return kwargs

    def publish_output_image_preview_placeholder(self) -> None:
        placeholder_image = PIL.Image.new("RGB", (self.get_width(), self.get_height()), (128, 128, 128))
        placeholder_artifact = pil_to_image_artifact(placeholder_image)
        self._node.set_parameter_value("output_image", placeholder_artifact)

    def publish_output_image_preview_latents(
        self, pipe: diffusers.StableDiffusionAttendAndExcitePipeline, latents: Any
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
