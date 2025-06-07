import logging
from typing import Any

import diffusers  # type: ignore[reportMissingImports]
import PIL.Image
from PIL.Image import Image
from pillow_nodes_library.utils import pil_to_image_artifact  # type: ignore[reportMissingImports]

from diffusers_nodes_library.common.parameters.huggingface_repo_parameter import HuggingFaceRepoParameter
from diffusers_nodes_library.common.parameters.seed_parameter import SeedParameter
from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import BaseNode

logger = logging.getLogger("diffusers_nodes_library")


class WuerstchenPipelineParameters:
    def __init__(self, node: BaseNode):
        self._node = node
        self._huggingface_repo_parameter = HuggingFaceRepoParameter(
            node,
            repo_ids=[
                "warp-ai/wuerstchen-v2-interpolated",
                "warp-ai/wuerstchen-v2-base",
                "warp-ai/wuerstchen-v2-aesthetic",
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
                allowed_modes={ParameterMode.INPUT},
                tooltip="Text description of the image to generate",
                default_value="A beautiful landscape with mountains and a lake",
            )
        )

        self._node.add_parameter(
            Parameter(
                name="negative_prompt",
                input_types=["str"],
                type="str",
                allowed_modes={ParameterMode.INPUT},
                tooltip="What not to include in the image",
                default_value="",
            )
        )

        self._node.add_parameter(
            Parameter(
                name="height",
                input_types=["int"],
                type="int",
                allowed_modes={ParameterMode.INPUT},
                tooltip="Height of the generated image in pixels (must be multiple of 128)",
                default_value=512,
            )
        )

        self._node.add_parameter(
            Parameter(
                name="width",
                input_types=["int"],
                type="int",
                allowed_modes={ParameterMode.INPUT},
                tooltip="Width of the generated image in pixels (must be multiple of 128)",
                default_value=512,
            )
        )

        self._node.add_parameter(
            Parameter(
                name="prior_num_inference_steps",
                input_types=["int"],
                type="int",
                allowed_modes={ParameterMode.INPUT},
                tooltip="Number of denoising steps for the prior stage",
                default_value=60,
            )
        )

        self._node.add_parameter(
            Parameter(
                name="prior_guidance_scale",
                input_types=["float"],
                type="float",
                allowed_modes={ParameterMode.INPUT},
                tooltip="Text guidance strength for the prior stage",
                default_value=4.0,
            )
        )

        self._node.add_parameter(
            Parameter(
                name="num_inference_steps",
                input_types=["int"],
                type="int",
                allowed_modes={ParameterMode.INPUT},
                tooltip="Number of denoising steps for the decoder stage",
                default_value=12,
            )
        )

        self._node.add_parameter(
            Parameter(
                name="decoder_guidance_scale",
                input_types=["float"],
                type="float",
                allowed_modes={ParameterMode.INPUT},
                tooltip="Text guidance strength for the decoder stage",
                default_value=0.0,
            )
        )

        self._node.add_parameter(
            Parameter(
                name="num_images_per_prompt",
                input_types=["int"],
                type="int",
                allowed_modes={ParameterMode.INPUT},
                tooltip="Number of images to generate per prompt",
                default_value=1,
            )
        )

        self._seed_parameter.add_input_parameters()

    def add_output_parameters(self) -> None:
        self._node.add_parameter(
            Parameter(
                name="image",
                input_types=[],
                type="image",
                allowed_modes={ParameterMode.OUTPUT},
                tooltip="Generated image",
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

        num_images_per_prompt = self._node.get_parameter_value("num_images_per_prompt")
        if num_images_per_prompt <= 0:
            errors.append(ValueError("num_images_per_prompt must be positive"))

        return errors or None

    def after_value_set(self, parameter: Parameter, value: Any, modified_parameters_set: set[str]) -> None:
        self._seed_parameter.after_value_set(parameter, value, modified_parameters_set)

    def preprocess(self) -> None:
        self._seed_parameter.preprocess()

    def get_repo_revision(self) -> tuple[str, str | None]:
        return self._huggingface_repo_parameter.get_repo_revision()

    def get_num_inference_steps(self) -> int:
        return self._node.get_parameter_value("num_inference_steps")

    def get_pipe_kwargs(self) -> dict[str, Any]:
        prompt = self._node.get_parameter_value("prompt")
        negative_prompt = self._node.get_parameter_value("negative_prompt")
        height = self._node.get_parameter_value("height")
        width = self._node.get_parameter_value("width")
        prior_num_inference_steps = self._node.get_parameter_value("prior_num_inference_steps")
        prior_guidance_scale = self._node.get_parameter_value("prior_guidance_scale")
        num_inference_steps = self._node.get_parameter_value("num_inference_steps")
        decoder_guidance_scale = self._node.get_parameter_value("decoder_guidance_scale")
        num_images_per_prompt = self._node.get_parameter_value("num_images_per_prompt")
        generator = self._seed_parameter.get_generator()

        kwargs = {
            "prompt": prompt,
            "height": height,
            "width": width,
            "prior_num_inference_steps": prior_num_inference_steps,
            "prior_guidance_scale": prior_guidance_scale,
            "num_inference_steps": num_inference_steps,
            "decoder_guidance_scale": decoder_guidance_scale,
            "num_images_per_prompt": num_images_per_prompt,
            "generator": generator,
        }

        if negative_prompt:
            kwargs["negative_prompt"] = negative_prompt

        return kwargs

    def publish_output_image_preview_placeholder(self) -> None:
        height = self._node.get_parameter_value("height")
        width = self._node.get_parameter_value("width")
        placeholder_image = PIL.Image.new("RGB", (width, height), (128, 128, 128))
        self._node.publish_update_to_parameter("image", pil_to_image_artifact(placeholder_image))

    def publish_output_image_preview_latents(self, pipe: diffusers.WuerstchenCombinedPipeline, latents: Any) -> None:
        # Wuerstchen operates in a highly compressed latent space,
        # so preview generation is more complex and may not be practical
        # For now, we'll skip latent previews
        pass

    def publish_output_image(self, output_image_pil: Image) -> None:
        self._node.parameter_output_values["image"] = pil_to_image_artifact(output_image_pil)
