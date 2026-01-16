from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import torch  # type: ignore[reportMissingImports]
from diffusers.pipelines.pipeline_utils import DiffusionPipeline  # type: ignore[reportMissingImports]

if TYPE_CHECKING:
    from PIL import Image

    from griptape_nodes.exe_types.node_types import BaseNode

from griptape.artifacts import ImageUrlArtifact
from pillow_nodes_library.utils import image_artifact_to_pil  # type: ignore[reportMissingImports]
from utils.image_utils import load_image_from_url_artifact

from diffusers_nodes_library.common.parameters.diffusion.runtime_parameters import (
    DiffusionPipelineRuntimeParameters,
)
from griptape_nodes.exe_types.core_types import Parameter

logger = logging.getLogger("diffusers_nodes_library")


class GlmImagePipelineRuntimeParameters(DiffusionPipelineRuntimeParameters):
    def __init__(self, node: BaseNode):
        super().__init__(node)

    def _add_input_parameters(self) -> None:
        self._node.add_parameter(
            Parameter(
                name="prompt",
                default_value="",
                type="str",
                tooltip="The prompt or prompts to guide the image generation.",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="image",
                input_types=["ImageArtifact", "ImageUrlArtifact"],
                type="ImageArtifact",
                tooltip="Optional condition image for image-to-image generation.",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="guidance_scale",
                default_value=1.5,
                type="float",
                tooltip="Guidance scale for classifier-free guidance.",
            )
        )

    def _remove_input_parameters(self) -> None:
        self._node.remove_parameter_element_by_name("prompt")
        self._node.remove_parameter_element_by_name("image")
        self._node.remove_parameter_element_by_name("guidance_scale")

    def _get_image_pil(self) -> Image.Image | None:
        input_image_artifact = self._node.get_parameter_value("image")
        if input_image_artifact is None:
            return None

        if isinstance(input_image_artifact, ImageUrlArtifact):
            input_image_artifact = load_image_from_url_artifact(input_image_artifact)
        input_image_pil = image_artifact_to_pil(input_image_artifact)
        return input_image_pil.convert("RGB")

    def _get_pipe_kwargs(self) -> dict:
        kwargs = {
            "prompt": self._node.get_parameter_value("prompt"),
            "guidance_scale": self._node.get_parameter_value("guidance_scale"),
        }

        image_pil = self._get_image_pil()
        if image_pil is not None:
            kwargs["image"] = [image_pil]

        return kwargs

    def process_pipeline(self, pipe: DiffusionPipeline) -> None:
        """Process the GLM-Image pipeline.

        GLM-Image pipeline doesn't support callback_on_step_end, so we override
        to run without step callbacks.
        """
        self._node.log_params.append_to_logs("Running GLM-Image generation...\n")  # type: ignore[reportAttributeAccessIssue]

        # GLM-Image doesn't support callback_on_step_end, so we can't track individual steps
        self._node.progress_bar_component.initialize(1)  # type: ignore[reportAttributeAccessIssue]

        with torch.inference_mode():
            output = pipe(
                **self.get_pipe_kwargs(),
                output_type="pil",
            )

        self._node.progress_bar_component.increment()  # type: ignore[reportAttributeAccessIssue]

        output_image_pil = output.images[0]
        self.publish_output_image(output_image_pil)

        self._node.log_params.append_to_logs("Done.\n")  # type: ignore[reportAttributeAccessIssue]
