import logging
from typing import Any

import PIL.Image
from PIL.Image import Image
from pillow_nodes_library.utils import pil_to_image_artifact  # type: ignore[reportMissingImports]

import diffusers  # type: ignore[reportMissingImports]

from diffusers_nodes_library.common.parameters.huggingface_repo_parameter import (
    HuggingFaceRepoParameter,
)
from diffusers_nodes_library.common.parameters.seed_parameter import SeedParameter
from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import BaseNode

logger = logging.getLogger("diffusers_nodes_library")


class LatentDiffusionPipelineParameters:
    """Wrapper around the collection of parameters needed for Latent Diffusion pipelines."""

    def __init__(self, node: BaseNode):
        self._node = node
        self._huggingface_repo_parameter = HuggingFaceRepoParameter(
            node,
            repo_ids=[
                "CompVis/ldm-text2im-large-256",
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
                name="prompt",
                default_value="",
                input_types=["str"],
                type="str",
                tooltip="Text prompt",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="eta",
                default_value=0.0,
                input_types=["float"],
                type="float",
                tooltip="DDIM eta parameter controlling stochasticity",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="guidance_scale",
                default_value=1.0,
                input_types=["float"],
                type="float",
                tooltip="CFG / guidance scale",
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
                tooltip="Generated image",
                allowed_modes={ParameterMode.OUTPUT},
            )
        )

    # ------------------------------------------------------------------
    # Validation / life-cycle hooks
    # ------------------------------------------------------------------
    def validate_before_node_run(self) -> list[Exception] | None:
        errors = self._huggingface_repo_parameter.validate_before_node_run()
        return errors or None

    def after_value_set(
        self, parameter: Parameter, value: Any, modified_parameters_set: set[str]
    ) -> None:
        self._seed_parameter.after_value_set(parameter, value, modified_parameters_set)

    def preprocess(self) -> None:
        self._seed_parameter.preprocess()

    # ------------------------------------------------------------------
    # Convenience getters
    # ------------------------------------------------------------------
    def get_repo_revision(self) -> tuple[str, str]:
        return self._huggingface_repo_parameter.get_repo_revision()

    def get_prompt(self) -> str:
        return self._node.get_parameter_value("prompt")

    def get_eta(self) -> float:
        return float(self._node.get_parameter_value("eta"))

    def get_guidance_scale(self) -> float:
        return float(self._node.get_parameter_value("guidance_scale"))

    def get_num_inference_steps(self) -> int:
        return int(self._node.get_parameter_value("num_inference_steps"))

    def get_generator(self):
        return self._seed_parameter.get_generator()

    def get_pipe_kwargs(self) -> dict:
        return {
            "prompt": self.get_prompt(),
            "eta": self.get_eta(),
            "guidance_scale": self.get_guidance_scale(),
            "num_inference_steps": self.get_num_inference_steps(),
            "generator": self.get_generator(),
        }

    # ------------------------------------------------------------------
    # Preview helpers
    # ------------------------------------------------------------------
    def publish_output_image_preview_placeholder(self) -> None:
        # LDM text2img typically generates 256x256 images
        width = 256
        height = 256
        preview_placeholder_image = PIL.Image.new("RGB", (width, height), color="black")
        self._node.publish_update_to_parameter(
            "output_image", pil_to_image_artifact(preview_placeholder_image)
        )

    def publish_output_image(self, output_image_pil: Image) -> None:
        image_artifact = pil_to_image_artifact(output_image_pil)
        self._node.set_parameter_value("output_image", image_artifact)
        self._node.parameter_output_values["output_image"] = image_artifact