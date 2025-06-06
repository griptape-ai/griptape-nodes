import functools
from typing import Any

import torch  # type: ignore[reportMissingImports]

from diffusers_nodes_library.common.parameters.huggingface_model_parameter import HuggingfaceModelParameter  # type: ignore[reportMissingImports]
from diffusers_nodes_library.common.parameters.seed_parameter import SeedParameter  # type: ignore[reportMissingImports]
from griptape_nodes.exe_types.core_types import Parameter
from griptape_nodes.exe_types.node_types import ControlNode


class DitPipelineParameters:
    def __init__(self, node: ControlNode):
        self.node = node

    def add_input_parameters(self) -> None:
        HuggingfaceModelParameter(self.node).add_input_parameters()
        SeedParameter(self.node).add_input_parameters()

        self.node.add_input_parameter("class_labels", default_value=None)
        self.node.add_input_parameter("num_inference_steps", default_value=20)
        self.node.add_input_parameter("guidance_scale", default_value=4.0)

    def add_output_parameters(self) -> None:
        self.node.add_output_parameter("output_image")

    def after_value_set(self, parameter: Parameter, value: Any, modified_parameters_set: set[str]) -> None:
        pass

    def validate_before_node_run(self) -> list[Exception]:
        errors = []
        return errors

    def preprocess(self) -> None:
        pass

    def get_repo_revision(self) -> tuple[str, str]:
        return HuggingfaceModelParameter(self.node).get_repo_revision()

    def get_num_inference_steps(self) -> int:
        return self.node.get_input_parameter_value("num_inference_steps")

    def get_pipe_kwargs(self) -> dict[str, Any]:
        kwargs = {
            "num_inference_steps": self.get_num_inference_steps(),
            "guidance_scale": self.node.get_input_parameter_value("guidance_scale"),
            "generator": SeedParameter(self.node).get_generator(),
        }

        class_labels = self.node.get_input_parameter_value("class_labels")
        if class_labels is not None:
            kwargs["class_labels"] = class_labels

        return kwargs

    def publish_output_image_preview_placeholder(self) -> None:
        self.node.set_output_parameter_value("output_image", "Generating image with DiT...")

    def publish_output_image_preview_latents(self, pipe, latents: torch.Tensor) -> None:
        # Convert latents to preview image if possible
        try:
            if hasattr(pipe, 'vae') and pipe.vae is not None:
                with torch.no_grad():
                    images = pipe.vae.decode(latents / pipe.vae.config.scaling_factor, return_dict=False)[0]
                    images = (images / 2 + 0.5).clamp(0, 1)
                    images = images.cpu().permute(0, 2, 3, 1).float().numpy()
                    if images.shape[0] > 0:
                        from diffusers.utils import numpy_to_pil
                        preview_image = numpy_to_pil(images)[0]
                        self.node.set_output_parameter_value("output_image", preview_image)
        except Exception:
            pass

    def publish_output_image(self, image) -> None:
        self.node.set_output_parameter_value("output_image", image)