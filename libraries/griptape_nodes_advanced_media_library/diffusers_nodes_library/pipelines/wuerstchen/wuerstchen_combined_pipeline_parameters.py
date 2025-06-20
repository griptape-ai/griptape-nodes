import logging
from typing import Any

import diffusers  # type: ignore[reportMissingImports]
import PIL.Image
import torch  # type: ignore[reportMissingImports]
from PIL.Image import Image
from pillow_nodes_library.utils import pil_to_image_artifact  # type: ignore[reportMissingImports]

from diffusers_nodes_library.common.parameters.huggingface_repo_parameter import (
    HuggingFaceRepoParameter,
)
from diffusers_nodes_library.common.parameters.seed_parameter import SeedParameter
from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import BaseNode

logger = logging.getLogger("diffusers_nodes_library")


class WuerstchenCombinedPipelineParameters:
    """Wrapper around the collection of parameters needed for Wuerstchen Combined pipelines."""

    def __init__(self, node: BaseNode):
        self._node = node
        self._huggingface_prior_repo_parameter = HuggingFaceRepoParameter(
            node,
            repo_ids=[
                "warp-ai/wuerstchen-prior",
            ],
            parameter_name="prior_model",
        )
        self._huggingface_decoder_repo_parameter = HuggingFaceRepoParameter(
            node,
            repo_ids=[
                "warp-ai/wuerstchen",
            ],
            parameter_name="decoder_model",
        )
        self._seed_parameter = SeedParameter(node)

    def add_input_parameters(self) -> None:
        self._huggingface_prior_repo_parameter.add_input_parameters()
        self._huggingface_decoder_repo_parameter.add_input_parameters()

        self._node.add_parameter(
            Parameter(
                name="prompt",
                input_types=["str"],
                type="str",
                tooltip="Text description of the image to generate",
                default_value="A beautiful landscape with mountains and a lake",
            )
        )

        self._node.add_parameter(
            Parameter(
                name="negative_prompt",
                input_types=["str"],
                type="str",
                tooltip="What not to include in the image",
                default_value="",
            )
        )

        self._node.add_parameter(
            Parameter(
                name="height",
                input_types=["int"],
                type="int",
                tooltip="Height of the generated image in pixels (must be multiple of 128)",
                default_value=1024,
            )
        )

        self._node.add_parameter(
            Parameter(
                name="width",
                input_types=["int"],
                type="int",
                tooltip="Width of the generated image in pixels (must be multiple of 128)",
                default_value=1024,
            )
        )

        self._node.add_parameter(
            Parameter(
                name="prior_num_inference_steps",
                input_types=["int"],
                type="int",
                tooltip="Number of denoising steps for the prior stage",
                default_value=60,
            )
        )

        self._node.add_parameter(
            Parameter(
                name="prior_guidance_scale",
                input_types=["float"],
                type="float",
                tooltip="Text guidance strength for the prior stage",
                default_value=4.0,
            )
        )

        self._node.add_parameter(
            Parameter(
                name="num_inference_steps",
                input_types=["int"],
                type="int",
                tooltip="Number of denoising steps for the decoder stage",
                default_value=12,
            )
        )

        self._node.add_parameter(
            Parameter(
                name="decoder_guidance_scale",
                input_types=["float"],
                type="float",
                tooltip="Text guidance strength for the decoder stage",
                default_value=0.0,
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

    def validate_before_node_run(self) -> list[Exception] | None:
        errors = []

        # Validate dimensions are multiples of 128
        height = self._node.get_parameter_value("height")
        width = self._node.get_parameter_value("width")

        if height % 128 != 0:
            errors.append(ValueError("Height must be a multiple of 128"))
        if width % 128 != 0:
            errors.append(ValueError("Width must be a multiple of 128"))

        # Validate positive values
        if height <= 0:
            errors.append(ValueError("Height must be positive"))
        if width <= 0:
            errors.append(ValueError("Width must be positive"))

        prior_num_inference_steps = self._node.get_parameter_value("prior_num_inference_steps")
        if prior_num_inference_steps <= 0:
            errors.append(ValueError("prior_num_inference_steps must be positive"))

        num_inference_steps = self._node.get_parameter_value("num_inference_steps")
        if num_inference_steps <= 0:
            errors.append(ValueError("num_inference_steps must be positive"))

        return errors or None

    def after_value_set(self, parameter: Parameter, value: Any) -> None:
        self._seed_parameter.after_value_set(parameter, value)

    def preprocess(self) -> None:
        self._seed_parameter.preprocess()

    def get_prior_repo_revision(self) -> tuple[str, str | None]:
        return self._huggingface_prior_repo_parameter.get_repo_revision()

    def get_decoder_repo_revision(self) -> tuple[str, str | None]:
        return self._huggingface_decoder_repo_parameter.get_repo_revision()

    def get_height(self) -> int:
        return int(self._node.get_parameter_value("height"))

    def get_width(self) -> int:
        return int(self._node.get_parameter_value("width"))

    def get_prior_num_inference_steps(self) -> int:
        return int(self._node.get_parameter_value("prior_num_inference_steps"))

    def get_prior_guidance_scale(self) -> float:
        return float(self._node.get_parameter_value("prior_guidance_scale"))

    def get_num_inference_steps(self) -> int:
        return int(self._node.get_parameter_value("num_inference_steps"))

    def get_decoder_guidance_scale(self) -> float:
        return float(self._node.get_parameter_value("decoder_guidance_scale"))

    def get_generator(self) -> torch.Generator:
        return self._seed_parameter.get_generator()

    def get_pipe_kwargs(self) -> dict[str, Any]:
        prompt = self._node.get_parameter_value("prompt")
        negative_prompt = self._node.get_parameter_value("negative_prompt")

        kwargs = {
            "prompt": prompt,
            "height": self.get_height(),
            "width": self.get_width(),
            "prior_num_inference_steps": self.get_prior_num_inference_steps(),
            "prior_guidance_scale": self.get_prior_guidance_scale(),
            "num_inference_steps": self.get_num_inference_steps(),
            "decoder_guidance_scale": self.get_decoder_guidance_scale(),
            "generator": self.get_generator(),
        }

        if negative_prompt:
            kwargs["negative_prompt"] = negative_prompt

        return kwargs

    def publish_output_image_preview_placeholder(self) -> None:
        width = self.get_width()
        height = self.get_height()
        preview_placeholder_image = PIL.Image.new("RGB", (width, height), color="black")
        self._node.publish_update_to_parameter("output_image", pil_to_image_artifact(preview_placeholder_image))

    def latents_to_image_pil(self, pipe: diffusers.WuerstchenDecoderPipeline, latents: Any) -> Image:
        latents = pipe.vqgan.config.scale_factor * latents
        images = pipe.vqgan.decode(latents).sample.clamp(0, 1)
        images = images.permute(0, 2, 3, 1).cpu().float().numpy()
        image = pipe.numpy_to_pil(images)[0]
        return image

    def publish_output_image_preview_latents(self, pipe: diffusers.WuerstchenDecoderPipeline, latents: Any) -> None:
        preview_image_pil = self.latents_to_image_pil(pipe, latents)
        preview_image_artifact = pil_to_image_artifact(preview_image_pil)
        self._node.publish_update_to_parameter("output_image", preview_image_artifact)

    def publish_output_image(self, output_image_pil: Image) -> None:
        image_artifact = pil_to_image_artifact(output_image_pil)
        self._node.set_parameter_value("output_image", image_artifact)
        self._node.parameter_output_values["output_image"] = image_artifact
