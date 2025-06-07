import logging
import uuid
from typing import Any

import diffusers  # type: ignore[reportMissingImports]
import PIL.Image
import torch  # type: ignore[reportMissingImports]
from pillow_nodes_library.utils import pil_to_image_artifact  # type: ignore[reportMissingImports]

from diffusers_nodes_library.common.parameters.huggingface_repo_parameter import HuggingFaceRepoParameter
from diffusers_nodes_library.common.parameters.seed_parameter import SeedParameter
from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import BaseNode

logger = logging.getLogger("diffusers_nodes_library")


class UnidiffuserPipelineParameters:
    def __init__(self, node: BaseNode):
        self._node = node
        self._huggingface_repo_parameter = HuggingFaceRepoParameter(
            node,
            repo_ids=[
                "thu-ml/unidiffuser-v1",
            ],
        )
        self._seed_parameter = SeedParameter(node)

    def add_input_parameters(self) -> None:
        self._huggingface_repo_parameter.add_input_parameters()
        self._node.add_parameter(
            Parameter(
                name="mode",
                default_value="img",
                input_types=["str"],
                type="str",
                tooltip="Generation mode: 'img' (text-to-image), 'text' (image-to-text), 'joint' (joint generation)",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="prompt",
                default_value="",
                input_types=["str"],
                type="str",
                tooltip="Text prompt (for img and joint modes)",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="image",
                default_value=None,
                input_types=["ImageArtifact", "ImageUrlArtifact"],
                type="ImageArtifact",
                tooltip="Input image (for text and joint modes)",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="num_inference_steps",
                default_value=20,
                input_types=["int"],
                type="int",
                tooltip="Number of denoising steps",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="guidance_scale",
                default_value=8.0,
                input_types=["float"],
                type="float",
                tooltip="Guidance scale for classifier-free guidance",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="height",
                default_value=512,
                input_types=["int"],
                type="int",
                tooltip="Height of generated image",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="width",
                default_value=512,
                input_types=["int"],
                type="int",
                tooltip="Width of generated image",
            )
        )
        self._seed_parameter.add_input_parameters()

    def add_output_parameters(self) -> None:
        self._node.add_parameter(
            Parameter(
                name="image",
                input_types=[],
                type="ImageArtifact",
                allowed_modes={ParameterMode.OUTPUT},
                tooltip="Generated or processed image",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="text",
                input_types=[],
                type="str",
                allowed_modes={ParameterMode.OUTPUT},
                tooltip="Generated text description",
            )
        )

    def after_value_set(self, parameter: Parameter, value: Any, modified_parameters_set: set[str]) -> None:
        self._seed_parameter.after_value_set(parameter, value, modified_parameters_set)

    def validate_before_node_run(self) -> list[Exception] | None:
        errors = []

        repo_errors = self._huggingface_repo_parameter.validate_before_node_run()
        if repo_errors:
            errors.extend(repo_errors)

        mode = self._node.get_parameter_value("mode")
        prompt = self._node.get_parameter_value("prompt")
        image = self._node.get_parameter_value("image")

        if mode == "img" and not prompt:
            errors.append(ValueError("Prompt is required for img mode"))
        elif mode == "text" and not image:
            errors.append(ValueError("Image is required for text mode"))
        elif mode == "joint" and not (prompt or image):
            errors.append(ValueError("Either prompt or image (or both) is required for joint mode"))

        return errors if errors else None

    def preprocess(self) -> None:
        self._seed_parameter.preprocess()

    def get_repo_revision(self) -> tuple[str, str]:
        return self._huggingface_repo_parameter.get_repo_revision()

    def get_num_inference_steps(self) -> int:
        return self._node.get_parameter_value("num_inference_steps")

    def get_pipe_kwargs(self) -> dict[str, Any]:
        mode = self._node.get_parameter_value("mode")
        kwargs = {
            "mode": mode,
            "num_inference_steps": self._node.get_parameter_value("num_inference_steps"),
            "guidance_scale": self._node.get_parameter_value("guidance_scale"),
            "height": self._node.get_parameter_value("height"),
            "width": self._node.get_parameter_value("width"),
            "generator": self._seed_parameter.get_generator(),
        }

        # Add prompt if available and needed
        prompt = self._node.get_parameter_value("prompt")
        if prompt and mode in ["img", "joint"]:
            kwargs["prompt"] = prompt

        # Add image if available and needed
        image = self._node.get_parameter_value("image")
        if image and mode in ["text", "joint"]:
            kwargs["image"] = image.value

        return kwargs

    def publish_output_image_preview_placeholder(self) -> None:
        """Publish a placeholder image for preview during processing."""
        # Create a placeholder image
        placeholder_image = PIL.Image.new("RGB", (512, 512), color=(128, 128, 128))
        image_artifact = pil_to_image_artifact(placeholder_image)
        image_artifact.name = f"unidiffuser_preview_{uuid.uuid4().hex[:8]}.png"
        self._node.set_parameter_value("image", image_artifact)

    def publish_output_image_preview_latents(self, pipe: diffusers.UniDiffuserPipeline, latents: torch.Tensor) -> None:
        """Publish intermediate latents as preview image."""
        try:
            with torch.no_grad():
                if hasattr(pipe, "vae") and pipe.vae is not None:
                    # Decode latents to image
                    latents = latents / pipe.vae.config.scaling_factor
                    image = pipe.vae.decode(latents, return_dict=False)[0]
                    image = (image / 2 + 0.5).clamp(0, 1)
                    image = image.cpu().permute(0, 2, 3, 1).float().numpy()
                    image = (image * 255).round().astype("uint8")
                    preview_image = PIL.Image.fromarray(image[0])
                    image_artifact = pil_to_image_artifact(preview_image)
                    image_artifact.name = f"unidiffuser_preview_{uuid.uuid4().hex[:8]}.png"
                    self._node.set_parameter_value("image", image_artifact)
        except Exception as e:
            logger.warning("Failed to generate preview from latents: %s", e)

    def publish_output_image(self, image: PIL.Image.Image) -> None:
        """Publish the final generated image."""
        image_artifact = pil_to_image_artifact(image)
        image_artifact.name = f"unidiffuser_{uuid.uuid4().hex[:8]}.png"
        self._node.set_parameter_value("image", image_artifact)

    def publish_output_text(self, text: str) -> None:
        """Publish the generated text."""
        self._node.set_parameter_value("text", text)
