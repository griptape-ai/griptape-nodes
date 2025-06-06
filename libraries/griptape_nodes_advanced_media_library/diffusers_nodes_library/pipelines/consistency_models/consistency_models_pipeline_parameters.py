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


class ConsistencyModelsPipelineParameters:
    def __init__(self, node: BaseNode):
        self._node = node
        self._huggingface_repo_parameter = HuggingFaceRepoParameter(
            node,
            repo_ids=[
                "openai/diffusers-cd_bedroom256_lpips",
                "openai/diffusers-cd_imagenet64_l2",
            ],
        )
        self._seed_parameter = SeedParameter(node)

    def add_input_parameters(self) -> None:
        self._huggingface_repo_parameter.add_input_parameters()
        self._node.add_parameter(
            Parameter(
                name="batch_size",
                input_types=["int"],
                type="int",
                allowed_modes={ParameterMode.MANUAL},
                tooltip="Number of images to generate in a batch",
                default_value=1,
            )
        )
        self._node.add_parameter(
            Parameter(
                name="class_labels",
                input_types=["int"],
                type="int",
                allowed_modes={ParameterMode.MANUAL},
                tooltip="Class labels for conditional generation (optional, set to -1 for unconditional)",
                default_value=-1,
            )
        )
        self._node.add_parameter(
            Parameter(
                name="num_inference_steps",
                input_types=["int"],
                type="int",
                allowed_modes={ParameterMode.MANUAL},
                tooltip="Number of denoising steps (1 for one-step generation)",
                default_value=1,
            )
        )
        self._node.add_parameter(
            Parameter(
                name="timesteps",
                input_types=["str"],
                type="str",
                allowed_modes={ParameterMode.MANUAL},
                tooltip="Custom timesteps (comma-separated, e.g., '22.0,0.0' for multi-step)",
                default_value="",
            )
        )
        self._seed_parameter.add_input_parameters()

    def add_output_parameters(self) -> None:
        self._node.add_parameter(
            Parameter(
                name="image",
                input_types=[],
                type="griptape_nodes_library.exe_types.core_types.ImageArtifact",
                allowed_modes=set(),
                tooltip="Generated image",
            )
        )

    def get_repo_revision(self) -> tuple[str, str]:
        return self._huggingface_repo_parameter.get_repo_revision()

    def get_num_inference_steps(self) -> int:
        return self._node.get_input_parameter_value("num_inference_steps")

    def get_pipe_kwargs(self) -> dict[str, Any]:
        kwargs = {
            "batch_size": self._node.get_input_parameter_value("batch_size"),
            "num_inference_steps": self._node.get_input_parameter_value("num_inference_steps"),
            "generator": self._seed_parameter.get_generator(),
        }
        
        # Add class labels if specified (not -1)
        class_labels = self._node.get_input_parameter_value("class_labels")
        if class_labels != -1:
            kwargs["class_labels"] = [class_labels] * kwargs["batch_size"]
        
        # Add custom timesteps if specified
        timesteps_str = self._node.get_input_parameter_value("timesteps").strip()
        if timesteps_str:
            try:
                timesteps = [float(t.strip()) for t in timesteps_str.split(",")]
                kwargs["timesteps"] = timesteps
            except ValueError:
                logger.warning(f"Invalid timesteps format: {timesteps_str}, ignoring")
        
        return kwargs

    def publish_output_image_preview_placeholder(self) -> None:
        placeholder = PIL.Image.new("RGB", (256, 256), (128, 128, 128))
        self._node.set_output_parameter_value("image", pil_to_image_artifact(placeholder))

    def publish_output_image_preview_latents(self, pipe: diffusers.ConsistencyModelPipeline, latents: Any) -> None:
        try:
            # For consistency models, we may not have a VAE decode step like other models
            # This is a simplified preview generation
            logger.debug("Generating preview for consistency model")
        except Exception as e:
            logger.warning(f"Failed to generate preview: {e}")

    def publish_output_image(self, image: Image) -> None:
        self._node.set_output_parameter_value("image", pil_to_image_artifact(image))

    def validate_before_node_run(self) -> list[Exception]:
        errors = []
        
        batch_size = self._node.get_input_parameter_value("batch_size")
        if batch_size < 1:
            errors.append(ValueError("Batch size must be at least 1"))
        if batch_size > 16:
            errors.append(ValueError("Batch size should not exceed 16 for memory reasons"))
        
        num_inference_steps = self._node.get_input_parameter_value("num_inference_steps")
        if num_inference_steps < 1:
            errors.append(ValueError("Number of inference steps must be at least 1"))
            
        return errors

    def preprocess(self) -> None:
        pass

    def after_value_set(self, parameter: Parameter, value: Any, modified_parameters_set: set[str]) -> None:
        pass