import logging
from typing import Any

import PIL.Image
import torch  # type: ignore[reportMissingImports]
from PIL.Image import Image
from pillow_nodes_library.utils import (  # type: ignore[reportMissingImports]
    image_artifact_to_pil,
    pil_to_image_artifact,
)

from diffusers_nodes_library.common.parameters.huggingface_repo_parameter import (
    HuggingFaceRepoParameter,
)
from diffusers_nodes_library.common.parameters.seed_parameter import SeedParameter
from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import BaseNode

logger = logging.getLogger("diffusers_nodes_library")


class LeditsPpPipelineParameters:
    """Wrapper around the collection of parameters needed for LEDITS++ pipelines."""

    def __init__(self, node: BaseNode):
        self._node = node
        self._huggingface_repo_parameter = HuggingFaceRepoParameter(
            node,
            repo_ids=[
                "runwayml/stable-diffusion-v1-5",
            ],
        )
        self._seed_parameter = SeedParameter(node)

    # ---------------------------------------------------------------------
    # Parameter registration helpers
    # ---------------------------------------------------------------------
    def add_input_parameters(self) -> None:
        self._huggingface_repo_parameter.add_input_parameters()

        self._node.add_parameter(
            Parameter(
                name="input_image",
                input_types=["ImageArtifact", "ImageUrlArtifact"],
                type="ImageArtifact",
                tooltip="Input image to edit",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="editing_prompt",
                default_value="",
                input_types=["str"],
                type="str",
                tooltip="Text prompt describing the desired edit",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="reverse_editing_direction",
                default_value=False,
                input_types=["bool"],
                type="bool",
                tooltip="Whether to reverse the editing direction",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="edit_guidance_scale",
                default_value=10.0,
                input_types=["float"],
                type="float",
                tooltip="Editing guidance scale",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="edit_warmup_steps",
                default_value=10,
                input_types=["int"],
                type="int",
                tooltip="Number of warmup steps for editing",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="edit_cooldown_steps",
                default_value=None,
                input_types=["int"],
                type="int",
                tooltip="Number of cooldown steps for editing (optional)",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="edit_threshold",
                default_value=0.9,
                input_types=["float"],
                type="float",
                tooltip="Threshold for editing strength",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="sem_guidance",
                default_value=False,
                input_types=["bool"],
                type="bool",
                tooltip="Whether to use semantic guidance",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="num_inference_steps",
                default_value=50,
                input_types=["int"],
                type="int",
                tooltip="Number of denoising steps",
            )
        )

        self._seed_parameter.add_input_parameters()

    def add_output_parameters(self) -> None:
        self._node.add_parameter(
            Parameter(
                name="output_image",
                output_type="ImageArtifact",
                tooltip="Edited image",
                allowed_modes={ParameterMode.OUTPUT},
            )
        )

    # ------------------------------------------------------------------
    # Validation / life-cycle hooks
    # ------------------------------------------------------------------
    def validate_before_node_run(self) -> list[Exception] | None:
        errors = self._huggingface_repo_parameter.validate_before_node_run()

        # Validate that input_image is provided
        input_image = self._node.get_parameter_value("input_image")
        if input_image is None:
            errors = errors or []
            errors.append(ValueError("input_image is required"))

        return errors or None

    def after_value_set(self, parameter: Parameter, value: Any, modified_parameters_set: set[str]) -> None:
        self._seed_parameter.after_value_set(parameter, value, modified_parameters_set)

    def preprocess(self) -> None:
        self._seed_parameter.preprocess()

    # ------------------------------------------------------------------
    # Convenience getters
    # ------------------------------------------------------------------
    def get_repo_revision(self) -> tuple[str, str]:
        return self._huggingface_repo_parameter.get_repo_revision()

    def get_input_image(self) -> Image:
        input_image_artifact = self._node.get_parameter_value("input_image")
        return image_artifact_to_pil(input_image_artifact)

    def get_editing_prompt(self) -> str:
        return self._node.get_parameter_value("editing_prompt")

    def get_reverse_editing_direction(self) -> bool:
        return bool(self._node.get_parameter_value("reverse_editing_direction"))

    def get_edit_guidance_scale(self) -> float:
        return float(self._node.get_parameter_value("edit_guidance_scale"))

    def get_edit_warmup_steps(self) -> int:
        return int(self._node.get_parameter_value("edit_warmup_steps"))

    def get_edit_cooldown_steps(self) -> int | None:
        value = self._node.get_parameter_value("edit_cooldown_steps")
        return int(value) if value is not None else None

    def get_edit_threshold(self) -> float:
        return float(self._node.get_parameter_value("edit_threshold"))

    def get_sem_guidance(self) -> bool:
        return bool(self._node.get_parameter_value("sem_guidance"))

    def get_num_inference_steps(self) -> int:
        return int(self._node.get_parameter_value("num_inference_steps"))

    def get_generator(self) -> torch.Generator:
        return self._seed_parameter.get_generator()

    def get_pipe_kwargs(self) -> dict:
        kwargs = {
            "image": self.get_input_image(),
            "editing_prompt": [self.get_editing_prompt()],
            "reverse_editing_direction": [self.get_reverse_editing_direction()],
            "edit_guidance_scale": [self.get_edit_guidance_scale()],
            "edit_warmup_steps": [self.get_edit_warmup_steps()],
            "edit_threshold": [self.get_edit_threshold()],
            "sem_guidance": [self.get_sem_guidance()],
            "num_inference_steps": self.get_num_inference_steps(),
            "generator": self.get_generator(),
        }

        # Only add edit_cooldown_steps if it's not None
        cooldown_steps = self.get_edit_cooldown_steps()
        if cooldown_steps is not None:
            kwargs["edit_cooldown_steps"] = [cooldown_steps]

        return kwargs

    # ------------------------------------------------------------------
    # Preview helpers
    # ------------------------------------------------------------------
    def publish_output_image_preview_placeholder(self) -> None:
        # Use the input image dimensions for the placeholder
        try:
            input_image = self.get_input_image()
            width, height = input_image.size
        except Exception:
            width, height = 512, 512

        preview_placeholder_image = PIL.Image.new("RGB", (width, height), color="black")
        self._node.publish_update_to_parameter("output_image", pil_to_image_artifact(preview_placeholder_image))

    def publish_output_image(self, output_image_pil: Image) -> None:
        image_artifact = pil_to_image_artifact(output_image_pil)
        self._node.set_parameter_value("output_image", image_artifact)
        self._node.parameter_output_values["output_image"] = image_artifact
