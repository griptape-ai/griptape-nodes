import logging
from typing import Any

import PIL.Image
from PIL.Image import Image
from pillow_nodes_library.utils import pil_to_image_artifact  # type: ignore[reportMissingImports]

from diffusers_nodes_library.common.parameters.huggingface_repo_parameter import HuggingFaceRepoParameter
from diffusers_nodes_library.common.parameters.seed_parameter import SeedParameter
from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import BaseNode

logger = logging.getLogger("diffusers_nodes_library")

# ImageNet has 1000 classes (0-999)
MAX_IMAGENET_CLASS_ID = 999


class DitPipelineParameters:
    def __init__(self, node: BaseNode):
        self._node = node
        self._huggingface_repo_parameter = HuggingFaceRepoParameter(
            node,
            repo_ids=[
                "facebook/DiT-XL-2-256",
                "facebook/DiT-XL-2-512",
                "facebook/DiT-L-2-256",
                "facebook/DiT-B-2-256",
            ],
        )
        self._seed_parameter = SeedParameter(node)

    def add_input_parameters(self) -> None:
        self._huggingface_repo_parameter.add_input_parameters()
        self._node.add_parameter(
            Parameter(
                name="class_labels",
                default_value=[207],  # Default to golden retriever ImageNet class
                input_types=["list"],
                type="list",
                tooltip="ImageNet class labels (integers 0-999) for image generation",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="guidance_scale",
                default_value=4.0,
                input_types=["float"],
                type="float",
                tooltip="Guidance scale for classifier-free guidance",
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
                tooltip="The generated image",
                allowed_modes={ParameterMode.OUTPUT},
            )
        )

    def validate_before_node_run(self) -> list[Exception] | None:
        errors = self._huggingface_repo_parameter.validate_before_node_run()

        # Validate class labels
        class_labels = self.get_class_labels()
        for label in class_labels:
            if not isinstance(label, int) or label < 0 or label > MAX_IMAGENET_CLASS_ID:
                if not errors:
                    errors = []
                errors.append(ValueError(f"Class label {label} must be an integer between 0 and 999"))

        return errors or None

    def after_value_set(self, parameter: Parameter, value: Any, modified_parameters_set: set[str]) -> None:
        self._seed_parameter.after_value_set(parameter, value, modified_parameters_set)

    def preprocess(self) -> None:
        self._seed_parameter.preprocess()

    def get_repo_revision(self) -> tuple[str, str]:
        return self._huggingface_repo_parameter.get_repo_revision()

    def publish_output_image_preview_placeholder(self) -> None:
        # DiT models typically generate 256x256 or 512x512 images
        # We'll determine size from the model name
        repo_id, _ = self.get_repo_revision()
        if "512" in repo_id:
            size = 512
        else:
            size = 256

        preview_placeholder_image = PIL.Image.new("RGB", (size, size), color="black")
        self._node.publish_update_to_parameter("output_image", pil_to_image_artifact(preview_placeholder_image))

    def get_class_labels(self) -> list[int]:
        labels = self._node.get_parameter_value("class_labels")
        if isinstance(labels, int):
            return [labels]
        return list(labels)

    def get_guidance_scale(self) -> float:
        return float(self._node.get_parameter_value("guidance_scale"))

    def get_num_inference_steps(self) -> int:
        return int(self._node.get_parameter_value("num_inference_steps"))

    def get_pipe_kwargs(self) -> dict:
        return {
            "class_labels": self.get_class_labels(),
            "guidance_scale": self.get_guidance_scale(),
            "num_inference_steps": self.get_num_inference_steps(),
            "generator": self._seed_parameter.get_generator(),
        }

    def publish_output_image_preview_latents(self, pipe: Any, latents: Any) -> None:
        # Convert latents to image for preview
        try:
            # Use the VAE to decode latents to image
            with pipe.progress_bar():
                image = pipe.vae.decode(latents / pipe.vae.config.scaling_factor, return_dict=False)[0]
            preview_image_pil = pipe.image_processor.postprocess(image, output_type="pil")[0]
            preview_image_artifact = pil_to_image_artifact(preview_image_pil)
            self._node.publish_update_to_parameter("output_image", preview_image_artifact)
        except Exception as e:
            logger.warning("Failed to generate preview image from latents: %s", e)

    def publish_output_image(self, output_image_pil: Image) -> None:
        image_artifact = pil_to_image_artifact(output_image_pil)
        self._node.set_parameter_value("output_image", image_artifact)
        self._node.parameter_output_values["output_image"] = image_artifact
