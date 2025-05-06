import logging
from typing import Any

import diffusers  # type: ignore[reportMissingImports]
import PIL.Image
import torch  # type: ignore[reportMissingImports]
from PIL.Image import Image
from pillow_nodes_library.utils import pil_to_image_artifact  # type: ignore[reportMissingImports]

from diffusers_nodes_library.common.parameters.huggingface_repo_parameter import (
    HuggingFaceRepoParameter,  # type: ignore[reportMissingImports]
)
from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import ControlNode

logger = logging.getLogger("diffusers_nodes_library")


class AmusedPipelineParameters:
    def __init__(self, node: ControlNode):
        self._node = node
        self._huggingface_repo_parameter = HuggingFaceRepoParameter(node, ["amused/amused-512"])

    def add_input_parameters(self) -> None:
        self._huggingface_repo_parameter.add_input_parameters()
        self._node.add_parameter(
            Parameter(
                name="prompt",
                default_value="",
                input_types=["str"],
                type="str",
                allowed_modes={ParameterMode.PROPERTY, ParameterMode.INPUT},
                tooltip="prompt",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="negative_prompt",
                default_value="",
                input_types=["str"],
                type="str",
                allowed_modes={ParameterMode.PROPERTY, ParameterMode.INPUT},
                tooltip="optional negative_prompt",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="num_inference_steps",
                default_value=12,
                input_types=["int"],
                type="int",
                allowed_modes={ParameterMode.PROPERTY, ParameterMode.INPUT},
                tooltip="num_inference_steps",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="guidance_scale",
                default_value=10.0,
                input_types=["float"],
                type="float",
                allowed_modes={ParameterMode.PROPERTY, ParameterMode.INPUT},
                tooltip="guidance_scale",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="height",
                default_value=None,
                input_types=["int", "None"],
                allowed_modes={ParameterMode.PROPERTY, ParameterMode.INPUT},
                tooltip="height",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="width",
                default_value=None,
                input_types=["int", "None"],
                allowed_modes={ParameterMode.PROPERTY, ParameterMode.INPUT},
                tooltip="width",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="seed",
                default_value=None,
                input_types=["int", "None"],
                allowed_modes={ParameterMode.PROPERTY, ParameterMode.INPUT},
                tooltip="seed",
            )
        )

    def add_output_parameters(self) -> None:
        self._node.add_parameter(
            Parameter(
                name="output_image",
                output_type="ImageArtifact",
                tooltip="The output image",
                allowed_modes={ParameterMode.OUTPUT},
            )
        )

    def get_repo_revision(self) -> tuple[str, str]:
        return self._huggingface_repo_parameter.get_repo_revision()

    def get_num_inference_steps(self) -> int:
        return int(self._node.get_parameter_value("num_inference_steps"))

    def get_pipe_kwargs(self) -> dict:
        prompt = self._node.parameter_values["prompt"]
        negative_prompt = self._node.parameter_values["negative_prompt"]
        width = self._node.get_parameter_value("width")
        if width is not None:
            width = int(width)
        height = self._node.get_parameter_value("height")
        if height is not None:
            height = int(height)
        num_inference_steps = int(self._node.parameter_values["num_inference_steps"])
        guidance_scale = float(self._node.parameter_values["guidance_scale"])
        seed = self._node.get_parameter_value("seed")
        generator = torch.Generator("cpu")
        if seed is not None:
            generator = generator.manual_seed(seed)

        return {
            "prompt": prompt,
            "negative_prompt": negative_prompt,
            "width": width,
            "height": height,
            "num_inference_steps": num_inference_steps,
            "guidance_scale": guidance_scale,
            "generator": generator,
        }

    def publish_output_image_preview_placeholder(self) -> None:
        width = int(self._node.get_parameter_value("width") or 512)
        height = int(self._node.get_parameter_value("height") or 512)
        # Immediately set a preview placeholder image to make it react quickly and adjust
        # the size of the image preview on the node.
        preview_placeholder_image = PIL.Image.new("RGB", (width, height), color="black")
        self._node.publish_update_to_parameter("output_image", pil_to_image_artifact(preview_placeholder_image))

    def latents_to_image_pil(self, pipe: diffusers.AmusedPipeline, latents: Any) -> Image:
        batch_size = 1
        width = int(self._node.get_parameter_value("width") or 512)
        height = int(self._node.get_parameter_value("height") or 512)
        image = pipe.vqvae.decode(
            latents,
            force_not_quantize=True,
            shape=(
                batch_size,
                height // pipe.vae_scale_factor,
                width // pipe.vae_scale_factor,
                pipe.vqvae.config.latent_channels,
            ),
        ).sample.clip(0, 1)
        intermediate_pil_image = pipe.image_processor.postprocess(image, output_type="pil")[0]
        return intermediate_pil_image

    def publish_output_image_preview_latents(self, pipe: diffusers.AmusedPipeline, latents: Any) -> None:
        preview_image_pil = self.latents_to_image_pil(pipe, latents)
        preview_image_artifact = pil_to_image_artifact(preview_image_pil)
        self._node.publish_update_to_parameter("output_image", preview_image_artifact)

    def publish_output_image(self, output_image_pil: Image) -> None:
        image_artifact = pil_to_image_artifact(output_image_pil)
        self._node.set_parameter_value("output_image", image_artifact)
        self._node.parameter_output_values["output_image"] = image_artifact
