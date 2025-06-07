import logging
from typing import Any

import PIL.Image
from PIL.Image import Image
from pillow_nodes_library.utils import pil_to_image_artifact  # type: ignore[reportMissingImports]

from diffusers_nodes_library.common.parameters.huggingface_repo_parameter import (
    HuggingFaceRepoParameter,  # type: ignore[reportMissingImports]
)
from diffusers_nodes_library.common.parameters.seed_parameter import SeedParameter  # type: ignore[reportMissingImports]
from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import BaseNode

logger = logging.getLogger("diffusers_nodes_library")


class DdimPipelineParameters:
    def __init__(self, node: BaseNode):
        self._node = node
        self._huggingface_repo_parameter = HuggingFaceRepoParameter(
            node,
            repo_ids=[
                "google/ddpm-celebahq-256",
                "google/ddpm-cifar10-32",
            ],
        )
        self._seed_parameter = SeedParameter(node)

    def add_input_parameters(self) -> None:
        self._huggingface_repo_parameter.add_input_parameters()
        self._node.add_parameter(
            Parameter(
                name="num_inference_steps",
                default_value=50,
                input_types=["int"],
                type="int",
                tooltip="Number of denoising steps for generation",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="eta",
                default_value=0.0,
                input_types=["float"],
                type="float",
                tooltip="Corresponds to parameter eta (η) in the DDIM paper",
            )
        )
        self._seed_parameter.add_input_parameters()

    def add_output_parameters(self) -> None:
        self._node.add_parameter(
            Parameter(
                name="output_image",
                output_type="Image",
                tooltip="The generated image",
                allowed_modes={ParameterMode.OUTPUT},
            )
        )

    def validate_before_node_run(self) -> list[Exception] | None:
        errors = self._huggingface_repo_parameter.validate_before_node_run()
        return errors or None

    def after_value_set(self, parameter: Parameter, value: Any, modified_parameters_set: set[str]) -> None:
        self._seed_parameter.after_value_set(parameter, value, modified_parameters_set)

    def preprocess(self) -> None:
        self._seed_parameter.preprocess()

    def get_repo_revision(self) -> tuple[str, str]:
        return self._huggingface_repo_parameter.get_repo_revision()

    def get_num_inference_steps(self) -> int:
        return int(self._node.get_parameter_value("num_inference_steps"))

    def get_eta(self) -> float:
        return float(self._node.get_parameter_value("eta"))

    def get_pipe_kwargs(self) -> dict:
        kwargs = {
            "num_inference_steps": self.get_num_inference_steps(),
            "eta": self.get_eta(),
            "generator": self._seed_parameter.get_generator(),
        }
        return kwargs

    def publish_output_image_preview_placeholder(self) -> None:
        placeholder_image = PIL.Image.new("RGB", (256, 256), (128, 128, 128))
        image_artifact = pil_to_image_artifact(placeholder_image)
        self._node.publish_update_to_parameter("output_image", image_artifact)

    def publish_output_image_preview_latents(self, pipe: Any, latents: Any) -> None:
        try:
            with pipe.vae.to(latents.device, dtype=latents.dtype):
                preview_image = pipe.vae.decode(latents / pipe.vae.config.scaling_factor, return_dict=False)[0]
                preview_image = pipe.image_processor.postprocess(preview_image, output_type="pil")[0]
                image_artifact = pil_to_image_artifact(preview_image)
                self._node.publish_update_to_parameter("output_image", image_artifact)
        except Exception as e:
            logger.warning("Failed to generate preview image: %s", e)

    def publish_output_image(self, image: Image) -> None:
        image_artifact = pil_to_image_artifact(image)
        self._node.parameter_output_values["output_image"] = image_artifact
