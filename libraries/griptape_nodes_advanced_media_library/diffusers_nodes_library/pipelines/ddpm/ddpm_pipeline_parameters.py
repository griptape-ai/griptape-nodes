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

# Constants
MAX_INFERENCE_STEPS = 10000


class DdpmPipelineParameters:
    def __init__(self, node: BaseNode):
        self._node = node
        self._huggingface_repo_parameter = HuggingFaceRepoParameter(
            node,
            repo_ids=[
                "google/ddpm-celebahq-256",
                "google/ddpm-church-256",
                "google/ddpm-bedroom-256",
            ],
        )
        self._seed_parameter = SeedParameter(node)

    def add_input_parameters(self) -> None:
        self._huggingface_repo_parameter.add_input_parameters()
        self._node.add_parameter(
            Parameter(
                name="num_inference_steps",
                default_value=1000,
                input_types=["int"],
                type="int",
                tooltip="Number of denoising steps",
            )
        )
        self._seed_parameter.add_input_parameters()

    def add_output_parameters(self) -> None:
        self._node.add_parameter(
            Parameter(
                name="image",
                input_types=[],
                type="ImageArtifact",
                allowed_modes={ParameterMode.OUTPUT},
                tooltip="Generated image",
            )
        )

    def validate_before_node_run(self) -> list[Exception]:
        errors = self._huggingface_repo_parameter.validate_before_node_run() or []

        # Validate num_inference_steps
        try:
            steps = self.get_num_inference_steps()
            if steps <= 0:
                errors.append(ValueError("Number of inference steps must be positive"))
            if steps > MAX_INFERENCE_STEPS:
                errors.append(ValueError(f"Number of inference steps too large (max {MAX_INFERENCE_STEPS})"))
        except Exception as e:
            errors.append(e)

        return errors

    def after_value_set(self, parameter: Parameter, value: Any, modified_parameters_set: set[str]) -> None:
        self._seed_parameter.after_value_set(parameter, value, modified_parameters_set)

    def preprocess(self) -> None:
        self._seed_parameter.preprocess()

    def get_repo_revision(self) -> tuple[str, str]:
        return self._huggingface_repo_parameter.get_repo_revision()

    def publish_output_image_preview_placeholder(self) -> None:
        # DDPM typically outputs 256x256 images
        width = 256
        height = 256
        preview_placeholder_image = PIL.Image.new("RGB", (width, height), color="black")
        self._node.publish_update_to_parameter("image", pil_to_image_artifact(preview_placeholder_image))

    def get_num_inference_steps(self) -> int:
        return int(self._node.get_parameter_value("num_inference_steps"))

    def get_pipe_kwargs(self) -> dict:
        return {
            "num_inference_steps": self.get_num_inference_steps(),
            "generator": self._seed_parameter.get_generator(),
        }

    def latents_to_image_pil(self, pipe: diffusers.DDPMPipeline, latents: Any) -> Image:
        # For DDPM, latents are typically the denoised samples
        image = pipe.unet.decode_latents(latents)
        intermediate_pil_image = pipe.image_processor.postprocess(image, output_type="pil")[0]
        return intermediate_pil_image

    def publish_output_image_preview_latents(self, pipe: diffusers.DDPMPipeline, latents: Any) -> None:
        try:
            preview_image_pil = self.latents_to_image_pil(pipe, latents)
            preview_image_artifact = pil_to_image_artifact(preview_image_pil)
            self._node.publish_update_to_parameter("image", preview_image_artifact)
        except Exception as e:
            # If preview fails, skip it
            logger.debug("Failed to generate preview image: %s", e)

    def publish_output_image(self, output_image_pil: Image) -> None:
        image_artifact = pil_to_image_artifact(output_image_pil)
        self._node.parameter_output_values["image"] = image_artifact
