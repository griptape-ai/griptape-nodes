import logging
from typing import Any

import diffusers  # type: ignore[reportMissingImports]
import numpy as np
import PIL.Image
import torch  # type: ignore[reportMissingImports]
from diffusers.pipelines.pipeline_utils import DiffusionPipeline  # type: ignore[reportMissingImports]
from griptape.artifacts import ImageUrlArtifact
from PIL.Image import Image
from pillow_nodes_library.utils import image_artifact_to_pil, pil_to_image_artifact  # type: ignore[reportMissingImports]
from utils.image_utils import load_image_from_url_artifact

from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import BaseNode
from griptape_nodes.exe_types.param_components.seed_parameter import SeedParameter
from griptape_nodes.traits.options import Options

logger = logging.getLogger("diffusers_nodes_library")


class MarigoldDepthPipelineRuntimeParameters:
    def __init__(self, node: BaseNode):
        self._node = node
        self._seed_parameter = SeedParameter(node)

    def add_input_parameters(self) -> None:
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
                name="num_inference_steps",
                type="int",
                tooltip="Number of denoising steps. Leave empty to use model default (typically 1-4 steps).",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="ensemble_size",
                default_value=1,
                type="int",
                tooltip="Number of ensemble predictions. Higher values improve quality but increase processing time.",
                ui_options={"slider": {"min_val": 1, "max_val": 10}},
            )
        )
        self._node.add_parameter(
            Parameter(
                name="processing_resolution",
                type="int",
                tooltip="Resolution for processing. Leave empty for model default. Set to 0 for native resolution.",
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

    def remove_input_parameters(self) -> None:
        self._node.remove_parameter_element_by_name("image")
        self._node.remove_parameter_element_by_name("num_inference_steps")
        self._node.remove_parameter_element_by_name("ensemble_size")
        self._node.remove_parameter_element_by_name("processing_resolution")
        self._node.remove_parameter_element_by_name("match_input_resolution")
        self._node.remove_parameter_element_by_name("color_map")
        self._seed_parameter.remove_input_parameters()

    def remove_output_parameters(self) -> None:
        self._node.remove_parameter_element_by_name("output_image")

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

    def get_pipe_kwargs(self) -> dict:
        kwargs: dict[str, Any] = {
            "image": self.get_image_pil(),
            "ensemble_size": self._node.get_parameter_value("ensemble_size"),
            "match_input_resolution": self._node.get_parameter_value("match_input_resolution"),
            "generator": torch.Generator().manual_seed(self._seed_parameter.get_seed()),
            "output_type": "np",
        }

        num_inference_steps = self._node.get_parameter_value("num_inference_steps")
        if num_inference_steps is not None and num_inference_steps > 0:
            kwargs["num_inference_steps"] = num_inference_steps

        processing_resolution = self._node.get_parameter_value("processing_resolution")
        if processing_resolution is not None:
            kwargs["processing_resolution"] = processing_resolution

        return kwargs

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

        num_inference_steps = self._node.get_parameter_value("num_inference_steps")
        if num_inference_steps is None or num_inference_steps <= 0:
            num_inference_steps = getattr(pipe, "default_denoising_steps", 4)

        ensemble_size = self._node.get_parameter_value("ensemble_size")
        total_steps = num_inference_steps * ensemble_size
        self._node.progress_bar_component.initialize(total_steps)  # type: ignore[reportAttributeAccessIssue]

        step_count = 0

        def callback_on_step_end(
            _pipe: DiffusionPipeline,
            _i: int,
            _t: int,
            callback_kwargs: dict,
        ) -> dict:
            nonlocal step_count
            if self._node.is_cancellation_requested:
                _pipe._interrupt = True
                self._node.log_params.append_to_logs("Cancellation requested, stopping...\n")  # type: ignore[reportAttributeAccessIssue]
                return callback_kwargs

            step_count += 1
            self._node.progress_bar_component.increment()  # type: ignore[reportAttributeAccessIssue]
            self._node.log_params.append_to_logs(f"Step {step_count} of {total_steps}\n")  # type: ignore[reportAttributeAccessIssue]
            return {}

        pipe_kwargs = self.get_pipe_kwargs()
        pipe_kwargs["callback_on_step_end"] = callback_on_step_end

        with torch.inference_mode():
            result = pipe(**pipe_kwargs)

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
