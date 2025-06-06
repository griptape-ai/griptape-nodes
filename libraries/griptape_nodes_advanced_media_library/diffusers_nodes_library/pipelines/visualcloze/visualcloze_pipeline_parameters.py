import logging
from typing import Any
import uuid

from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

import diffusers  # type: ignore[reportMissingImports]
import PIL.Image
import torch

from pillow_nodes_library.utils import pil_to_image_artifact  # type: ignore[reportMissingImports]

from diffusers_nodes_library.common.parameters.huggingface_repo_parameter import HuggingFaceRepoParameter
from diffusers_nodes_library.common.parameters.seed_parameter import SeedParameter
from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import BaseNode

logger = logging.getLogger("diffusers_nodes_library")


class VisualclozePipelineParameters:
    def __init__(self, node: BaseNode):
        self._node = node
        self._huggingface_repo_parameter = HuggingFaceRepoParameter(
            node,
            repo_ids=[
                "google/if-xl",  # placeholder - actual VisualCloze models would be different
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
                tooltip="Text prompt describing the image to complete",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="image",
                default_value=None,
                input_types=["ImageArtifact"],
                type="ImageArtifact",
                tooltip="Input image with missing parts to fill in",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="mask_image",
                default_value=None,
                input_types=["ImageArtifact"],
                type="ImageArtifact",
                tooltip="Mask indicating areas to fill (white = fill, black = keep)",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="negative_prompt",
                default_value="",
                input_types=["str"],
                type="str",
                tooltip="Optional negative prompt",
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
                default_value=7.5,
                input_types=["float"],
                type="float",
                tooltip="Guidance scale for classifier-free guidance",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="strength",
                default_value=1.0,
                input_types=["float"],
                type="float",
                tooltip="Strength of transformation (0.0 = no change, 1.0 = full transformation)",
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
                tooltip="Generated image with filled regions",
            )
        )

    def after_value_set(self, parameter: Parameter, value: Any, modified_parameters_set: set[str]) -> None:
        self._huggingface_repo_parameter.after_value_set(parameter, value, modified_parameters_set)
        self._seed_parameter.after_value_set(parameter, value, modified_parameters_set)

    def validate_before_node_run(self) -> list[Exception] | None:
        errors = []
        
        repo_errors = self._huggingface_repo_parameter.validate_before_node_run()
        if repo_errors:
            errors.extend(repo_errors)
            
        seed_errors = self._seed_parameter.validate_before_node_run()
        if seed_errors:
            errors.extend(seed_errors)
            
        prompt = self._node.get_parameter_value("prompt")
        image = self._node.get_parameter_value("image")
        
        if not prompt:
            errors.append(ValueError("Prompt is required"))
        if not image:
            errors.append(ValueError("Input image is required"))
            
        return errors if errors else None

    def preprocess(self) -> None:
        self._huggingface_repo_parameter.preprocess()
        self._seed_parameter.preprocess()

    def get_repo_revision(self) -> tuple[str, str]:
        return self._huggingface_repo_parameter.get_repo_revision()

    def get_num_inference_steps(self) -> int:
        return self._node.get_parameter_value("num_inference_steps")

    def get_pipe_kwargs(self) -> dict[str, Any]:
        kwargs = {
            "prompt": self._node.get_parameter_value("prompt"),
            "image": self._node.get_parameter_value("image").value,
            "num_inference_steps": self._node.get_parameter_value("num_inference_steps"),
            "guidance_scale": self._node.get_parameter_value("guidance_scale"),
            "strength": self._node.get_parameter_value("strength"),
            "generator": self._seed_parameter.get_generator(),
        }
        
        # Add negative prompt if provided
        negative_prompt = self._node.get_parameter_value("negative_prompt")
        if negative_prompt:
            kwargs["negative_prompt"] = negative_prompt
            
        # Add mask image if provided
        mask_image = self._node.get_parameter_value("mask_image")
        if mask_image:
            kwargs["mask_image"] = mask_image.value
            
        return kwargs

    def publish_output_image_preview_placeholder(self) -> None:
        """Publish a placeholder image for preview during processing."""
        # Create a placeholder image
        placeholder_image = PIL.Image.new("RGB", (512, 512), color=(128, 128, 128))
        image_artifact = pil_to_image_artifact(placeholder_image)
        image_artifact.name = f"visualcloze_preview_{uuid.uuid4().hex[:8]}.png"
        self._node.set_parameter_value("image", image_artifact)

    def publish_output_image_preview_latents(self, pipe: diffusers.VisualClozePipeline, latents: torch.Tensor) -> None:
        """Publish intermediate latents as preview image."""
        try:
            with torch.no_grad():
                if hasattr(pipe, 'vae') and pipe.vae is not None:
                    # Decode latents to image
                    latents = latents / pipe.vae.config.scaling_factor
                    image = pipe.vae.decode(latents, return_dict=False)[0]
                    image = (image / 2 + 0.5).clamp(0, 1)
                    image = image.cpu().permute(0, 2, 3, 1).float().numpy()
                    image = (image * 255).round().astype("uint8")
                    preview_image = PIL.Image.fromarray(image[0])
                    image_artifact = pil_to_image_artifact(preview_image)
                    image_artifact.name = f"visualcloze_preview_{uuid.uuid4().hex[:8]}.png"
                    self._node.set_parameter_value("image", image_artifact)
        except Exception as e:
            logger.warning(f"Failed to generate preview from latents: {e}")

    def publish_output_image(self, image: PIL.Image.Image) -> None:
        """Publish the final generated image."""
        image_artifact = pil_to_image_artifact(image)
        image_artifact.name = f"visualcloze_{uuid.uuid4().hex[:8]}.png"
        self._node.set_parameter_value("image", image_artifact)