import logging
from typing import Any

import diffusers  # type: ignore[reportMissingImports]
import PIL.Image
from PIL.Image import Image
from pillow_nodes_library.utils import pil_to_image_artifact  # type: ignore[reportMissingImports]

from diffusers_nodes_library.common.parameters.huggingface_repo_parameter import HuggingFaceRepoParameter
from diffusers_nodes_library.common.parameters.seed_parameter import SeedParameter
from griptape_nodes.exe_types.core_types import Parameter
from griptape_nodes.exe_types.node_types import BaseNode

# Constants for validation
MIN_DIMENSION = 512
MAX_DIMENSION = 2048

logger = logging.getLogger("diffusers_nodes_library")


class Cogview4PipelineParameters:
    def __init__(self, node: BaseNode):
        self._node = node
        self._huggingface_repo_parameter = HuggingFaceRepoParameter(
            node,
            repo_ids=[
                "THUDM/CogView4-6B",
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
                tooltip="Text prompt for image generation (supports Chinese)",
                default_value="A beautiful landscape with mountains and a lake",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="negative_prompt",
                input_types=["str"],
                type="str",
                tooltip="Negative text prompt to guide what not to generate",
                default_value="",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="height",
                input_types=["int"],
                type="int",
                tooltip="Height of the generated image (must be divisible by 32, range 512-2048)",
                default_value=1024,
            )
        )
        self._node.add_parameter(
            Parameter(
                name="width",
                input_types=["int"],
                type="int",
                tooltip="Width of the generated image (must be divisible by 32, range 512-2048)",
                default_value=1024,
            )
        )
        self._node.add_parameter(
            Parameter(
                name="num_inference_steps",
                input_types=["int"],
                type="int",
                tooltip="Number of denoising steps",
                default_value=50,
            )
        )
        self._node.add_parameter(
            Parameter(
                name="guidance_scale",
                input_types=["float"],
                type="float",
                tooltip="Guidance scale for classifier-free guidance",
                default_value=7.0,
            )
        )
        self._seed_parameter.add_input_parameters()

    def add_output_parameters(self) -> None:
        self._node.add_parameter(
            Parameter(
                name="image",
                input_types=[],
                type="ImageArtifact",
                tooltip="Generated image",
            )
        )

    def get_repo_revision(self) -> tuple[str, str]:
        return self._huggingface_repo_parameter.get_repo_revision()

    def get_width(self) -> int:
        return int(self.get_width())

    def get_height(self) -> int:
        return int(self.get_height())

    def get_num_inference_steps(self) -> int:
        return self._node.get_parameter_value("num_inference_steps")

    def get_pipe_kwargs(self) -> dict[str, Any]:
        return {
            "prompt": self._node.get_parameter_value("prompt"),
            "negative_prompt": self._node.get_parameter_value("negative_prompt") or None,
            "height": self.get_height(),
            "width": self.get_width(),
            "num_inference_steps": self._node.get_parameter_value("num_inference_steps"),
            "guidance_scale": self._node.get_parameter_value("guidance_scale"),
            "generator": self._seed_parameter.get_generator(),
        }

    def publish_output_image_preview_placeholder(self) -> None:
        width = self.get_width()
        height = self.get_height()
        preview_placeholder_image = PIL.Image.new("RGB", (width, height), color="black")
        self._node.publish_update_to_parameter("output_image", pil_to_image_artifact(preview_placeholder_image))

    def publish_output_image_preview_latents(self, pipe: diffusers.CogView4Pipeline, latents: Any) -> None:
        try:
            with pipe.vae.no_grad():
                image = pipe.vae.decode(latents / pipe.vae.config.scaling_factor, return_dict=False)[0]
                image = pipe.image_processor.postprocess(image, output_type="pil")[0]
                self._node.publish_update_to_parameter("image", pil_to_image_artifact(image))
        except Exception as e:
            logger.warning("Failed to generate preview: %s", e)

    def publish_output_image(self, image: Image) -> None:
        self._node.publish_update_to_parameter("image", pil_to_image_artifact(image))

    def validate_before_node_run(self) -> list[Exception]:
        errors = []

        height = self.get_height()
        width = self.get_width()

        if height % 32 != 0:
            errors.append(ValueError("Height must be divisible by 32"))
        if width % 32 != 0:
            errors.append(ValueError("Width must be divisible by 32"))
        if height < MIN_DIMENSION or height > MAX_DIMENSION:
            errors.append(ValueError(f"Height must be between {MIN_DIMENSION} and {MAX_DIMENSION}"))
        if width < MIN_DIMENSION or width > MAX_DIMENSION:
            errors.append(ValueError(f"Width must be between {MIN_DIMENSION} and {MAX_DIMENSION}"))

        return errors

    def preprocess(self) -> None:
        pass

    def after_value_set(self, parameter: Parameter, value: Any, modified_parameters_set: set[str]) -> None:
        pass
