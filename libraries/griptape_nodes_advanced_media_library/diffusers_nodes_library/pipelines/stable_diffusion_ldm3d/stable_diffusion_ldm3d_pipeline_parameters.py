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


class StableDiffusionLdm3dPipelineParameters:
    def __init__(self, node: BaseNode):
        self._node = node
        self._huggingface_repo_parameter = HuggingFaceRepoParameter(
            node,
            repo_ids=[
                "Intel/ldm3d-4c",
                "Intel/ldm3d",
            ],
        )
        self._seed_parameter = SeedParameter(node)

    def add_input_parameters(self) -> None:
        self._huggingface_repo_parameter.add_input_parameters()
        self._node.add_parameter(
            Parameter(
                name="prompt",
                default_value="",
                input_types=["str"],
                type="str",
                tooltip="Text prompt describing the image to generate",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="negative_prompt",
                default_value="",
                input_types=["str"],
                type="str",
                tooltip="Optional negative prompt to guide what not to generate",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="num_inference_steps",
                default_value=20,
                input_types=["int"],
                type="int",
                tooltip="Number of denoising steps",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="guidance_scale",
                default_value=7.5,
                input_types=["float"],
                type="float",
                tooltip="Guidance scale for classifier-free guidance",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="height",
                default_value=512,
                input_types=["int"],
                type="int",
                tooltip="Height of the generated image in pixels",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="width",
                default_value=512,
                input_types=["int"],
                type="int",
                tooltip="Width of the generated image in pixels",
            )
        )
        self._seed_parameter.add_input_parameters()

    def add_output_parameters(self) -> None:
        self._node.add_parameter(
            Parameter(
                name="output_rgb_image",
                type="image",
                output_types=["image"],
                allowed_modes={ParameterMode.OUTPUT},
                tooltip="Generated RGB image",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="output_depth_image",
                type="image",
                output_types=["image"],
                allowed_modes={ParameterMode.OUTPUT},
                tooltip="Generated depth image",
            )
        )

    def after_value_set(self, parameter: Parameter, value: Any, modified_parameters_set: set[str]) -> None:
        self._huggingface_repo_parameter.after_value_set(parameter, value, modified_parameters_set)
        self._seed_parameter.after_value_set(parameter, value, modified_parameters_set)

    def validate_before_node_run(self) -> list[Exception] | None:
        errors = []
        
        repo_errors = self._huggingface_repo_parameter.validate_before_node_run()
        if repo_errors:
            errors.extend(repo_errors)
            
        seed_errors = self._seed_parameter.validate_before_node_run()
        if seed_errors:
            errors.extend(seed_errors)
            
        return errors or None

    def preprocess(self) -> None:
        self._huggingface_repo_parameter.preprocess()
        self._seed_parameter.preprocess()

    def get_repo_revision(self) -> tuple[str, str]:
        return self._huggingface_repo_parameter.get_repo_revision()

    def get_num_inference_steps(self) -> int:
        return self._node.get_parameter_value("num_inference_steps")

    def get_pipe_kwargs(self) -> dict[str, Any]:
        kwargs = {
            "prompt": self._node.get_parameter_value("prompt"),
            "num_inference_steps": self._node.get_parameter_value("num_inference_steps"),
            "guidance_scale": self._node.get_parameter_value("guidance_scale"),
            "height": self._node.get_parameter_value("height"),
            "width": self._node.get_parameter_value("width"),
            "generator": self._seed_parameter.get_generator(),
        }
        
        negative_prompt = self._node.get_parameter_value("negative_prompt")
        if negative_prompt:
            kwargs["negative_prompt"] = negative_prompt
            
        return kwargs

    def publish_output_image_preview_placeholder(self) -> None:
        height = self._node.get_parameter_value("height")
        width = self._node.get_parameter_value("width")
        placeholder_rgb = PIL.Image.new("RGB", (width, height), (128, 128, 128))
        placeholder_depth = PIL.Image.new("RGB", (width, height), (64, 64, 64))
        self._node.set_parameter_value("output_rgb_image", pil_to_image_artifact(placeholder_rgb))
        self._node.set_parameter_value("output_depth_image", pil_to_image_artifact(placeholder_depth))

    def publish_output_image_preview_latents(self, pipe: diffusers.StableDiffusionLDM3DPipeline, latents: Any) -> None:
        with pipe.vae.disable_slicing():
            latents = 1 / pipe.vae.config.scaling_factor * latents
            preview_image = pipe.vae.decode(latents).sample
            preview_image = (preview_image / 2 + 0.5).clamp(0, 1)
            preview_image = preview_image.cpu().permute(0, 2, 3, 1).float().numpy()
            preview_image = (preview_image * 255).round().astype("uint8")[0]
            
            # For LDM3D, the latents contain both RGB and depth channels
            if preview_image.shape[-1] >= 3:
                rgb_preview = PIL.Image.fromarray(preview_image[:, :, :3])
                self._node.set_parameter_value("output_rgb_image", pil_to_image_artifact(rgb_preview))
            
            if preview_image.shape[-1] >= 4:
                # Use the 4th channel as depth, convert to grayscale for visualization
                depth_channel = preview_image[:, :, 3]
                depth_preview = PIL.Image.fromarray(depth_channel).convert("RGB")
                self._node.set_parameter_value("output_depth_image", pil_to_image_artifact(depth_preview))

    def publish_output_images(self, rgb_image: Image, depth_image: Image) -> None:
        self._node.set_parameter_value("output_rgb_image", pil_to_image_artifact(rgb_image))
        self._node.set_parameter_value("output_depth_image", pil_to_image_artifact(depth_image))