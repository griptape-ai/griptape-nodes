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


class StableCascadePipelineParameters:
    def __init__(self, node: BaseNode):
        self._node = node
        self._huggingface_repo_parameter = HuggingFaceRepoParameter(
            node,
            repo_ids=[
                "stabilityai/stable-cascade",
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
                tooltip="prompt",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="negative_prompt",
                default_value="",
                input_types=["str"],
                type="str",
                tooltip="optional negative_prompt",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="width",
                default_value=1024,
                input_types=["int"],
                type="int",
                tooltip="width",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="height",
                default_value=1024,
                input_types=["int"],
                type="int",
                tooltip="height",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="guidance_scale",
                default_value=4.0,
                input_types=["float"],
                type="float",
                tooltip="guidance_scale",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="num_inference_steps",
                default_value=10,
                input_types=["int"],
                type="int",
                tooltip="num_inference_steps for stage B",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="prior_num_inference_steps",
                default_value=20,
                input_types=["int"],
                type="int",
                tooltip="num_inference_steps for stage C (prior)",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="prior_guidance_scale",
                default_value=4.0,
                input_types=["float"],
                type="float",
                tooltip="guidance scale for stage C (prior)",
            )
        )
        self._seed_parameter.add_input_parameters()

    def add_output_parameters(self) -> None:
        self._node.add_parameter(
            Parameter(
                name="image",
                type="image",
                allowed_modes=set([ParameterMode.OUTPUT]),
                tooltip="Generated image",
            )
        )

    def get_repo_revision(self) -> tuple[str, str | None]:
        return self._huggingface_repo_parameter.get_repo_revision()

    def get_num_inference_steps(self) -> int:
        return self._node.get_parameter("num_inference_steps").value

    def get_pipe_kwargs(self) -> dict[str, Any]:
        kwargs = {
            "prompt": self._node.get_parameter("prompt").value,
            "height": self._node.get_parameter("height").value,
            "width": self._node.get_parameter("width").value,
            "num_inference_steps": self._node.get_parameter("num_inference_steps").value,
            "guidance_scale": self._node.get_parameter("guidance_scale").value,
            "prior_num_inference_steps": self._node.get_parameter("prior_num_inference_steps").value,
            "prior_guidance_scale": self._node.get_parameter("prior_guidance_scale").value,
            "generator": self._seed_parameter.get_generator(),
        }

        negative_prompt = self._node.get_parameter("negative_prompt").value
        if negative_prompt:
            kwargs["negative_prompt"] = negative_prompt

        return kwargs

    def publish_output_image_preview_placeholder(self) -> None:
        placeholder_image = PIL.Image.new("RGB", (1024, 1024), (128, 128, 128))
        self._node.set_parameter("image", pil_to_image_artifact(placeholder_image))

    def publish_output_image_preview_latents(self, pipe: diffusers.StableCascadePipeline, latents) -> None:
        if hasattr(pipe, "vqgan"):
            with pipe.vqgan.disable_slicing():
                images = pipe.vqgan.decode(latents)[0]
                images = (images / 2 + 0.5).clamp(0, 1)
                images = images.cpu().permute(0, 2, 3, 1).float().numpy()
                image = pipe.image_processor.numpy_to_pil(images)[0]
                self._node.set_parameter("image", pil_to_image_artifact(image))

    def publish_output_image(self, image: PIL.Image.Image) -> None:
        self._node.set_parameter("image", pil_to_image_artifact(image))

    def after_value_set(self, parameter: Parameter, value: Any, modified_parameters_set: set[str]) -> None:
        self._huggingface_repo_parameter.after_value_set(parameter, value, modified_parameters_set)

    def validate_before_node_run(self) -> list[Exception]:
        errors = []
        errors.extend(self._huggingface_repo_parameter.validate_before_node_run())
        return errors

    def preprocess(self) -> None:
        self._huggingface_repo_parameter.preprocess()
        self._seed_parameter.preprocess()