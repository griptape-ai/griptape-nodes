import logging
from typing import Any

import PIL.Image
from griptape.artifacts import ImageUrlArtifact
from griptape.loaders import ImageLoader
from PIL.Image import Image
from pillow_nodes_library.utils import (  # type: ignore[reportMissingImports]
    image_artifact_to_pil,
    pil_to_image_artifact,
)

from diffusers_nodes_library.common.parameters.huggingface_repo_parameter import (
    HuggingFaceRepoParameter,  # type: ignore[reportMissingImports]
)
from diffusers_nodes_library.common.parameters.seed_parameter import SeedParameter  # type: ignore[reportMissingImports]
from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import BaseNode

logger = logging.getLogger("diffusers_nodes_library")


class BlipDiffusionPipelineParameters:
    def __init__(self, node: BaseNode):
        self._node = node
        self._huggingface_repo_parameter = HuggingFaceRepoParameter(
            node,
            repo_ids=[
                "Salesforce/blipdiffusion",
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
                name="reference_image",
                input_types=["ImageArtifact", "ImageUrlArtifact"],
                type="ImageArtifact",
                tooltip="Reference image for subject-driven generation",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="source_subject_category",
                default_value="",
                input_types=["str"],
                type="str",
                tooltip="Category of the source subject (e.g., 'dog', 'cat', 'person')",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="target_subject_category",
                default_value="",
                input_types=["str"],
                type="str",
                tooltip="Category of the target subject (e.g., 'dog', 'cat', 'person')",
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
                name="guidance_scale",
                default_value=7.5,
                input_types=["float"],
                type="float",
                tooltip="Higher values follow the text prompt more closely",
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

    def get_prompt(self) -> str:
        return self._node.get_parameter_value("prompt")

    def get_reference_image(self) -> Image:
        reference_image_artifact = self._node.get_parameter_value("reference_image")
        if isinstance(reference_image_artifact, ImageUrlArtifact):
            reference_image_artifact = ImageLoader().load(reference_image_artifact.value)
        return image_artifact_to_pil(reference_image_artifact)

    def get_source_subject_category(self) -> str:
        return self._node.get_parameter_value("source_subject_category")

    def get_target_subject_category(self) -> str:
        return self._node.get_parameter_value("target_subject_category")

    def get_height(self) -> int:
        return int(self._node.get_parameter_value("height"))

    def get_width(self) -> int:
        return int(self._node.get_parameter_value("width"))

    def get_num_inference_steps(self) -> int:
        return int(self._node.get_parameter_value("num_inference_steps"))

    def get_guidance_scale(self) -> float:
        return float(self._node.get_parameter_value("guidance_scale"))

    def get_pipe_kwargs(self) -> dict:
        kwargs = {
            "prompt": self.get_prompt(),
            "reference_image": self.get_reference_image(),
            "source_subject_category": self.get_source_subject_category(),
            "target_subject_category": self.get_target_subject_category(),
            "height": self.get_height(),
            "width": self.get_width(),
            "num_inference_steps": self.get_num_inference_steps(),
            "guidance_scale": self.get_guidance_scale(),
            "generator": self._seed_parameter.get_generator(),
        }
        return kwargs

    def publish_output_image_preview_placeholder(self) -> None:
        width = self.get_width()
        height = self.get_height()
        preview_placeholder_image = PIL.Image.new("RGB", (width, height), color="black")
        self._node.publish_update_to_parameter("output_image", pil_to_image_artifact(preview_placeholder_image))

    def publish_output_image(self, image: Image) -> None:
        image_artifact = pil_to_image_artifact(image)
        self._node.parameter_output_values["output_image"] = image_artifact
