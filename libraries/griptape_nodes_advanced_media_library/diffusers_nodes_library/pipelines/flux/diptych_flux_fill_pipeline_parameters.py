import logging
from typing import Any

import diffusers  # type: ignore[reportMissingImports]
import numpy as np
import PIL.Image
from griptape.artifacts import ImageUrlArtifact
from griptape.loaders import ImageLoader
from PIL.Image import Image
from pillow_nodes_library.utils import (  # type: ignore[reportMissingImports]
    image_artifact_to_pil,
    pil_to_image_artifact,
)

from diffusers_nodes_library.common.parameters.huggingface_repo_parameter import HuggingFaceRepoParameter
from diffusers_nodes_library.common.parameters.seed_parameter import SeedParameter
from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import BaseNode

logger = logging.getLogger("diffusers_nodes_library")


class DiptychFluxFillPipelineParameters:
    def __init__(self, node: BaseNode):
        self._node = node
        self._huggingface_repo_parameter = HuggingFaceRepoParameter(
            node,
            repo_ids=[
                "black-forest-labs/FLUX.1-Fill-dev",
            ],
        )
        self._seed_parameter = SeedParameter(node)
        self._input_image_size = (None, None)

    def add_input_parameters(self) -> None:
        self._huggingface_repo_parameter.add_input_parameters()
        self._node.add_parameter(
            Parameter(
                name="text_encoder",
                input_types=["str"],
                type="str",
                allowed_modes=set(),
                tooltip="text_encoder",
                default_value="openai/clip-vit-large-patch14",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="text_encoder_2",
                input_types=["str"],
                type="str",
                allowed_modes=set(),
                tooltip="text_encoder_2",
                default_value="google/t5-v1_1-xxl",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="input_image",
                input_types=["ImageArtifact", "ImageUrlArtifact"],
                type="ImageArtifact",
                tooltip="input_image",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="prompt",
                default_value="",
                input_types=["str"],
                type="str",
                tooltip="prompt",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="prompt_2",
                default_value="",
                input_types=["str"],
                type="str",
                tooltip="prompt",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="num_inference_steps",
                default_value=28,
                input_types=["int"],
                type="int",
                tooltip="num_inference_steps",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="guidance_scale",
                default_value=50,
                input_types=["float"],
                type="float",
                tooltip="guidance_scale",
                ui_options={"slider": {"min_val": 1, "max_val": 100}, "step": 1},
            )
        )
        self._seed_parameter.add_input_parameters()

    def add_output_parameters(self) -> None:
        self._node.add_parameter(
            Parameter(
                name="output_image",
                output_type="ImageArtifact",
                tooltip="The output image",
                allowed_modes={ParameterMode.OUTPUT},
            )
        )

    def validate_before_node_run(self) -> list[Exception] | None:
        errors = self._huggingface_repo_parameter.validate_before_node_run() or []
        return errors or None

    def after_value_set(self, parameter: Parameter, value: Any, modified_parameters_set: set[str]) -> None:
        self._seed_parameter.after_value_set(parameter, value, modified_parameters_set)

    def validate_before_node_process(self) -> None:
        input_image_pil = self.get_input_image_pil()
        if input_image_pil.width != 512:  # noqa: PLR2004
            msg = f"The input image's width must be 512. Current width: {input_image_pil.width}"
            raise RuntimeError(msg)

    def preprocess(self) -> None:
        self._seed_parameter.preprocess()

    def get_repo_revision(self) -> tuple[str, str]:
        return self._huggingface_repo_parameter.get_repo_revision()

    def get_input_image_pil(self) -> Image:
        input_image_artifact = self._node.get_parameter_value("input_image")
        if isinstance(input_image_artifact, ImageUrlArtifact):
            input_image_artifact = ImageLoader().parse(input_image_artifact.to_bytes())
        input_image_pil = image_artifact_to_pil(input_image_artifact)
        return input_image_pil.convert("RGB")

    def get_dyptych_image(self) -> Image:
        input_image = self.get_input_image_pil()
        width, height = input_image.size
        dyptych_image = PIL.Image.new("RGB", (width * 2, height))
        # Place the input image in the left half of the diptych image.
        dyptych_image.paste(input_image, (0, 0))
        return dyptych_image

    def get_dyptych_mask(self) -> Image:
        input_image = self.get_input_image_pil()
        width, height = input_image.size
        dyptych_mask_array = np.zeros((height, width * 2), dtype=np.uint8)
        dyptych_mask_array[:, width:] = 255
        dyptych_mask = PIL.Image.fromarray(dyptych_mask_array)
        return dyptych_mask

    def extract_output_image(self, diptych_image_pil: Image) -> Image:
        w, h = diptych_image_pil.size
        right_image_pil = diptych_image_pil.crop((w // 2, 0, w, h))
        return right_image_pil

    def get_prompt(self) -> str:
        prompt = self._node.get_parameter_value("prompt")
        return (
            "A diptych with two side-by-side images of the same scene. "
            f"On the right, the scene is exactly the same as on the left but {prompt}"
        )

    def get_prompt_2(self) -> str:
        prompt_2 = self._node.get_parameter_value("prompt_2")
        if not prompt_2:
            return self.get_prompt()
        return (
            "A diptych with two side-by-side images of the same scene. "
            f"On the right, the scene is exactly the same as on the left but {prompt_2}"
        )

    def get_num_inference_steps(self) -> int:
        return int(self._node.get_parameter_value("num_inference_steps"))

    def get_guidance_scale(self) -> float:
        return float(self._node.get_parameter_value("guidance_scale"))

    def get_pipe_kwargs(self) -> dict:
        width, height = self.get_input_image_pil().size
        return {
            "prompt": self.get_prompt(),
            "prompt_2": self.get_prompt_2(),
            "width": width * 2,
            "height": height,
            "image": self.get_dyptych_image(),
            "mask_image": self.get_dyptych_mask(),
            "num_inference_steps": self.get_num_inference_steps(),
            "guidance_scale": self.get_guidance_scale(),
            "generator": self._seed_parameter.get_generator(),
        }

    def publish_output_image_preview_placeholder(self) -> None:
        width, height = self.get_input_image_pil().size
        # Immediately set a preview placeholder image to make it react quickly and adjust
        # the size of the image preview on the node.
        preview_placeholder_image = PIL.Image.new("RGB", (width, height), color="black")
        self._node.publish_update_to_parameter("output_image", pil_to_image_artifact(preview_placeholder_image))

    def latents_to_image_pil(
        self, pipe: diffusers.FluxPipeline | diffusers.FluxControlNetPipeline, latents: Any
    ) -> Image:
        width, height = self.get_input_image_pil().size
        width *= 2
        latents = pipe._unpack_latents(latents, height, width, pipe.vae_scale_factor)
        latents = (latents / pipe.vae.config.scaling_factor) + pipe.vae.config.shift_factor
        image = pipe.vae.decode(latents, return_dict=False)[0]
        # TODO: https://github.com/griptape-ai/griptape-nodes/issues/845
        intermediate_pil_image = pipe.image_processor.postprocess(image, output_type="pil")[0]
        return self.extract_output_image(intermediate_pil_image)

    def publish_output_image_preview_latents(
        self, pipe: diffusers.FluxPipeline | diffusers.FluxControlNetPipeline, latents: Any
    ) -> None:
        preview_image_pil = self.latents_to_image_pil(pipe, latents)
        preview_image_artifact = pil_to_image_artifact(preview_image_pil)
        self._node.publish_update_to_parameter("output_image", preview_image_artifact)

    def publish_output_image(self, output_image_pil: Image) -> None:
        image_artifact = pil_to_image_artifact(self.extract_output_image(output_image_pil))
        self._node.set_parameter_value("output_image", image_artifact)
        self._node.parameter_output_values["output_image"] = image_artifact
