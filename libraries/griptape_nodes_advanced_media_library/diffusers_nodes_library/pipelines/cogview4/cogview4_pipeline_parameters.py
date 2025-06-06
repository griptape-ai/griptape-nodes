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
                allowed_modes={ParameterMode.MANUAL},
                tooltip="Text prompt for image generation (supports Chinese)",
                default_value="A beautiful landscape with mountains and a lake",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="negative_prompt",
                input_types=["str"],
                type="str",
                allowed_modes={ParameterMode.MANUAL},
                tooltip="Negative text prompt to guide what not to generate",
                default_value="",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="height",
                input_types=["int"],
                type="int",
                allowed_modes={ParameterMode.MANUAL},
                tooltip="Height of the generated image (must be divisible by 32, range 512-2048)",
                default_value=1024,
            )
        )
        self._node.add_parameter(
            Parameter(
                name="width",
                input_types=["int"],
                type="int",
                allowed_modes={ParameterMode.MANUAL},
                tooltip="Width of the generated image (must be divisible by 32, range 512-2048)",
                default_value=1024,
            )
        )
        self._node.add_parameter(
            Parameter(
                name="num_inference_steps",
                input_types=["int"],
                type="int",
                allowed_modes={ParameterMode.MANUAL},
                tooltip="Number of denoising steps",
                default_value=50,
            )
        )
        self._node.add_parameter(
            Parameter(
                name="guidance_scale",
                input_types=["float"],
                type="float",
                allowed_modes={ParameterMode.MANUAL},
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
                type="griptape_nodes_library.exe_types.core_types.ImageArtifact",
                allowed_modes=set(),
                tooltip="Generated image",
            )
        )

    def get_repo_revision(self) -> tuple[str, str]:
        return self._huggingface_repo_parameter.get_repo_revision()

    def get_num_inference_steps(self) -> int:
        return self._node.get_input_parameter_value("num_inference_steps")

    def get_pipe_kwargs(self) -> dict[str, Any]:
        return {
            "prompt": self._node.get_input_parameter_value("prompt"),
            "negative_prompt": self._node.get_input_parameter_value("negative_prompt") or None,
            "height": self._node.get_input_parameter_value("height"),
            "width": self._node.get_input_parameter_value("width"),
            "num_inference_steps": self._node.get_input_parameter_value("num_inference_steps"),
            "guidance_scale": self._node.get_input_parameter_value("guidance_scale"),
            "generator": self._seed_parameter.get_generator(),
        }

    def publish_output_image_preview_placeholder(self) -> None:
        height = self._node.get_input_parameter_value("height")
        width = self._node.get_input_parameter_value("width")
        placeholder = PIL.Image.new("RGB", (width, height), (128, 128, 128))
        self._node.set_output_parameter_value("image", pil_to_image_artifact(placeholder))

    def publish_output_image_preview_latents(self, pipe: diffusers.CogView4Pipeline, latents: Any) -> None:
        try:
            with pipe.vae.no_grad():
                image = pipe.vae.decode(latents / pipe.vae.config.scaling_factor, return_dict=False)[0]
                image = pipe.image_processor.postprocess(image, output_type="pil")[0]
                self._node.set_output_parameter_value("image", pil_to_image_artifact(image))
        except Exception as e:
            logger.warning(f"Failed to generate preview: {e}")

    def publish_output_image(self, image: Image) -> None:
        self._node.set_output_parameter_value("image", pil_to_image_artifact(image))

    def validate_before_node_run(self) -> list[Exception]:
        errors = []
        
        height = self._node.get_input_parameter_value("height")
        width = self._node.get_input_parameter_value("width")
        
        if height % 32 != 0:
            errors.append(ValueError("Height must be divisible by 32"))
        if width % 32 != 0:
            errors.append(ValueError("Width must be divisible by 32"))
        if height < 512 or height > 2048:
            errors.append(ValueError("Height must be between 512 and 2048"))
        if width < 512 or width > 2048:
            errors.append(ValueError("Width must be between 512 and 2048"))
            
        return errors

    def preprocess(self) -> None:
        pass

    def after_value_set(self, parameter: Parameter, value: Any, modified_parameters_set: set[str]) -> None:
        pass