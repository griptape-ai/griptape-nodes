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


class Lumina2PipelineParameters:
    def __init__(self, node: BaseNode):
        self._node = node
        self._huggingface_repo_parameter = HuggingFaceRepoParameter(
            node,
            repo_ids=[
                "Alpha-VLLM/Lumina-Next-T2I",
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
                allowed_modes=set(),
                tooltip="The text prompt to guide the image generation.",
                default_value="A majestic lion in the savanna",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="negative_prompt",
                input_types=["str"],
                type="str",
                allowed_modes=set(),
                tooltip="The text prompt to guide what not to include in image generation.",
                default_value="",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="num_inference_steps",
                input_types=["int"],
                type="int",
                allowed_modes=set(),
                tooltip="Number of denoising steps.",
                default_value=20,
                minimum=1,
                maximum=1000,
            )
        )
        self._node.add_parameter(
            Parameter(
                name="guidance_scale",
                input_types=["float"],
                type="float",
                allowed_modes=set(),
                tooltip="Guidance scale for classifier-free guidance.",
                default_value=4.0,
                minimum=0.0,
                maximum=50.0,
            )
        )
        self._node.add_parameter(
            Parameter(
                name="width",
                input_types=["int"],
                type="int",
                allowed_modes=set(),
                tooltip="Width of the generated image.",
                default_value=1024,
                minimum=64,
                maximum=2048,
                step=64,
            )
        )
        self._node.add_parameter(
            Parameter(
                name="height",
                input_types=["int"],
                type="int",
                allowed_modes=set(),
                tooltip="Height of the generated image.",
                default_value=1024,
                minimum=64,
                maximum=2048,
                step=64,
            )
        )
        self._seed_parameter.add_input_parameters()

    def add_output_parameters(self) -> None:
        self._node.add_parameter(
            Parameter(
                name="output_image",
                input_types=[],
                type="image",
                allowed_modes={ParameterMode.OUTPUT},
                tooltip="Generated image",
            )
        )

    def after_value_set(self, parameter: Parameter, value: Any, modified_parameters_set: set[str]) -> None:
        self._huggingface_repo_parameter.after_value_set(parameter, value, modified_parameters_set)

    def validate_before_node_run(self) -> list[Exception] | None:
        errors = []
        
        huggingface_errors = self._huggingface_repo_parameter.validate_before_node_run()
        if huggingface_errors:
            errors.extend(huggingface_errors)
        
        return errors if errors else None

    def preprocess(self) -> None:
        self._seed_parameter.preprocess()

    def get_repo_revision(self) -> tuple[str, str]:
        return self._huggingface_repo_parameter.get_repo_revision()

    def get_num_inference_steps(self) -> int:
        return self._node.get_parameter_value("num_inference_steps")

    def get_pipe_kwargs(self) -> dict[str, Any]:
        pipe_kwargs = {
            "prompt": self._node.get_parameter_value("prompt"),
            "negative_prompt": self._node.get_parameter_value("negative_prompt"),
            "num_inference_steps": self._node.get_parameter_value("num_inference_steps"),
            "guidance_scale": self._node.get_parameter_value("guidance_scale"),
            "width": self._node.get_parameter_value("width"),
            "height": self._node.get_parameter_value("height"),
            "generator": self._seed_parameter.get_generator(),
        }
        
        # Remove empty negative prompt
        if not pipe_kwargs["negative_prompt"]:
            del pipe_kwargs["negative_prompt"]
            
        return pipe_kwargs

    def publish_output_image_preview_placeholder(self) -> None:
        width = self._node.get_parameter_value("width")
        height = self._node.get_parameter_value("height")
        placeholder_image = PIL.Image.new("RGB", (width, height), color="black")
        self._node.set_parameter_value("output_image", pil_to_image_artifact(placeholder_image))

    def publish_output_image_preview_latents(self, pipe: diffusers.Lumina2Text2ImgPipeline, latents: Any) -> None:
        try:
            preview_image = pipe.vae.decode(latents / pipe.vae.config.scaling_factor, return_dict=False)[0]
            preview_image = pipe.image_processor.postprocess(preview_image, output_type="pil")[0]
            self._node.set_parameter_value("output_image", pil_to_image_artifact(preview_image))
        except Exception as e:
            logger.warning(f"Failed to generate preview from latents: {e}")

    def publish_output_image(self, image: Image) -> None:
        self._node.set_parameter_value("output_image", pil_to_image_artifact(image))