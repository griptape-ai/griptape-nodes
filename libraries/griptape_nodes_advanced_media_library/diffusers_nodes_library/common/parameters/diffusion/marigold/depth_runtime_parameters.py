from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

import PIL.Image
import torch  # type: ignore[reportMissingImports]
from griptape.artifacts import ImageUrlArtifact
from pillow_nodes_library.utils import (  # type: ignore[reportMissingImports]
    image_artifact_to_pil,
    pil_to_image_artifact,
)
from utils.image_utils import load_image_from_url_artifact

from diffusers_nodes_library.common.parameters.diffusion.runtime_parameters import (
    DiffusionPipelineRuntimeParameters,
)
from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.traits.options import Options

if TYPE_CHECKING:
    from diffusers.pipelines.pipeline_utils import DiffusionPipeline  # type: ignore[reportMissingImports]
    from PIL.Image import Image

    from griptape_nodes.exe_types.node_types import BaseNode

logger = logging.getLogger("diffusers_nodes_library")


class MarigoldDepthPipelineRuntimeParameters(DiffusionPipelineRuntimeParameters):
    def __init__(self, node: BaseNode):
        super().__init__(node)

    def _add_input_parameters(self) -> None:
        self._node.add_parameter(
            Parameter(
                name="image",
                input_types=["ImageArtifact", "ImageUrlArtifact"],
                type="ImageArtifact",
                tooltip="Input image for depth estimation.",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="ensemble_size",
                default_value=1,
                type="int",
                tooltip="Number of ensemble predictions. Higher values improve quality but increase processing time.",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="processing_resolution",
                default_value=768,
                type="int",
                tooltip="Resolution (longest edge) for processing. 0 uses native input resolution.",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="match_input_resolution",
                default_value=True,
                type="bool",
                tooltip="Resize output to match input dimensions.",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="color_map",
                default_value="Spectral",
                type="str",
                traits={Options(choices=["Spectral", "binary", "viridis", "magma", "inferno", "plasma"])},
                tooltip="Color map for depth visualization.",
            )
        )

    def add_input_parameters(self) -> None:
        self._add_input_parameters()
        self._node.add_parameter(
            Parameter(
                name="num_inference_steps",
                default_value=4,
                type="int",
                tooltip="The number of denoising steps.",
            )
        )
        self._seed_parameter.add_input_parameters()

    def add_output_parameters(self) -> None:
        self._node.add_parameter(
            Parameter(
                name="output_image",
                output_type="ImageArtifact",
                tooltip="Colorized depth visualization",
                allowed_modes={ParameterMode.OUTPUT},
            )
        )

    def _remove_input_parameters(self) -> None:
        self._node.remove_parameter_element_by_name("image")
        self._node.remove_parameter_element_by_name("ensemble_size")
        self._node.remove_parameter_element_by_name("processing_resolution")
        self._node.remove_parameter_element_by_name("match_input_resolution")
        self._node.remove_parameter_element_by_name("color_map")

    def remove_input_parameters(self) -> None:
        self._node.remove_parameter_element_by_name("num_inference_steps")
        self._seed_parameter.remove_input_parameters()
        self._remove_input_parameters()

    def after_value_set(self, parameter: Parameter, value: Any) -> None:
        self._seed_parameter.after_value_set(parameter, value)

    def preprocess(self) -> None:
        self._seed_parameter.preprocess()

    def get_image_pil(self) -> Image:
        input_image_artifact = self._node.get_parameter_value("image")
        if input_image_artifact is None:
            msg = f"{self._node.name} requires an input image"
            logger.error(msg)
            raise ValueError(msg)

        if isinstance(input_image_artifact, ImageUrlArtifact):
            input_image_artifact = load_image_from_url_artifact(input_image_artifact)
        input_image_pil = image_artifact_to_pil(input_image_artifact)
        return input_image_pil.convert("RGB")

    def _get_pipe_kwargs(self) -> dict:
        return {}

    def get_pipe_kwargs(self) -> dict:
        return {
            "image": self.get_image_pil(),
            "num_inference_steps": self.get_num_inference_steps(),
            "ensemble_size": self._node.get_parameter_value("ensemble_size"),
            "processing_resolution": self._node.get_parameter_value("processing_resolution"),
            "match_input_resolution": self._node.get_parameter_value("match_input_resolution"),
            "generator": torch.Generator().manual_seed(self._seed_parameter.get_seed()),
            "output_type": "np",
        }

    def publish_output_image_preview_placeholder(self) -> None:
        input_image = self.get_image_pil()
        width, height = input_image.size
        preview_placeholder_image = PIL.Image.new("RGB", (width, height), color="black")
        self._node.publish_update_to_parameter(
            "output_image",
            pil_to_image_artifact(preview_placeholder_image),
        )

    def process_pipeline(self, pipe: DiffusionPipeline) -> None:
        self._node.log_params.append_to_logs("Running Marigold depth estimation...\n")  # type: ignore[reportAttributeAccessIssue]

        # Marigold pipelines don't support callback_on_step_end, so we can't track individual steps
        self._node.progress_bar_component.initialize(1)  # type: ignore[reportAttributeAccessIssue]

        pipe_kwargs = self.get_pipe_kwargs()

        with torch.inference_mode():
            result = pipe(**pipe_kwargs)

        self._node.progress_bar_component.increment()  # type: ignore[reportAttributeAccessIssue]

        depth_prediction = result.prediction

        color_map = self._node.get_parameter_value("color_map")
        vis_images = pipe.image_processor.visualize_depth(depth_prediction, color_map=color_map)

        if vis_images:
            output_image_pil = vis_images[0]
            self.publish_output_image(output_image_pil)

        self._node.log_params.append_to_logs("Done.\n")  # type: ignore[reportAttributeAccessIssue]

    def publish_output_image(self, output_image_pil: Image) -> None:
        image_artifact = pil_to_image_artifact(output_image_pil)
        self._node.publish_update_to_parameter("output_image", image_artifact)
        self._node.set_parameter_value("output_image", image_artifact)
        self._node.parameter_output_values["output_image"] = image_artifact

    def validate_before_node_run(self) -> list[Exception] | None:
        errors = []
        image_artifact = self._node.get_parameter_value("image")
        if image_artifact is None:
            errors.append(ValueError(f"{self._node.name} requires an input image"))

        if errors:
            return errors
        return None
