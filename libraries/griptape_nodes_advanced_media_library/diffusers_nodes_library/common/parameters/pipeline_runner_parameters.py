import logging
from typing import Any

import PIL.Image
from PIL.Image import Image
from pillow_nodes_library.utils import pil_to_image_artifact  # type: ignore[reportMissingImports]
from utils.directory_utils import check_cleanup_intermediates_directory, get_intermediates_directory_path

from diffusers_nodes_library.common.parameters.seed_parameter import SeedParameter
from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import BaseNode

logger = logging.getLogger("diffusers_nodes_library")


class PipelineRunnerParameters:
    def __init__(self, node: BaseNode):
        self._node = node
        self._seed_parameter = SeedParameter(node)

    def add_input_parameters(self) -> None:
        # Pipeline configuration input (connects to PipelineBuilder output)
        self._node.add_parameter(
            Parameter(
                name="pipeline",
                input_types=["Pipeline Config"],
                type="Pipeline Config",
                tooltip="Pipeline configuration from PipelineBuilder",
                allowed_modes={ParameterMode.INPUT},
            )
        )

        # Text prompts
        self._node.add_parameter(
            Parameter(
                name="prompt",
                default_value="",
                input_types=["str"],
                type="str",
                tooltip="Text prompt for image generation",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="prompt_2",
                input_types=["str"],
                type="str",
                tooltip="Optional secondary prompt (defaults to main prompt)",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="negative_prompt",
                default_value="",
                input_types=["str"],
                type="str",
                tooltip="Negative prompt to avoid certain features",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="negative_prompt_2",
                input_types=["str"],
                type="str",
                tooltip="Optional secondary negative prompt (defaults to main negative prompt)",
            )
        )

        # Generation parameters
        self._node.add_parameter(
            Parameter(
                name="true_cfg_scale",
                default_value=1.0,
                input_types=["float"],
                type="float",
                tooltip="True CFG scale for guidance",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="width",
                default_value=1024,
                input_types=["int"],
                type="int",
                tooltip="Output image width",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="height",
                default_value=1024,
                input_types=["int"],
                type="int",
                tooltip="Output image height",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="num_inference_steps",
                default_value=4,
                input_types=["int"],
                type="int",
                tooltip="Number of denoising inference steps",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="guidance_scale",
                default_value=3.5,
                input_types=["float"],
                type="float",
                tooltip="Guidance scale for classifier-free guidance",
            )
        )

        # Seed parameter
        self._seed_parameter.add_input_parameters()

    def add_output_parameters(self) -> None:
        self._node.add_parameter(
            Parameter(
                name="output_image",
                output_type="ImageArtifact",
                tooltip="Generated image",
                allowed_modes={ParameterMode.OUTPUT},
            )
        )

    def after_value_set(self, parameter: Parameter, value: Any) -> None:
        self._seed_parameter.after_value_set(parameter, value)

    def preprocess(self) -> None:
        self._seed_parameter.preprocess()

    def get_pipeline_config_hash(self) -> str:
        """Get the pipeline configuration hash from the connected PipelineBuilder."""
        return self._node.get_parameter_value("pipeline")

    def publish_output_image_preview_placeholder(self) -> None:
        width = int(self.get_width())
        height = int(self.get_height())

        # Check to ensure there's enough space in the intermediates directory
        # if that setting is enabled.
        check_cleanup_intermediates_directory()

        preview_placeholder_image = PIL.Image.new("RGB", (width, height), color="black")
        self._node.publish_update_to_parameter(
            "output_image",
            pil_to_image_artifact(preview_placeholder_image, directory_path=get_intermediates_directory_path()),
        )

    def get_prompt(self) -> str:
        return self._node.get_parameter_value("prompt")

    def get_prompt_2(self) -> str:
        return self._node.get_parameter_value("prompt_2") or self.get_prompt()

    def get_negative_prompt(self) -> str:
        return self._node.get_parameter_value("negative_prompt")

    def get_negative_prompt_2(self) -> str:
        return self._node.get_parameter_value("negative_prompt_2") or self.get_negative_prompt()

    def get_true_cfg_scale(self) -> float:
        return float(self._node.get_parameter_value("true_cfg_scale"))

    def get_width(self) -> int:
        return int(self._node.get_parameter_value("width"))

    def get_height(self) -> int:
        return int(self._node.get_parameter_value("height"))

    def get_num_inference_steps(self) -> int:
        return int(self._node.get_parameter_value("num_inference_steps"))

    def get_guidance_scale(self) -> float:
        return float(self._node.get_parameter_value("guidance_scale"))

    def get_pipe_kwargs(self) -> dict:
        """Get kwargs for pipeline execution."""
        return {
            "prompt": self.get_prompt(),
            "prompt_2": self.get_prompt_2(),
            "negative_prompt": self.get_negative_prompt(),
            "negative_prompt_2": self.get_negative_prompt_2(),
            "true_cfg_scale": self.get_true_cfg_scale(),
            "width": self.get_width(),
            "height": self.get_height(),
            "num_inference_steps": self.get_num_inference_steps(),
            "guidance_scale": self.get_guidance_scale(),
            "generator": self._seed_parameter.get_generator(),
        }

    def latents_to_image_pil(self, pipe: Any, latents: Any) -> Image:
        """Convert latents to PIL Image for preview."""
        width = int(self._node.parameter_values["width"])
        height = int(self._node.parameter_values["height"])
        latents = pipe._unpack_latents(latents, height, width, pipe.vae_scale_factor)
        latents = (latents / pipe.vae.config.scaling_factor) + pipe.vae.config.shift_factor
        image = pipe.vae.decode(latents, return_dict=False)[0]
        intermediate_pil_image = pipe.image_processor.postprocess(image, output_type="pil")[0]
        return intermediate_pil_image

    def publish_output_image_preview_latents(self, pipe: Any, latents: Any) -> None:
        """Publish intermediate preview during generation."""
        # Check to ensure there's enough space in the intermediates directory
        # if that setting is enabled.
        check_cleanup_intermediates_directory()

        preview_image_pil = self.latents_to_image_pil(pipe, latents)
        preview_image_artifact = pil_to_image_artifact(
            preview_image_pil, directory_path=get_intermediates_directory_path()
        )
        self._node.publish_update_to_parameter("output_image", preview_image_artifact)

    def publish_output_image(self, output_image_pil: Image) -> None:
        """Publish final generated image."""
        image_artifact = pil_to_image_artifact(output_image_pil)
        self._node.set_parameter_value("output_image", image_artifact)
        self._node.parameter_output_values["output_image"] = image_artifact
