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


class MarigoldPipelineParameters:
    def __init__(self, node: BaseNode):
        self._node = node
        self._huggingface_repo_parameter = HuggingFaceRepoParameter(
            node,
            repo_ids=[
                "prs-eth/marigold-depth-lcm-v1-0",
                "prs-eth/marigold-depth-v1-0",
            ],
        )
        self._seed_parameter = SeedParameter(node)

    def add_input_parameters(self) -> None:
        self._huggingface_repo_parameter.add_input_parameters()
        self._node.add_parameter(
            Parameter(
                name="input_image",
                input_types=["image"],
                type="image",
                allowed_modes=set(),
                tooltip="Input image for depth estimation.",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="num_inference_steps",
                input_types=["int"],
                type="int",
                allowed_modes=set(),
                tooltip="Number of denoising steps.",
                default_value=10,
                minimum=1,
                maximum=100,
            )
        )
        self._node.add_parameter(
            Parameter(
                name="ensemble_size",
                input_types=["int"],
                type="int",
                allowed_modes=set(),
                tooltip="Number of predictions to make for ensemble.",
                default_value=1,
                minimum=1,
                maximum=10,
            )
        )
        self._node.add_parameter(
            Parameter(
                name="processing_resolution",
                input_types=["int"],
                type="int",
                allowed_modes=set(),
                tooltip="Processing resolution (will be resized if different from input).",
                default_value=768,
                minimum=256,
                maximum=1024,
                step=64,
            )
        )
        self._seed_parameter.add_input_parameters()

    def add_output_parameters(self) -> None:
        self._node.add_parameter(
            Parameter(
                name="output_depth_image",
                input_types=[],
                type="image",
                allowed_modes={ParameterMode.OUTPUT},
                tooltip="Generated depth map",
            )
        )

    def after_value_set(self, parameter: Parameter, value: Any, modified_parameters_set: set[str]) -> None:
        self._huggingface_repo_parameter.after_value_set(parameter, value, modified_parameters_set)

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

    def preprocess(self) -> None:
        self._seed_parameter.preprocess()

    def get_repo_revision(self) -> tuple[str, str]:
        return self._huggingface_repo_parameter.get_repo_revision()

    def get_num_inference_steps(self) -> int:
        return self._node.get_parameter_value("num_inference_steps")

    def get_pipe_kwargs(self) -> dict[str, Any]:
        from pillow_nodes_library.utils import image_artifact_to_pil  # type: ignore[reportMissingImports]
        
        input_image_artifact = self._node.get_parameter_value("input_image")
        input_image_pil = image_artifact_to_pil(input_image_artifact)
        
        pipe_kwargs = {
            "image": input_image_pil,
            "num_inference_steps": self._node.get_parameter_value("num_inference_steps"),
            "ensemble_size": self._node.get_parameter_value("ensemble_size"),
            "processing_resolution": self._node.get_parameter_value("processing_resolution"),
            "generator": self._seed_parameter.get_generator(),
        }
            
        return pipe_kwargs

    def publish_output_depth_image_preview_placeholder(self) -> None:
        # Create a placeholder depth image (gray)
        placeholder_image = PIL.Image.new("RGB", (512, 512), color="gray")
        self._node.set_parameter_value("output_depth_image", pil_to_image_artifact(placeholder_image))

    def publish_output_depth_image(self, image: Image) -> None:
        self._node.set_parameter_value("output_depth_image", pil_to_image_artifact(image))