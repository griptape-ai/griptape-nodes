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


class SemanticStableDiffusionPipelineParameters:
    def __init__(self, node: BaseNode):
        self._node = node
        self._huggingface_repo_parameter = HuggingFaceRepoParameter(
            node,
            repo_ids=[
                "runwayml/stable-diffusion-v1-5",
                "CompVis/stable-diffusion-v1-4",
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
                name="editing_prompt",
                default_value="",
                input_types=["str"],
                type="str",
                tooltip="editing prompt for semantic guidance",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="reverse_editing_direction",
                input_types=["list"],
                type="list",
                tooltip="reverse editing direction for each editing prompt",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="edit_guidance_scale",
                default_value=7.5,
                input_types=["float"],
                type="float",
                tooltip="edit guidance scale",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="edit_warmup_steps",
                default_value=10,
                input_types=["int"],
                type="int",
                tooltip="edit warmup steps",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="edit_threshold",
                default_value=0.9,
                input_types=["float"],
                type="float",
                tooltip="edit threshold",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="sem_guidance",
                default_value=True,
                input_types=["bool"],
                type="bool",
                tooltip="enable semantic guidance",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="width",
                default_value=512,
                input_types=["int"],
                type="int",
                tooltip="width",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="height",
                default_value=512,
                input_types=["int"],
                type="int",
                tooltip="height",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="guidance_scale",
                default_value=7.5,
                input_types=["float"],
                type="float",
                tooltip="guidance_scale",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="num_inference_steps",
                default_value=50,
                input_types=["int"],
                type="int",
                tooltip="num_inference_steps",
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
            "generator": self._seed_parameter.get_generator(),
        }

        negative_prompt = self._node.get_parameter("negative_prompt").value
        if negative_prompt:
            kwargs["negative_prompt"] = negative_prompt

        editing_prompt = self._node.get_parameter("editing_prompt").value
        if editing_prompt:
            kwargs["editing_prompt"] = editing_prompt

        reverse_editing_direction = self._node.get_parameter("reverse_editing_direction").value
        if reverse_editing_direction:
            kwargs["reverse_editing_direction"] = reverse_editing_direction

        kwargs["edit_guidance_scale"] = self._node.get_parameter("edit_guidance_scale").value
        kwargs["edit_warmup_steps"] = self._node.get_parameter("edit_warmup_steps").value
        kwargs["edit_threshold"] = self._node.get_parameter("edit_threshold").value
        kwargs["sem_guidance"] = self._node.get_parameter("sem_guidance").value

        return kwargs

    def publish_output_image_preview_placeholder(self) -> None:
        placeholder_image = PIL.Image.new("RGB", (512, 512), (128, 128, 128))
        self._node.set_parameter("image", pil_to_image_artifact(placeholder_image))

    def publish_output_image_preview_latents(self, pipe: diffusers.SemanticStableDiffusionPipeline, latents) -> None:
        if hasattr(pipe, "vae"):
            with pipe.vae.disable_slicing():
                images = pipe.vae.decode(latents / pipe.vae.config.scaling_factor, return_dict=False)[0]
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