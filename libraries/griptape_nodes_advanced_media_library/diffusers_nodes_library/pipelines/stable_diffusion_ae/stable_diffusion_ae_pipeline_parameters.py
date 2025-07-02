import logging
from typing import Any

import diffusers  # type: ignore[reportMissingImports]
import PIL.Image
import torch  # type: ignore[reportMissingImports]
from PIL.Image import Image
from pillow_nodes_library.utils import pil_to_image_artifact  # type: ignore[reportMissingImports]

from diffusers_nodes_library.common.parameters.huggingface_repo_parameter import HuggingFaceRepoParameter
from diffusers_nodes_library.common.parameters.seed_parameter import SeedParameter
from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import BaseNode

logger = logging.getLogger("diffusers_nodes_library")


class StableDiffusionAttendAndExcitePipelineParameters:
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
                name="prompt",
                input_types=["str"],
                type="str",
                tooltip="The prompt to guide image generation",
                default_value="",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="words_to_emphasize",
                input_types=["str"],
                type="str",
                tooltip="Words to emphasize (whitespace separated). Token indices will be automatically detected.",
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
                name="guidance_scale",
                input_types=["float"],
                type="float",
                tooltip="Guidance scale for generation",
                default_value=7.5,
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
                name="max_iter_to_alter",
                input_types=["int"],
                type="int",
                tooltip="Number of denoising steps to apply attend-and-excite",
                default_value=25,
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

    def after_value_set(self, parameter: Parameter, value: Any) -> None:
        self._seed_parameter.after_value_set(parameter, value)

    def validate_before_node_run(self) -> list[Exception] | None:
        errors = []
        errors.extend(self._huggingface_repo_parameter.validate_before_node_run() or [])
        words_to_emphasize = self._node.get_parameter_value("words_to_emphasize")
        if not words_to_emphasize.strip():
            errors.append(
                ValueError("Parameter 'words_to_emphasize' cannot be empty. Please provide words to emphasize.")
            )
        return errors

    def preprocess(self) -> None:
        self._seed_parameter.preprocess()

    def get_repo_revision(self) -> tuple[str, str | None]:
        return self._huggingface_repo_parameter.get_repo_revision()

    def get_prompt(self) -> str:
        return self._node.get_parameter_value("prompt")

    def get_words_to_emphasize(self) -> str:
        return self._node.get_parameter_value("words_to_emphasize")

    def get_negative_prompt(self) -> str:
        return self._node.get_parameter_value("negative_prompt")

    def get_height(self) -> int:
        return int(self._node.get_parameter_value("height"))

    def get_width(self) -> int:
        return int(self._node.get_parameter_value("width"))

    def get_guidance_scale(self) -> float:
        return float(self._node.get_parameter_value("guidance_scale"))

    def get_num_inference_steps(self) -> int:
        return int(self._node.get_parameter_value("num_inference_steps"))

    def get_max_iter_to_alter(self) -> int:
        return int(self._node.get_parameter_value("max_iter_to_alter"))

    def get_token_indices(self, pipe: diffusers.StableDiffusionAttendAndExcitePipeline) -> list[int]:
        """Get token indices by computing them from words_to_emphasize."""
        words_to_emphasize = self.get_words_to_emphasize()

        if not words_to_emphasize.strip():
            return []

        prompt = self.get_prompt()
        words = words_to_emphasize.strip().split()

        if not words or not prompt:
            return []

        # Get token indices from the pipeline
        token_map = pipe.get_indices(prompt)

        token_indices = []
        for word in words:
            # Find tokens that start with the word (case-insensitive)
            for idx, token in token_map.items():
                # Remove tokenizer artifacts like </w> and <|...
                clean_token = token.replace("</w>", "").replace("<|", "").replace("|>", "").lower()
                if clean_token.startswith(word.lower()) and idx not in token_indices:
                    token_indices.append(idx)

        return token_indices

    def get_attention_store_steps(self) -> int:
        return self._node.get_parameter_value("attention_store_steps")

    def get_attention_res(self) -> int:
        return self._node.get_parameter_value("attention_res")

    def get_generator(self) -> torch.Generator:
        return self._seed_parameter.get_generator()

    def get_pipe_kwargs(self, pipe: diffusers.StableDiffusionAttendAndExcitePipeline) -> dict[str, Any]:
        return {
            "prompt": self.get_prompt(),
            "token_indices": self.get_token_indices(pipe),
            "negative_prompt": self.get_negative_prompt(),
            "height": self.get_height(),
            "width": self.get_width(),
            "guidance_scale": self.get_guidance_scale(),
            "num_inference_steps": self.get_num_inference_steps(),
            "max_iter_to_alter": self.get_max_iter_to_alter(),
            "generator": self.get_generator(),
        }

    def publish_output_image_preview_placeholder(self) -> None:
        placeholder_image = PIL.Image.new("RGB", (self.get_width(), self.get_height()), "black")
        placeholder_artifact = pil_to_image_artifact(placeholder_image)
        self._node.set_parameter_value("output_image", placeholder_artifact)

    def latents_to_image_pil(self, pipe: diffusers.StableDiffusionAttendAndExcitePipeline, latents: Any) -> Image:
        latents_scaled = 1 / pipe.vae.config.scaling_factor * latents
        image = pipe.vae.decode(latents_scaled, return_dict=False)[0]
        intermediate_pil_image = pipe.image_processor.postprocess(image, output_type="pil")[0]
        return intermediate_pil_image

    def publish_output_image_preview_latents(
        self, pipe: diffusers.StableDiffusionAttendAndExcitePipeline, latents: Any
    ) -> None:
        try:
            preview_image_pil = self.latents_to_image_pil(pipe, latents)
            preview_image_artifact = pil_to_image_artifact(preview_image_pil)
            self._node.publish_update_to_parameter("output_image", preview_image_artifact)
        except Exception as e:
            logger.warning("Failed to publish preview from latents: %s", e)

    def publish_output_image(self, image: Image) -> None:
        image_artifact = pil_to_image_artifact(image)
        self._node.set_parameter_value("output_image", image_artifact)
        self._node.parameter_output_values["output_image"] = image_artifact
