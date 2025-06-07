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


class StableCascadeCombinedPipelineParameters:
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
                allowed_modes={ParameterMode.OUTPUT},
                tooltip="Generated image",
            )
        )

    def validate_before_node_run(self) -> list[Exception] | None:
        errors = []

        huggingface_errors = self._huggingface_repo_parameter.validate_before_node_run()
        if huggingface_errors:
            errors.extend(huggingface_errors)

        # Validate input image
        input_image = self._node.get_parameter_value("input_image")
        if input_image is None:
            errors.append(ValueError("Input image is required"))

        return errors if errors else None

    def after_value_set(self, parameter: Parameter, value: Any, modified_parameters_set: set[str]) -> None:
        self._seed_parameter.after_value_set(parameter, value, modified_parameters_set)

    def preprocess(self) -> None:
        self._seed_parameter.preprocess()

    def get_repo_revision(self) -> tuple[str, str | None]:
        return self._huggingface_repo_parameter.get_repo_revision()

    def get_num_inference_steps(self) -> int:
        return self._node.get_parameter_value("num_inference_steps")

    def get_pipe_kwargs(self) -> dict[str, Any]:
        kwargs = {
            "prompt": self._node.get_parameter_value("prompt"),
            "height": self._node.get_parameter_value("height"),
            "width": self._node.get_parameter_value("width"),
            "num_inference_steps": self._node.get_parameter_value("num_inference_steps"),
            "guidance_scale": self._node.get_parameter_value("guidance_scale"),
            "prior_num_inference_steps": self._node.get_parameter_value("prior_num_inference_steps"),
            "prior_guidance_scale": self._node.get_parameter_value("prior_guidance_scale"),
            "generator": self._seed_parameter.get_generator(),
        }

        negative_prompt = self._node.get_parameter_value("negative_prompt")
        if negative_prompt:
            kwargs["negative_prompt"] = negative_prompt

        return kwargs

    def publish_output_image_preview_placeholder(self) -> None:
        placeholder_image = PIL.Image.new("RGB", (1024, 1024), (128, 128, 128))
        self._node.publish_update_to_parameter("image", pil_to_image_artifact(placeholder_image))

    def publish_output_image_preview_latents(self, pipe: diffusers.StableCascadeCombinedPipeline, latents: Any) -> None:
        if hasattr(pipe, "vqgan"):
            with pipe.vqgan.disable_slicing():
                images = pipe.vqgan.decode(latents)[0]
                images = (images / 2 + 0.5).clamp(0, 1)
                images = images.cpu().permute(0, 2, 3, 1).float().numpy()
                image = pipe.image_processor.numpy_to_pil(images)[0]
                self._node.publish_update_to_parameter("image", pil_to_image_artifact(image))

    def publish_output_image(self, image: PIL.Image.Image) -> None:
        self._node.parameter_output_values["image"] = pil_to_image_artifact(image)
