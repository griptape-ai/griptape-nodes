import logging
from typing import Any

import diffusers  # type: ignore[reportMissingImports]
import PIL.Image
from pillow_nodes_library.utils import pil_to_image_artifact  # type: ignore[reportMissingImports]

from diffusers_nodes_library.common.parameters.huggingface_repo_parameter import HuggingFaceRepoParameter
from diffusers_nodes_library.common.parameters.seed_parameter import SeedParameter
from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import BaseNode

logger = logging.getLogger("diffusers_nodes_library")


class SanaPipelineParameters:
    def __init__(self, node: BaseNode):
        self._node = node
        self._huggingface_repo_parameter = HuggingFaceRepoParameter(
            node,
            repo_ids=[
                "Efficient-Large-Model/Sana_1600M_1024px_BF16_diffusers",
                "Efficient-Large-Model/Sana_600M_512px_diffusers",
                "Efficient-Large-Model/Sana_1600M_1024px_diffusers",
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
                tooltip="Text prompt describing the image to generate",
            )
        )

        self._node.add_parameter(
            Parameter(
                name="negative_prompt",
                input_types=["str"],
                type="str",
                tooltip="Negative prompt to guide what to avoid",
                default_value="",
            )
        )

        self._node.add_parameter(
            Parameter(
                name="height",
                input_types=["int"],
                type="int",
                tooltip="Height of generated image",
                default_value=1024,
            )
        )

        self._node.add_parameter(
            Parameter(
                name="width",
                input_types=["int"],
                type="int",
                tooltip="Width of generated image",
                default_value=1024,
            )
        )

        self._node.add_parameter(
            Parameter(
                name="num_inference_steps",
                input_types=["int"],
                type="int",
                tooltip="Number of denoising steps",
                default_value=20,
            )
        )

        self._node.add_parameter(
            Parameter(
                name="guidance_scale",
                input_types=["float"],
                type="float",
                tooltip="Guidance scale for classifier-free guidance",
                default_value=4.5,
            )
        )

        self._seed_parameter.add_input_parameters()

    def add_output_parameters(self) -> None:
        self._node.add_parameter(
            Parameter(
                name="output_image",
                type="ImageArtifact",
                allowed_modes={ParameterMode.OUTPUT},
                tooltip="Generated image",
            )
        )

    def validate_before_node_run(self) -> list[Exception] | None:
        errors = []

        if not self._node.get_parameter_value("prompt"):
            errors.append(ValueError("Prompt is required"))

        height = self._node.get_parameter_value("height")
        width = self._node.get_parameter_value("width")

        if height <= 0 or width <= 0:
            errors.append(ValueError("Height and width must be positive"))

        if height % 32 != 0 or width % 32 != 0:
            errors.append(ValueError("Height and width must be multiples of 32"))

        return errors if errors else None

    def preprocess(self) -> None:
        self._seed_parameter.preprocess()

    def get_repo_revision(self) -> tuple[str, str]:
        return self._huggingface_repo_parameter.get_repo_revision()

    def get_num_inference_steps(self) -> int:
        return self._node.get_parameter_value("num_inference_steps")

    def get_pipe_kwargs(self) -> dict[str, Any]:
        return {
            "prompt": self._node.get_parameter_value("prompt"),
            "negative_prompt": self._node.get_parameter_value("negative_prompt"),
            "height": self._node.get_parameter_value("height"),
            "width": self._node.get_parameter_value("width"),
            "num_inference_steps": self._node.get_parameter_value("num_inference_steps"),
            "guidance_scale": self._node.get_parameter_value("guidance_scale"),
            "generator": self._seed_parameter.get_generator(),
        }

    def publish_output_image_preview_placeholder(self) -> None:
        width = self._node.get_parameter_value("width")
        height = self._node.get_parameter_value("height")
        output_image_pil = PIL.Image.new("RGB", (width, height), color=(255, 255, 255))
        output_image_artifact = pil_to_image_artifact(output_image_pil)
        self._node.publish_update_to_parameter("output_image", output_image_artifact)

    def publish_output_image_preview_latents(self, pipe: diffusers.SanaPipeline, latents: Any) -> None:
        """Publish preview of current latents during generation."""

    def publish_output_image(self, output_image_pil: PIL.Image.Image) -> None:
        output_image_artifact = pil_to_image_artifact(output_image_pil)
        self._node.parameter_output_values["output_image"] = output_image_artifact
