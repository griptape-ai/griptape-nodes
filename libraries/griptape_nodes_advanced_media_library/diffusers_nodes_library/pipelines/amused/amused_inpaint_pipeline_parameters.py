import logging
from typing import Any

import diffusers  # type: ignore[reportMissingImports]
import PIL.Image
import torch  # type: ignore[reportMissingImports]
from griptape.artifacts import ImageUrlArtifact
from griptape.loaders import ImageLoader
from PIL.Image import Image
from pillow_nodes_library.utils import (
    image_artifact_to_pil,  # type: ignore[reportMissingImports]
    pil_to_image_artifact,  # type: ignore[reportMissingImports]
)

from diffusers_nodes_library.common.parameters.huggingface_repo_parameter import (
    HuggingFaceRepoParameter,  # type: ignore[reportMissingImports]
)

# type: ignore[reportMissingImports]
from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import ControlNode

logger = logging.getLogger("diffusers_nodes_library")


class AmusedInpaintPipelineParameters:
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
        self._node.add_parameter(
            Parameter(
                name="input_image",
                input_types=["ImageArtifact", "ImageUrlArtifact"],
                type="ImageArtifact",
                allowed_modes={ParameterMode.PROPERTY, ParameterMode.INPUT},
                tooltip="input_image",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="mask_image",
                input_types=["ImageArtifact", "ImageUrlArtifact"],
                type="ImageArtifact",
                allowed_modes={ParameterMode.PROPERTY, ParameterMode.INPUT},
                tooltip="mask_image",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="strength",
                default_value=0.5,
                input_types=["float"],
                type="float",
                allowed_modes={ParameterMode.PROPERTY, ParameterMode.INPUT},
                tooltip="strength",
                ui_options={"slider": {"min_val": 0.0, "max_val": 1.0}, "step": 0.01},
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

    def get_strength(self) -> float:
        return float(self._node.get_parameter_value("strength"))

    def get_input_image(self) -> Image:
        input_image_artifact = self._node.get_parameter_value("input_image")

        if isinstance(input_image_artifact, ImageUrlArtifact):
            input_image_artifact = ImageLoader().parse(input_image_artifact.to_bytes())
        input_image_pil = image_artifact_to_pil(input_image_artifact)
        input_image_pil = input_image_pil.convert("RGB")
        logger.warning("resizing input image to 512x512 for model compatibility")
        input_image_pil = input_image_pil.resize(
            (512, 512)
        )  # TODO: https://github.com/griptape-ai/griptape-nodes/issues/1168
        return input_image_pil

    def get_mask_image(self) -> Image:
        mask_image_artifact = self._node.get_parameter_value("mask_image")

        if isinstance(mask_image_artifact, ImageUrlArtifact):
            mask_image_artifact = ImageLoader().parse(mask_image_artifact.to_bytes())
        mask_image_pil = image_artifact_to_pil(mask_image_artifact)
        mask_image_pil = mask_image_pil.convert("RGB")
        logger.warning("resizing mask image to 512x512 for model compatibility")
        mask_image_pil = mask_image_pil.resize(
            (512, 512)
        )  # TODO: https://github.com/griptape-ai/griptape-nodes/issues/1168
        return mask_image_pil

    def get_repo_revision(self) -> tuple[str, str]:
        return self._huggingface_repo_parameter.get_repo_revision()

    def get_num_inference_steps(self) -> int:
        return int(self._node.get_parameter_value("num_inference_steps"))

    def get_generator(self) -> torch.Generator:
        seed = self._node.get_parameter_value("seed")
        generator = torch.Generator("cpu")
        if seed is not None:
            generator = generator.manual_seed(seed)
        return generator

    def get_pipe_kwargs(self) -> dict:
        return {
            "prompt": self._node.get_parameter_value("prompt"),
            "negative_prompt": self._node.get_parameter_value("negative_prompt"),
            "image": self.get_input_image(),
            "mask_image": self.get_mask_image(),
            "strength": self.get_strength(),
            "num_inference_steps": self.get_num_inference_steps(),
            "guidance_scale": float(self._node.parameter_values["guidance_scale"]),
            "generator": self.get_generator(),
        }

    def publish_output_image_preview_placeholder(self) -> None:
        # Immediately set a preview placeholder image to make it react quickly and adjust
        # the size of the image preview on the node.
        preview_placeholder_image = PIL.Image.new("RGB", self.get_input_image().size, color="black")
        self._node.publish_update_to_parameter("output_image", pil_to_image_artifact(preview_placeholder_image))

    def latents_to_image_pil(self, pipe: diffusers.AmusedPipeline, latents: Any) -> Image:
        batch_size = 1
        width, height = self.get_input_image().size
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
