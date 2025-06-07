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


class PaintByExamplePipelineParameters:
    def __init__(self, node: BaseNode):
        self._node = node
        self._huggingface_repo_parameter = HuggingFaceRepoParameter(
            node,
            repo_ids=[
                "Fantasy-Studio/Paint-by-Example",
            ],
        )
        self._seed_parameter = SeedParameter(node)

    def add_input_parameters(self) -> None:
        self._huggingface_repo_parameter.add_input_parameters()

        self._node.add_parameter(
            Parameter(
                name="image",
                input_types=["ImageArtifact", "ImageUrlArtifact"],
                type="ImageArtifact",
                allowed_modes={ParameterMode.INPUT},
                tooltip="Input image to be inpainted",
            )
        )

        self._node.add_parameter(
            Parameter(
                name="mask_image",
                input_types=["ImageArtifact", "ImageUrlArtifact"],
                type="ImageArtifact",
                allowed_modes={ParameterMode.INPUT},
                tooltip="Mask image indicating which areas to inpaint (white = inpaint, black = keep)",
            )
        )

        self._node.add_parameter(
            Parameter(
                name="example_image",
                input_types=["ImageArtifact", "ImageUrlArtifact"],
                type="ImageArtifact",
                allowed_modes={ParameterMode.INPUT},
                tooltip="Example image to guide the inpainting process",
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
                default_value=5.0,
            )
        )

        self._seed_parameter.add_input_parameters()

    def add_output_parameters(self) -> None:
        self._node.add_parameter(
            Parameter(
                name="output_image",
                type="ImageArtifact",
                allowed_modes={ParameterMode.OUTPUT},
                tooltip="Generated inpainted image",
            )
        )

    def validate_before_node_run(self) -> list[Exception] | None:
        errors = []

        if not self._node.get_parameter_value("image"):
            errors.append(ValueError("Input image is required"))
        if not self._node.get_parameter_value("mask_image"):
            errors.append(ValueError("Mask image is required"))
        if not self._node.get_parameter_value("example_image"):
            errors.append(ValueError("Example image is required"))

        return errors if errors else None

    def preprocess(self) -> None:
        self._seed_parameter.preprocess()

    def get_repo_revision(self) -> tuple[str, str]:
        return self._huggingface_repo_parameter.get_repo_revision()

    def get_num_inference_steps(self) -> int:
        return self._node.get_parameter_value("num_inference_steps")

    def get_pipe_kwargs(self) -> dict[str, Any]:
        return {
            "image": self._get_input_image(),
            "mask_image": self._get_mask_image(),
            "example_image": self._get_example_image(),
            "num_inference_steps": self._node.get_parameter_value("num_inference_steps"),
            "guidance_scale": self._node.get_parameter_value("guidance_scale"),
            "generator": self._seed_parameter.get_generator(),
        }

    def _get_input_image(self) -> Image:
        image_artifact = self._node.get_parameter_value("image")
        return image_artifact.value

    def _get_mask_image(self) -> Image:
        mask_artifact = self._node.get_parameter_value("mask_image")
        return mask_artifact.value

    def _get_example_image(self) -> Image:
        example_artifact = self._node.get_parameter_value("example_image")
        return example_artifact.value

    def publish_output_image_preview_placeholder(self) -> None:
        self._node.publish_update_to_parameter("output_image", None)

    def publish_output_image_preview_latents(self, pipe: diffusers.PaintByExamplePipeline, latents: Any) -> None:
        """Publish preview of current latents during generation."""

    def publish_output_image(self, output_image_pil: PIL.Image.Image) -> None:
        output_image_artifact = pil_to_image_artifact(output_image_pil)
        self._node.parameter_output_values["output_image"] = output_image_artifact
